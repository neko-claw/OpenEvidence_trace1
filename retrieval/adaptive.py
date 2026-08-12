"""Adaptive K rules for the retrieval pipeline (4.3.4).

K adapts within fixed rules only; the rules themselves are frozen with the
config.  Decision signals (low score, single source, missing claim evidence)
are left to the service's warning layer.
"""

from __future__ import annotations

from .config import RetrievalConfig
from .models import Query


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
    # round2 P2 差异记录：规划 §4.3.4 的意图是“按原子主张分路召回后适当增大
    # K0”；P0 的融合池受 fusion_top_k 硬上限约束，此处增大的是 K1（rerank
    # 输入）而非 K0。P1 按 atomic_claims 分路召回后再改为增大 K0。
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
