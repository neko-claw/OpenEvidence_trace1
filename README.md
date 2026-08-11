# OpenEvidence A5 MVP

A5 is a Python 3.11, Pydantic-based finite-state workflow for evidence-bound
claim generation and fail-closed publishing. The current repository is an
offline integration skeleton: it does not retrieve real medical literature and
must not be treated as a clinical system.

## What works now

- Explicit workflow: `CLASSIFY -> PLAN -> SELECT_SKILL -> RETRIEVE ->
  CHECK_EVIDENCE -> GENERATE_CLAIMS -> VERIFY_CLAIMS -> FINALIZE -> END`.
- Replaceable Protocols for retrieval, claim generation, claim verification,
  and safety policy.
- `evidence_research@v0.1` produces a configurable search plan.
- `citation_audit@v0.1` enforces citation presence and whitelist membership,
  then aggregates claim results into `PASS`, `WARN`, or `REFUSE`.
- Only verified atomic claims reach the final answer. A `WARN` answer omits
  failed non-critical claims; any critical failure is `REFUSE`.
- Pydantic `AgentRun` output includes state/tool/claim/verification/decision
  events, per-step latency, errors, and JSON serialization.
- Offline E1-E5 fixtures are visibly synthetic and all have `mock=true`.

## What is temporary

- `EvidenceRecord` is a **TEMPORARY COMPATIBILITY MODEL**, not the final A2/A3
  Evidence schema.
- `QuestionClassifierConfig` and `DefaultSafetyPolicy` are development defaults
  awaiting A1.
- `MockEvidenceRetriever` and `MockClaimGenerator` exist only to run the offline
  workflow.
- `RuleBasedClaimVerifier` checks citation mechanics and explicit fixture
  markers. It performs no medical semantic inference.

## Run

With Pixi installed:

```powershell
pixi run demo
pixi run test
```

Or in any activated Python 3.11 environment:

```powershell
python -m pip install -r requirements.txt
python main.py
pytest
```

`python main.py` runs PASS, WARN, and REFUSE fixtures and prints the complete
terminal trace. `AgentRun.model_dump_json()` or
`a5.observability.trace.trace_as_json()` produces the A6/B4-friendly JSON form.

## Architecture

```text
A5Workflow
  |-- EvidenceRetriever       -> Mock today; A2 MCP / A4 RAG later
  |-- ClaimGenerator          -> Mock today; structured LLM adapter later
  |-- ClaimVerifier           -> Rule-based today; LLM/NLI/medical later
  |-- SafetyPolicy            -> Temporary default today; A1 later
  |-- EvidenceResearchSkill   -> configurable planning policy
  `-- CitationAuditSkill      -> fail-closed publication gate
```

Mock classes are wired only in `a5/bootstrap.py`, the demo composition root.
`a5/agent/workflow.py` imports no adapter package.

## Decision semantics

- `PASS`: non-empty evidence and every claim is supported, including all
  critical claims.
- `WARN`: all critical claims are supported; failed non-critical claims are
  removed and limitations are displayed.
- `REFUSE`: no valid evidence, no verifiable claims, illegal evidence ID,
  unsupported/contradicted critical claim, unresolved critical conflict, safety
  refusal, or workflow error.

See [INTEGRATION.md](INTEGRATION.md) for upstream contracts and
[docs/DESIGN_REFERENCES.md](docs/DESIGN_REFERENCES.md) for research grounding.
