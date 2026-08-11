"""Adaptive K rules for the retrieval pipeline (4.3.4).

K adapts within fixed rules only; the rules themselves are frozen with the
config.  Decision signals (low score, single source, missing claim evidence)
are left to the service's warning layer.
"""

from __future__ import annotations

from .config import RetrievalConfig
from .models import Query


_DEFAULT_VERIFIED_RATIO = 0.65


def compute_verified_ratio(
    query: Query,
    config: RetrievalConfig,
) -> tuple[float, tuple[str, ...]]:
    """Return ``(verified_ratio, actions)`` for the Evidence Mixer (4.3 可信池).

    The ratio is driven by question type and freshness only, never by claim
    criticality: A5's Claim objects do not exist when retrieval runs.  Claim
    criticality instead gates Gate5's use of discovery evidence (A5 side).
    """
    if not isinstance(query, Query):
        raise ValueError("query must be a Query")
    if not isinstance(config, RetrievalConfig):
        raise ValueError("config must be a RetrievalConfig")

    actions: list[str] = []
    base = dict(config.verified_ratio_base)
    ratio = base.get(query.question_type, _DEFAULT_VERIFIED_RATIO)
    actions.append(f"verified_ratio_base_{query.question_type}={ratio:.2f}")

    if query.freshness in {"current", "latest"}:
        ratio += config.verified_ratio_freshness_bump
        actions.append(f"verified_ratio_freshness_{query.freshness}_bump")

    capped = min(ratio, config.verified_ratio_max)
    if capped != ratio:
        actions.append(f"verified_ratio_capped={capped:.2f}")
    return capped, tuple(actions)


def adapt_k(query: Query, config: RetrievalConfig) -> tuple[int, int, tuple[str, ...]]:
    """Return (k1, k2, actions) adjusted by deterministic question rules."""
    if not isinstance(query, Query):
        raise ValueError("query must be a Query")
    if not isinstance(config, RetrievalConfig):
        raise ValueError("config must be a RetrievalConfig")

    actions: list[str] = []

    # Rule 1: precise entity / guideline-number questions need a smaller K.
    if query.question_type == "guideline":
        actions.append("small_k_for_guideline")
        return 10, 3, tuple(actions)

    # Rule 2: broad or multi-PICO questions recall per claim and merge, so
    # the fused pool needs a larger rerank input.
    filled_pico = sum(
        1
        for values in (
            query.pico_population,
            query.pico_intervention,
            query.pico_comparator,
            query.pico_outcome,
        )
        if values
    )
    if query.question_type == "therapy" and filled_pico >= 3:
        actions.append("large_k_for_multi_pico")
        return 30, 8, tuple(actions)

    # Rule 3: latest-research questions raise source weights and tighten the
    # window; a smaller context keeps stale papers out without expanding K.
    if query.question_type == "latest_trial" and query.freshness in {"current", "latest"}:
        actions.append("small_k_for_latest")
        return 20, 5, tuple(actions)

    return config.rerank_top_k, config.selection_top_k, tuple(actions)
