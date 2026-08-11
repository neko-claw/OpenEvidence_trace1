# A5 Integration Contract

The A5 state machine and public `answer(question, workflow=...) -> AgentRun`
shape should remain stable. When upstream files arrive, first produce an
Integration Diff and prefer a new adapter over changes to the workflow.

## Integration procedure

1. Read the new upstream files and sample payloads.
2. Compare them with the current Port and compatibility model.
3. Classify each difference as direct replacement, adapter required, or schema
   conflict.
4. Add the smallest adapter and keep core state transitions stable.
5. Run all regression tests.
6. Remove only temporary assumptions made obsolete by the upstream contract.
7. Update this document with the real implementation and remaining gaps.

## A1 -> policy and termination

Required from A1:

- frozen question types and classification rules;
- allowed medical safety scope and escalation boundaries;
- refusal rules and reason codes;
- Agent termination policy.

Replace/integrate at:

- `config/skills.yaml` classifier/routing policy;
- `a5.adapters.default_safety_policy.DefaultFailClosedSafetyPolicy` via a new A1-backed
  `SafetyPolicy` implementation;
- workflow early-finalization mapping only if A1 adds new explicit termination
  outcomes. Keep the state machine otherwise unchanged.

## A2 -> Evidence and MCP

Required from A2:

- frozen Evidence Schema and versioning rules;
- MCP Tool Schema and error contract;
- MCP client/server invocation code;
- fixture/sample Evidence payloads.

Replace/integrate at:

- add an Evidence compatibility adapter that maps the A2 model to the narrow
  `EvidenceRecord` view;
- add `A2MCPRetriever(EvidenceRetriever)`;
- replace `MockEvidenceRetriever` only in the production composition root.

Do not copy or invent the A2 MCP Tool Schema inside A5.

## A3 -> PICO, spans, and evidence hierarchy

Required from A3:

- final PICO types;
- evidence span representation;
- evidence level/quality fields;
- page, section, and chunk schema.

Replace/integrate at:

- Evidence compatibility adapter mapping into `EvidenceSpan` and temporary
  PICO/evidence-level fields;
- `RuleBasedClaimVerifier` metadata/provenance checks;
- optional A6 presentation fields on an output adapter.

Do not expand the temporary `EvidenceRecord` into an assumed final schema before
these definitions arrive.

## A4 -> retrieval and reranking

Required from A4:

- `search()` and `rerank()` callable contracts;
- Top-K Evidence response schema;
- score, rank, and feature-log fields;
- empty-result and exception formats.

Replace/integrate at:

- add `A4RAGRetriever(EvidenceRetriever)` and normalize its response to
  `RetrievalResult`;
- map A4 diagnostics into `RetrievalResult.diagnostics`; each normalized call
  receives a `RetrievalRequest` with source and call index and flows to Trace.

A5 will not implement BM25, vector search, RRF, reranking, or MMR.

## A6 <- A5 UI contract

A6 can call:

```python
run = answer(question, workflow=configured_workflow)
payload = run.model_dump(mode="json")
```

Primary fields are `decision`, `final_answer`, `evidence_sufficiency`,
`evidence_summary`, `retrieved_evidence`, `claims`, `verification_results`,
`trace`, runtime versions/config, `error`, and timestamps/latency. A6 should show
limitations for `WARN` and the refusal reason for `REFUSE`.

## B4 <- A5 batch/evaluation contract

B4 can use the same entry point per question and persist
`AgentRun.model_dump_json()`. Batch orchestration is intentionally outside A5;
`run_id`, timings, state events, tool diagnostics, and decision are already
available for aggregation.

## Current temporary assumptions

- question type strings, source routes and gate thresholds are labeled
  development defaults in `config/`;
- mock candidate statements drive generation only; the verifier never reads
  fixture support/contradiction gold labels;
- `question.metadata.mock_safety_decision` is consumed only by the offline
  `FixtureSafetyPolicy`; default safety remains UNKNOWN/refuse;
- no live LLM, MCP, RAG, medical NLI, data collection, or formal medical
  evaluation is present.

## Integration Diff template

For each upstream delivery record:

- upstream file/version;
- current A5 Port/model affected;
- direct replacement / adapter / schema conflict;
- fields mapped, dropped, or missing;
- core-code changes, if unavoidable;
- tests added or updated;
- temporary assumption removed;
- remaining owner and TODO.

## A3 Integration Diff — a3-schema/index v0.2

- Upstream: `a3.domain.models` is authoritative for A3 Evidence, PICO, Chunk,
  EvidenceSpan, SearchHit, and IndexManifest. No formal A2 schema or sample was
  present on `origin/main`; the checked-in A3 sample is explicitly mock/offline.
- A5 models affected: `EvidenceRecord` and `EvidenceSpan` through
  `a5.adapters.a3_evidence_adapter.adapt_a3_evidence`; `Claim`,
  `VerificationResult`, and `RuleBasedClaimVerifier` are exercised unchanged.
- Classification: direct mapping for identity/text/source/title/PICO/date/level;
  adapter required for selected chunk content, page conversion, spans, and
  provenance; no core schema conflict.
- Mapped: A3 `id`, selected exact Chunk `text`, `source_type`, `title`, explicit
  PICO, parseable `published_at`, explicit `evidence_level`, exact spans, and
  `mock`.
- Retained in `source_metadata`: stable ID, content hash, raw page, only-present
  identifiers, guideline name, chunk IDs, corpus/index versions, and provenance.
- Dropped: none. Non-numeric pages map to A5 `page=None` while the original is
  retained as `raw_page`. A3 raw BM25 score/vector distance is deliberately not
  converted into A5's normalized `retrieval_score`.
- Core A5 changes: none. The workflow, gates, FSM, and public
  `answer(question, workflow=...) -> AgentRun` API are unchanged.
- Tests: `test_a3_a5_adapter.py` and `test_a3_gate5_integration.py` cover legal
  span, illegal Evidence ID, illegal/wrong span, missing span, PICO
  match/mismatch/UNKNOWN, time match/mismatch/UNKNOWN, exact textual support,
  and paraphrase remaining INSUFFICIENT using the real rule-based verifier.
- Missing/remaining owner: A2 final schema and importer semantics (A2), A4
  normalized retrieval score and BM25/vector fusion/rerank/MMR (A4), semantic
  medical verification (A5 owner), and source-card/Wiki presentation (A6).

- Frozen downstream artifacts are checked in under `contracts/a3/v0.2/`; they
  contain Pydantic-generated schemas and a versioned mock fixture, not an A2
  final Evidence declaration. Field and provenance semantics are documented in
  `docs/A3_CONTRACT.md`.
- Chunk offsets are document-relative. Span offsets are chunk-relative and also
  carry explicit document-relative offsets. Both carry current content hashes;
  non-numeric locators such as `S12` and `appendix-A` remain in `raw_page`.
- `config/a3.yaml` is validated strictly and controls every A3 build path and
  semantic version input. Its effective values are persisted in IndexManifest.
- Wiki lexical hits are marked `document_kind=wiki_navigation`; only configured
  title/synonym/MeSH terms enter BM25, never Chroma or the raw evidence corpus.

### A4 remote contract observation (2026-08-11)

- `origin/A4` exposes lexical `search(query: str, k: int)` and vector
  `search(query_vector, k)` ports producing A4 `ScoredChunk` objects; A4 retains
  ownership of RRF, feature reranking, and MMR.
- A3's `SearchHit` carries the required raw channel/rank/score-or-distance,
  evidence/chunk identity, PICO, locator, and frozen index version needed by a
  future A4 adapter.
- The observed A4 branch is not based on current `origin/main` and its branch
  diff removes the A5 tree. It was therefore treated as a read-only contract
  reference and was not merged into this branch.

### BGE-M3 local source handoff

- The semantic model identity remains `BAAI/bge-m3` at frozen revision
  `5617a9f61b028005a4858fdac845db406aefb181`.
- `A3_BGE_M3_MODEL_PATH` may point to a verified local snapshot. The provider
  validates required files and loads FlagEmbedding from that directory while
  keeping the logical model ID/revision—and therefore index semantics—stable.
- Local absolute paths are never included in corpus/index version hashes or
  persisted index metadata. If the variable is absent, the provider retains
  the official Hub fallback.
- `modelscope-hub` is a downloader-only Pixi dependency used to retrieve the
  official `BAAI/bge-m3` snapshot when the Hugging Face large-file CDN is not
  reachable; it is not part of A3's runtime API.
