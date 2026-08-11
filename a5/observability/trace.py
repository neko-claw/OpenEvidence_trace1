from __future__ import annotations

from a5.domain.models import AgentRun


def trace_as_json(run: AgentRun, *, indent: int = 2) -> str:
    return run.model_dump_json(indent=indent)


def render_trace(run: AgentRun) -> str:
    lines = [f"AgentRun {run.run_id}"]
    for event in run.trace:
        details: list[str] = [f"at={event.timestamp.isoformat()}"]
        if event.selected_skill:
            details.append(f"skill={event.selected_skill}")
        if event.details.get("question_type"):
            details.append(f"type={event.details['question_type']}")
        if event.agent_plan:
            search_plan = event.agent_plan.get("search_plan", {})
            sources = search_plan.get("preferred_sources", [])
            if sources:
                details.append(f"sources={','.join(sources)}")
        if event.tool:
            details.append(f"tool={event.tool}")
        if event.tool_input_summary:
            summary = ",".join(
                f"{key}={value}" for key, value in event.tool_input_summary.items()
            )
            details.append(f"input={summary}")
        if event.tool_output_count is not None:
            details.append(f"count={event.tool_output_count}")
        if event.retrieved_evidence_ids:
            details.append(f"evidence={','.join(event.retrieved_evidence_ids)}")
        if event.generated_claim_ids:
            details.append(f"claims={','.join(event.generated_claim_ids)}")
        if event.verification_result:
            verification = ",".join(
                f"{claim_id}:{status}"
                for claim_id, status in event.verification_result.items()
            )
            details.append(f"verify={verification}")
        if event.final_decision:
            details.append(f"decision={event.final_decision}")
        if event.error:
            details.append(f"error={event.error}")
        details.append(f"latency_ms={event.latency_ms:.2f}")
        lines.append(f"{event.state.value:<18} " + " ".join(details))
    return "\n".join(lines)
