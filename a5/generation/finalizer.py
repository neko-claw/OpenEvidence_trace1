from __future__ import annotations

from collections.abc import Sequence

from a5.domain.enums import Decision
from a5.domain.models import CitationAuditReport, Claim, FinalAnswer


class Finalizer:
    """Render only verified claims; never asks an LLM to invent citations."""

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
                limitations=[reason or "The fail-closed publication gate rejected this run."],
            )

        approved_ids = set(audit.approved_claim_ids if audit else [])
        approved_claims = [claim for claim in claims if claim.claim_id in approved_ids]
        lines = [
            f"- {claim.text} [{', '.join(claim.evidence_ids)}]"
            for claim in approved_claims
        ]
        limitations = list(audit.reasons if audit else [])
        if decision is Decision.WARN:
            lines.append("\nLimitations: one or more non-critical claims were omitted.")

        cited_ids = list(
            dict.fromkeys(
                evidence_id
                for claim in approved_claims
                for evidence_id in claim.evidence_ids
            )
        )
        return FinalAnswer(
            decision=decision,
            text="\n".join(lines),
            included_claim_ids=[claim.claim_id for claim in approved_claims],
            cited_evidence_ids=cited_ids,
            limitations=limitations,
        )
