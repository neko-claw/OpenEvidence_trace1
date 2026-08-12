from __future__ import annotations

from collections.abc import Sequence

from a5.domain.enums import EvidenceIntegrityStatus
from a5.domain.models import (
    EvidenceIntegrityItem,
    EvidenceIntegrityResult,
    EvidenceRecord,
)
from a5.runtime_config import Gate1Config


class EvidenceIntegrityGate:
    """Deterministic Gate1 over adapter-supplied provenance facts.

    This gate does not call or imitate an upstream registry. It accepts only an
    explicit adapter integrity marker plus the configured provenance fields.
    Mock evidence is eligible only in an explicitly constructed fixture gate.
    """

    def __init__(self, config: Gate1Config, *, allow_mock: bool = False) -> None:
        self.config = config
        self.allow_mock = allow_mock

    def evaluate(self, evidence: Sequence[EvidenceRecord]) -> EvidenceIntegrityResult:
        items = [self._evaluate_one(record) for record in evidence]
        eligible = [item.evidence_id for item in items if item.status is EvidenceIntegrityStatus.ELIGIBLE]
        rejected = [item.evidence_id for item in items if item.status is EvidenceIntegrityStatus.REJECTED]
        unknown = [item.evidence_id for item in items if item.status is EvidenceIntegrityStatus.UNKNOWN]
        if rejected:
            status = EvidenceIntegrityStatus.REJECTED
        elif eligible:
            status = EvidenceIntegrityStatus.ELIGIBLE
        else:
            status = EvidenceIntegrityStatus.UNKNOWN
        return EvidenceIntegrityResult(
            status=status,
            eligible_evidence_ids=eligible,
            rejected_evidence_ids=rejected,
            unknown_evidence_ids=unknown,
            items=items,
            reasons=list(dict.fromkeys(reason for item in items for reason in item.reason_codes)),
        )

    def _evaluate_one(self, record: EvidenceRecord) -> EvidenceIntegrityItem:
        if record.mock:
            return EvidenceIntegrityItem(
                evidence_id=record.id,
                status=(EvidenceIntegrityStatus.ELIGIBLE if self.allow_mock else EvidenceIntegrityStatus.REJECTED),
                reason_codes=["mock_fixture_allowed" if self.allow_mock else "mock_evidence_not_allowed"],
            )
        integrity = str(record.source_metadata.get("source_integrity", "")).strip()
        missing = [
            field
            for field in self.config.required_source_metadata
            if not record.source_metadata.get(field)
        ]
        if record.source_metadata.get("tombstone") is True:
            return EvidenceIntegrityItem(
                evidence_id=record.id,
                status=EvidenceIntegrityStatus.REJECTED,
                reason_codes=["tombstoned_evidence"],
            )
        if record.source_metadata.get("provenance_mismatch"):
            return EvidenceIntegrityItem(
                evidence_id=record.id,
                status=EvidenceIntegrityStatus.REJECTED,
                reason_codes=["evidence_provenance_mismatch"],
            )
        reasons: list[str] = []
        if missing:
            reasons.append("missing_provenance:" + ",".join(missing))
        if integrity not in self.config.accepted_integrity_markers:
            reasons.append("source_integrity_unknown")
        return EvidenceIntegrityItem(
            evidence_id=record.id,
            status=(EvidenceIntegrityStatus.UNKNOWN if reasons else EvidenceIntegrityStatus.ELIGIBLE),
            reason_codes=reasons or ["source_provenance_eligible"],
        )
