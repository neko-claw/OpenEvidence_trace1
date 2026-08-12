from __future__ import annotations

import re
from collections.abc import Sequence

from a5.domain.enums import ClaimCriticality, Decision, VerificationStatus
from a5.domain.models import (
    CitationAuditOutput,
    CitationAuditReport,
    Claim,
    EvidenceRecord,
    VerificationContext,
)
from a5.ports.claim_verifier import ClaimVerifier
from a5.runtime_config import RuntimeConfig, load_runtime_config
from a5.skills.loader import LoadedSkill, SkillLoader


class ClaimSplitter:
    """Conservative deterministic atomic-claim splitter.

    It splits explicit sentence/conjunction boundaries only. Production semantic
    decomposition may be supplied through a future structured LLM adapter.
    """

    _boundary = re.compile(r"(?:[.;。；]\s*|\s+(?:and|but)\s+|\s*(?:并且|但是|且)\s*)", re.I)

    def split(self, claims: Sequence[Claim]) -> list[Claim]:
        atomic: list[Claim] = []
        used_ids: set[str] = set()
        for claim in claims:
            parts = [part.strip(" -") for part in self._boundary.split(claim.text) if part.strip(" -")]
            if not parts:
                continue
            for index, text in enumerate(parts, start=1):
                claim_id = claim.claim_id if len(parts) == 1 else f"{claim.claim_id}.{index}"
                if claim_id in used_ids:
                    raise ValueError(f"duplicate atomic claim ID: {claim_id}")
                used_ids.add(claim_id)
                atomic.append(claim.model_copy(update={"claim_id": claim_id, "text": text}))
        return atomic


class CitationAuditSkill:
    name = "citation_audit"

    def __init__(
        self,
        verifier: ClaimVerifier,
        runtime_config: RuntimeConfig | None = None,
        loader: SkillLoader | None = None,
        splitter: ClaimSplitter | None = None,
    ) -> None:
        self._verifier = verifier
        self._splitter = splitter or ClaimSplitter()
        self.runtime_config = runtime_config or load_runtime_config()
        selection = self.runtime_config.skills.citation_audit
        self.asset: LoadedSkill = (loader or SkillLoader()).load(
            selection.manifest, expected_version=selection.version
        )

    @property
    def version(self) -> str:
        return self.asset.manifest.version

    @property
    def prompt_version(self) -> str:
        return self.asset.manifest.prompt_version

    @property
    def identifier(self) -> str:
        return f"{self.name}@{self.version}"

    def split_claims(self, claims: Sequence[Claim]) -> list[Claim]:
        return self._splitter.split(claims)

    def audit(
        self,
        claims: Sequence[Claim],
        evidence: Sequence[EvidenceRecord],
        context: VerificationContext | None = None,
        *,
        split: bool = False,
    ) -> CitationAuditReport:
        atomic = self.split_claims(claims) if split else list(claims)
        if not evidence:
            return CitationAuditReport(
                decision=Decision.REFUSE,
                rejected_claim_ids=[claim.claim_id for claim in atomic],
                reasons=["retrieval_insufficient: no valid evidence was retrieved"],
            )
        if not atomic:
            return CitationAuditReport(
                decision=Decision.REFUSE,
                reasons=["unsupported_claim: no verifiable atomic claims were generated"],
            )
        verification_context = context or VerificationContext()
        results = [
            self._verifier.verify(claim, evidence, verification_context)
            for claim in atomic
        ]
        claims_by_id = {claim.claim_id: claim for claim in atomic}
        illegal = any(result.illegal_evidence_ids for result in results)
        critical_failures = [
            result
            for result in results
            if claims_by_id[result.claim_id].criticality is ClaimCriticality.CRITICAL
            and result.status is not VerificationStatus.SUPPORTED
        ]
        if illegal or critical_failures:
            recommendation = Decision.REFUSE
        elif any(result.status is not VerificationStatus.SUPPORTED for result in results):
            recommendation = Decision.WARN
        else:
            recommendation = Decision.PASS
        approved = [
            result.claim_id
            for result in results
            if result.status is VerificationStatus.SUPPORTED
            and not result.illegal_evidence_ids
        ]
        rejected = [claim.claim_id for claim in atomic if claim.claim_id not in approved]
        reasons = [
            reason
            for result in results
            if result.status is not VerificationStatus.SUPPORTED
            for reason in result.reasons
        ]
        return CitationAuditReport(
            decision=recommendation,
            verification_results=results,
            approved_claim_ids=approved,
            rejected_claim_ids=rejected,
            reasons=list(dict.fromkeys(reasons)),
        )

    def execute(
        self,
        claims: Sequence[Claim],
        evidence: Sequence[EvidenceRecord],
        context: VerificationContext | None = None,
    ) -> CitationAuditOutput:
        atomic = self.split_claims(claims)
        return CitationAuditOutput(
            atomic_claims=atomic,
            report=self.audit(atomic, evidence, context),
        )
