# OpenEvidence A5 — Agent, Skill and trustworthy generation

A5 is a Python 3.11/Pydantic finite-state control layer. It provides versioned
Skills, bounded retrieval orchestration, fail-closed gates, atomic claim
verification and structured traces. It is an offline engineering MVP, not a
clinical system and not a medical-effect evaluation.

## Implemented control flow

```text
START -> Gate0 -> CLASSIFY -> SELECT_SKILL -> PLAN
      -> RETRIEVE -> Gate1 <-> Gate2 -> SUMMARIZE_EVIDENCE
      -> GENERATE_CLAIMS -> CLAIM_SPLITTER -> AUDIT_CITATIONS
      -> Gate5 -> Gate6 -> FINALIZE -> END
```

- Gate0 requires an explicit `ALLOW`; default `UNKNOWN` refuses before tools.
- Gate1 admits Mock Evidence only in explicit fixture mode and checks adapter
  provenance markers/fields; rejected or tombstoned records fail closed.
- `ToolBudgetManager` checks before every retrieval call. Gate2 can retry the
  next source, stop early when sufficient, or refuse on conflict/exhaustion.
- Gate2 records count, calibrated cross-query quality score, diagnostic ranking
  score, source coverage/diversity, evidence level,
  freshness and conflicts. Missing upstream fields stay UNKNOWN/null.
- `ClaimSplitter` produces atomic claims. Gate5 checks Evidence/Span
  whitelists, PICO/time consistency, conflicts and an injectable textual-support
  evaluator. The P0 evaluator supports only exact normalized span matches;
  unknown semantic entailment is `INSUFFICIENT`. Numeric/unit mismatch remains
  blocking even if a future semantic evaluator returns support.
- Gate6 uses criticality and uncertainty. Only supported claims reach the final
  answer; failed non-critical claims produce `WARN`, while critical failures,
  illegal IDs, safety failures and insufficient retrieval produce `REFUSE`.

## Versioned assets

- Skill packages: `a5/skills/evidence_research/` and
  `a5/skills/citation_audit/` contain manifest, prompt, input/output JSON Schema,
  fixture and implementation.
- Shared prompts live in `prompts/` and are checked against packaged prompts.
- Runtime configuration lives in `config/agent.yaml`, `gates.yaml`,
  `skills.yaml`, and `models.yaml`. These files use JSON syntax, which is valid
  YAML, to avoid adding a YAML production dependency.
- Every `AgentRun` records agent/Skill/Prompt/Gate versions and a full
  `RuntimeConfigSnapshot`.

## Run and verify

```powershell
pixi run demo
pixi run test
```

The demo prints PASS, WARN and REFUSE runs and writes the PASS run to
`artifacts/demo_trace.json` and `artifacts/demo_trace.txt`. The stable downstream
entry remains:

```python
run = answer(question, workflow=configured_workflow)
payload = run.model_dump(mode="json")
```

Mock classes are wired only by `a5/bootstrap.py`; the workflow depends on
`EvidenceRetriever`, `ClaimGenerator`, `ClaimVerifier`, `TextualSupportEvaluator`
and `SafetyPolicy` ports. A2/A3/A4 production capabilities are deliberately not
implemented here. See `INTEGRATION.md` and `docs/review_compliance.md`.

## Provisional upstream integration

Current A1/A3/A4 branch snapshots and the missing A2 delivery are represented by
replaceable adapters under `a5/adapters/provisional/`. They are intentionally not
wired into the default composition root. Production use must inject the real A1
evaluator, A2 MCP client, A3 records, and A4 query factory/search service.

The adapters fail closed on unknown safety, invalid terminal status, missing
reproducibility versions, Gate1 provenance gaps, and fixture-like data without
`mock=true`. Contract versions and vocabulary mappings come from
`config/integrations.yaml` and are recorded in the runtime snapshot. Detailed
mappings, remaining blockers, and literature/open-source attribution are in
`docs/A1_A2_A3_A4_A5_兼容性审查与实施报告.md`.

A4 query-local rerank values are recorded as uncalibrated ranking diagnostics,
not Gate2 quality probabilities. BGE-M3 and CrossEncoder capabilities remain
disabled until their owning teams provide the plan-required reproducible dev
metrics; A5 does not load either model.
