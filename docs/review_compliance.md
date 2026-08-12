# Review compliance matrix

Date: 2026-08-12

Scope: A5 B1–B5 blockers plus the A1→A5 Track-1 composition required before
A6/B4 integration. `PASS` means executable code and behavior-specific tests,
not clinical validation.

## B1 — versioned Skill delivery

- Status: **PASS**
- Problem: Python-only Skills lacked manifests, prompts, schemas, fixtures,
  EvidenceSummary and atomic Claim splitting.
- Implementation: both Skills are versioned asset packages loadable by
  name/version. Pydantic contracts match checked-in JSON Schema; fixtures
  validate; evidence research returns structured summary; citation audit uses
  `ClaimSplitter` before per-Claim verification.
- Files: `a5/skills/`, `prompts/`, `a5/domain/models.py`.
- Tests: `test_skill_assets.py`, `test_skill_logic_v2.py`,
  `test_a5_backend_contract.py`.
- Demo Evidence: both Skill versions and split Claim IDs appear in
  `artifacts/demo_trace.json` and `artifacts/backend_demo_trace.json`.
- Remaining Upstream Dependency: final A1 taxonomy may replace routing config;
  no workflow rewrite is required.

## B2 — restricted orchestration

- Status: **PASS**
- Problem: declared tool budget was not enforced; routing/retrieval were fixed;
  no quality-driven retry or early stop existed.
- Implementation: `SkillRouter` and `ToolBudgetManager` execute inside the FSM.
  Each retrieval checks remaining budget; Gate2 chooses continue/retry/refuse;
  sufficient evidence stops early and exhaustion prohibits call N+1.
- Files: `a5/agent/router.py`, `budget.py`, `state.py`, `workflow.py`,
  `backend/source.py`.
- Tests: `test_workflow.py`, `test_state_machine.py`,
  `test_backend_source.py`, `test_backend_integration.py`.
- Demo Evidence: the backend trace makes calls 1 and 2, reaches SUFFICIENT with
  one call remaining, and does not call a third source.
- Remaining Upstream Dependency: production source availability affects
  results, not enforcement.

## B3 — Gate2/Gate5 trustworthy generation

- Status: **PASS**
- Problem: retrieval sufficiency and Claim support gates were incomplete;
  fixture labels could masquerade as verification; uncertainty was unused.
- Implementation: Gate2 evaluates count, calibrated quality, source coverage/
  diversity, evidence level, freshness and conflicts. A4 ranking is separately
  typed and cannot satisfy the quality threshold. Gate3 plans atomic claims;
  Gate4 enforces structured output and ID/span whitelists; Gate5 checks span,
  PICO, time, numeric/unit consistency, conflicts and an independent textual
  support Port. Unknown entailment remains INSUFFICIENT. Gate6 applies
  criticality and uncertainty.
- Files: `a5/gates/`, `a5/adapters/rule_based_claim_verifier.py`,
  `openai_compatible_claim_generator.py`, `semantic_claim_verifier.py`,
  `retrieval/models.py`, `retrieval/service.py`.
- Tests: `test_gate_edges.py`, `test_workflow.py`,
  `test_a5_backend_contract.py`, `test_a3_gate5_integration.py`,
  `test_a3_a4_retrieval_integration.py`.
- Demo Evidence: Gate2→Gate3→Gate4→ClaimSplitter→Gate5→Gate6 is present in
  both trace formats.
- Remaining Upstream Dependency: an independently validated medical semantic
  verifier and calibrated A4 quality scorer are still deployment/evaluation
  dependencies; exact-span P0 is not presented as medical NLI.

## B4 — Gate0 fail-closed safety

- Status: **PASS**
- Problem: default safety allowed processing and Gate0 was not a pre-tool
  tripwire.
- Implementation: Gate0 runs first. `A1SafetyPolicyAdapter` accepts only a
  complete explicit verdict; absent classifier/signals, exception or malformed
  output produces UNKNOWN and REFUSE before retrieval/generation.
- Files: `a1/ports/safety_classifier.py`, `a1/adapters/a5_safety.py`,
  `a5/agent/workflow.py`.
- Tests: `test_a1_a2_backend_contracts.py`, `test_gate_edges.py`,
  `test_workflow.py`.
- Demo Evidence: Gate0 is the first post-START event in both traces.
- Remaining Upstream Dependency: production A1 free-text classifier/final
  medical policy must be injected.

## B5 — Prompt/config/versioning

- Status: **PASS**
- Problem: prompts, versions and thresholds were hardcoded or not recorded.
- Implementation: Prompt/Skill assets and Gate/Agent/model settings are loaded
  from versioned files. Every `AgentRun` records effective versions and runtime
  config. `config/backend.yaml` snapshots composition routing/chunk policy.
- Files: `config/`, `prompts/`, `a5/runtime_config.py`, `backend/config.py`,
  `contracts/a5/v0.4.0/`.
- Tests: `test_config_versioning.py`, `test_skill_assets.py`,
  `test_backend_source.py`, `test_a5_backend_contract.py`.
- Demo Evidence: JSON traces contain Skill/Prompt/Gate/Agent versions and the
  runtime snapshot.
- Remaining Upstream Dependency: production versions replace config values via
  injection; the FSM remains stable.

## I1 — A2/A3/A4 composition and provenance

- Status: **PASS**
- Problem: module-level tests did not prove the planned ownership chain worked
  as one backend.
- Implementation: `CoordinatedEvidenceRetriever` invokes one A2 MCP tool,
  normalizes to A3, creates A3 Chunk/Span/index provenance, builds one frozen A4
  candidate pool and adapts its SearchResult to A5. Errors/empty results remain
  structured and fail closed.
- Files: `backend/`, `a2/adapters/a3_evidence.py`,
  `retrieval/a3_pool_adapter.py`, `a5/adapters/a4_evidence_retriever.py`.
- Tests: `test_backend_source.py`, `test_backend_retriever.py`,
  `test_backend_integration.py`.
- Demo Evidence: `artifacts/backend_demo_trace.*`.
- Remaining Upstream Dependency: live connector/model injection only.

## I2 — rerank and BGE-M3 risk controls

- Status: **PASS**
- Problem: query-local rerank values could be misused as evidence quality, and
  A4 could accidentally own/load a second BGE-M3 stack.
- Implementation: ranking and quality have distinct kind/scope/calibration
  fields. Only `CalibratedQualityScorer` output reaches Gate2. R2/R3 require
  explicit ready capabilities. `retrieval.bge_m3` is an A3 provider adapter,
  disabled by default; A4 does not load or download models.
- Files: `retrieval/models.py`, `ports.py`, `service.py`, `cross_encoder.py`,
  `bge_m3.py`, `a5/adapters/a4_evidence_retriever.py`.
- Tests: `test_a3_a4_retrieval_integration.py`, `test_bge_m3.py`,
  `test_adaptive_cross_encoder.py`, `test_a4_adapter.py`.
- Demo Evidence: backend R1 trace records ranking diagnostics and explicit
  fixture-only quality semantics separately.
- Remaining Upstream Dependency: A3 embedding DEV metrics and optional A4
  calibrated P1 ablation.

## Verification state

- `pixi run test`: **505 passed, 3 skipped**.
- `pixi run demo`: PASS/WARN/REFUSE and A5 traces generated.
- `pixi run backend-demo`: PASS; A1→A2 MCP→A3→A4→A5 trace generated.

**All B1–B5 and integration blockers are PASS for backend architecture/A6
contract integration. Clinical validation and live-production capability are
explicitly not claimed.**
