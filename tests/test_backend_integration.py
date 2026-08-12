from __future__ import annotations

from a5.domain.enums import Decision, WorkflowState
from backend.demo import run_fixture_demo


def test_full_backend_coordination_reaches_all_owned_boundaries(tmp_path) -> None:
    run = run_fixture_demo(tmp_path)

    assert run.decision is Decision.PASS
    assert len(run.retrieved_evidence) >= 2
    assert all(record.mock for record in run.retrieved_evidence)
    assert all(not record.source_metadata.get(name) for record in run.retrieved_evidence for name in ("pmid", "doi", "nct_id", "url"))
    assert run.evidence_sufficiency is not None
    assert run.evidence_sufficiency.status.value == "SUFFICIENT"
    assert run.evidence_sufficiency.metrics.usable_quality_score_count >= 2
    assert run.claims and run.verification_results
    assert run.final_answer is not None and run.final_answer.included_claim_ids

    states = [event.state for event in run.trace]
    for required in (
        WorkflowState.GATE0,
        WorkflowState.SELECT_SKILL,
        WorkflowState.RETRIEVE,
        WorkflowState.GATE1,
        WorkflowState.GATE2,
        WorkflowState.GATE3,
        WorkflowState.GATE4,
        WorkflowState.CLAIM_SPLITTER,
        WorkflowState.AUDIT_CITATIONS,
        WorkflowState.GATE5,
        WorkflowState.GATE6,
        WorkflowState.FINALIZE,
        WorkflowState.END,
    ):
        assert required in states
    tool_events = [event for event in run.trace if event.tool_call_index is not None]
    assert [event.tool_call_index for event in tool_events] == [1, 2]
    assert any(event.details.get("diagnostics", {}).get("pipeline") == [
        "A2_MCP", "A2_TO_A3", "A3_INDEX", "A4_RETRIEVAL"
    ] for event in tool_events)
