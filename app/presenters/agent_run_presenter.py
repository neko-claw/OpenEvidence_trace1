from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import TypeVar

from app.contracts import AgentPayload, TraceEventView

T = TypeVar("T")


@dataclass(frozen=True)
class DecisionPresentation:
    title: str
    message: str
    icon: str
    tone: str


@dataclass(frozen=True)
class TimelineStep:
    label: str
    states: tuple[str, ...]
    status: str
    latency_ms: float
    result: str


_DECISIONS = {
    "PASS": DecisionPresentation(
        "证据已核验",
        "当前回答仅包含通过 A5 核验的主张。",
        ":material/verified:", "success",
    ),
    "WARN": DecisionPresentation(
        "已有证据，但存在限制",
        "已展示通过核验的主张，并明确列出尚未解决的限制。",
        ":material/warning:", "warning",
    ),
    "REFUSE": DecisionPresentation(
        "证据不足，无法提供可靠回答",
        "OpenEvidence 已在发布无充分支持的医学主张前停止。",
        ":material/shield:", "error",
    ),
}

_REASON_LABELS = {
    "safety_denied": "该问题超出当前允许的安全范围。",
    "integrity_rejected": "一条或多条证据记录未通过来源完整性检查。",
    "retrieval_insufficient": "检索到的证据未达到充分性要求。",
    "retrieval_conflict": "关键证据冲突尚未解决。",
    "budget_exhausted": "证据检索已达到配置的工具调用预算。",
    "generation_rejected": "候选主张未满足生成约束。",
    "illegal_citation": "主张引用了本次运行证据白名单以外的证据。",
    "missing_span": "无法定位支持该主张的证据片段。",
    "pico_mismatch": "人群或干预措施等上下文不一致。",
    "time_mismatch": "证据时间不满足问题的时效要求。",
    "unsupported_claim": "检索到的证据不足以支持该主张。",
    "contradicted_claim": "检索到的证据与该主张相矛盾。",
    "high_uncertainty": "关键主张仍存在较高或未知不确定性。",
    "upstream_unavailable": "上游证据服务暂时不可用。",
    "internal_error": "内部步骤未完成，系统已按封闭原则停止发布。",
}

_TIMELINE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("范围与安全检查", ("GATE0",)),
    ("问题理解", ("CLASSIFY", "SELECT_SKILL", "PLAN")),
    ("证据研究", ("RETRIEVE", "GATE1", "GATE2")),
    ("证据摘要", ("SUMMARIZE_EVIDENCE",)),
    ("主张生成", ("GATE3", "GENERATE_CLAIMS", "CLAIM_SPLITTER", "GATE4")),
    ("引用审计", ("AUDIT_CITATIONS", "GATE5")),
    ("发布门禁", ("GATE6", "FINALIZE", "END")),
)


def present_decision(payload: AgentPayload) -> DecisionPresentation:
    return _DECISIONS[payload.decision]


def present_reasons(payload: AgentPayload) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for code in payload.reason_codes:
        label = _REASON_LABELS.get(code, f"未识别的原因代码：{code}")
        if label not in seen:
            seen.add(label)
            result.append(label)
    for text in (*payload.warnings, *payload.limitations):
        readable = _REASON_LABELS.get(text.split(":", 1)[0].strip(), text)
        if readable and readable not in seen:
            seen.add(readable)
            result.append(readable)
    return result


def present_timeline(events: tuple[TraceEventView, ...]) -> list[TimelineStep]:
    steps: list[TimelineStep] = []
    for label, states in _TIMELINE_GROUPS:
        matched = [event for event in events if event.state in states]
        if not matched:
            continue
        errored = next((event for event in matched if event.error), None)
        decisions = [event.decision for event in matched if event.decision]
        outputs = [event.output_count for event in matched if event.output_count is not None]
        if errored:
            status, result = "已停止", "该步骤未完成。"
        elif decisions:
            status, result = "已完成", _decision_label(decisions[-1])
        elif outputs:
            status, result = "已完成", f"输出 {outputs[-1]} 项"
        else:
            status, result = "已完成", "已记录"
        steps.append(TimelineStep(
            label=label,
            states=states,
            status=status,
            latency_ms=sum(event.latency_ms for event in matched),
            result=result,
        ))
    return steps


def paginate(items: tuple[T, ...] | list[T], page_index: int, page_size: int) -> tuple[list[T], int, int]:
    if page_size < 1:
        raise ValueError("page_size must be positive")
    page_count = max(1, ceil(len(items) / page_size))
    safe_index = min(max(page_index, 0), page_count - 1)
    start = safe_index * page_size
    return list(items[start : start + page_size]), safe_index, page_count


def _decision_label(value: str) -> str:
    return {
        "PASS": "通过",
        "WARN": "警告",
        "REFUSE": "拒答",
        "ALLOW": "允许",
        "DENY": "拒绝",
        "UNKNOWN": "未知",
        "SUFFICIENT": "证据充分",
        "INSUFFICIENT": "证据不足",
        "ELIGIBLE": "符合要求",
        "ACCEPTED": "已接受",
    }.get(value, value)
