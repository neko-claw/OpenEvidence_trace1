from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from a5.domain.enums import FreshnessState, RecommendedAction, SufficiencyStatus
from a5.domain.models import (
    EvidenceRecord,
    EvidenceSufficiencyMetrics,
    EvidenceSufficiencyResult,
)
from a5.runtime_config import Gate2Config


class EvidenceSufficiencyGate:
    """CRAG-style retrieval-quality evaluator and corrective-action gate."""

    def __init__(self, config: Gate2Config) -> None:
        self.config = config

    def evaluate(
        self,
        evidence: Sequence[EvidenceRecord],
        *,
        freshness_required: bool,
        budget_remaining: int,
    ) -> EvidenceSufficiencyResult:
        candidate_count = len(evidence)
        scores = [record.retrieval_score for record in evidence if record.retrieval_score is not None]
        top_score = max(scores) if scores else None
        source_types = {record.source_type for record in evidence}
        source_diversity = len(source_types) / candidate_count if candidate_count else None
        strongest_level = next(
            (
                level
                for level in self.config.accepted_evidence_levels
                if any(record.evidence_level == level for record in evidence)
            ),
            None,
        )
        conflict_pairs = {
            tuple(sorted((record.id, other_id)))
            for record in evidence
            for other_id in record.conflicts_with_ids
            if any(other.id == other_id for other in evidence)
        }
        freshness = self._freshness(evidence, freshness_required)
        metrics = EvidenceSufficiencyMetrics(
            candidate_count=candidate_count,
            top_score=top_score,
            source_type_count=len(source_types),
            source_diversity=source_diversity,
            strongest_evidence_level=strongest_level,
            freshness_state=freshness,
            conflict_count=len(conflict_pairs),
        )
        reasons: list[str] = []
        if candidate_count < self.config.min_candidates:
            reasons.append("retrieval_insufficient: candidate_count below threshold")
        if top_score is None:
            reasons.append("retrieval_insufficient: top_score UNKNOWN")
        elif top_score < self.config.min_top_score:
            reasons.append("retrieval_insufficient: top_score below threshold")
        if len(source_types) < self.config.min_source_types:
            reasons.append("retrieval_insufficient: source coverage below threshold")
        if source_diversity is None:
            reasons.append("retrieval_insufficient: source_diversity UNKNOWN")
        elif source_diversity < self.config.min_source_diversity:
            reasons.append("retrieval_insufficient: source diversity below threshold")
        if strongest_level is None:
            reasons.append("retrieval_insufficient: strongest_evidence_level UNKNOWN/unaccepted")
        if freshness_required and freshness is not FreshnessState.FRESH:
            reasons.append(f"retrieval_insufficient: freshness={freshness.value}")
        if len(conflict_pairs) > self.config.max_conflicts:
            reasons.append("retrieval_conflict: unresolved evidence conflict")

        if len(conflict_pairs) > self.config.max_conflicts:
            status = SufficiencyStatus.CONFLICTED
            action = RecommendedAction.REFUSE
        elif reasons:
            status = SufficiencyStatus.INSUFFICIENT
            action = RecommendedAction.RETRY if budget_remaining > 0 else RecommendedAction.REFUSE
            if budget_remaining == 0:
                reasons.append("budget_exhausted: evidence remained insufficient")
        else:
            status = SufficiencyStatus.SUFFICIENT
            action = RecommendedAction.CONTINUE
        return EvidenceSufficiencyResult(
            status=status,
            reasons=reasons,
            metrics=metrics,
            recommended_action=action,
        )

    def _freshness(
        self,
        evidence: Sequence[EvidenceRecord],
        required: bool,
    ) -> FreshnessState:
        if not required:
            return FreshnessState.NOT_REQUIRED
        if not evidence or any(record.published_at is None for record in evidence):
            return FreshnessState.UNKNOWN
        now = datetime.now(timezone.utc)
        fresh = sum(
            (now - record.published_at).days <= self.config.max_age_days
            for record in evidence
            if record.published_at is not None
        )
        return (
            FreshnessState.FRESH
            if fresh / len(evidence) >= self.config.min_fresh_fraction
            else FreshnessState.STALE
        )
