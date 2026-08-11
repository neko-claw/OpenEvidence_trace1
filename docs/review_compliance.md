# A5 Review Compliance Matrix

This matrix tracks the blocking review for PR #1. A blocker is marked `PASS`
only after its implementation and behavior-specific tests pass. Upstream A1–A4
dependencies remain behind A5 ports/adapters and are never counted as an A5
implementation.

Baseline: 2026-08-12. The original B1–B5 remediation is retained; this revision
adds the planning-defined Gate1 and reviewed A1–A4 branch contracts.

## B1 — Skill delivery

- Status: PASS
- Problem: Skills lack versioned manifests, prompt/schema assets, reusable
  fixtures, evidence summary, and atomic claim splitting.
- Implementation: Both Skills are loadable versioned asset packages. Pydantic
  contracts, JSON Schema, prompts, manifests, fixtures, EvidenceSummary, and a
  deterministic ClaimSplitter are implemented. Missing evidence metrics remain
  UNKNOWN/null.
- Files: `a5/skills/loader.py`, `a5/skills/evidence_research/`,
  `a5/skills/citation_audit/`, `prompts/`, `a5/domain/models.py`.
- Tests: `tests/test_skill_assets.py`, `tests/test_skill_logic_v2.py`.
- Demo Evidence: `artifacts/demo_trace.json` records both Skill versions,
  EvidenceSummary, generated/atomic claim IDs and Gate5 results.
- Remaining Upstream Dependency: Final A1 question taxonomy and A2/A3 evidence
  schemas; A5 will consume them through configuration/adapters.

## B2 — Restricted Agent orchestration

- Status: PASS
- Problem: Tool budget and corrective retry are not enforced; routing is fixed;
  evidence sufficiency cannot stop or retry retrieval.
- Implementation: State-aware SkillRouter, ToolBudgetManager, corrective Gate2
  retry, source-by-source calls, early stop, budget exhaustion and explicit
  termination transitions are enforced.
- Files: `a5/agent/router.py`, `a5/agent/budget.py`,
  `a5/agent/state.py`, `a5/agent/workflow.py`.
- Tests: `tests/test_workflow.py`, `tests/test_state_machine.py`.
- Demo Evidence: `artifacts/demo_trace.json` shows call #1 insufficient, call #2
  sufficient, and one remaining call not spent.
- Remaining Upstream Dependency: A4 retrieval implementation and result adapter.

## B3 — Gate2 and Gate5 trustworthy generation

- Status: PASS
- Problem: Retrieval quality metrics and claim-level whitelist/span/PICO/time/
  textual-support checks are absent; the current verifier reads fixture gold
  labels and ignores uncertainty.
- Implementation: Gate2 reports candidate count, top score, source count/
  diversity, strongest evidence level, freshness and conflict count. Gate5
  enforces Evidence/Span whitelists, PICO/time consistency, conflicts, exact
  span support and nullable entailment through an injectable evaluator. Fixture
  support labels are ignored. Gate6 enforces uncertainty and publishes only
  supported claims.
- Files: `a5/gates/evidence_sufficiency.py`, `a5/gates/release.py`,
  `a5/adapters/rule_based_claim_verifier.py`, `a5/ports/textual_support.py`.
- Tests: `tests/test_gate_edges.py`, `tests/test_workflow.py`,
  `tests/test_config_versioning.py`.
- Demo Evidence: `artifacts/demo_trace.json` contains structured Gate2 metrics
  and per-claim Gate5 results with spans/matches/entailment method.
- Remaining Upstream Dependency: A3 frozen span/PICO/evidence-level schema and
  optional future medical NLI/LLM verifier.

## B4 — Gate0 fail-closed safety

- Status: PASS
- Problem: Temporary policy defaults to allow and Gate0 is not an explicit
  pre-retrieval tripwire.
- Implementation: Gate0 executes before classification/retrieval/generation.
  DefaultFailClosedSafetyPolicy returns UNKNOWN, and both UNKNOWN/DENY trip the
  release gate. Fixture ALLOW is an explicit offline adapter, not an A1 policy.
- Files: `a5/adapters/default_safety_policy.py`, `a5/agent/workflow.py`.
- Tests: `tests/test_gate_edges.py`, `tests/test_workflow.py`.
- Demo Evidence: First post-START event in `artifacts/demo_trace.json` is Gate0;
  separate tests prove UNKNOWN/DENY cause zero retriever calls.
- Remaining Upstream Dependency: A1 safety/scope/refusal policy adapter.

## B5 — Prompt/config/versioning

- Status: PASS
- Problem: Prompts are absent; versions and thresholds are hardcoded; run
  configuration is not snapshotted.
- Implementation: Versioned Prompt assets and JSON-compatible YAML config drive
  agent/Skill/Prompt/Gate versions, model adapter identifiers, tool budget,
  thresholds and uncertainty policy. Every AgentRun stores the effective
  RuntimeConfigSnapshot.
- Files: `prompts/`, `config/`, `a5/runtime_config.py`,
  `a5/skills/loader.py`, `a5/domain/models.py`.
- Tests: `tests/test_skill_assets.py`, `tests/test_config_versioning.py`,
  `tests/test_workflow.py`.
- Demo Evidence: `artifacts/demo_trace.json` includes agent/Skill/Prompt/Gate
  versions and the complete effective config snapshot.
- Remaining Upstream Dependency: Final A1 policy versions and production model
  selection; both remain replaceable configuration.

## I1 — Gate1 and upstream provenance

- Status: PASS (A5 scope)
- Implementation: Explicit Gate1 state/event; production records require
  configured provenance fields and an accepted Adapter integrity marker;
  tombstone/mismatch/mock-in-production fail closed.
- Files: `a5/gates/evidence_integrity.py`,
  `a5/ports/evidence_integrity.py`, workflow/state/models/config.
- Tests: Gate1 strict/mock states, workflow trace, production UNKNOWN/eligible.
- Remaining Upstream Dependency: A2 source validation and A3 provenance enter
  through reviewed adapters; branch-to-main integration remains pending.

## I2 — Rerank and Embedding isolation

- Status: PASS (A5 scope)
- Implementation: Retrieval score kind/scope/calibration are explicit. Gate2
  accepts only calibrated cross-query quality scores. A4 rank values remain
  query-local diagnostics. Unverified BGE-M3/CrossEncoder are disabled in the
  effective config and rejected when presented as enabled production features.
- Tests: uncalibrated scores remain UNKNOWN; capability blockers execute.
- Remaining Upstream Dependency: A3 dev Recall@50/latency and A4 valid R0–R3
  same-candidate-pool ablation.

## Merge state

**MERGE READY (A5 CONTROL LAYER)** — `pixi run test` reports 74 passed; the
refreshed demo covers Gate0→Gate1→Gate2→Claim→Gate5→Gate6; Schema, capability,
Mock boundary and diff checks pass. Upstream production integration remains
PENDING and is not part of this A5-owned readiness claim. See
`docs/merge_readiness_report.md`.
