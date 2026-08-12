# OpenEvidence Track-1 backend — A1 to A5 trustworthy evidence workflow

This repository contains the integrated Track-1 backend boundary. A5 is the
Python 3.11/Pydantic finite-state control layer; A1 safety, A2 read-only MCP
tools, A3 evidence/index/span contracts and A4 retrieval/rerank stay behind
replaceable adapters. This is an engineering MVP, not a clinical system and not
a medical-effect evaluation.

## Integrated ownership chain

```text
Question -> A5 Gate0 -> A1 safety/scope
         -> A5 Skill plan and tool budget
         -> A2 MCP tool -> A2 Evidence
         -> A3 Evidence/Chunk/Span and indexes
         -> A4 R0/R1/R2/R3 retrieval condition
         -> A5 Gate2 -> atomic claims -> Gate5 -> Gate6
         -> AgentRun / AgentRunView for A6 and B4
```

`backend.CoordinatedEvidenceRetriever` is the composition adapter; it does not
move A2/A3/A4 algorithms into A5. One A5 retrieval request spends at most one
A2 MCP call. A3 owns embeddings and index provenance. A4 query-local ranking
scores remain diagnostics; only an explicitly injected calibrated quality
scorer may emit Gate2-eligible `QUALITY/CROSS_QUERY` scores.

## A5 control flow

```text
START -> Gate0 -> CLASSIFY -> SELECT_SKILL -> PLAN
      -> RETRIEVE -> Gate1 <-> Gate2 -> SUMMARIZE_EVIDENCE
      -> Gate3 claim plan -> Gate4 structured generation
      -> CLAIM_SPLITTER -> AUDIT_CITATIONS -> Gate5 -> Gate6
      -> FINALIZE -> END
```

- Gate0 requires explicit `ALLOW`; missing or invalid safety input refuses
  before tools.
- `ToolBudgetManager` checks before every retrieval call. Gate2 retries the next
  source, stops early when sufficient, or refuses on conflict/exhaustion.
- Gate2 records candidate count, calibrated quality, diagnostic ranking score,
  source diversity, evidence level, freshness and conflicts. Missing upstream
  fields stay UNKNOWN/null.
- Gate3 creates an atomic-claim plan. Gate4 requires structured output and
  applies Evidence/Span whitelists before Claim splitting.
- Gate5 checks Evidence/Span whitelists, PICO/time/numeric consistency,
  conflicts and an injectable textual-support evaluator. Unknown semantic
  entailment is `INSUFFICIENT`, never supported by default.
- Gate6 applies criticality and uncertainty. Only supported claims enter the
  final answer.

## Versioned assets

- Skill packages under `a5/skills/evidence_research/` and
  `a5/skills/citation_audit/` include manifests, prompts, JSON Schemas,
  fixtures and implementations.
- Runtime configuration lives in `config/`; every `AgentRun` preserves the
  effective Skill/Prompt/Gate/Agent versions and configuration snapshot.
- A2 and A5 downstream schemas and replay fixtures live in `contracts/`.

## Run and verify

```powershell
pixi run test
pixi run demo
pixi run backend-demo
```

`pixi run demo` produces PASS/WARN/REFUSE examples and writes
`artifacts/demo_trace.json` plus `.txt`. `pixi run backend-demo` exercises the
actual in-process MCP client/server, A2→A3 normalization, A3 chunk/span/index,
A4 R1 retrieval and A5 Gate0–Gate6 using explicitly marked offline fixtures.
It writes `artifacts/backend_demo_trace.json` plus `.txt`.

## A6 and B4 entry points

A6 can validate the UI before live dependencies are configured:

```python
from a5.facade import answer_text, to_ui_view

run = answer_text("question", mode="replay", replay_case="PASS")
ui_payload = to_ui_view(run).model_dump(mode="json")
```

B4 persists the full `AgentRun.model_dump(mode="json")`. Live mode requires an
explicitly injected `BackendDependencies(workflow=...)`; it never constructs
credentials, models or connectors inside A5 and refuses if mock evidence escapes
into a live run. The stable schemas and PASS/WARN/REFUSE/ERROR replay fixtures
are under `contracts/a5/v0.4.0/`.

## Production boundaries

The reviewed provisional adapters remain as compatibility tests, while current
A1/A2/A3/A4 implementations are connected by `backend/`. Production deployment
must still inject a validated A1 free-text classifier, A2 live connectors, an A3
embedding provider, optional calibrated A4 capabilities, and structured
generation/verification transports.

BGE-M3 is not an A4-owned default: A4 consumes an already-constructed A3
`EmbeddingProvider`. BGE-M3 and CrossEncoder remain pending until the planning
document's reproducible development metrics and calibration are supplied. Raw
rerank logits never become Gate2 quality probabilities.

See `INTEGRATION.md`, `docs/backend_integration_architecture.md`,
`docs/review_compliance.md` and `docs/merge_readiness_report.md`.
