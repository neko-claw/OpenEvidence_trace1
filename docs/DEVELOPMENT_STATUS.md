# A5 current development status

## A. Independently implemented

- versioned Prompt/manifest/JSON Schema/fixture/implementation packages for
  `evidence_research@0.2.0` and `citation_audit@0.2.0`;
- configurable classifier/search planning, EvidenceSummary and atomic
  ClaimSplitter;
- explicit finite-state workflow, state-aware Skill routing, real tool-call
  budget and Gate2 corrective retry/early stop;
- fail-closed Gate0 and Gate6;
- Gate2 quality metrics and Gate5 mechanical whitelist/span/PICO/time/conflict/
  exact-span and critical-claim verified-trust checks with extension ports;
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

## C. Waiting for frozen upstream interfaces

- A1 question taxonomy, scope/safety/refusal rules and termination policy;
- A2 Evidence/MCP schema, client calls, errors and real samples;
- A3 frozen PICO/span/evidence-level/provenance schema;
- A4 search/rerank response, score/rank/feature logs and error forms;
- future LLM/NLI/medical verifier and formal medical evaluation.

The C items do not block the A5 offline control-layer tests. They enter through
adapters documented in `INTEGRATION.md`.

## Deliberately out of scope

A5 does not collect PubMed/ClinicalTrials/guidelines, implement MCP servers,
build BM25/vector/RRF/rerank/MMR, train models, create medical gold data, or
provide a Streamlit UI.
