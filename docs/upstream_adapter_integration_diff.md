# A5 Upstream Adapter Integration Diff

Status: **REVIEWED BRANCH CONTRACTS / MAIN INTEGRATION PENDING**
Date: 2026-08-12
Plan baseline: `OpenEvidence MVP：赛道 1 与赛道 3 实施规划` v0.5
Adapter config: `config/integrations.yaml` v0.3.0

The public `answer(...)->AgentRun` API remains stable. A5 owns the finite-state
control layer; every upstream capability remains behind a Port/Adapter.

## Integration matrix

| Upstream | Reviewed snapshot | Classification | A5 action | Remaining conflict |
|---|---|---|---|---|
| A1 | Question v0.2 + Safety/termination v0.2, commit `b3e1ea6` | Adapter | Update Question/Safety output shapes; normalized signals only | free-text signal classifier and main integration pending |
| A2 | `a2-evidence-v1` + MCP tools, commit `881025a` | Adapter | consume `ok/evidence/diagnostics/error`; canonical source routes; add A2→A3 normalizer | normalizer ownership and real-source E2E pending |
| A3 | compatibility v0.3, commit `91a9180` | Adapter | map real Evidence/Chunk/Span; validate ID/hash/offset; preserve locators | v0.3 main integration and real Embedding validation pending |
| A4 | SearchResult branch, commit `21ad3a0` | Adapter + schema conflict | group chunks by Evidence ID; external Span Provider; ranking-score semantics | R0/R2/R3 execution and calibrated quality score blocked |

## Direct replacements

- A1 decision vocabulary: `ALLOW | DENY | UNKNOWN` and separate reason codes.
- A2 search envelope: boolean `ok`; no invented `status=partial` input field.
- A2 request: `queries[]` and configured `limit`.
- A3 explicit EvidenceSpan locator fields.

## Adapter-required differences

- A5 logical sources (`current_guideline`, `pubmed_review`,
  `clinicaltrials_record`) map to A2/A4 canonical sources in config.
- A2 `schema_version/content_hash/source_metadata` are normalized into A3
  fields/provenance; A2 hash is not presented as A3-computed identity.
- A3 object properties such as `stable_id/content_hash` are preserved when
  present; serialized payloads missing them stay incomplete/UNKNOWN.
- A4 chunk results are grouped into document-level `EvidenceRecord` values so
  Gate2 does not count several chunks from one Evidence as independent sources.
- A4 conflicts remain Evidence IDs. A4 token overlap stays diagnostics only.

## Schema conflicts and fail-closed behavior

- Chunk ID is not Span ID. Without an A3 Span Provider, A4 records expose
  `spans=[]` and Gate5 remains insufficient.
- A4 rerank scores are query-local ranking signals. They are mapped as
  `RANKING/QUERY_LOCAL/calibrated=false`; Gate2 accepts only the configured
  `QUALITY/CROSS_QUERY/calibrated=true` contract.
- BGE-M3 and CrossEncoder are disabled capabilities until their owners provide
  real dev metrics, latency, fixed versions and valid ablations.
- Missing provenance is UNKNOWN; tombstone/hash mismatch/invalid mock identity
  is rejected. Neither state becomes eligible by default.

## Tests and replacement points

- Tests: `tests/test_provisional_upstream_adapters.py`,
  `tests/test_gate_edges.py`, `tests/test_workflow.py`,
  `tests/test_architecture.py`.
- A1 replacement: `a5/adapters/provisional/a1.py`.
- A2/MCP and A2→A3 replacement: `a5/adapters/provisional/a2.py`.
- A3 compatibility replacement: `a5/adapters/provisional/a3.py`.
- A4 retrieval replacement: `a5/adapters/provisional/a4.py`.

Full rationale, rerank/Embedding review and literature attribution:
`docs/A1_A2_A3_A4_A5_兼容性审查与实施报告.md`.
