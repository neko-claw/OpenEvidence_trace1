# Backend merge readiness report

Date: 2026-08-12

Branch: `feature/backend-integration`

Planning baseline: `docs/OpenEvidence_MVP_赛道1与赛道3实施规划.md`

## Verdict

**MERGE READY — TRACK-1 BACKEND ARCHITECTURE AND A6/B4 CONTRACTS**

This verdict means the A1→A5 ownership chain, fail-closed controls, adapters,
offline acceptance path and downstream schemas are executable and tested. It
does not mean the system is clinically validated or that live network/model
dependencies have been deployed.

## Blocker result

| Item | Status | Primary evidence |
|---|---|---|
| B1 Skill assets/splitting | PASS | `test_skill_assets.py`, `test_skill_logic_v2.py` |
| B2 routing/budget/retry | PASS | `test_workflow.py`, `test_backend_integration.py` |
| B3 Gate2/Gate5/Gate6 | PASS | `test_gate_edges.py`, `test_a5_backend_contract.py` |
| B4 Gate0 fail-closed | PASS | `test_a1_a2_backend_contracts.py`, zero-call safety tests |
| B5 Prompt/config/version | PASS | `test_config_versioning.py`, contract export tests |
| A2→A3 normalization | PASS | `test_a1_a2_backend_contracts.py` |
| A3→A4 one-pool retrieval | PASS | `test_a3_a4_retrieval_integration.py` |
| A4 score semantics | PASS | explicit ranking/quality separation tests |
| A1→A5 full composition | PASS | `test_backend_integration.py` |
| A6/B4 schemas/replays | PASS | `test_a5_backend_contract.py`, `contracts/a5/v0.4.0/` |

## Actual verification

- `pixi run test`: **505 passed, 3 skipped in 4.57s**. The skipped tests are
  opt-in live-network tests; all offline unit, contract and integration tests
  passed.
- `pixi run demo`: PASS/WARN/REFUSE completed and regenerated
  `artifacts/demo_trace.json` / `.txt`.
- `pixi run backend-demo`: PASS with two Evidence records and one publishable
  atomic Claim; regenerated `artifacts/backend_demo_trace.json` / `.txt`.
- A4 smoke evaluation: Recall@50 1.000, nDCG@8 0.750, span proxy recall 1.000,
  Claim chunk coverage 1.000. These are pipeline smoke metrics over explicit
  mock data, not medical-effect metrics.

## Rerank/embedding safeguards

- R0–R3 consume the same immutable candidate pool per question.
- R1 uses feature rerank/MMR; R2/R3 remain unavailable unless calibrated
  capabilities are injected.
- Cross-Encoder raw logits cannot become probabilities without explicit
  semantics/calibration.
- A4 never constructs BGE-M3. It consumes an A3 `EmbeddingProvider`; capability
  stays pending until A3 reports the required DEV recall, latency and rebuild
  reproducibility.
- Query-local ranking values never satisfy Gate2's calibrated cross-query
  quality threshold.

## A6 handoff

- Safe UI model/schema: `AgentRunView` /
  `contracts/a5/v0.4.0/schemas/AgentRunView.schema.json`.
- Full B4 model/schema: `AgentRun` /
  `contracts/a5/v0.4.0/schemas/AgentRun.schema.json`.
- Replay fixtures: PASS, WARN, REFUSE and ERROR.
- Entry points: `a5.facade.answer_text` and `a5.facade.to_ui_view`.
- Live mode requires explicit `BackendDependencies`; mock leakage forces
  REFUSE.

## Remaining non-merge blockers for later production milestones

- A1: validated free-text safety classifier and final reviewed policy.
- A2: deployed live connectors, credentials/rate limits and source governance.
- A3: approved embedding model/revision plus DEV Recall@50, latency and rebuild
  report.
- A4: optional Cross-Encoder/quality calibration and formal same-pool ablation.
- A5: independent medical semantic verifier and formal medical evaluation.
- A6/B4: UI deployment and batch runner implementation.

These items do not block A6 from implementing and testing the front end against
the frozen replay/mock contracts. They do block clinical/live-production
claims.
