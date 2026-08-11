"""End-to-end, failure-aware orchestration for the A4 retrieval pipeline."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import date
from math import isfinite
from numbers import Real
from time import perf_counter
from typing import Protocol

from .bm25 import BM25Index
from .config import FeatureWeights, RetrievalConfig
from .fusion import fuse_rrf
from .models import MAX_RRF_OPERAND, EvidenceChunk, Query, RankLog, ScoredChunk, SearchResult, SearchStatus
from .adaptive import adapt_k, compute_verified_ratio
from .evidence_mixer import mix_evidence
from .rerank import FeatureReranker, select_mmr
from .support_check import ClaimSupport, check_claims, detect_conflicts
from .vector import VectorSearch


class _LexicalSearch(Protocol):
    def search(self, query: str, k: int) -> list[ScoredChunk]: ...


QueryVectorProvider = Callable[[Query], Sequence[float]]
_LOW_TOP_RERANK_SCORE = 0.35
_STAGES = ("bm25", "vector", "fusion", "mix", "rerank", "mmr", "total")


class RetrievalService:
    """Run lexical retrieval, semantic retrieval, fusion, reranking, and MMR.

    The service captures immutable config/version values at construction, never
    asks the system clock for relevance decisions, and returns an explicit
    degraded terminal state whenever either candidate channel is unavailable.
    """

    def __init__(
        self,
        bm25_index: BM25Index | _LexicalSearch,
        vector_search: VectorSearch | None,
        query_vector_provider: QueryVectorProvider | None,
        config: RetrievalConfig,
    ) -> None:
        if not callable(getattr(bm25_index, "search", None)):
            raise ValueError("bm25_index must provide a callable search method")
        if vector_search is not None and not callable(getattr(vector_search, "search", None)):
            raise ValueError("vector_search must provide a callable search method")
        if query_vector_provider is not None and not callable(query_vector_provider):
            raise ValueError("query_vector_provider must be callable or None")
        if not isinstance(config, RetrievalConfig):
            raise ValueError("config must be a RetrievalConfig")
        config.__post_init__()

        self._bm25_index = bm25_index
        self._vector_search = vector_search
        self._query_vector_provider = query_vector_provider
        self._config = _snapshot_config(config)
        self._reranker = FeatureReranker(self._config)

    def search(self, query: Query) -> SearchResult:
        """Retrieve evidence with controlled degradation rather than fallback silence."""
        # This validates even a request that later experiences two channel failures.
        self._reranker.rank(query, ())
        if query.out_of_scope:
            # Scope gating (dosing / prescription / diagnosis / emergency) belongs
            # to A1/A5; A4 must not silently cross the boundary and return
            # evidence that could be read as advice.  Hand off explicitly.
            return self._result(
                query,
                SearchStatus.EMPTY,
                (),
                (),
                ["out_of_scope"],
                {stage: 0 for stage in _STAGES},
            )
        started = perf_counter()
        timings = {stage: 0 for stage in _STAGES}
        reasons: list[str] = []

        bm25, bm25_operational = self._search_bm25(query, timings, reasons)
        vector, vector_operational = self._search_vector(query, timings, reasons)

        if not bm25_operational and not vector_operational:
            timings["total"] = _elapsed_ms(started)
            return self._result(query, SearchStatus.FAILED, (), (), reasons, timings)

        if not bm25 and not vector:
            timings["total"] = _elapsed_ms(started)
            status = SearchStatus.EMPTY if bm25_operational and vector_operational and not reasons else SearchStatus.PARTIAL
            return self._result(query, status, (), (), reasons, timings)

        try:
            stage_started = perf_counter()
            candidates = fuse_rrf(
                bm25=bm25,
                vector=vector,
                rrf_k=self._config.rrf_k,
                candidate_limit=self._config.fusion_top_k,
            )
            timings["fusion"] = _elapsed_ms(stage_started)

            stage_started = perf_counter()
            verified_ratio, ratio_actions = compute_verified_ratio(query, self._config)
            mixed_candidates, mix_log = mix_evidence(
                candidates,
                verified_ratio,
                self._config.fusion_top_k,
            )
            timings["mix"] = _elapsed_ms(stage_started)

            k1, k2, adaptive_actions = adapt_k(query, self._config)
            # The context budget is a hard cap: adaptive rules may shrink K,
            # but never grow it beyond the frozen selection budget.
            k2 = min(k2, self._config.selection_top_k)

            stage_started = perf_counter()
            reranked = self._reranker.rank_all(query, mixed_candidates)
            timings["rerank"] = _elapsed_ms(stage_started)

            stage_started = perf_counter()
            selected = select_mmr(reranked[:k1], self._config, k2)
            timings["mmr"] = _elapsed_ms(stage_started)
        except Exception as error:
            reasons.append(_failure_reason("pipeline", error))
            timings["total"] = _elapsed_ms(started)
            return self._result(query, SearchStatus.FAILED, (), (), reasons, timings)

        if not reranked or not selected:
            reasons.append("pipeline produced candidates but no selectable audit rows")
            timings["total"] = _elapsed_ms(started)
            return self._result(query, SearchStatus.FAILED, (), (), reasons, timings)

        full_log = _merge_selection_logs(reranked, selected)
        selected_chunks = tuple(log.candidate.chunk for log in selected)
        claim_support = (
            check_claims(query, query.atomic_claims, selected_chunks) if query.atomic_claims else ()
        )
        conflicts = detect_conflicts(selected_chunks)
        status = SearchStatus.OK if bm25_operational and vector_operational and not reasons else SearchStatus.PARTIAL
        timings["total"] = _elapsed_ms(started)
        return self._result(
            query,
            status,
            selected_chunks,
            full_log,
            reasons,
            timings,
            claim_support=claim_support,
            conflicts=conflicts,
            notes=(*adaptive_actions, mix_log.summary),
        )

    def _search_bm25(
        self, query: Query, timings: dict[str, int], reasons: list[str]
    ) -> tuple[list[ScoredChunk], bool]:
        started = perf_counter()
        try:
            raw = self._bm25_index.search(_bm25_query_text(query), self._config.bm25_top_k)
            candidates, excluded = _intake_candidates(raw, "bm25", self._config, query)
            if excluded:
                reasons.append(f"bm25 channel excluded {excluded} invalid or stale candidate(s)")
            return candidates, True
        except Exception as error:
            reasons.append(_failure_reason("bm25", error))
            return [], False
        finally:
            timings["bm25"] = _elapsed_ms(started)

    def _search_vector(
        self, query: Query, timings: dict[str, int], reasons: list[str]
    ) -> tuple[list[ScoredChunk], bool]:
        started = perf_counter()
        try:
            if self._vector_search is None:
                reasons.append("vector_unavailable")
                return [], False
            if self._query_vector_provider is None:
                reasons.append("vector_unavailable")
                return [], False
            query_vector = self._query_vector_provider(query)
            raw = self._vector_search.search(query_vector, self._config.vector_top_k)
            candidates, excluded = _intake_candidates(raw, "vector", self._config, query)
            if excluded:
                reasons.append(f"vector channel excluded {excluded} invalid or stale candidate(s)")
            return candidates, True
        except Exception as error:
            reasons.append(_failure_reason("vector", error))
            return [], False
        finally:
            timings["vector"] = _elapsed_ms(started)

    def _result(
        self,
        query: Query,
        status: SearchStatus,
        selected_chunks: tuple[EvidenceChunk, ...],
        rank_log: tuple[RankLog, ...],
        reasons: list[str],
        timings: Mapping[str, int],
        *,
        claim_support: tuple[ClaimSupport, ...] = (),
        conflicts: tuple[tuple[str, str, str], ...] = (),
        notes: Sequence[str] = (),
    ) -> SearchResult:
        return SearchResult(
            query_id=query.query_id,
            index_version=self._config.index_version,
            corpus_version=self._config.corpus_version,
            rerank_config_version=self._config.rerank_config_version,
            status=status,
            selected_chunks=selected_chunks,
            rank_log=rank_log,
            degradation_reasons=tuple(reasons),
            latency_ms=timings["total"],
            stage_latency_ms=timings,
            retrieval_warning=_warning(status, selected_chunks, rank_log, reasons, claim_support, conflicts, notes),
            claim_support=claim_support,
            conflicts=conflicts,
        )


def _intake_candidates(
    raw: object, expected_stage: str, config: RetrievalConfig, query: Query
) -> tuple[list[ScoredChunk], int]:
    """Keep only immutable, live candidates tied to this fixed index release.

    Returns ``(candidates, excluded)`` where ``excluded`` counts candidates
    that are invalid or stale (tombstoned, malformed, version mismatch, or
    duplicate).  Candidates that fail the *intended per-query metadata filters*
    (domain / source type / evidence level / latest window) are skipped
    silently: that is normal query behavior, not a degradation, and must not
    inflate the degradation reasons.
    """
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError(f"{expected_stage} channel returned a non-sequence candidate collection")
    candidates: list[ScoredChunk] = []
    excluded = 0
    seen: set[str] = set()
    for item in raw:
        if not _is_valid_scored_chunk(item, expected_stage, config):
            excluded += 1
            continue
        chunk = item.chunk
        if chunk.chunk_id in seen:
            excluded += 1
            continue
        if not _passes_latest_filter(chunk, query, config) or not _passes_metadata_filters(chunk, query):
            continue  # intended per-query metadata filtering, not degradation
        seen.add(chunk.chunk_id)
        candidates.append(item)
    return candidates, excluded


def _is_valid_scored_chunk(item: object, expected_stage: str, config: RetrievalConfig) -> bool:
    """Contract/version validity only; per-query metadata filters are separate."""
    if not isinstance(item, ScoredChunk) or item.stage != expected_stage:
        return False
    if (
        not isinstance(item.rank, int)
        or isinstance(item.rank, bool)
        or item.rank < 1
        or item.rank > MAX_RRF_OPERAND
        or not _finite(item.score)
        or item.score < 0
    ):
        return False
    chunk = item.chunk
    if not isinstance(chunk, EvidenceChunk) or chunk.is_tombstoned is not False:
        return False
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            chunk.chunk_id,
            chunk.evidence_id,
            chunk.stable_id,
            chunk.text,
            chunk.index_version,
            chunk.corpus_version,
        )
    ):
        return False
    if not all(isinstance(value, str) for value in (chunk.title, chunk.source_type, chunk.url, chunk.evidence_level, chunk.topic)):
        return False
    if not chunk.source_type.strip() or (chunk.published_at is not None and not isinstance(chunk.published_at, str)):
        return False
    if any(not _valid_terms(getattr(chunk, field_name)) for field_name in (
        "pico_population", "pico_intervention", "pico_comparator", "pico_outcome"
    )):
        return False
    if not isinstance(chunk.content_vector, tuple) or any(not _finite(value) for value in chunk.content_vector):
        return False
    return chunk.index_version == config.index_version and chunk.corpus_version == config.corpus_version


def _is_live_scored_chunk(item: object, expected_stage: str, config: RetrievalConfig, query: Query) -> bool:
    """Backward-compatible full check: validity plus per-query metadata filters."""
    if not _is_valid_scored_chunk(item, expected_stage, config):
        return False
    chunk = item.chunk
    return _passes_latest_filter(chunk, query, config) and _passes_metadata_filters(chunk, query)


def _passes_metadata_filters(chunk: EvidenceChunk, query: Query) -> bool:
    """Fail-closed metadata filtering: topic, source types, evidence levels.

    A non-generic domain must match the chunk topic; chunks without a topic are
    excluded rather than guessed.  Empty filter sets mean "no constraint".
    """
    if query.domain != "generic":
        if not chunk.topic.strip() or chunk.topic.strip().casefold() != query.domain.casefold():
            return False
    if query.source_types:
        allowed = {value.casefold() for value in query.source_types}
        if chunk.source_type.casefold() not in allowed:
            return False
    if query.evidence_levels:
        allowed = {value.casefold() for value in query.evidence_levels}
        if chunk.evidence_level.casefold() not in allowed:
            return False
    return True


def _passes_latest_filter(chunk: EvidenceChunk, query: Query, config: RetrievalConfig) -> bool:
    """Fail closed for explicitly latest requests before RRF fusion.

    Only ``freshness == "latest"`` (最新试验) hard-excludes undated or stale
    records, per 6.1 "对于最新问题增加发表日期下限".  ``current`` (当前推荐,
    e.g. guideline questions) keeps undated chunks eligible so a missing
    ``published_at`` cannot blank out an entire guideline corpus; recency is
    then expressed by the freshness feature, whose weight is redistributed
    when the date is unavailable.  See the A3 index-data convention note in
    the README.
    """
    if query.freshness != "latest":
        return True
    if not isinstance(chunk.published_at, str):
        return False
    try:
        published = date.fromisoformat(chunk.published_at)
    except ValueError:
        return False
    if published.isoformat() != chunk.published_at:
        return False
    return (query.as_of_date - published).days <= config.latest_window_days


def _finite(value: object) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _valid_terms(value: object) -> bool:
    return isinstance(value, tuple) and all(isinstance(term, str) and term.strip() for term in value)


def _merge_selection_logs(reranked: Sequence[RankLog], selected: Sequence[RankLog]) -> tuple[RankLog, ...]:
    selected_by_id = {log.candidate.chunk.chunk_id: (position, log) for position, log in enumerate(selected, start=1)}
    selected_rows: dict[str, RankLog] = {}
    unselected_rows: list[RankLog] = []
    for log in reranked:
        selection = selected_by_id.get(log.candidate.chunk.chunk_id)
        if selection is None:
            unselected_rows.append(log)
            continue
        selection_rank, selected_log = selection
        features = dict(selected_log.candidate.feature_scores)
        features["mmr_selection_rank"] = float(selection_rank)
        candidate = replace(selected_log.candidate, feature_scores=features)
        selected_rows[log.candidate.chunk.chunk_id] = (
            RankLog(
                candidate=candidate,
                feature_scores=features,
                final_rank=log.final_rank,
                selected=True,
                rerank_config_version=log.rerank_config_version,
                as_of_date=log.as_of_date,
            )
        )
    ordered_selected = [selected_rows[log.candidate.chunk.chunk_id] for log in selected]
    return tuple((*ordered_selected, *unselected_rows))


def _warning(
    status: SearchStatus,
    selected_chunks: Sequence[EvidenceChunk],
    rank_log: Sequence[RankLog],
    reasons: Sequence[str],
    claim_support: Sequence[ClaimSupport] = (),
    conflicts: Sequence[tuple[str, str, str]] = (),
    notes: Sequence[str] = (),
) -> str | None:
    messages: list[str] = []
    if status is SearchStatus.FAILED:
        messages.append("Retrieval failed; no evidence was returned.")
    elif status is SearchStatus.EMPTY:
        messages.append("Retrieval was empty; no eligible evidence was returned.")
        if "out_of_scope" in reasons:
            messages.append(
                "Question is out of scope (dosing/prescription/diagnosis/emergency); "
                "scope gating belongs to A1/A5 and no evidence was retrieved."
            )
    elif status is SearchStatus.PARTIAL:
        messages.append("Retrieval is partial; one or more candidate channels were unavailable or degraded.")
    if selected_chunks and len({chunk.source_type.casefold().strip() for chunk in selected_chunks}) == 1:
        messages.append("Final selection is from a single source.")
    if rank_log and rank_log[0].candidate is not None:
        top_score = rank_log[0].candidate.rerank_score
        if top_score is not None and top_score < _LOW_TOP_RERANK_SCORE:
            messages.append("Top rerank score is low; evidence relevance may be limited.")
    for support in claim_support:
        if support.decision in {"insufficient", "mismatch"}:
            messages.append(
                f"Claim {support.claim_index + 1} lacks supporting evidence ({support.decision})."
            )
    if conflicts:
        reasons_seen = {reason for _, _, reason in conflicts}
        messages.append("Conflicting evidence detected: " + ", ".join(sorted(reasons_seen)) + ".")
    if reasons and status in (SearchStatus.FAILED, SearchStatus.PARTIAL):
        messages.append("Details: " + "; ".join(reasons))
    if notes:
        messages.append("Adjustments: " + "; ".join(notes) + ".")
    return " ".join(messages) if messages else None


def _failure_reason(channel: str, _error: Exception) -> str:
    """Return a safe, stable reason code without leaking provider details."""
    return f"{channel}_unavailable"


def _bm25_query_text(query: Query) -> str:
    """Build the lexical query without translation, generation, or hidden expansion.

    Only English terms explicitly supplied in the immutable ``Query`` contract
    are appended.  The semantic provider deliberately receives the original
    Query object and can therefore apply its own fixed embedding protocol.
    """
    return " ".join((query.text, *query.english_terms))


def _elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))


def _snapshot_config(config: RetrievalConfig) -> RetrievalConfig:
    weights = config.feature_weights
    return RetrievalConfig(
        bm25_top_k=config.bm25_top_k,
        vector_top_k=config.vector_top_k,
        fusion_top_k=config.fusion_top_k,
        rerank_top_k=config.rerank_top_k,
        selection_top_k=config.selection_top_k,
        rrf_k=config.rrf_k,
        max_chunks_per_document=config.max_chunks_per_document,
        max_chunks_per_source=config.max_chunks_per_source,
        mmr_lambda=config.mmr_lambda,
        latest_window_days=config.latest_window_days,
        evidence_type_bonus=config.evidence_type_bonus,
        cross_encoder_alpha=config.cross_encoder_alpha,
        freshness_weight_latest_trial=config.freshness_weight_latest_trial,
        source_quality_table=config.source_quality_table,
        verified_ratio_base=config.verified_ratio_base,
        verified_ratio_freshness_bump=config.verified_ratio_freshness_bump,
        verified_ratio_max=config.verified_ratio_max,
        feature_weights=FeatureWeights(
            semantic=weights.semantic,
            lexical=weights.lexical,
            pico_match=weights.pico_match,
            evidence_level=weights.evidence_level,
            freshness=weights.freshness,
            source_reliability=weights.source_reliability,
        ),
        index_version=config.index_version,
        corpus_version=config.corpus_version,
        rerank_config_version=config.rerank_config_version,
    )
