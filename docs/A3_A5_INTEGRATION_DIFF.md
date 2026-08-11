# A3 → A5 Integration Diff (a3-compat-v0.3)

Baseline: `feature/a3-data-wiki@9593706a`; comparison base:
`origin/main@a68ef8f`. The current main and all fetched remote branches contain
no `a5/adapters/provisional/a3.py`. The only earlier A3 mapper was
`a5/adapters/a3_evidence_adapter.py`; v0.3 replaces it with the single canonical
`a5/adapters/a3.py` boundary.

| Classification | Fields / behavior | Decision |
|---|---|---|
| Direct mapping | Evidence ID, selected Chunk text, source type, title, PICO, published time, evidence level, `mock`; Span ID/text/chunk/page/section | Preserve explicit values; missing optional values remain `None`/UNKNOWN. |
| Adapter required | A4-selected Chunk whitelist, Span parentage and dual offsets, content hashes, raw locator, tombstone, corpus/index/config/model versions | Validate fail-closed; retain per-Span details and version diagnostics in `EvidenceRecord.source_metadata`. |
| Schema conflict | A3 exposes raw BM25 score/vector distance; A5 accepts only normalized `retrieval_score` | Do not map raw scores. Until A4 supplies a normalized score, A5 receives `None`. |
| Schema conflict | `wiki_navigation` is searchable but is not medical Evidence | It has `evidence_id=None`, `mock=true`, `navigation_only`; the canonical adapter accepts only Evidence + A4-selected Chunks, never SearchHit. |
| Missing upstream | A1 final safety/freshness policy | Keep A5 fail-closed Protocol boundary. |
| Missing upstream | A2 final production Evidence/provenance mapping | A3 remains a provisional compatibility contract; require explicit production provenance when the canonical adapter is used. |
| Missing upstream | A4 selected-chunk schema, normalized score, RRF/rerank/MMR diagnostics | Accept selected A3 Chunk objects at the compatibility seam; do not implement or bypass A4. |
| Missing upstream | reviewed real LLM Wiki provider and medical review | Keep Issue #4 open; the injected structured adapter has no bound provider and fails closed. |

## Merge-blocking checklist

- [x] P0-1 typed BM25/Vector SearchHit provenance and navigation separation
- [x] P0-2 unique canonical adapter with structured reason codes
- [x] P0-3 per-Span locator/offset/hash provenance
- [x] P0-4 Chinese punctuation splitting without whitespace
- [x] P0-5 requested vs runtime-effective Manifest snapshot
- [x] P0-6 PyYAML/retrieval/embedding packaging profiles and import smoke
- [x] P0-7 latest local command matrix; minimal CI workflow added (remote result checked after push)
- [x] P0-8 A3 versions/selection/diagnostics preserved in AgentRun/Trace
- [x] P1-1 safe generated Wiki stale-page cleanup
- [x] P1-2 complete injected `LLMWikiGeneratorAdapter.generate()` control flow
- [x] P1-3 precise external blocker recorded for incomplete local BGE snapshot

Workflow/FSM, Gate0/2/5/6, `answer(...)->AgentRun`, and A4 ranking algorithms
remain unchanged.
