from __future__ import annotations

from a5.domain.models import AgentRun


def trace_as_json(run: AgentRun, *, indent: int = 2) -> str:
    return run.model_dump_json(indent=indent)


def render_trace(run: AgentRun) -> str:
    lines = [
        f"AgentRun {run.run_id} agent={run.agent_version} gate_config={run.gate_config_version}"
    ]
    for event in run.trace:
        fields = [f"event={event.event_type.value}", f"at={event.timestamp.isoformat()}"]
        for label, value in (
            ("gate", event.gate),
            ("skill", event.skill),
            ("tool", event.tool),
            ("call", event.tool_call_index),
            ("budget_remaining", event.tool_budget_remaining),
            ("count", event.output_count),
            ("decision", event.decision),
        ):
            if value is not None:
                fields.append(f"{label}={value}")
        if event.input_summary:
            fields.append(
                "input=" + ",".join(f"{key}={value}" for key, value in event.input_summary.items())
            )
        if event.evidence_ids:
            fields.append(f"evidence={','.join(event.evidence_ids)}")
        if event.claim_ids:
            fields.append(f"claims={','.join(event.claim_ids)}")
        if event.error:
            fields.append(f"error={event.error}")
        fields.append(f"latency_ms={event.latency_ms:.2f}")
        lines.append(f"{event.state.value:<22} " + " ".join(fields))
    return "\n".join(lines)
