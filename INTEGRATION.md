# A5 Integration Contract

The A5 state machine and public `answer(question, workflow=...) -> AgentRun`
shape should remain stable. When upstream files arrive, first produce an
Integration Diff and prefer a new adapter over changes to the workflow.

## Integration procedure

1. Read the new upstream files and sample payloads.
2. Compare them with the current Port and compatibility model.
3. Classify each difference as direct replacement, adapter required, or schema
   conflict.
4. Add the smallest adapter and keep core state transitions stable.
5. Run all regression tests.
6. Remove only temporary assumptions made obsolete by the upstream contract.
7. Update this document with the real implementation and remaining gaps.

## A1 -> policy and termination

Required from A1:

- frozen question types and classification rules;
- allowed medical safety scope and escalation boundaries;
- refusal rules and reason codes;
- Agent termination policy.

Replace/integrate at:

- `config/skills.yaml` classifier/routing policy;
- `a5.adapters.default_safety_policy.DefaultFailClosedSafetyPolicy` via a new A1-backed
  `SafetyPolicy` implementation;
- workflow early-finalization mapping only if A1 adds new explicit termination
  outcomes. Keep the state machine otherwise unchanged.

## A2 -> Evidence and MCP

Required from A2:

- frozen Evidence Schema and versioning rules;
- MCP Tool Schema and error contract;
- MCP client/server invocation code;
- fixture/sample Evidence payloads.

Replace/integrate at:

- add an Evidence compatibility adapter that maps the A2 model to the narrow
  `EvidenceRecord` view;
- add `A2MCPRetriever(EvidenceRetriever)`;
- replace `MockEvidenceRetriever` only in the production composition root.

Do not copy or invent the A2 MCP Tool Schema inside A5.

## A3 -> PICO, spans, and evidence hierarchy

Required from A3:

- final PICO types;
- evidence span representation;
- evidence level/quality fields;
- page, section, and chunk schema.

Replace/integrate at:

- Evidence compatibility adapter mapping into `EvidenceSpan` and temporary
  PICO/evidence-level fields;
- `RuleBasedClaimVerifier` metadata/provenance checks;
- optional A6 presentation fields on an output adapter.

Do not expand the temporary `EvidenceRecord` into an assumed final schema before
these definitions arrive.

## A4 -> retrieval and reranking

Required from A4:

- `search()` and `rerank()` callable contracts;
- Top-K Evidence response schema;
- score, rank, and feature-log fields;
- empty-result and exception formats.

Replace/integrate at:

- add `A4RAGRetriever(EvidenceRetriever)` and normalize its response to
  `RetrievalResult`;
- map A4 diagnostics into `RetrievalResult.diagnostics`; each normalized call
  receives a `RetrievalRequest` with source and call index and flows to Trace.

A5 will not implement BM25, vector search, RRF, reranking, or MMR.

## A6 <- A5 UI contract

A6 can call:

```python
run = answer(question, workflow=configured_workflow)
payload = run.model_dump(mode="json")
```

Primary fields are `decision`, `final_answer`, `evidence_sufficiency`,
`evidence_summary`, `retrieved_evidence`, `claims`, `verification_results`,
`trace`, runtime versions/config, `error`, and timestamps/latency. A6 should show
limitations for `WARN` and the refusal reason for `REFUSE`.

## B4 <- A5 batch/evaluation contract

B4 can use the same entry point per question and persist
`AgentRun.model_dump_json()`. Batch orchestration is intentionally outside A5;
`run_id`, timings, state events, tool diagnostics, and decision are already
available for aggregation.

## Current temporary assumptions

- question type strings, source routes and gate thresholds are labeled
  development defaults in `config/`;
- mock candidate statements drive generation only; the verifier never reads
  fixture support/contradiction gold labels;
- `question.metadata.mock_safety_decision` is consumed only by the offline
  `FixtureSafetyPolicy`; default safety remains UNKNOWN/refuse;
- no live LLM, MCP, RAG, medical NLI, data collection, or formal medical
  evaluation is present.

## Integration Diff template

For each upstream delivery record:

- upstream file/version;
- current A5 Port/model affected;
- direct replacement / adapter / schema conflict;
- fields mapped, dropped, or missing;
- core-code changes, if unavoidable;
- tests added or updated;
- temporary assumption removed;
- remaining owner and TODO.
