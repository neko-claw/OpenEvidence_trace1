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
from .models import (
    MAX_RRF_OPERAND,
    Candidate,
    EvidenceChunk,
    InitialCandidatePool,
    Query,
    RankLog,
    ReasonCode,
    RetrievalCondition,
    RetrievalAlignmentHint,
    ScoredChunk,
    SearchResult,
    SearchStatus,
)
from .adaptive import adapt_k
from .cross_encoder import CrossEncoderScorer
from .ports import CalibratedQualityScorer, ClaimEvidenceSupportGate
from .rerank import FeatureReranker, select_mmr
from .support_check import check_alignment, detect_conflicts
from .vector import VectorSearch


class _LexicalSearch(Protocol):
    def search(self, query: str, k: int) -> list[ScoredChunk]: ...


QueryVectorProvider = Callable[[Query], Sequence[float]]
_STAGES = ("bm25", "vector", "fusion", "rerank", "mmr", "total")


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
        *,
        cross_encoder: CrossEncoderScorer | None = None,
        support_gate: ClaimEvidenceSupportGate | None = None,
        quality_scorer: CalibratedQualityScorer | None = None,
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
        self._cross_encoder = cross_encoder
        self._support_gate = support_gate
        self._quality_scorer = quality_scorer

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
                codes=[ReasonCode.OUT_OF_SCOPE.value],
            )
        started = perf_counter()
        timings = {stage: 0 for stage in _STAGES}
        reasons: list[str] = []

        bm25, bm25_operational, bm25_version_stale = self._search_bm25(query, timings, reasons)
        vector, vector_operational, vector_version_stale = self._search_vector(query, timings, reasons)

        if bm25_version_stale or vector_version_stale:
            # 设计 spec §9：索引版本不一致 → 停止执行 failed（round2 P1 修复）。
            # 返回非冻结版本候选说明检索的索引不是预期发布版本，fail-closed；
            # 下游不得把结果误解为部分可用（AGENTS.md fail-closed 原则）。
            timings["total"] = _elapsed_ms(started)
            return self._result(
                query,
                SearchStatus.FAILED,
                (),
                (),
                reasons,
                timings,
                codes=[ReasonCode.INDEX_VERSION_MISMATCH.value],
            )

        if not bm25_operational and not vector_operational:
            timings["total"] = _elapsed_ms(started)
            return self._result(
                query,
                SearchStatus.FAILED,
                (),
                (),
                reasons,
                timings,
                codes=_reason_codes(reasons),
            )

        if not bm25 and not vector:
            timings["total"] = _elapsed_ms(started)
            status = SearchStatus.EMPTY if bm25_operational and vector_operational and not reasons else SearchStatus.PARTIAL
            return self._result(query, status, (), (), reasons, timings, codes=_reason_codes(reasons))

        try:
            stage_started = perf_counter()
            candidates = fuse_rrf(
                bm25=bm25,
                vector=vector,
                rrf_k=self._config.rrf_k,
                candidate_limit=self._config.fusion_top_k,
            )
            timings["fusion"] = _elapsed_ms(stage_started)

            k1, k2, adaptive_actions = adapt_k(query, self._config)
            # The context budget is a hard cap: adaptive rules may shrink K,
            # but never grow it beyond the frozen selection budget.
            k2 = min(k2, self._config.selection_top_k)

            stage_started = perf_counter()
            reranked = self._reranker.rank_all(query, candidates)
            timings["rerank"] = _elapsed_ms(stage_started)

            stage_started = perf_counter()
            selected = select_mmr(reranked[:k1], self._config, k2)
            timings["mmr"] = _elapsed_ms(stage_started)
        except Exception as error:
            reasons.append(_failure_reason("pipeline", error))
            timings["total"] = _elapsed_ms(started)
            return self._result(
                query,
                SearchStatus.FAILED,
                (),
                (),
                reasons,
                timings,
                codes=[ReasonCode.PIPELINE_FAILED.value],
            )

        if not reranked or not selected:
            reasons.append("pipeline produced candidates but no selectable audit rows")
            timings["total"] = _elapsed_ms(started)
            return self._result(
                query,
                SearchStatus.FAILED,
                (),
                (),
                reasons,
                timings,
                codes=[ReasonCode.NO_CANDIDATES.value],
            )

        full_log = _merge_selection_logs(reranked, selected)
        selected_chunks = tuple(log.candidate.chunk for log in selected)
        alignment_hints = (
            check_alignment(query, query.atomic_claims, selected_chunks, self._config)
            if query.atomic_claims
            else ()
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
            alignment_hints=alignment_hints,
            conflicts=conflicts,
            notes=adaptive_actions,
        )

    def retrieve_initial_pool(self, query: Query) -> InitialCandidatePool:
        """Retrieve BM25/vector once and freeze their RRF candidate pool.

        Track-3 R0--R3 comparisons must call this exactly once per query and
        reuse the returned object.  No downstream condition is allowed to
        retrieve or append evidence.
        """
        if not isinstance(query, Query):
            raise ValueError("query must be an A4 Query")
        query.__post_init__()
        timings = {"bm25": 0, "vector": 0, "fusion": 0}
        reasons: list[str] = []
        if query.out_of_scope:
            return InitialCandidatePool(
                query_id=query.query_id,
                index_version=self._config.index_version,
                corpus_version=self._config.corpus_version,
                degradation_reasons=("out_of_scope",),
                bm25_operational=False,
                vector_operational=False,
                stage_latency_ms=timings,
                pool_hash=_pool_hash(query, (), (), ()),
            )
        bm25, bm25_operational, bm25_version_stale = self._search_bm25(query, timings, reasons)
        vector, vector_operational, vector_version_stale = self._search_vector(query, timings, reasons)
        if bm25_version_stale or vector_version_stale:
            # 设计 spec §9：索引版本不一致 → fail-closed；池路径同样不得降级为部分可用。
            return InitialCandidatePool(
                query_id=query.query_id,
                index_version=self._config.index_version,
                corpus_version=self._config.corpus_version,
                degradation_reasons=("index_version_mismatch",),
                bm25_operational=False,
                vector_operational=False,
                stage_latency_ms=timings,
                pool_hash=_pool_hash(query, (), (), ()),
            )
        stage_started = perf_counter()
        fused = fuse_rrf(
            bm25=bm25,
            vector=vector,
            rrf_k=self._config.rrf_k,
            candidate_limit=self._config.fusion_top_k,
        )
        timings["fusion"] = _elapsed_ms(stage_started)
        return InitialCandidatePool(
            query_id=query.query_id,
            index_version=self._config.index_version,
            corpus_version=self._config.corpus_version,
            bm25_candidates=tuple(bm25),
            vector_candidates=tuple(vector),
            fused_candidates=tuple(fused),
            degradation_reasons=tuple(reasons),
            bm25_operational=bm25_operational,
            vector_operational=vector_operational,
            stage_latency_ms=timings,
            pool_hash=_pool_hash(query, bm25, vector, fused),
        )

    def search_condition(
        self,
        query: Query,
        condition: RetrievalCondition | str,
    ) -> SearchResult:
        """Convenience path for one condition; ablations should reuse a pool."""
        return self.search_from_pool(query, self.retrieve_initial_pool(query), condition)

    def search_from_pool(
        self,
        query: Query,
        pool: InitialCandidatePool,
        condition: RetrievalCondition | str,
    ) -> SearchResult:
        """Apply R0/R1/R2/R3 to one immutable initial candidate pool."""
        try:
            selected_condition = (
                condition if isinstance(condition, RetrievalCondition) else RetrievalCondition(condition)
            )
        except ValueError as error:
            raise ValueError("condition must be R0/R1/R2/R3") from error
        _validate_pool(query, pool, self._config)
        started = perf_counter()
        timings = {stage: 0 for stage in _STAGES}
        timings.update(pool.stage_latency_ms)
        reasons = list(pool.degradation_reasons)
        trace = ["bm25", "vector", "rrf"]

        if not pool.fused_candidates:
            if not pool.bm25_operational and not pool.vector_operational:
                status = SearchStatus.FAILED
            elif reasons:
                status = SearchStatus.PARTIAL
            else:
                status = SearchStatus.EMPTY
            timings["total"] = _elapsed_ms(started)
            return self._result(
                query, status, (), (), reasons, timings,
                codes=_reason_codes(reasons), condition=selected_condition,
                pool_hash=pool.pool_hash, stage_trace=trace,
            )

        k1, k2, adaptive_actions = adapt_k(query, self._config)
        k2 = min(k2, self._config.selection_top_k)
        reranked: list[RankLog]
        selected: tuple[RankLog, ...]

        if selected_condition is RetrievalCondition.R0:
            trace.append("rrf_top_k")
            reranked = _rrf_rank_logs(query, pool.fused_candidates, self._config)
            selected = tuple(
                replace(log, selected=True) for log in reranked[:k2]
            )
        else:
            stage_started = perf_counter()
            reranked = self._reranker.rank_all(query, pool.fused_candidates)
            timings["rerank"] = _elapsed_ms(stage_started)
            trace.append("feature_rerank")
            if selected_condition in {RetrievalCondition.R2, RetrievalCondition.R3}:
                if self._cross_encoder is None or not self._cross_encoder.is_ready:
                    raise RuntimeError(
                        "cross_encoder capability PENDING: R2/R3 require an explicitly calibrated scorer"
                    )
                candidates = self._cross_encoder.score(
                    query, [log.candidate for log in reranked[:k1] if log.candidate is not None]
                )
                reranked = _candidate_rank_logs(query, candidates, self._config)
                trace.append("cross_encoder")
            stage_started = perf_counter()
            selected = select_mmr(reranked[:k1], self._config, k2)
            timings["mmr"] = _elapsed_ms(stage_started)
            trace.append("mmr")

        if selected_condition is RetrievalCondition.R3:
            if self._support_gate is None:
                raise RuntimeError("support gate capability PENDING: R3 requires an injected gate")
            gate_result = self._support_gate.filter(
                query, [log.candidate for log in selected if log.candidate is not None]
            )
            available = {log.candidate.chunk.chunk_id for log in selected if log.candidate is not None}
            retained = tuple(dict.fromkeys(gate_result.retained_chunk_ids))
            if any(chunk_id not in available for chunk_id in retained):
                raise ValueError("support gate cannot add chunks outside the selected candidate set")
            selected = tuple(
                log for log in selected
                if log.candidate is not None and log.candidate.chunk.chunk_id in retained
            )
            reasons.extend(gate_result.reasons)
            trace.append("claim_evidence_support_gate")

        full_log = _merge_selection_logs(reranked, selected)
        selected_chunks = tuple(log.candidate.chunk for log in selected if log.candidate is not None)
        quality_scores = _score_quality(self._quality_scorer, query, selected_chunks)
        alignment_hints = (
            check_alignment(query, query.atomic_claims, selected_chunks, self._config)
            if query.atomic_claims else ()
        )
        conflicts = detect_conflicts(selected_chunks)
        if selected_condition is RetrievalCondition.R3 and not selected_chunks:
            status = SearchStatus.EMPTY
        else:
            status = (
                SearchStatus.OK
                if pool.bm25_operational and pool.vector_operational and not pool.degradation_reasons
                else SearchStatus.PARTIAL
            )
        timings["total"] = _elapsed_ms(started)
        return self._result(
            query, status, selected_chunks, full_log, reasons, timings,
            alignment_hints=alignment_hints, conflicts=conflicts,
            notes=adaptive_actions, condition=selected_condition,
            pool_hash=pool.pool_hash, stage_trace=trace,
            quality_scores=quality_scores,
        )

    def _search_bm25(
        self, query: Query, timings: dict[str, int], reasons: list[str]
    ) -> tuple[list[ScoredChunk], bool, bool]:
        """Return (candidates, operational, version_stale)."""
        started = perf_counter()
        try:
            raw = self._bm25_index.search(_bm25_query_text(query), self._config.bm25_top_k)
            candidates, version_excluded, excluded = _intake_candidates(raw, "bm25", self._config, query)
            if version_excluded:
                reasons.append(f"bm25 channel index_version mismatch ({version_excluded} candidate(s))")
                return candidates, False, True
            if excluded:
                reasons.append(f"bm25 channel excluded {excluded} invalid or stale candidate(s)")
            return candidates, True, False
        except Exception as error:
            reasons.append(_failure_reason("bm25", error))
            return [], False, False
        finally:
            timings["bm25"] = _elapsed_ms(started)

    def _search_vector(
        self, query: Query, timings: dict[str, int], reasons: list[str]
    ) -> tuple[list[ScoredChunk], bool, bool]:
        """Return (candidates, operational, version_stale)."""
        started = perf_counter()
        try:
            if self._vector_search is None:
                reasons.append("vector_unavailable")
                return [], False, False
            if self._query_vector_provider is None:
                reasons.append("vector_unavailable")
                return [], False, False
            query_vector = self._query_vector_provider(query)
            raw = self._vector_search.search(query_vector, self._config.vector_top_k)
            candidates, version_excluded, excluded = _intake_candidates(raw, "vector", self._config, query)
            if version_excluded:
                reasons.append(f"vector channel index_version mismatch ({version_excluded} candidate(s))")
                return candidates, False, True
            if excluded:
                reasons.append(f"vector channel excluded {excluded} invalid or stale candidate(s)")
            return candidates, True, False
        except Exception as error:
            reasons.append(_failure_reason("vector", error))
            return [], False, False
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
        alignment_hints: tuple[RetrievalAlignmentHint, ...] = (),
        conflicts: tuple[tuple[str, str, str], ...] = (),
        notes: Sequence[str] = (),
        codes: Sequence[str] = (),
        condition: RetrievalCondition = RetrievalCondition.R1,
        pool_hash: str = "",
        stage_trace: Sequence[str] = (),
        quality_scores: Mapping[str, float] | None = None,
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
            degradation_codes=tuple(codes),
            latency_ms=timings["total"],
            stage_latency_ms=timings,
            retrieval_warning=_warning(
                status,
                selected_chunks,
                rank_log,
                reasons,
                alignment_hints,
                conflicts,
                notes,
                low_top_rerank_score=self._config.low_top_rerank_score,
            ),
            alignment_hints=alignment_hints,
            conflicts=conflicts,
            run_hash=_run_hash(query, status, selected_chunks, tuple(reasons)),
            reason_code_version=self._config.reason_code_version,
            condition=condition,
            initial_candidate_pool_hash=pool_hash,
            stage_trace=tuple(stage_trace),
            quality_scores=dict(quality_scores or {}),
            quality_score_kind="QUALITY" if quality_scores else "UNKNOWN",
            quality_score_scope="CROSS_QUERY" if quality_scores else "UNKNOWN",
            quality_score_calibrated=bool(quality_scores),
        )


def _rrf_rank_logs(
    query: Query,
    candidates: Sequence[Candidate],
    config: RetrievalConfig,
) -> list[RankLog]:
    """R0 audit rows: direct RRF order, without feature rerank or MMR."""
    rows: list[RankLog] = []
    for rank, candidate in enumerate(candidates, start=1):
        audited = replace(
            candidate,
            rerank_score=candidate.rrf_score,
            feature_scores={"rrf_ranking_score": candidate.rrf_score},
        )
        rows.append(
            RankLog(
                candidate=audited,
                feature_scores=audited.feature_scores,
                final_rank=rank,
                selected=False,
                rerank_config_version=config.rerank_config_version,
                as_of_date=query.as_of_date,
            )
        )
    return rows


def _candidate_rank_logs(
    query: Query,
    candidates: Sequence[Candidate],
    config: RetrievalConfig,
) -> list[RankLog]:
    return [
        RankLog(
            candidate=candidate,
            feature_scores=candidate.feature_scores,
            final_rank=rank,
            selected=False,
            rerank_config_version=config.rerank_config_version,
            as_of_date=query.as_of_date,
        )
        for rank, candidate in enumerate(candidates, start=1)
    ]


def _validate_pool(query: Query, pool: InitialCandidatePool, config: RetrievalConfig) -> None:
    if not isinstance(query, Query) or not isinstance(pool, InitialCandidatePool):
        raise ValueError("query and pool must use A4 native contracts")
    if pool.query_id != query.query_id:
        raise ValueError("initial candidate pool belongs to another query")
    if pool.index_version != config.index_version or pool.corpus_version != config.corpus_version:
        raise ValueError("initial candidate pool version does not match RetrievalConfig")


def _score_quality(
    scorer: CalibratedQualityScorer | None,
    query: Query,
    chunks: Sequence[EvidenceChunk],
) -> dict[str, float]:
    if scorer is None or not chunks:
        return {}
    raw = dict(scorer.score(query, chunks))
    expected = {chunk.chunk_id for chunk in chunks}
    if set(raw) != expected:
        raise ValueError("quality scorer must return exactly one score per selected chunk")
    scores: dict[str, float] = {}
    for chunk_id, score in raw.items():
        if not _finite(score) or not 0.0 <= float(score) <= 1.0:
            raise ValueError("quality scorer values must be calibrated probabilities in [0, 1]")
        scores[chunk_id] = float(score)
    return scores


def _pool_hash(
    query: Query,
    bm25: Sequence[ScoredChunk],
    vector: Sequence[ScoredChunk],
    fused: Sequence[Candidate],
) -> str:
    from hashlib import sha256

    canonical = "\x1f".join(
        (
            query.query_id,
            query.text,
            ",".join(f"{item.chunk.chunk_id}:{item.rank}" for item in bm25),
            ",".join(f"{item.chunk.chunk_id}:{item.rank}" for item in vector),
            ",".join(f"{item.chunk.chunk_id}:{item.rrf_score:.17g}" for item in fused),
        )
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _intake_candidates(
    raw: object, expected_stage: str, config: RetrievalConfig, query: Query
) -> tuple[list[ScoredChunk], int, int]:
    """Keep only immutable, live candidates tied to this fixed index release.

    Returns ``(candidates, version_excluded, excluded)``.  Candidates whose
    index/corpus version differs from the frozen config are counted separately
    (``version_excluded``): per 设计 spec §9 a version mismatch fails the whole
    request instead of degrading to PARTIAL (round2 P1).  Other invalid or
    stale candidates (tombstoned, malformed, duplicate) count as ``excluded``.
    Candidates that fail the *intended per-query metadata filters* (domain /
    source type / evidence level / latest window) are skipped silently: that
    is normal query behavior, not a degradation, and must not inflate the
    degradation reasons.
    """
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError(f"{expected_stage} channel returned a non-sequence candidate collection")
    candidates: list[ScoredChunk] = []
    version_excluded = 0
    excluded = 0
    seen: set[str] = set()
    for item in raw:
        if _has_version_mismatch(item, expected_stage, config):
            version_excluded += 1
            continue
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
    return candidates, version_excluded, excluded


def _has_version_mismatch(item: object, expected_stage: str, config: RetrievalConfig) -> bool:
    """Whether a structurally valid candidate comes from a different index release.

    A version-mismatched candidate means the searched index is not the frozen
    one (设计 spec §9: 索引版本不一致 → failed).  Structurally invalid records
    are *not* reported here so they keep the ordinary excluded path.
    """
    if not isinstance(item, ScoredChunk) or item.stage != expected_stage:
        return False
    chunk = item.chunk
    if not isinstance(chunk, EvidenceChunk):
        return False
    return chunk.index_version != config.index_version or chunk.corpus_version != config.corpus_version


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
    alignment_hints: Sequence[RetrievalAlignmentHint] = (),
    conflicts: Sequence[tuple[str, str, str]] = (),
    notes: Sequence[str] = (),
    low_top_rerank_score: float = 0.35,
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
        if top_score is not None and top_score < low_top_rerank_score:
            messages.append("Top rerank score is low; evidence relevance may be limited.")
    for hint in alignment_hints:
        if hint.decision in {"INSUFFICIENT", "MISMATCH"}:
            messages.append(
                f"Claim {hint.claim_index + 1} lacks aligning evidence ({hint.decision})."
            )
    if conflicts:
        reasons_seen = {reason for _, _, reason in conflicts}
        messages.append("Conflicting evidence detected: " + ", ".join(sorted(reasons_seen)) + ".")
    if reasons and status in (SearchStatus.FAILED, SearchStatus.PARTIAL):
        messages.append("Details: " + "; ".join(reasons))
    if notes:
        messages.append("Adaptive K adjustments: " + "; ".join(notes) + ".")
    return " ".join(messages) if messages else None


def _reason_codes(reasons: Sequence[str]) -> tuple[str, ...]:
    """Map human-readable degradation reasons to stable ReasonCode values."""
    codes: list[str] = []
    for reason in reasons:
        if reason == "out_of_scope":
            codes.append(ReasonCode.OUT_OF_SCOPE.value)
        elif reason == "bm25_unavailable":
            codes.append(ReasonCode.BM25_UNAVAILABLE.value)
        elif reason == "vector_unavailable":
            codes.append(ReasonCode.VECTOR_UNAVAILABLE.value)
        elif reason.startswith("bm25 channel excluded") or reason.startswith("vector channel excluded"):
            codes.append(ReasonCode.EXCLUDED_INVALID.value)
        elif "index_version mismatch" in reason or reason == "index_version_mismatch":
            codes.append(ReasonCode.INDEX_VERSION_MISMATCH.value)
        else:
            codes.append(ReasonCode.PIPELINE_FAILED.value)
    return tuple(dict.fromkeys(codes))


def _run_hash(
    query: Query,
    status: SearchStatus,
    selected_chunks: Sequence[EvidenceChunk],
    reasons: Sequence[str],
) -> str:
    """A4's own ranking/run hash (never an upstream content identity)."""
    from hashlib import sha256

    canonical = "".join(
        (
            query.query_id,
            query.text,
            status.value,
            ",".join(chunk.chunk_id for chunk in selected_chunks),
            ",".join(reasons),
        )
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


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
        low_top_rerank_score=config.low_top_rerank_score,
        default_as_of_date=config.default_as_of_date,
        citation_id_rule=config.citation_id_rule,
        alignment_overlap_aligned=config.alignment_overlap_aligned,
        alignment_overlap_background=config.alignment_overlap_background,
        alignment_threshold_version=config.alignment_threshold_version,
        reason_code_version=config.reason_code_version,
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
