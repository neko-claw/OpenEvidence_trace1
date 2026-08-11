"""Explainable, deterministic P0 feature reranking for clinical evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from math import fsum, hypot, isfinite
from numbers import Real
import re

from .config import FeatureWeights, RetrievalConfig
from .models import MAX_RRF_OPERAND, Candidate, EvidenceChunk, Query, RankLog


_FEATURE_NAMES = (
    "semantic",
    "lexical",
    "rrf",
    "title_abstract",
    "pico_match",
    "evidence_level",
    "freshness",
    "source_reliability",
    "source_quality",
    "fulltext",
    "redundancy",
)
_LATEST_TERMS = frozenset({"latest", "current", "recent", "newest", "最新", "近期", "当前", "新近"})
_THERAPY_TERMS = frozenset({"treatment", "therapy", "treat", "intervention", "drug", "治疗", "疗法", "干预", "药物", "用药"})
_CJK_LATEST_TERMS = frozenset({"最新", "近期", "当前", "新近"})
_CJK_THERAPY_TERMS = frozenset({"治疗", "疗法", "干预", "药物", "用药"})
_GUIDELINE_TERMS = frozenset({"guideline", "guidelines"})
_CJK_GUIDELINE_TERMS = frozenset({"指南"})
_TRIAL_TERMS = frozenset({"trial", "rct", "randomized", "randomised"})
_CJK_TRIAL_TERMS = frozenset({"试验", "随机"})
_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)

# These P0 mappings deliberately describe study type, separately from
# ``source_reliability`` (stable identifier, URL, and source metadata only).
_EVIDENCE_SCORES: Mapping[str, Mapping[str, float]] = {
    "therapy": {
        "guideline": 1.00,
        "systematic_review": 0.95,
        "meta_analysis": 0.95,
        "rct": 0.90,
        "trial": 0.80,
        "cohort": 0.55,
        "observational": 0.50,
        "case_control": 0.45,
        "case_series": 0.30,
        "unknown": 0.20,
    },
    "latest_trial": {
        "rct": 1.00,
        "trial": 0.95,
        "guideline": 0.65,
        "systematic_review": 0.60,
        "meta_analysis": 0.60,
        "cohort": 0.45,
        "observational": 0.40,
        "case_control": 0.35,
        "case_series": 0.25,
        "unknown": 0.20,
    },
    "guideline": {
        "guideline": 1.00,
        "systematic_review": 0.90,
        "meta_analysis": 0.90,
        "rct": 0.70,
        "trial": 0.65,
        "cohort": 0.50,
        "observational": 0.45,
        "case_control": 0.40,
        "case_series": 0.25,
        "unknown": 0.20,
    },
    "generic": {
        "guideline": 1.00,
        "systematic_review": 0.90,
        "meta_analysis": 0.90,
        "rct": 0.80,
        "trial": 0.70,
        "cohort": 0.55,
        "observational": 0.50,
        "case_control": 0.45,
        "case_series": 0.30,
        "unknown": 0.20,
    },
}


class FeatureReranker:
    """Rank fused candidates using auditable query-local P0 features.

    Each returned ``RankLog`` contains a copied candidate with its six raw
    feature values.  ``None`` means that a feature was unavailable, never that
    it had a zero score.  Weights are renormalized independently for every
    candidate across the available features.
    """

    def __init__(self, config: RetrievalConfig) -> None:
        if not isinstance(config, RetrievalConfig):
            raise ValueError("config must be a RetrievalConfig")
        config.__post_init__()
        self._config = _snapshot_config(config)

    def rank(self, query: Query, candidates: Sequence[Candidate]) -> list[RankLog]:
        """Return at most ``rerank_top_k`` deterministic, unselected audit rows."""
        return self._rank(query, candidates, limit=self._config.rerank_top_k)

    def rank_all(self, query: Query, candidates: Sequence[Candidate]) -> list[RankLog]:
        """Return an auditable rank row for every fused candidate.

        Selection-context limits belong to the caller.  Keeping this complete
        sequence permits the service to expose why a candidate was not passed
        to MMR, without widening the generator's evidence budget.
        """
        return self._rank(query, candidates, limit=None)

    def _rank(
        self, query: Query, candidates: Sequence[Candidate], *, limit: int | None
    ) -> list[RankLog]:
        _validate_query(query)
        validated = _validate_candidates(candidates)
        if not validated:
            return []

        query_type = _classify_query(query)
        semantic = _percentile_scores(validated, "vector_raw_score")
        lexical = _percentile_scores(validated, "bm25_raw_score")
        rrf = _percentile_scores(validated, "rrf_score")
        corpus_vectors = {candidate.chunk.chunk_id: candidate.chunk.content_vector for candidate in validated}
        query_tokens = _tokens(query.text)
        rescored: list[Candidate] = []
        for candidate in validated:
            chunk = candidate.chunk
            features: dict[str, float | None] = {
                "semantic": semantic.get(chunk.chunk_id),
                "lexical": lexical.get(chunk.chunk_id),
                "rrf": rrf.get(chunk.chunk_id),
                "title_abstract": _title_abstract_match(query_tokens, chunk),
                "pico_match": _pico_match(query, chunk),
                "evidence_level": _evidence_level(chunk, query_type),
                "freshness": _freshness(query, chunk),
                "source_reliability": _source_reliability(chunk),
                "source_quality": _source_quality(chunk, self._config),
                "fulltext": _fulltext_availability(chunk),
                "redundancy": _redundancy(chunk, corpus_vectors),
            }
            score = max(0.0, _weighted_score(features, self._config, query_type))
            rescored.append(
                Candidate(
                    chunk=chunk,
                    bm25_rank=candidate.bm25_rank,
                    vector_rank=candidate.vector_rank,
                    bm25_raw_score=candidate.bm25_raw_score,
                    vector_raw_score=candidate.vector_raw_score,
                    rrf_score=candidate.rrf_score,
                    rerank_score=score,
                    feature_scores=features,
                )
            )

        rescored.sort(key=lambda candidate: (-_required_score(candidate), candidate.chunk.chunk_id))
        ranked = rescored if limit is None else rescored[:limit]
        return [
            RankLog(
                candidate=candidate,
                feature_scores=candidate.feature_scores,
                final_rank=rank,
                selected=False,
                rerank_config_version=self._config.rerank_config_version,
                as_of_date=query.as_of_date,
            )
            for rank, candidate in enumerate(ranked, start=1)
        ]


def select_mmr(rank_logs: Sequence[RankLog], config: RetrievalConfig, k: int) -> tuple[RankLog, ...]:
    """Select diverse, auditable evidence from reranked candidates.

    The selector is deliberately a pure post-rerank stage.  It uses the
    reranker score as relevance, applies document and source caps before each
    choice, and records the exact MMR score and redundancy penalty on each
    returned log.  Inputs that no longer identify a live, stable evidence
    record are ignored instead of risking a stale citation downstream.  A
    request above ``config.selection_top_k`` is rejected rather than silently
    widening the downstream answer-generation context budget.
    """
    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError("k must be a positive integer")
    snapshot = _validated_config_snapshot(config)
    if k > snapshot.selection_top_k:
        raise ValueError("k must not exceed config.selection_top_k")
    ordered_logs = _validate_rank_logs(rank_logs, snapshot)
    eligible = [log for log in ordered_logs if _is_live_selectable_chunk(log.candidate.chunk)]

    selected: list[RankLog] = []
    selected_chunks: list[EvidenceChunk] = []
    document_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}

    while eligible and len(selected) < k:
        best_index: int | None = None
        best_score: float | None = None
        best_penalty = 0.0
        best_bonus = 0.0
        covered_types = {
            chunk.evidence_level.casefold().strip()
            for chunk in selected_chunks
            if isinstance(chunk.evidence_level, str) and chunk.evidence_level.strip()
        }
        for index, log in enumerate(eligible):
            chunk = log.candidate.chunk
            document_key = chunk.stable_id.strip()
            source_key = chunk.source_type.strip().casefold()
            if (
                document_counts.get(document_key, 0) >= snapshot.max_chunks_per_document
                or source_counts.get(source_key, 0) >= snapshot.max_chunks_per_source
            ):
                continue
            penalty = max(
                (max(0.0, _cosine_similarity(chunk.content_vector, previous.content_vector)) for previous in selected_chunks),
                default=0.0,
            )
            level = chunk.evidence_level.casefold().strip() if isinstance(chunk.evidence_level, str) else ""
            bonus = snapshot.evidence_type_bonus if level and level not in covered_types else 0.0
            score = snapshot.mmr_lambda * _rerank_score(log.candidate) - (1.0 - snapshot.mmr_lambda) * penalty + bonus
            # ``eligible`` is in rerank order, so a strict comparison keeps
            # that order whenever MMR scores tie.
            if best_score is None or score > best_score:
                best_index = index
                best_score = score
                best_penalty = penalty
                best_bonus = bonus

        if best_index is None:
            break

        chosen = eligible.pop(best_index)
        chunk = chosen.candidate.chunk
        document_key = chunk.stable_id.strip()
        source_key = chunk.source_type.strip().casefold()
        document_counts[document_key] = document_counts.get(document_key, 0) + 1
        source_counts[source_key] = source_counts.get(source_key, 0) + 1
        selected_chunks.append(chunk)
        selected.append(_selected_rank_log(chosen, len(selected) + 1, best_penalty, best_score, best_bonus))

    return tuple(selected)


def _validated_config_snapshot(config: RetrievalConfig) -> RetrievalConfig:
    if not isinstance(config, RetrievalConfig):
        raise ValueError("config must be a RetrievalConfig")
    config.__post_init__()
    return _snapshot_config(config)


def _validate_rank_logs(rank_logs: Sequence[RankLog], config: RetrievalConfig) -> list[RankLog]:
    if isinstance(rank_logs, (str, bytes)) or not isinstance(rank_logs, Sequence):
        raise ValueError("rank_logs must be a sequence of RankLog")

    seen_chunk_ids: set[str] = set()
    seen_ranks: set[int] = set()
    validated: list[RankLog] = []
    for log in rank_logs:
        if not isinstance(log, RankLog) or not isinstance(log.candidate, Candidate):
            raise ValueError("rank_logs must contain RankLog values with a Candidate")
        if not isinstance(log.final_rank, int) or isinstance(log.final_rank, bool) or not 1 <= log.final_rank <= MAX_RRF_OPERAND:
            raise ValueError("rank log final_rank must be a positive integer within the float-representable domain")
        if log.final_rank in seen_ranks:
            raise ValueError(f"duplicate rank log final_rank: {log.final_rank}")
        if log.rerank_config_version != config.rerank_config_version:
            raise ValueError("rank log rerank_config_version must match config")
        candidate = log.candidate
        if not isinstance(candidate.chunk, EvidenceChunk):
            raise ValueError("rank log candidate chunk must be an EvidenceChunk")
        chunk_id = candidate.chunk.chunk_id
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("rank log candidate chunk_id must be a nonblank string")
        if chunk_id in seen_chunk_ids:
            raise ValueError(f"duplicate rank log chunk_id: {chunk_id}")
        seen_chunk_ids.add(chunk_id)
        if not isinstance(candidate.feature_scores, Mapping):
            raise ValueError("rank log candidate feature_scores must be a mapping")
        _rerank_score(candidate)
        validated.append(log)
        seen_ranks.add(log.final_rank)

    # FeatureReranker assigns increasing final ranks; sorting by them makes
    # tie-breaking robust even if a caller passes a permuted sequence.
    return sorted(validated, key=lambda log: log.final_rank)


def _is_live_selectable_chunk(chunk: EvidenceChunk) -> bool:
    """Safely filter stale/unusable records that may have been mutated post-validation."""
    # The data contract only permits a literal bool.  Fail closed here because
    # frozen dataclasses can be bypassed by a caller after construction.
    if chunk.is_tombstoned is not False:
        return False
    return all(
        isinstance(value, str) and bool(value.strip())
        for value in (chunk.stable_id, chunk.evidence_id, chunk.source_type)
    )


def _rerank_score(candidate: Candidate) -> float:
    score = candidate.rerank_score
    if not _finite_real(score) or score is None or score < 0:
        raise ValueError("rank log candidate rerank_score must be a finite nonnegative number")
    return float(score)


def _cosine_similarity(left: object, right: object) -> float:
    """Return a finite cosine similarity, treating unavailable vectors as zero."""
    if not isinstance(left, tuple) or not isinstance(right, tuple) or not left or len(left) != len(right):
        return 0.0
    if any(not _finite_real(value) for value in left) or any(not _finite_real(value) for value in right):
        return 0.0
    try:
        left_values = tuple(float(value) for value in left)
        right_values = tuple(float(value) for value in right)
    except (OverflowError, TypeError, ValueError):
        return 0.0
    left_scale = max((abs(value) for value in left_values), default=0.0)
    right_scale = max((abs(value) for value in right_values), default=0.0)
    if left_scale == 0.0 or right_scale == 0.0:
        return 0.0
    left_normalized = tuple(value / left_scale for value in left_values)
    right_normalized = tuple(value / right_scale for value in right_values)
    left_norm = _scaled_norm(left_normalized)
    right_norm = _scaled_norm(right_normalized)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    try:
        similarity = fsum(left_value * right_value for left_value, right_value in zip(left_normalized, right_normalized)) / (left_norm * right_norm)
    except (OverflowError, ValueError, ZeroDivisionError):
        return 0.0
    if not isfinite(similarity):
        return 0.0
    return max(-1.0, min(1.0, similarity))


def _scaled_norm(values: Sequence[float]) -> float:
    norm = 0.0
    for value in values:
        norm = hypot(norm, value)
    return norm


def _selected_rank_log(log: RankLog, final_rank: int, penalty: float, mmr_score: float, type_bonus: float) -> RankLog:
    features = dict(log.candidate.feature_scores)
    features["mmr_similarity_penalty"] = penalty
    features["mmr_score"] = mmr_score
    features["mmr_evidence_type_diversity_bonus"] = type_bonus
    candidate = Candidate(
        chunk=log.candidate.chunk,
        bm25_rank=log.candidate.bm25_rank,
        vector_rank=log.candidate.vector_rank,
        bm25_raw_score=log.candidate.bm25_raw_score,
        vector_raw_score=log.candidate.vector_raw_score,
        rrf_score=log.candidate.rrf_score,
        rerank_score=log.candidate.rerank_score,
        feature_scores=features,
    )
    return RankLog(
        candidate=candidate,
        feature_scores=features,
        final_rank=final_rank,
        selected=True,
        rerank_config_version=log.rerank_config_version,
        as_of_date=log.as_of_date,
    )


def _validate_query(query: Query) -> None:
    if not isinstance(query, Query):
        raise ValueError("query must be a Query")
    # Query is frozen but callers can still bypass its constructor with mutation.
    if not isinstance(query.query_id, str) or not query.query_id.strip():
        raise ValueError("query_id must be a nonblank string")
    if not isinstance(query.text, str) or not query.text.strip():
        raise ValueError("query text must be a nonblank string")
    if not isinstance(query.language, str) or not query.language.strip():
        raise ValueError("query language must be a nonblank string")
    if type(query.as_of_date) is not date:
        raise ValueError("query as_of_date must be a date")
    if query.topic not in {"generic", "therapy", "diagnosis", "prognosis", "prevention", "safety"}:
        raise ValueError("query topic is invalid")
    if query.question_type not in {"generic", "therapy", "diagnosis", "prognosis", "guideline", "latest_trial"}:
        raise ValueError("query question_type is invalid")
    if query.freshness not in {"generic", "current", "latest"}:
        raise ValueError("query freshness is invalid")
    if (
        isinstance(query.english_terms, str)
        or not isinstance(query.english_terms, tuple)
        or any(not isinstance(value, str) or not value.strip() for value in query.english_terms)
    ):
        raise ValueError("english_terms must be a tuple of nonblank strings")
    for field_name in ("pico_population", "pico_intervention", "pico_comparator", "pico_outcome"):
        values = getattr(query, field_name)
        if isinstance(values, str) or not isinstance(values, tuple) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"{field_name} must be a tuple of nonblank strings")


def _validate_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise ValueError("candidates must be a sequence of Candidate")
    validated: list[Candidate] = []
    seen_ids: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, Candidate):
            raise ValueError("candidates must contain only Candidate values")
        if not isinstance(candidate.chunk, EvidenceChunk):
            raise ValueError("candidate chunk must be an EvidenceChunk")
        _validate_chunk(candidate.chunk)
        _validate_candidate_scores(candidate)
        chunk_id = candidate.chunk.chunk_id
        if chunk_id in seen_ids:
            raise ValueError(f"duplicate candidate chunk_id: {chunk_id}")
        seen_ids.add(chunk_id)
        validated.append(candidate)
    return validated


def _validate_chunk(chunk: EvidenceChunk) -> None:
    for field_name in ("chunk_id", "evidence_id", "stable_id", "text", "index_version", "corpus_version"):
        value = getattr(chunk, field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"candidate chunk {field_name} must be a nonblank string")
    for field_name in ("title", "source_type", "url", "evidence_level"):
        if not isinstance(getattr(chunk, field_name), str):
            raise ValueError(f"candidate chunk {field_name} must be a string")
    if chunk.published_at is not None and not isinstance(chunk.published_at, str):
        raise ValueError("candidate chunk published_at must be a string or None")
    for field_name in ("pico_population", "pico_intervention", "pico_comparator", "pico_outcome"):
        values = getattr(chunk, field_name)
        if isinstance(values, str) or not isinstance(values, tuple) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"candidate chunk {field_name} must be a tuple of nonblank strings")
    if not isinstance(chunk.content_vector, tuple) or any(not _finite_real(value) for value in chunk.content_vector):
        raise ValueError("candidate chunk content_vector must be a tuple of finite numbers")
    if not isinstance(chunk.is_tombstoned, bool):
        raise ValueError("candidate chunk is_tombstoned must be a bool")


def _validate_candidate_scores(candidate: Candidate) -> None:
    for field_name in ("bm25_rank", "vector_rank"):
        value = getattr(candidate, field_name)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > MAX_RRF_OPERAND
        ):
            raise ValueError(f"candidate {field_name} must be a positive integer within the float-representable domain")
    for field_name in ("bm25_raw_score", "vector_raw_score", "rrf_score", "rerank_score"):
        value = getattr(candidate, field_name)
        if value is not None and (not _finite_real(value) or value < 0):
            raise ValueError(f"candidate {field_name} must be a finite nonnegative number")
    if not isinstance(candidate.feature_scores, Mapping):
        raise ValueError("candidate feature_scores must be a mapping")
    for name, score in candidate.feature_scores.items():
        if not isinstance(name, str) or not name.strip() or (score is not None and not _finite_real(score)):
            raise ValueError("candidate feature_scores must use nonblank names and finite values or None")


def _finite_real(value: object) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _percentile_scores(candidates: Sequence[Candidate], field_name: str) -> dict[str, float]:
    """Empirical percentiles over the current query's available channel scores."""
    available = [(candidate.chunk.chunk_id, getattr(candidate, field_name)) for candidate in candidates]
    scores = [(chunk_id, score) for chunk_id, score in available if score is not None]
    if not scores:
        return {}
    unique = sorted({float(score) for _, score in scores})
    if len(unique) == 1:
        return {chunk_id: 1.0 for chunk_id, _ in scores}
    denominator = len(unique) - 1
    positions = {value: position for position, value in enumerate(unique)}
    return {chunk_id: positions[float(score)] / denominator for chunk_id, score in scores}


def _classify_query(query: Query) -> str:
    tokens = _tokens(query.text)
    normalized_text = query.text.casefold()
    has_latest = bool(tokens & _LATEST_TERMS) or any(term in normalized_text for term in _CJK_LATEST_TERMS)
    has_guideline = bool(tokens & _GUIDELINE_TERMS) or any(term in normalized_text for term in _CJK_GUIDELINE_TERMS)
    has_trial = bool(tokens & _TRIAL_TERMS) or any(term in normalized_text for term in _CJK_TRIAL_TERMS)
    if has_guideline:
        return "guideline"
    if has_latest and has_trial:
        return "latest_trial"
    if query.pico_intervention or tokens & _THERAPY_TERMS or any(term in normalized_text for term in _CJK_THERAPY_TERMS):
        return "therapy"
    return "generic"


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_PATTERN.findall(value.casefold()) if token.strip()}


def _pico_match(query: Query, chunk: EvidenceChunk) -> float | None:
    field_pairs = (
        (query.pico_population, chunk.pico_population),
        (query.pico_intervention, chunk.pico_intervention),
        (query.pico_comparator, chunk.pico_comparator),
        (query.pico_outcome, chunk.pico_outcome),
    )
    overlaps: list[float] = []
    for query_terms, chunk_terms in field_pairs:
        if not query_terms or not chunk_terms:
            continue
        query_tokens = _tokens(" ".join(query_terms))
        chunk_tokens = _tokens(" ".join(chunk_terms))
        if query_tokens:
            overlaps.append(len(query_tokens & chunk_tokens) / len(query_tokens))
    return sum(overlaps) / len(overlaps) if overlaps else None


def _evidence_level(chunk: EvidenceChunk, query_type: str) -> float:
    level = chunk.evidence_level.casefold().strip() if isinstance(chunk.evidence_level, str) else "unknown"
    return _EVIDENCE_SCORES[query_type].get(level, _EVIDENCE_SCORES[query_type]["unknown"])


def _freshness(query: Query, chunk: EvidenceChunk) -> float | None:
    if not _is_freshness_requested(query) or not isinstance(chunk.published_at, str):
        return None
    try:
        published = date.fromisoformat(chunk.published_at)
    except ValueError:
        return None
    if published.isoformat() != chunk.published_at:
        return None
    age_days = (query.as_of_date - published).days
    # A ten-year linear window keeps scores in [0, 1] and grants future-dated
    # records no advantage over records dated today.
    return max(0.0, min(1.0, 1.0 - max(age_days, 0) / 3652.5))


def _is_freshness_requested(query: Query) -> bool:
    tokens = _tokens(query.text)
    normalized_text = query.text.casefold()
    return bool(tokens & _LATEST_TERMS) or any(term in normalized_text for term in _CJK_LATEST_TERMS)


def _source_reliability(chunk: EvidenceChunk) -> float:
    """Provenance completeness only; this does not score research quality."""
    components = (
        isinstance(chunk.stable_id, str) and bool(chunk.stable_id.strip()),
        isinstance(chunk.url, str) and bool(chunk.url.strip()),
        isinstance(chunk.source_type, str) and bool(chunk.source_type.strip()),
    )
    return sum(components) / len(components)


def _weighted_score(features: Mapping[str, float | None], config: RetrievalConfig, query_type: str = "generic") -> float:
    weights = config.feature_weights
    freshness_weight = weights.freshness
    # 4.2: freshness is not one-size-fits-all — latest-trial questions raise
    # its weight; stable/mechanism questions leave it unavailable (weight
    # redistributed) so stale papers never dominate.
    if query_type == "latest_trial":
        freshness_weight = config.freshness_weight_latest_trial
    configured = {
        "semantic": weights.semantic,
        "lexical": weights.lexical,
        "pico_match": weights.pico_match,
        "evidence_level": weights.evidence_level,
        "freshness": freshness_weight,
        "source_reliability": weights.source_reliability,
    }
    available = {name: value for name, value in features.items() if value is not None}
    scorable = {name: value for name, value in available.items() if name in configured}
    total_weight = sum(configured[name] for name in scorable)
    if total_weight <= 0:
        raise ValueError("no positive feature weight is available for candidate")
    score = sum(configured[name] / total_weight * value for name, value in scorable.items())
    if not _finite_real(score):
        raise ValueError("rerank score must be finite")
    return score


def _title_abstract_match(query_tokens: set[str], chunk: EvidenceChunk) -> float | None:
    """Token-level Jaccard between the query and title + abstract text."""
    if not query_tokens:
        return None
    document_tokens = _tokens(f"{chunk.title} {chunk.text}")
    if not document_tokens:
        return None
    overlap = len(query_tokens & document_tokens)
    return overlap / len(query_tokens | document_tokens)


def _source_quality(chunk: EvidenceChunk, config: RetrievalConfig) -> float:
    """Source-type reliability table (guideline > pubmed > trials > europepmc)."""
    table = {source.casefold(): score for source, score in config.source_quality_table}
    return table.get(chunk.source_type.casefold().strip(), 0.5)


def _fulltext_availability(chunk: EvidenceChunk) -> float:
    """Full-text vs abstract-only availability heuristic."""
    if chunk.source_type.casefold().strip() == "europepmc":
        return 1.0
    return 1.0 if len(chunk.text) >= 800 else 0.5


def _redundancy(chunk: EvidenceChunk, corpus_vectors: Mapping[str, tuple[float, ...]]) -> float:
    """Max cosine similarity to any other candidate in the pool (0 when vectors are absent)."""
    vector = chunk.content_vector
    if not vector or len(corpus_vectors) <= 1:
        return 0.0
    best = 0.0
    for other_id, other in corpus_vectors.items():
        if other_id == chunk.chunk_id or not other:
            continue
        similarity = _cosine_similarity(vector, other)
        if similarity > best:
            best = similarity
    return best


def _required_score(candidate: Candidate) -> float:
    assert candidate.rerank_score is not None
    return candidate.rerank_score


def _snapshot_config(config: RetrievalConfig) -> RetrievalConfig:
    """Copy validated configuration so later frozen-object mutation cannot alter a run.

    Every tunable field is copied: a frozen YAML config must take full effect
    even when a caller mutates the original object after construction.
    """
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
