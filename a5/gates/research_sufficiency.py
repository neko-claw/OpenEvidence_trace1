from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import date

from a5.domain.enums import FreshnessState, RecommendedAction, SufficiencyStatus
from a5.domain.models import (
    EvidenceRecord,
    EvidenceSufficiencyMetrics,
    EvidenceSufficiencyResult,
)
from backend.research_profile import ResearchRetrievalConfig


class ResearchEvidenceSufficiencyGate:
    """CRAG-style routing for public evidence research.

    This profile consumes auditable query-local ranking and source coverage.
    It never relabels those values as calibrated clinical probabilities. The
    strict production/live Gate2 remains ``EvidenceSufficiencyGate``.
    """

    def __init__(self, config: ResearchRetrievalConfig) -> None:
        self.config = config

    def evaluate(
        self,
        evidence: Sequence[EvidenceRecord],
        *,
        freshness_required: bool,
        budget_remaining: int,
        as_of_date: date,
        expected_evidence_types: Sequence[str] = (),
    ) -> EvidenceSufficiencyResult:
        ranking_scores = [
            float(score)
            for item in evidence
            if isinstance((score := item.source_metadata.get("ranking_score")), (int, float))
            and not isinstance(score, bool)
            and 0.0 <= float(score) <= 1.0
        ]
        source_counts = Counter(item.source_type for item in evidence)
        sources = set(source_counts)
        # Gini-Simpson diversity: 0 means a single-source result set, while a
        # more balanced multi-source set approaches 1. Unlike
        # ``source_count / candidate_count``, this metric does not penalise a
        # retriever merely for returning more documents.
        diversity = (
            1.0
            - sum((count / len(evidence)) ** 2 for count in source_counts.values())
            if evidence
            else None
        )
        strongest = next(
            (
                level
                for level in self.config.accepted_evidence_levels
                if any(item.evidence_level == level for item in evidence)
            ),
            None,
        )
        freshness = self._freshness(evidence, freshness_required, as_of_date)
        conflict_pairs = {
            tuple(sorted((item.id, other_id)))
            for item in evidence
            for other_id in item.conflicts_with_ids
            if any(other.id == other_id for other in evidence)
        }
        top_ranking = max(ranking_scores) if ranking_scores else None
        metrics = EvidenceSufficiencyMetrics(
            candidate_count=len(evidence),
            top_score=None,
            top_ranking_score=top_ranking,
            usable_quality_score_count=0,
            source_type_count=len(sources),
            source_diversity=diversity,
            strongest_evidence_level=strongest,
            freshness_state=freshness,
            conflict_count=len(conflict_pairs),
        )
        reasons: list[str] = []
        if len(evidence) < self.config.min_candidates:
            reasons.append("retrieval_insufficient: candidate_count below research threshold")
        if top_ranking is None:
            reasons.append("retrieval_insufficient: query-local ranking score UNKNOWN")
        elif top_ranking < self.config.min_top_ranking_score:
            reasons.append("retrieval_insufficient: query-local ranking below research threshold")
        if len(sources) < self.config.min_source_types:
            reasons.append("retrieval_insufficient: source coverage below research threshold")
        if diversity is None or diversity < self.config.min_source_diversity:
            reasons.append("retrieval_insufficient: source diversity below research threshold")
        if strongest is None:
            reasons.append("retrieval_insufficient: accepted evidence type unavailable")
        if expected_evidence_types and not any(
            item.evidence_level in expected_evidence_types for item in evidence
        ):
            reasons.append(
                "retrieval_insufficient: required evidence type unavailable "
                f"({', '.join(expected_evidence_types)})"
            )
        if freshness_required and freshness is not FreshnessState.FRESH:
            reasons.append(f"retrieval_insufficient: freshness={freshness.value}")
        if len(conflict_pairs) > self.config.max_conflicts:
            reasons.append("retrieval_conflict: unresolved evidence conflict")
        if len(conflict_pairs) > self.config.max_conflicts:
            status, action = SufficiencyStatus.CONFLICTED, RecommendedAction.REFUSE
        elif reasons:
            status = SufficiencyStatus.INSUFFICIENT
            action = RecommendedAction.RETRY if budget_remaining else RecommendedAction.REFUSE
            if not budget_remaining:
                reasons.append("budget_exhausted: evidence remained insufficient")
        else:
            status, action = SufficiencyStatus.SUFFICIENT, RecommendedAction.CONTINUE
        return EvidenceSufficiencyResult(
            status=status,
            reasons=reasons,
            metrics=metrics,
            recommended_action=action,
        )


    def _freshness(
        self, evidence: Sequence[EvidenceRecord], required: bool, as_of_date: date
    ) -> FreshnessState:
        if not required:
            return FreshnessState.NOT_REQUIRED
        dated = [item.published_at for item in evidence if item.published_at is not None]
        if not evidence or not dated:
            return FreshnessState.UNKNOWN
        # Issue dates can legitimately be ahead of an electronic publication
        # date. Future-dated records are therefore excluded from freshness
        # credit instead of making the entire result set stale.
        eligible = [item.date() for item in dated if item.date() <= as_of_date]
        if not eligible:
            return FreshnessState.UNKNOWN
        fresh = sum(
            (as_of_date - item).days <= self.config.max_age_days for item in eligible
        )
        return (
            FreshnessState.FRESH
            if fresh / len(evidence) >= self.config.min_fresh_fraction
            else FreshnessState.STALE
        )
