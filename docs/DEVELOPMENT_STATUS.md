# A5 current development status

## 2026-08-12 reviewed upstream branch integration

- Updated versioned A1/A2/A3/A4 Adapter boundaries under
  `a5/adapters/provisional/` against current branch contracts without changing
  the public
  `answer(...)->AgentRun` API.
- A1 Question/Safety v0.2, A2 Evidence/MCP v1, A3 compatibility v0.3 and the
  current A4 SearchResult are mapped structurally; missing values remain UNKNOWN.
- Added explicit Gate1, A2→A3 normalization, real A3 Span mapping, hash/offset
  checks, source canonicalization and reproducible question as-of dates.
- A4 rank scores are query-local diagnostics, not Gate2 probabilities.
  Unverified BGE-M3/CrossEncoder capabilities remain disabled.
- Effective contract refs and vocabulary maps are recorded from
  `config/integrations.yaml` in every RuntimeConfigSnapshot.
- Dedicated contract tests and the full A5 regression suite pass; see
  `docs/upstream_adapter_integration_diff.md` for field mappings and sources.

## A. Independently implemented

- versioned Prompt/manifest/JSON Schema/fixture/implementation packages for
  `evidence_research@0.2.0` and `citation_audit@0.3.0`;
- configurable classifier/search planning, EvidenceSummary and atomic
  ClaimSplitter;
- explicit finite-state workflow, state-aware Skill routing, real tool-call
  budget and Gate2 corrective retry/early stop;
- fail-closed Gate0, Gate1 and Gate6;
- Gate2 quality metrics and Gate5 mechanical whitelist/span/PICO/time/conflict/
  exact-span, numeric/unit checks with extension ports;
- PASS/WARN/REFUSE publication policy using criticality and uncertainty;
- serializable AgentRun/config snapshot and terminal/JSON demo traces;
- behavior, contract, config, architecture and artifact tests.

## B. Implemented through replaceable offline adapters

- `MockEvidenceRetriever` for `EvidenceRetriever`;
- `MockClaimGenerator` for `ClaimGenerator`;
- `ExactSpanTextualSupportEvaluator` behind `TextualSupportEvaluator`;
- `RuleBasedClaimVerifier` for `ClaimVerifier`;
- `FixtureSafetyPolicy` for explicit offline ALLOW/DENY scenarios.

These are clearly synthetic and do not claim medical semantic accuracy.

## C. Waiting for upstream main integration or real validation

- A1 free-text safety signal classifier and full branch-to-main integration;
- A2→A3 normalizer ownership decision and real-source end-to-end samples;
- A3 compatibility v0.3 main integration and real Embedding validation;
- A4 valid R0–R3 same-candidate-pool ablation and calibrated quality score;
- future LLM/NLI/medical verifier and formal medical evaluation.

The C items do not block the A5 offline control-layer tests. They enter through
adapters documented in `INTEGRATION.md`.

## Deliberately out of scope

A5 does not collect PubMed/ClinicalTrials/guidelines, implement MCP servers,
build BM25/vector/RRF/rerank/MMR, train models, create medical gold data, or
provide a Streamlit UI.
