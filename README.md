# OpenEvidence A5 — Agent, Skill and trustworthy generation

A5 is a Python 3.11/Pydantic finite-state control layer. It provides versioned
Skills, bounded retrieval orchestration, fail-closed gates, atomic claim
verification and structured traces. It is an offline engineering MVP, not a
clinical system and not a medical-effect evaluation.

## Implemented control flow

```text
START -> Gate0 -> CLASSIFY -> SELECT_SKILL -> PLAN
      -> RETRIEVE <-> Gate2 -> SUMMARIZE_EVIDENCE
      -> GENERATE_CLAIMS -> CLAIM_SPLITTER -> AUDIT_CITATIONS
      -> Gate5 -> Gate6 -> FINALIZE -> END
```

- Gate0 requires an explicit `ALLOW`; default `UNKNOWN` refuses before tools.
- `ToolBudgetManager` checks before every retrieval call. Gate2 can retry the
  next source, stop early when sufficient, or refuse on conflict/exhaustion.
- Gate2 records count, score, source coverage/diversity, evidence level,
  freshness and conflicts. Missing upstream fields stay UNKNOWN/null.
- `ClaimSplitter` produces atomic claims. Gate5 checks Evidence/Span
  whitelists, PICO/time consistency, conflicts and an injectable textual-support
  evaluator. The P0 evaluator supports only exact normalized span matches;
  unknown semantic entailment is `INSUFFICIENT`.
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
and `SafetyPolicy` ports. A2 now provides opt-in multi-source connectors,
SQLite/cache, a local MCP v2 boundary, and `A2MCPRetriever`; A3 provides its
versioned evidence/index boundary. The default/demo composition remains fully
offline and unchanged. A4 ranking remains external. See `docs/a2/README.md`,
`INTEGRATION.md`, and `docs/review_compliance.md`.
