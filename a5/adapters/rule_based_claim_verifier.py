from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from a5.domain.enums import ClaimCriticality, MatchStatus, VerificationStatus
from a5.domain.trust import TrustTier, trust_tier_of
from a5.domain.models import (
    Claim,
    EvidenceRecord,
    TextualSupportAssessment,
    VerificationContext,
    VerificationResult,
)
from a5.ports.textual_support import TextualSupportEvaluator
from a5.runtime_config import Gate5Config, load_runtime_config


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[\w]+", text.casefold()))


class ExactSpanTextualSupportEvaluator:
    """Deterministic P0 support check; not medical semantic inference."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or load_runtime_config().models.textual_support_evaluator

    def evaluate(
        self,
        claim: Claim,
        evidence: Sequence[EvidenceRecord],
    ) -> TextualSupportAssessment:
        allowed_span_ids = set(claim.evidence_span_ids)
        texts = [
            span.text
            for record in evidence
            for span in record.spans
            if span.span_id in allowed_span_ids
        ]
        normalized_claim = _normalize(claim.text)
        for text in texts:
            normalized_text = _normalize(text)
            if normalized_claim and normalized_claim in normalized_text:
                return TextualSupportAssessment(
                    status=VerificationStatus.SUPPORTED,
                    entailment_score=1.0,
                    method=self.name,
                    reason="textual_support: exact normalized claim text found in cited span",
                )
            claim_tokens = normalized_claim.split()
            text_tokens = normalized_text.split()
            text_without_not = " ".join(token for token in text_tokens if token != "not")
            claim_without_not = " ".join(token for token in claim_tokens if token != "not")
            if (
                "not" in text_tokens and text_without_not == normalized_claim
            ) or (
                "not" in claim_tokens and claim_without_not == normalized_text
            ):
                return TextualSupportAssessment(
                    status=VerificationStatus.CONTRADICTED,
                    entailment_score=0.0,
                    method=self.name,
                    reason="contradicted_claim: deterministic negation found in cited span",
                )
        return TextualSupportAssessment(
            status=VerificationStatus.INSUFFICIENT,
            entailment_score=None,
            method=self.name,
            reason="unsupported_claim: exact span support unavailable; semantic evaluator required",
        )


class RuleBasedClaimVerifier:
    """Gate5 P0 checks with an injectable textual-support extension point.

    The verifier never reads fixture support/contradiction labels. Unknown
    span/PICO/time/entailment data remains UNKNOWN and cannot become SUPPORTED.
    Discovery-tier evidence cannot independently support a CRITICAL claim.
    """

    def __init__(
        self,
        config: Gate5Config | None = None,
        textual_support: TextualSupportEvaluator | None = None,
        *,
        name: str | None = None,
        textual_support_name: str | None = None,
    ) -> None:
        runtime = load_runtime_config()
        self.config = config or runtime.gates.gate5
        self.name = name or runtime.models.claim_verifier
        self._textual_support = textual_support or ExactSpanTextualSupportEvaluator(
            textual_support_name or runtime.models.textual_support_evaluator
        )

    def verify(
        self,
        claim: Claim,
        evidence: Sequence[EvidenceRecord],
        context: VerificationContext,
    ) -> VerificationResult:
        evidence_by_id = {record.id: record for record in evidence}
        illegal_evidence = sorted(set(claim.evidence_ids) - set(evidence_by_id))
        cited = [evidence_by_id[evidence_id] for evidence_id in claim.evidence_ids if evidence_id in evidence_by_id]
        citation_valid = bool(claim.evidence_ids) and not illegal_evidence
        reasons: list[str] = []
        if not claim.evidence_ids:
            reasons.append("illegal_citation: claim has no Evidence ID")
        if illegal_evidence:
            reasons.append("illegal_citation: Evidence ID outside this run's whitelist")

        cited_spans = {span.span_id for record in cited for span in record.spans}
        illegal_spans = sorted(set(claim.evidence_span_ids) - cited_spans)
        if not claim.evidence_span_ids:
            span_check = MatchStatus.UNKNOWN
            reasons.append("missing_span: no supporting Evidence span ID")
        elif illegal_spans:
            span_check = MatchStatus.MISMATCH
            reasons.append("missing_span: span is absent from the cited Evidence")
        else:
            span_check = MatchStatus.MATCH

        matches = {
            field: self._match_metadata(getattr(claim, field), cited, field)
            for field in ("population", "intervention", "comparator", "outcome")
        }
        for field, match in matches.items():
            if getattr(claim, field) is not None and match is not MatchStatus.MATCH:
                reasons.append(f"pico_mismatch: {field}={match.value}")

        time_match = self._time_match(cited, context, claim.as_of_date)
        if (context.freshness_required or claim.as_of_date is not None) and time_match is not MatchStatus.MATCH:
            reasons.append(f"time_mismatch: time={time_match.value}")

        cited_ids = {record.id for record in cited}
        conflicts = sorted(
            {
                other_id
                for record in cited
                for other_id in record.conflicts_with_ids
                if other_id in cited_ids
            }
            | set(claim.conflict_ids)
        )
        if conflicts:
            reasons.append("contradicted_claim: unresolved cited-evidence conflict")

        textual = self._textual_support.evaluate(claim, cited)
        reasons.append(textual.reason)

        non_verified = [
            record.id
            for record in cited
            if trust_tier_of(record.source_metadata) is not TrustTier.VERIFIED
        ]
        trust_blocked = (
            self.config.require_verified_for_critical
            and claim.criticality is ClaimCriticality.CRITICAL
            and bool(non_verified)
        )
        if trust_blocked:
            reasons.append(
                "unverified_critical: CRITICAL claim cites non-verified evidence: "
                + ", ".join(sorted(non_verified))
            )
        pico_blocked = self.config.require_pico_when_claim_specified and any(
            getattr(claim, field) is not None and match is not MatchStatus.MATCH
            for field, match in matches.items()
        )
        span_blocked = self.config.require_span and span_check is not MatchStatus.MATCH
        time_blocked = (
            self.config.require_time_when_fresh
            and (context.freshness_required or claim.as_of_date is not None)
            and time_match is not MatchStatus.MATCH
        )
        entailment_blocked = (
            textual.entailment_score is None
            or textual.entailment_score < self.config.supported_entailment_threshold
        )
        if conflicts or textual.status is VerificationStatus.CONTRADICTED:
            status = VerificationStatus.CONTRADICTED
        elif (
            not citation_valid
            or span_blocked
            or pico_blocked
            or time_blocked
            or entailment_blocked
            or trust_blocked
            or textual.status is not VerificationStatus.SUPPORTED
        ):
            status = VerificationStatus.INSUFFICIENT
        else:
            status = VerificationStatus.SUPPORTED
        return VerificationResult(
            claim_id=claim.claim_id,
            status=status,
            evidence_ids=list(claim.evidence_ids),
            evidence_span_ids=list(claim.evidence_span_ids),
            checked_evidence_ids=[record.id for record in cited],
            illegal_evidence_ids=illegal_evidence,
            illegal_span_ids=illegal_spans,
            citation_valid=citation_valid,
            span_check=span_check,
            population_match=matches["population"],
            intervention_match=matches["intervention"],
            comparator_match=matches["comparator"],
            outcome_match=matches["outcome"],
            time_match=time_match,
            entailment_score=textual.entailment_score,
            conflict_ids=conflicts,
            uncertainty=claim.uncertainty,
            verification_method=textual.method,
            reasons=list(dict.fromkeys(reasons)),
        )

    @staticmethod
    def _match_metadata(
        expected: str | None,
        evidence: Sequence[EvidenceRecord],
        field: str,
    ) -> MatchStatus:
        if expected is None:
            return MatchStatus.UNKNOWN
        values: list[Any] = [getattr(record, field) for record in evidence]
        normalized_expected = _normalize(expected)
        if any(value is not None and _normalize(str(value)) == normalized_expected for value in values):
            return MatchStatus.MATCH
        if any(value is None for value in values) or not values:
            return MatchStatus.UNKNOWN
        return MatchStatus.MISMATCH

    @staticmethod
    def _time_match(
        evidence: Sequence[EvidenceRecord],
        context: VerificationContext,
        claim_as_of_date: Any,
    ) -> MatchStatus:
        if not context.freshness_required and claim_as_of_date is None:
            return MatchStatus.UNKNOWN
        if not evidence or any(record.published_at is None for record in evidence):
            return MatchStatus.UNKNOWN
        cutoff = claim_as_of_date or context.run_date
        if any(record.published_at.date() > cutoff for record in evidence if record.published_at):
            return MatchStatus.MISMATCH
        return MatchStatus.MATCH
