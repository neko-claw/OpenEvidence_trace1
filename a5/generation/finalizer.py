from __future__ import annotations

from collections.abc import Sequence

from a5.domain.enums import Decision, VerificationStatus
from a5.domain.models import CitationAuditReport, Claim, FinalAnswer


class Finalizer:
    """Gate6 renderer: only Gate5-supported atomic claims can be published."""

    def finalize(
        self,
        decision: Decision,
        claims: Sequence[Claim],
        audit: CitationAuditReport | None,
        refusal_reason: str | None = None,
    ) -> FinalAnswer:
        if decision is Decision.REFUSE:
            reason = refusal_reason or "; ".join(audit.reasons if audit else [])
            return FinalAnswer(
                decision=decision,
                text="Unable to provide an evidence-grounded answer for this request.",
                limitations=[reason or "The fail-closed release gate rejected this run."],
            )
        approved_ids = set(audit.approved_claim_ids if audit else [])
        approved = [
            claim
            for claim in claims
            if claim.claim_id in approved_ids
            and claim.decision is VerificationStatus.SUPPORTED
        ]
        lines = [
            f"- {claim.text} [{', '.join(claim.evidence_ids)}]"
            for claim in approved
        ]
        warnings = list(audit.reasons if audit else [])
        if decision is Decision.WARN:
            warnings.append("One or more non-critical claims were omitted after Gate5.")
        return FinalAnswer(
            decision=decision,
            text="\n".join(lines),
            included_claim_ids=[claim.claim_id for claim in approved],
            cited_evidence_ids=list(
                dict.fromkeys(evidence_id for claim in approved for evidence_id in claim.evidence_ids)
            ),
            limitations=warnings,
            warnings=warnings,
        )
