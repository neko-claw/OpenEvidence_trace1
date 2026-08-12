from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from a5.domain.enums import Decision, VerificationStatus
from a5.domain.models import (
    AgentPlan,
    AnswerFinding,
    CitationAuditReport,
    Claim,
    EvidenceRecord,
    FinalAnswer,
    Question,
    StructuredAnswer,
)
from a5.ports.answer_presenter import VerifiedClaimPresenter


class ResearchAnswerFinalizer:
    """Answer-first renderer over Gate5-approved claims only.

    This deterministic fallback organises verified claims as an answer rather
    than presenting retrieved records as the product. An optional presenter may
    localize a verified statement after Gate5; the original statement remains
    the authoritative audit anchor and failed presentation falls back to it.
    """

    def __init__(self, presenter: VerifiedClaimPresenter | None = None) -> None:
        self._presenter = presenter

    def finalize(
        self,
        decision: Decision,
        claims: Sequence[Claim],
        audit: CitationAuditReport | None,
        refusal_reason: str | None = None,
    ) -> FinalAnswer:
        return self.finalize_with_context(
            decision,
            Question(text="未提供问题上下文"),
            None,
            claims,
            [],
            audit,
            refusal_reason,
        )

    def finalize_with_context(
        self,
        decision: Decision,
        question: Question,
        plan: AgentPlan | None,
        claims: Sequence[Claim],
        evidence: Sequence[EvidenceRecord],
        audit: CitationAuditReport | None,
        refusal_reason: str | None = None,
    ) -> FinalAnswer:
        if decision is Decision.REFUSE:
            reason = refusal_reason or "; ".join(audit.reasons if audit else [])
            return FinalAnswer(
                decision=decision,
                text="当前检索结果不足以形成可核验的回答。",
                limitations=[reason or "可信发布门禁已停止本次回答。"],
            )
        approved_ids = set(audit.approved_claim_ids if audit else [])
        approved = [
            claim
            for claim in claims
            if claim.claim_id in approved_ids
            and claim.decision is VerificationStatus.SUPPORTED
        ]
        cited = list(dict.fromkeys(eid for claim in approved for eid in claim.evidence_ids))
        cited_records = [item for item in evidence if item.id in cited]
        findings = []
        for index, claim in enumerate(approved, start=1):
            display = self._presenter.present(claim.text) if self._presenter else None
            findings.append(AnswerFinding(
                finding_id=f"F{index}",
                statement=claim.text,
                claim_ids=[claim.claim_id],
                evidence_ids=list(claim.evidence_ids),
                display_statement=display,
                display_language="zh-CN" if display else None,
                applicability=claim.population,
            ))
        profile = self._evidence_profile(cited_records)
        applicability = self._applicability(approved)
        uncertainties = self._uncertainties(approved, cited_records, audit, decision)
        direct = findings[0].display_statement or findings[0].statement if findings else (
            "当前没有通过逐条核验、可直接回答该问题的医学主张。"
        )
        structured = StructuredAnswer(
            direct_answer=direct,
            direct_evidence_ids=(list(findings[0].evidence_ids) if findings else []),
            findings=findings,
            applicability=applicability,
            evidence_profile=profile,
            uncertainties=uncertainties,
            composition_method="verified-claim-organizer-v0.2.0",
        )
        text = self._render_text(structured)
        return FinalAnswer(
            decision=decision,
            text=text,
            included_claim_ids=[claim.claim_id for claim in approved],
            cited_evidence_ids=cited,
            limitations=uncertainties,
            warnings=uncertainties if decision is Decision.WARN else [],
            structured=structured,
        )

    @staticmethod
    def _evidence_profile(evidence: Sequence[EvidenceRecord]) -> list[str]:
        counts = Counter(item.evidence_level or item.source_type for item in evidence)
        labels = {
            "guideline": "指南/共识",
            "systematic_review": "系统综述/Meta分析",
            "controlled_study": "随机或对照研究",
            "clinical_trial_registry": "临床试验注册",
            "review": "综述",
            "study": "原始研究",
            "pubmed": "PubMed 文献",
            "europe_pmc": "Europe PMC 文献",
        }
        return [f"{labels.get(kind, kind)} {count} 项" for kind, count in counts.items()]

    @staticmethod
    def _applicability(claims: Sequence[Claim]) -> str:
        populations = list(dict.fromkeys(claim.population for claim in claims if claim.population))
        if populations:
            return "；".join(populations)
        return "本轮证据的人群/PICO 信息未完整结构化；应用结论前请核对各来源纳入人群。"

    @staticmethod
    def _uncertainties(
        claims: Sequence[Claim],
        evidence: Sequence[EvidenceRecord],
        audit: CitationAuditReport | None,
        decision: Decision,
    ) -> list[str]:
        result = list(audit.reasons if audit else [])
        if any(claim.population is None for claim in claims):
            result.append("部分证据缺少结构化人群/PICO 信息，适用性需要人工核对。")
        if not any(item.evidence_level == "guideline" for item in evidence):
            result.append("本次已发布证据中未包含经正式指南连接器确认的指南原文。")
        if any(item.evidence_level is None for item in evidence):
            result.append("部分来源的证据等级未知，未进行正式 GRADE 确定性评级。")
        if decision is Decision.WARN:
            result.append("部分非关键候选主张未通过验证，已从回答中移除。")
        return list(dict.fromkeys(result))

    def _render_text(self, answer: StructuredAnswer) -> str:
        direct_citations = ", ".join(
            self._citation_label(eid) for eid in answer.direct_evidence_ids
        )
        direct = (
            f"{answer.direct_answer} [{direct_citations}]"
            if direct_citations else answer.direct_answer
        )
        lines = ["### 直接回答", direct, "", "### 已核验结论"]
        lines.extend(
            f"- {finding.statement} [{', '.join(self._citation_label(eid) for eid in finding.evidence_ids)}]"
            for finding in answer.findings
        )
        lines.extend(["", "### 适用范围", answer.applicability])
        if answer.evidence_profile:
            lines.extend(["", "### 证据构成", "；".join(answer.evidence_profile)])
        return "\n".join(lines)

    @staticmethod
    def _citation_label(evidence_id: str) -> str:
        return evidence_id.split("::", 1)[0]
