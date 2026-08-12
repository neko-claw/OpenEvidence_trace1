from __future__ import annotations

import re
from collections.abc import Sequence

from a5.domain.enums import GenerationConstraintStatus
from a5.domain.models import Claim, EvidenceRecord, GenerationConstraintResult


class EvidenceConstrainedGenerationGate:
    """Gate4 structural tripwire, independent from the model adapter."""

    _external_reference = re.compile(
        r"(?:https?://|www\.|\bPMID\s*:?\s*\d+\b|\bNCT\d{8}\b|"
        r"\b10\.\d{4,9}/\S+|\bGUIDELINE\s*:)",
        re.IGNORECASE,
    )

    def evaluate(
        self,
        claims: Sequence[Claim],
        evidence: Sequence[EvidenceRecord],
        *,
        run_id: str,
    ) -> GenerationConstraintResult:
        evidence_ids = {record.id for record in evidence}
        span_owner = {span.span_id: record.id for record in evidence for span in record.spans}
        accepted: list[str] = []
        rejected: list[str] = []
        reasons: list[str] = []
        seen: set[str] = set()
        for claim in claims:
            claim_reasons: list[str] = []
            if claim.claim_id in seen:
                claim_reasons.append("duplicate_claim_id")
            seen.add(claim.claim_id)
            if claim.run_id != run_id:
                claim_reasons.append("generation_run_id_mismatch")
            if not claim.evidence_ids or set(claim.evidence_ids) - evidence_ids:
                claim_reasons.append("illegal_citation")
            if not claim.evidence_span_ids or set(claim.evidence_span_ids) - set(span_owner):
                claim_reasons.append("missing_span")
            if any(span_owner.get(span_id) not in claim.evidence_ids for span_id in claim.evidence_span_ids):
                claim_reasons.append("span_evidence_mismatch")
            if self._external_reference.search(claim.text):
                claim_reasons.append("generated_external_reference")
            if claim_reasons:
                rejected.append(claim.claim_id)
                reasons.extend(
                    f"generation_rejected: {claim.claim_id}: {reason}"
                    for reason in claim_reasons
                )
            else:
                accepted.append(claim.claim_id)
        status = (
            GenerationConstraintStatus.REJECTED
            if rejected or not claims
            else GenerationConstraintStatus.ACCEPTED
        )
        if not claims:
            reasons.append("generation_rejected: no atomic claims generated")
        return GenerationConstraintResult(
            status=status,
            accepted_claim_ids=accepted,
            rejected_claim_ids=rejected,
            reasons=list(dict.fromkeys(reasons)),
        )
