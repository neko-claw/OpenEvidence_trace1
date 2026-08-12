from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from a5.agent.workflow import A5Workflow
from a5.bootstrap import build_demo_workflow
from a5.domain.enums import Decision, SafetyDecision, UIReasonCode, VerificationStatus
from a5.domain.models import AgentRun, AgentRunView, EvidenceCardView, Question

BackendMode = Literal["replay", "mock", "live"]
ReplayCase = Literal["PASS", "WARN", "REFUSE", "ERROR"]


@dataclass(frozen=True)
class BackendDependencies:
    """Application composition object; A6 never constructs an A5 workflow."""

    workflow: A5Workflow


def answer_text(
    question: str,
    *,
    mode: BackendMode = "replay",
    dependencies: BackendDependencies | None = None,
    replay_case: ReplayCase = "PASS",
) -> AgentRun:
    """Stable A6/B4 entry point for replay, offline mock and injected live modes."""

    if mode == "replay":
        return load_replay(replay_case)
    if mode == "mock":
        batches = {
            "PASS": [["E1"], ["E2"]],
            "WARN": [["E1"], ["E3"]],
            "REFUSE": [[], [], []],
            "ERROR": [[], [], []],
        }[replay_case]
        return build_demo_workflow().answer(
            Question(
                text=question,
                metadata={
                    "mock_safety_decision": "ALLOW",
                    "fixture_batches": batches,
                    "demo_mode": True,
                },
            )
        )
    if mode != "live":
        raise ValueError(f"unsupported backend mode: {mode}")
    if dependencies is None:
        raise ValueError("live mode requires injected BackendDependencies")
    run = dependencies.workflow.answer(question)
    if any(record.mock for record in run.retrieved_evidence):
        run.decision = Decision.REFUSE
        run.error = "LiveModeMockEvidenceError: live workflow returned mock evidence"
        if run.final_answer is not None:
            run.final_answer = run.final_answer.model_copy(
                update={
                    "decision": Decision.REFUSE,
                    "text": "Unable to provide an evidence-grounded answer for this request.",
                    "included_claim_ids": [],
                    "cited_evidence_ids": [],
                    "warnings": ["upstream_unavailable"],
                    "limitations": ["upstream_unavailable: live evidence validation failed"],
                }
            )
    return run


def load_replay(case: ReplayCase) -> AgentRun:
    path = _contract_root() / "fixtures" / f"{case.lower()}.json"
    return AgentRun.model_validate_json(path.read_text(encoding="utf-8"))


def to_ui_view(run: AgentRun) -> AgentRunView:
    """Project a full B4 run into a safe, stable A6 view model."""

    answer = run.final_answer
    decision = run.decision or Decision.REFUSE
    included_claim_ids = list(answer.included_claim_ids if answer else [])
    included = {
        claim.claim_id: claim
        for claim in run.claims
        if claim.claim_id in included_claim_ids and claim.decision is VerificationStatus.SUPPORTED
    }
    cited_ids = {evidence_id for claim in included.values() for evidence_id in claim.evidence_ids}
    cards: list[EvidenceCardView] = []
    for evidence in run.retrieved_evidence:
        if evidence.id not in cited_ids:
            continue
        cited_span_ids = {
            span_id
            for claim in included.values()
            if evidence.id in claim.evidence_ids
            for span_id in claim.evidence_span_ids
        }
        span = next((item for item in evidence.spans if item.span_id in cited_span_ids), None)
        cards.append(
            EvidenceCardView(
                evidence_id=evidence.id,
                title=evidence.title,
                source_type=evidence.source_type,
                published_at=evidence.published_at,
                url=_safe_url(evidence.source_metadata.get("url"), mock=evidence.mock),
                page=span.page if span else None,
                section=span.section if span else None,
                evidence_level=evidence.evidence_level,
                mock=evidence.mock,
            )
        )
    reason_codes = _reason_codes(run)
    error_code = None
    error_message = None
    if run.error:
        error_code = (
            UIReasonCode.UPSTREAM_UNAVAILABLE
            if any(token in run.error.casefold() for token in ("retriev", "upstream", "mcp", "live"))
            else UIReasonCode.INTERNAL_ERROR
        )
        error_message = (
            "An upstream evidence service is unavailable."
            if error_code is UIReasonCode.UPSTREAM_UNAVAILABLE
            else "The request failed closed due to an internal error."
        )
        if error_code not in reason_codes:
            reason_codes.append(error_code)
    return AgentRunView(
        run_id=run.run_id,
        decision=decision,
        answer_text=answer.text if answer else "Unable to provide an evidence-grounded answer for this request.",
        included_claim_ids=included_claim_ids,
        reason_codes=reason_codes,
        warnings=list(answer.warnings if answer else []),
        limitations=list(answer.limitations if answer else []),
        evidence_cards=cards,
        trace=list(run.trace),
        error_code=error_code,
        error_message=error_message,
    )


def _reason_codes(run: AgentRun) -> list[UIReasonCode]:
    raw: list[str] = []
    if run.safety_assessment and run.safety_assessment.decision is not SafetyDecision.ALLOW:
        raw.append(UIReasonCode.SAFETY_DENIED.value)
    if run.evidence_integrity:
        raw.extend(run.evidence_integrity.reasons)
    if run.evidence_sufficiency:
        raw.extend(run.evidence_sufficiency.reasons)
    if run.generation_constraints:
        raw.extend(run.generation_constraints.reasons)
    raw.extend(reason for result in run.verification_results for reason in result.reasons)
    if run.final_answer:
        raw.extend(run.final_answer.limitations)
        raw.extend(run.final_answer.warnings)
    allowed = {item.value: item for item in UIReasonCode}
    result: list[UIReasonCode] = []
    for reason in raw:
        code = allowed.get(str(reason).split(":", 1)[0].strip())
        if code and code not in result:
            result.append(code)
    return result


def _safe_url(value: object, *, mock: bool) -> str | None:
    if mock or not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def _contract_root() -> Path:
    return Path(__file__).parents[1] / "contracts" / "a5" / "v0.4.0"
