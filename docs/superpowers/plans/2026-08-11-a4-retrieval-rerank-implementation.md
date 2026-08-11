# A4 Retrieval and Rerank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, testable A4 clinical-evidence retrieval core with hybrid recall, RRF fusion, explainable reranking, MMR selection, logs, and evaluation.

**Architecture:** The package accepts normalized evidence chunks and query metadata, retrieves with a dependency-free BM25 index and an injectable vector-search adapter, fuses results through RRF, then selects diverse evidence using normalized feature scores and MMR. It returns immutable run records rather than producing medical answers.

**Tech Stack:** Python 3.13, standard library, pytest, JSON/JSONL, dataclasses.

---

## File Structure

- Create: `pyproject.toml` — package and pytest configuration.
- Create: `retrieval/models.py` — dataclasses and result/status contracts.
- Create: `retrieval/config.py` — validated immutable retrieval configuration.
- Create: `retrieval/bm25.py` — tokenization and BM25 lexical retrieval.
- Create: `retrieval/vector.py` — injectable vector-search adapter and cosine implementation.
- Create: `retrieval/fusion.py` — deterministic RRF merge.
- Create: `retrieval/rerank.py` — feature scoring and MMR selection.
- Create: `retrieval/service.py` — end-to-end orchestration, warnings, and timing.
- Create: `retrieval/evaluation.py` — retrieval ranking metrics.
- Create: `retrieval/__init__.py` — public API exports.
- Create: `tests/conftest.py` — shared evidence fixtures.
- Create: `tests/test_models.py`, `tests/test_bm25.py`, `tests/test_fusion.py`, `tests/test_rerank.py`, `tests/test_service.py`, `tests/test_evaluation.py` — behavioral tests.
- Create: `README.md` — local install and sample query instructions.

### Task 1: Project contracts and configuration

**Files:**
- Create: `pyproject.toml`
- Create: `retrieval/__init__.py`
- Create: `retrieval/models.py`
- Create: `retrieval/config.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing contract tests**

```python
def test_chunk_requires_stable_id_and_non_empty_text():
    with pytest.raises(ValueError, match="stable_id"):
        EvidenceChunk(chunk_id="c1", evidence_id="e1", stable_id="", text="text")

def test_config_rejects_weights_that_do_not_sum_to_one():
    with pytest.raises(ValueError, match="sum"):
        RetrievalConfig(weights=FeatureWeights(semantic=0.5, lexical=0.5))
```

- [ ] **Step 2: Run the contract tests and confirm RED**

Run: `python -m pytest tests/test_models.py -v`  
Expected: collection/import failure because the package does not yet exist.

- [ ] **Step 3: Implement minimal contracts**

```python
@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: str
    evidence_id: str
    stable_id: str
    text: str
    # metadata fields with safe defaults

    def __post_init__(self) -> None:
        if not self.stable_id.strip():
            raise ValueError("stable_id is required")
```

Define `Query`, `Candidate`, `RankLog`, `SearchResult`, `SearchStatus`, `FeatureWeights`, and `RetrievalConfig`; validate positive K values and a weight sum of one.

- [ ] **Step 4: Run the contract tests and confirm GREEN**

Run: `python -m pytest tests/test_models.py -v`  
Expected: 2 passing tests.

- [ ] **Step 5: Review Task 1**

Check that no public model permits a missing stable ID, invalid K value, or unversioned `SearchResult`.

### Task 2: Lexical and vector retrieval primitives

**Files:**
- Create: `retrieval/bm25.py`
- Create: `retrieval/vector.py`
- Create: `tests/conftest.py`
- Test: `tests/test_bm25.py`

- [ ] **Step 1: Write failing retrieval tests**

```python
def test_bm25_ranks_exact_drug_name_first(chunks):
    index = BM25Index(chunks)
    assert index.search("amlodipine", k=2)[0].chunk_id == "c-drug"

def test_cosine_vector_search_returns_most_similar_chunk(chunks):
    search = InMemoryVectorSearch({"c-drug": (1.0, 0.0), "c-other": (0.0, 1.0)})
    assert search.search((0.9, 0.1), k=1)[0].chunk_id == "c-drug"
```

- [ ] **Step 2: Run and confirm RED**

Run: `python -m pytest tests/test_bm25.py -v`  
Expected: import failure for `BM25Index` and `InMemoryVectorSearch`.

- [ ] **Step 3: Implement minimal retrieval primitives**

```python
class BM25Index:
    def search(self, query: str, k: int) -> list[ScoredChunk]:
        # tokenize, calculate BM25, sort by (-score, chunk_id), return top k
        ...

class InMemoryVectorSearch:
    def search(self, query_vector: Sequence[float], k: int) -> list[ScoredChunk]:
        # dimension check, cosine similarity, stable sort, top k
        ...
```

Tokenization must lowercase Latin terms and preserve contiguous Chinese characters. Vector dimension mismatch must raise `ValueError`.

- [ ] **Step 4: Run and confirm GREEN**

Run: `python -m pytest tests/test_bm25.py -v`  
Expected: exact-term and cosine-search tests pass.

- [ ] **Step 5: Review Task 2**

Verify no network access, LLM call, or non-deterministic sorting is introduced.

### Task 3: RRF fusion and explainable feature reranking

**Files:**
- Create: `retrieval/fusion.py`
- Create: `retrieval/rerank.py`
- Test: `tests/test_fusion.py`
- Test: `tests/test_rerank.py`

- [ ] **Step 1: Write failing fusion and feature tests**

```python
def test_rrf_rewards_chunk_found_by_both_channels(chunks):
    merged = fuse_rrf([scored("c1", 1)], [scored("c1", 2), scored("c2", 1)], rrf_k=60)
    assert merged[0].chunk_id == "c1"

def test_rerank_prefers_matching_population_and_evidence_level(query, candidates):
    ranked = FeatureReranker(RetrievalConfig()).rank(query, candidates)
    assert ranked[0].chunk_id == "c-guideline-older-adult"
```

- [ ] **Step 2: Run and confirm RED**

Run: `python -m pytest tests/test_fusion.py tests/test_rerank.py -v`  
Expected: import failure for fusion/reranking modules.

- [ ] **Step 3: Implement RRF and features**

```python
def fuse_rrf(bm25: Sequence[ScoredChunk], vector: Sequence[ScoredChunk], rrf_k: int) -> list[Candidate]:
    # sum 1 / (rrf_k + rank) per available channel; retain ranks and raw scores
    ...

class FeatureReranker:
    def rank(self, query: Query, candidates: Sequence[Candidate]) -> list[RankLog]:
        # query-local percentile normalization and feature-score calculation
        ...
```

Implement semantic/lexical normalization, token-overlap PICO scoring, question-type evidence-level scoring, date freshness scoring, and source-completeness scoring. If no PICO field is available for a query, redistribute its weight among available features rather than assigning zero.

- [ ] **Step 4: Run and confirm GREEN**

Run: `python -m pytest tests/test_fusion.py tests/test_rerank.py -v`  
Expected: fusion formula, metadata-based ordering, and missing-PICO behavior pass.

- [ ] **Step 5: Review Task 3**

Inspect all `RankLog` values to ensure raw ranks, normalized scores, feature score, and configuration version are retained.

### Task 4: MMR, warnings, and orchestration

**Files:**
- Create: `retrieval/service.py`
- Modify: `retrieval/rerank.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write failing service tests**

```python
def test_service_limits_chunks_from_one_document(service, query):
    result = service.search(query)
    assert sum(c.evidence_id == "e-duplicate" for c in result.selected_chunks) <= 2

def test_service_reports_partial_when_vector_search_fails(service_with_failing_vector, query):
    result = service_with_failing_vector.search(query)
    assert result.status is SearchStatus.PARTIAL
    assert "vector" in result.degradation_reasons[0]
```

- [ ] **Step 2: Run and confirm RED**

Run: `python -m pytest tests/test_service.py -v`  
Expected: import failure for `RetrievalService`.

- [ ] **Step 3: Implement orchestration**

```python
class RetrievalService:
    def search(self, query: Query) -> SearchResult:
        # filter invalid chunks, retrieve independent channels, fuse, rerank, MMR-select
        # record component timings and convert failures to partial/empty/failed status
        ...
```

MMR must use `lambda * feature_score - (1-lambda) * max_similarity`, apply per-document and per-source caps, preserve rank logs, and set `retrieval_warning` for empty/one-source/low-score outcomes.

- [ ] **Step 4: Run and confirm GREEN**

Run: `python -m pytest tests/test_service.py -v`  
Expected: MMR cap, partial-failure, empty-result, and warning tests pass.

- [ ] **Step 5: Review Task 4**

Confirm partial execution never reports `ok`, and that no candidate without a stable ID reaches `selected_chunks`.

### Task 5: Metrics, documentation, and end-to-end validation

**Files:**
- Create: `retrieval/evaluation.py`
- Create: `tests/test_evaluation.py`
- Create: `README.md`
- Modify: `retrieval/__init__.py`

- [ ] **Step 1: Write failing metric tests**

```python
def test_recall_at_k_counts_any_acceptable_gold_id():
    assert recall_at_k(["e1", "e2"], {"e2", "e3"}, k=2) == 0.5

def test_ndcg_rewards_relevant_evidence_near_the_top():
    assert ndcg_at_k(["e1", "e2"], {"e1": 3, "e2": 1}, k=2) == 1.0
```

- [ ] **Step 2: Run and confirm RED**

Run: `python -m pytest tests/test_evaluation.py -v`  
Expected: import failure for evaluation functions.

- [ ] **Step 3: Implement metrics and usage guide**

```python
def recall_at_k(ranked_ids: Sequence[str], gold_ids: set[str], k: int) -> float:
    return len(set(ranked_ids[:k]) & gold_ids) / len(gold_ids) if gold_ids else 0.0
```

Implement `success_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, and source-diversity. README must document installation, the no-LLM P0 architecture, a runnable local example, test command, expected inputs, and the educational/non-diagnostic boundary.

- [ ] **Step 4: Run all tests and confirm GREEN**

Run: `python -m pytest -q`  
Expected: all tests pass with no collection errors.

- [ ] **Step 5: Final review**

Compare the design document against the implementation: verify every P0 requirement has either executable code and a test or a clearly documented upstream dependency. Scan source and docs for unresolved placeholder markers and secret-like values.
