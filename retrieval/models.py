"""Immutable data contracts shared by A4 retrieval pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from hashlib import sha256
from math import isfinite
from collections.abc import Iterable, Mapping
from numbers import Real
from sys import float_info
from types import MappingProxyType


MAX_RRF_OPERAND = int(float_info.max) // 2
DEFAULT_AS_OF_DATE = date(2026, 8, 11)
_QUERY_TOPICS = frozenset({"generic", "therapy", "diagnosis", "prognosis", "prevention", "safety"})
_QUESTION_TYPES = frozenset({"generic", "therapy", "diagnosis", "prognosis", "guideline", "latest_trial"})
_FRESHNESS_VALUES = frozenset({"generic", "current", "latest"})


def _require_nonblank(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a nonblank string")


def _is_float_representable_finite(value: object) -> bool:
    """Return whether a real value can safely participate in float math."""
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _require_nonnegative_finite(value: float, field_name: str) -> None:
    if not _is_float_representable_finite(value) or value < 0:
        raise ValueError(f"{field_name} must be a finite nonnegative number")


def _require_positive_fusion_rank(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > MAX_RRF_OPERAND:
        raise ValueError(f"{field_name} must be a positive integer within the float-representable domain")


def _normalize_terms(value: Iterable[str], field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise ValueError(f"{field_name} must be an iterable of nonblank strings")
    try:
        normalized = tuple(value)
    except TypeError as error:
        raise ValueError(f"{field_name} must be an iterable of nonblank strings") from error
    if any(not isinstance(term, str) or not term.strip() for term in normalized):
        raise ValueError(f"{field_name} must be an iterable of nonblank strings")
    return normalized


def _normalize_feature_scores(value: Mapping[str, float | None], field_name: str) -> Mapping[str, float | None]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    normalized = dict(value)
    for key, score in normalized.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be nonblank strings")
        if score is not None and not _is_float_representable_finite(score):
            raise ValueError(f"{field_name} values must be finite numbers or None")
    return MappingProxyType(normalized)


def _normalize_typed_collection(value: Iterable[object], expected_type: type[object], field_name: str) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be an iterable of {expected_type.__name__}")
    try:
        normalized = tuple(value)
    except TypeError as error:
        raise ValueError(f"{field_name} must be an iterable of {expected_type.__name__}") from error
    if any(not isinstance(item, expected_type) for item in normalized):
        raise ValueError(f"{field_name} must contain only {expected_type.__name__} values")
    return normalized


class SearchStatus(str, Enum):
    """Terminal state for one retrieval request."""

    OK = "ok"
    PARTIAL = "partial"
    EMPTY = "empty"
    FAILED = "failed"


class RetrievalCondition(str, Enum):
    """Frozen Track-3 ablation conditions from planning section 4.6."""

    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


class ReasonCode(str, Enum):
    """Structured degradation/decision codes (stable machine contract).

    ``SearchResult.degradation_reasons`` keeps the human-readable strings while
    ``degradation_codes`` carries these stable codes; consumers must branch on
    codes, never on message text.  Codes are versioned via
    ``RetrievalConfig.reason_code_version``.
    """

    OUT_OF_SCOPE = "out_of_scope"
    BM25_UNAVAILABLE = "bm25_unavailable"
    VECTOR_UNAVAILABLE = "vector_unavailable"
    PIPELINE_FAILED = "pipeline_failed"
    EXCLUDED_INVALID = "excluded_invalid"
    NO_CANDIDATES = "no_candidates"
    PROVENANCE_UNKNOWN = "provenance_unknown"
    SPAN_UNAVAILABLE = "span_unavailable_a3_pending"


@dataclass(frozen=True, slots=True)
class RetrievalAlignmentHint:
    """One atomic claim's token-overlap pre-check against selected evidence.

    This is an *alignment pre-check*, never a medical-support verdict: the
    decision vocabulary is ALIGNED | BACKGROUND | MISMATCH | INSUFFICIENT |
    UNKNOWN and intentionally does not reuse A5's
    ``VerificationStatus.SUPPORTED``.  The method and threshold version are
    recorded so consumers can reproduce or discard the hint; final claim
    verification belongs to A5 (Gate5).
    """

    claim_index: int
    claim_text: str
    decision: str  # ALIGNED | BACKGROUND | MISMATCH | INSUFFICIENT | UNKNOWN
    evidence_ids: tuple[str, ...] = ()
    reason: str = ""
    method: str = "token_overlap_heuristic"
    threshold_version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.claim_index, int) or isinstance(self.claim_index, bool) or self.claim_index < 0:
            raise ValueError("claim_index must be a nonnegative integer")
        _require_nonblank(self.claim_text, "claim_text")
        if not isinstance(self.decision, str) or self.decision not in {
            "ALIGNED", "BACKGROUND", "MISMATCH", "INSUFFICIENT", "UNKNOWN",
        }:
            raise ValueError("decision must be one of ALIGNED/BACKGROUND/MISMATCH/INSUFFICIENT/UNKNOWN")
        object.__setattr__(self, "evidence_ids", _normalize_terms(self.evidence_ids, "evidence_ids"))
        if not isinstance(self.reason, str):
            raise ValueError("reason must be a string")
        if not isinstance(self.method, str) or not self.method.strip():
            raise ValueError("method must be a nonblank string")
        if not isinstance(self.threshold_version, str):
            raise ValueError("threshold_version must be a string")


@dataclass(frozen=True, slots=True)
class EvidenceChunk:
    """An evidence snippet and the stable metadata needed to rank and cite it."""

    chunk_id: str
    evidence_id: str
    stable_id: str
    text: str
    title: str = ""
    source_type: str = ""
    url: str = ""
    published_at: str | None = None
    evidence_level: str = "unknown"
    topic: str = ""
    pico_population: tuple[str, ...] = ()
    pico_intervention: tuple[str, ...] = ()
    pico_comparator: tuple[str, ...] = ()
    pico_outcome: tuple[str, ...] = ()
    content_vector: tuple[float, ...] = ()
    content_hash: str = ""
    page: str = ""
    section: str = ""
    span_refs: tuple[Mapping[str, object], ...] | Iterable[Mapping[str, object]] = ()
    token_count: int = 0
    # --- Gate1 source-provenance contract (5.7) ---
    # Structured stable identifiers; ``stable_id`` keeps the canonical
    # "PMID:..." / "DOI:..." / "NCT..." string for cross-source dedup while
    # these fields carry the machine-readable parts for citation and gating.
    pmid: str = ""
    doi: str = ""
    nct_id: str = ""
    authors: tuple[str, ...] = ()
    guideline_name: str = ""
    fetched_at: str | None = None
    # --- A3 provenance: A4 never recomputes upstream identity hashes ---
    # ``content_hash`` is the A3 chunk hash; when the caller supplies one it is
    # preserved verbatim.  ``evidence_content_hash`` is the A3 evidence-level
    # hash.  Empty values mean the upstream field is UNKNOWN (never fabricated),
    # and the adapter records a PROVENANCE_UNKNOWN diagnostic.
    evidence_content_hash: str = ""
    chunk_policy_version: str = ""
    embedding_model: str = ""
    embedding_revision: str = ""
    # Synthetic/mock fixture marker: mock records must never carry fabricated
    # PMID/DOI/NCT/URL/guideline IDs (AGENTS).
    mock: bool = False
    # Set when a caller-supplied ``content_hash`` differs from A4's own derived
    # content hash: the upstream value is preserved verbatim (never overwritten)
    # and consumers record a PROVENANCE_UNKNOWN/hash-mismatch diagnostic.
    content_hash_mismatch: bool = False
    is_tombstoned: bool = False
    index_version: str = "v1"
    corpus_version: str = "v1"

    def __post_init__(self) -> None:
        for field_name in ("chunk_id", "evidence_id", "stable_id", "text", "index_version", "corpus_version"):
            _require_nonblank(getattr(self, field_name), field_name)
        if not isinstance(self.title, str) or not isinstance(self.source_type, str) or not isinstance(self.url, str):
            raise ValueError("title, source_type and url must be strings")
        if self.published_at is not None and not isinstance(self.published_at, str):
            raise ValueError("published_at must be a string or None")
        if not isinstance(self.evidence_level, str) or not isinstance(self.topic, str):
            raise ValueError("evidence_level and topic must be strings")
        for field_name in ("pico_population", "pico_intervention", "pico_comparator", "pico_outcome"):
            object.__setattr__(self, field_name, _normalize_terms(getattr(self, field_name), field_name))
        if not isinstance(self.content_vector, tuple) or any(
            not _is_float_representable_finite(value) for value in self.content_vector
        ):
            raise ValueError("content_vector must be a tuple of finite numbers")
        if not isinstance(self.is_tombstoned, bool):
            raise ValueError("is_tombstoned must be a bool")
        if not isinstance(self.page, str) or not isinstance(self.section, str):
            raise ValueError("page and section must be strings")
        try:
            span_refs = tuple(dict(item) for item in self.span_refs)
        except (TypeError, ValueError) as error:
            raise ValueError("span_refs must be an iterable of mappings") from error
        object.__setattr__(self, "span_refs", tuple(MappingProxyType(item) for item in span_refs))
        if not isinstance(self.token_count, int) or isinstance(self.token_count, bool) or self.token_count < 0:
            raise ValueError("token_count must be a nonnegative integer")
        if not isinstance(self.content_hash, str):
            raise ValueError("content_hash must be a string")
        for field_name in ("pmid", "doi", "nct_id", "guideline_name"):
            if not isinstance(getattr(self, field_name), str):
                raise ValueError(f"{field_name} must be a string")
        object.__setattr__(self, "authors", _normalize_terms(self.authors, "authors"))
        if self.fetched_at is not None and not isinstance(self.fetched_at, str):
            raise ValueError("fetched_at must be a string or None")
        for field_name in ("evidence_content_hash", "chunk_policy_version", "embedding_model", "embedding_revision"):
            if not isinstance(getattr(self, field_name), str):
                raise ValueError(f"{field_name} must be a string")
        if not isinstance(self.mock, bool):
            raise ValueError("mock must be a bool")
        if self.mock and any((self.url, self.pmid, self.doi, self.nct_id, self.guideline_name)):
            raise ValueError(
                "mock evidence cannot carry real-world identifiers, URLs, or guideline IDs"
            )
        if not isinstance(self.content_hash_mismatch, bool):
            raise ValueError("content_hash_mismatch must be a bool")
        # A3 chunk hash is upstream identity: a caller-supplied nonempty value
        # is preserved verbatim.  Only when the upstream field is absent does
        # A4 compute its own deterministic fallback hash (and the adapter marks
        # provenance UNKNOWN); A4 never overwrites an upstream hash.  A supplied
        # hash that differs from A4's derived value is flagged (e.g. an A3 hash
        # computed with a different algorithm, or a stale ``replace()`` value)
        # but kept intact.
        derived = _compute_content_hash(self)
        if not self.content_hash.strip():
            object.__setattr__(self, "content_hash", derived)
        elif self.content_hash != derived:
            object.__setattr__(self, "content_hash_mismatch", True)

    @property
    def derived_content_hash(self) -> str:
        """A4's own deterministic content hash (never an upstream identity)."""
        return _compute_content_hash(self)

    @property
    def provenance_complete(self) -> bool:
        """Whether the A3 provenance fields are present (never fabricated)."""
        return bool(self.content_hash.strip()) and bool(self.evidence_content_hash.strip())

    @property
    def population_terms(self) -> tuple[str, ...]:
        """Backward-compatible readable alias for PICO population terms."""
        return self.pico_population

    @property
    def intervention_terms(self) -> tuple[str, ...]:
        return self.pico_intervention

    @property
    def comparator_terms(self) -> tuple[str, ...]:
        return self.pico_comparator

    @property
    def outcome_terms(self) -> tuple[str, ...]:
        return self.pico_outcome

    @property
    def embedding(self) -> tuple[float, ...]:
        return self.content_vector

    @property
    def tombstone(self) -> bool:
        return self.is_tombstoned


_CONTENT_SEPARATOR = "\x1f"
_PICO_SEPARATOR = "\x1e"


def _compute_content_hash(chunk: EvidenceChunk) -> str:
    """Deterministic SHA-256 over the content fields that define a chunk version.

    Provenance fields (``fetched_at``, ``url``, ``pmid``/``doi``/``nct_id``) do
    not define content identity and are deliberately excluded; authorship and
    guideline name are content and therefore included.
    """
    pico_parts = []
    for field_name in ("pico_population", "pico_intervention", "pico_comparator", "pico_outcome"):
        pico_parts.append(_PICO_SEPARATOR.join(getattr(chunk, field_name)))
    canonical = _CONTENT_SEPARATOR.join(
        (
            chunk.stable_id,
            chunk.source_type,
            chunk.topic,
            chunk.title,
            chunk.text,
            chunk.published_at if chunk.published_at is not None else "",
            chunk.evidence_level,
            _PICO_SEPARATOR.join(pico_parts),
            _PICO_SEPARATOR.join(chunk.authors),
            chunk.guideline_name,
        )
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Query:
    """A normalized user query passed to the retrievers."""

    query_id: str
    text: str
    language: str = "zh"
    pico_population: tuple[str, ...] | Iterable[str] = ()
    pico_intervention: tuple[str, ...] | Iterable[str] = ()
    pico_comparator: tuple[str, ...] | Iterable[str] = ()
    pico_outcome: tuple[str, ...] | Iterable[str] = ()
    as_of_date: date = DEFAULT_AS_OF_DATE
    topic: str = "generic"
    question_type: str = "generic"
    freshness: str = "generic"
    english_terms: tuple[str, ...] | Iterable[str] = ()
    source_types: tuple[str, ...] | Iterable[str] = ()
    evidence_levels: tuple[str, ...] | Iterable[str] = ()
    atomic_claims: tuple[str, ...] | Iterable[str] = ()
    domain: str = "generic"
    out_of_scope: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.out_of_scope, bool):
            raise ValueError("out_of_scope must be a bool")
        _require_nonblank(self.query_id, "query_id")
        _require_nonblank(self.text, "text")
        _require_nonblank(self.language, "language")
        if type(self.as_of_date) is not date:
            raise ValueError("as_of_date must be a date")
        for field_name in (
            "pico_population",
            "pico_intervention",
            "pico_comparator",
            "pico_outcome",
            "source_types",
            "evidence_levels",
            "atomic_claims",
        ):
            object.__setattr__(self, field_name, _normalize_terms(getattr(self, field_name), field_name))
        for field_name, allowed in (
            ("topic", _QUERY_TOPICS),
            ("question_type", _QUESTION_TYPES),
            ("freshness", _FRESHNESS_VALUES),
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or value not in allowed:
                raise ValueError(f"{field_name} must be one of: {', '.join(sorted(allowed))}")
        if not isinstance(self.domain, str) or not self.domain.strip():
            raise ValueError("domain must be a nonblank string")
        object.__setattr__(self, "english_terms", _normalize_terms(self.english_terms, "english_terms"))


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A chunk score produced by a named retrieval or reranking stage."""

    chunk: EvidenceChunk
    score: float
    rank: int
    stage: str
    feature_scores: Mapping[str, float | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.chunk, EvidenceChunk):
            raise ValueError("chunk must be an EvidenceChunk")
        _require_nonnegative_finite(self.score, "score")
        _require_positive_fusion_rank(self.rank, "rank")
        _require_nonblank(self.stage, "stage")
        object.__setattr__(self, "feature_scores", _normalize_feature_scores(self.feature_scores, "feature_scores"))


@dataclass(frozen=True, slots=True)
class Candidate:
    """Fused candidate state retained for reranking diagnostics."""

    chunk: EvidenceChunk
    bm25_rank: int | None = None
    vector_rank: int | None = None
    bm25_raw_score: float | None = None
    vector_raw_score: float | None = None
    rrf_score: float = 0.0
    rerank_score: float | None = None
    feature_scores: Mapping[str, float | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.chunk, EvidenceChunk):
            raise ValueError("chunk must be an EvidenceChunk")
        for field_name in ("bm25_rank", "vector_rank"):
            value = getattr(self, field_name)
            if value is not None:
                _require_positive_fusion_rank(value, field_name)
        for field_name in ("bm25_raw_score", "vector_raw_score"):
            value = getattr(self, field_name)
            if value is not None:
                _require_nonnegative_finite(value, field_name)
        _require_nonnegative_finite(self.rrf_score, "rrf_score")
        if self.rerank_score is not None:
            _require_nonnegative_finite(self.rerank_score, "rerank_score")
        object.__setattr__(self, "feature_scores", _normalize_feature_scores(self.feature_scores, "feature_scores"))


@dataclass(frozen=True, slots=True)
class RankLog:
    """Audit record of candidates at each selection stage."""

    candidate: Candidate | None = None
    bm25_candidates: tuple[ScoredChunk, ...] | Iterable[ScoredChunk] = ()
    vector_candidates: tuple[ScoredChunk, ...] | Iterable[ScoredChunk] = ()
    fused_candidates: tuple[Candidate, ...] | Iterable[Candidate] = ()
    reranked_candidates: tuple[Candidate, ...] | Iterable[Candidate] = ()
    selected_candidates: tuple[Candidate, ...] | Iterable[Candidate] = ()
    feature_scores: Mapping[str, float | None] = field(default_factory=dict)
    final_rank: int | None = None
    selected: bool = False
    rerank_config_version: str | None = None
    as_of_date: date | None = None

    def __post_init__(self) -> None:
        if self.candidate is not None and not isinstance(self.candidate, Candidate):
            raise ValueError("candidate must be a Candidate or None")
        for field_name, expected_type in (
            ("bm25_candidates", ScoredChunk),
            ("vector_candidates", ScoredChunk),
            ("fused_candidates", Candidate),
            ("reranked_candidates", Candidate),
            ("selected_candidates", Candidate),
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_typed_collection(getattr(self, field_name), expected_type, field_name),
            )
        object.__setattr__(self, "feature_scores", _normalize_feature_scores(self.feature_scores, "feature_scores"))
        if self.final_rank is not None:
            _require_positive_fusion_rank(self.final_rank, "final_rank")
        if not isinstance(self.selected, bool):
            raise ValueError("selected must be a bool")
        if self.rerank_config_version is not None:
            _require_nonblank(self.rerank_config_version, "rerank_config_version")
        if self.as_of_date is not None and not isinstance(self.as_of_date, date):
            raise ValueError("as_of_date must be a date or None")


@dataclass(frozen=True, slots=True)
class InitialCandidatePool:
    """Immutable BM25/vector/RRF pool shared by R0--R3 for one query.

    This is the fairness boundary for Track 3: downstream conditions may rank
    or filter this pool, but may not retrieve additional evidence.
    """

    query_id: str
    index_version: str
    corpus_version: str
    bm25_candidates: tuple[ScoredChunk, ...] | Iterable[ScoredChunk] = ()
    vector_candidates: tuple[ScoredChunk, ...] | Iterable[ScoredChunk] = ()
    fused_candidates: tuple[Candidate, ...] | Iterable[Candidate] = ()
    degradation_reasons: tuple[str, ...] | Iterable[str] = ()
    bm25_operational: bool = True
    vector_operational: bool = True
    stage_latency_ms: Mapping[str, int] = field(default_factory=dict)
    pool_hash: str = ""

    def __post_init__(self) -> None:
        _require_nonblank(self.query_id, "query_id")
        _require_nonblank(self.index_version, "index_version")
        _require_nonblank(self.corpus_version, "corpus_version")
        for field_name, expected_type in (
            ("bm25_candidates", ScoredChunk),
            ("vector_candidates", ScoredChunk),
            ("fused_candidates", Candidate),
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_typed_collection(getattr(self, field_name), expected_type, field_name),
            )
        object.__setattr__(
            self,
            "degradation_reasons",
            _normalize_terms(self.degradation_reasons, "degradation_reasons"),
        )
        if not isinstance(self.bm25_operational, bool) or not isinstance(self.vector_operational, bool):
            raise ValueError("channel operational flags must be bool")
        object.__setattr__(self, "stage_latency_ms", _normalize_latency_map(self.stage_latency_ms))
        _require_nonblank(self.pool_hash, "pool_hash")


@dataclass(frozen=True, slots=True)
class SearchResult:
    """The A4 hand-off payload for A5 answer generation and citation checks."""

    query_id: str
    index_version: str
    rerank_config_version: str
    status: SearchStatus
    corpus_version: str = "unknown"
    selected_chunks: tuple[EvidenceChunk, ...] | Iterable[EvidenceChunk] = ()
    rank_log: tuple[RankLog, ...] | Iterable[RankLog] = ()
    degradation_reasons: tuple[str, ...] | Iterable[str] = ()
    degradation_codes: tuple[str, ...] | Iterable[str] = ()
    latency_ms: float = 0.0
    stage_latency_ms: Mapping[str, int] = field(default_factory=dict)
    retrieval_warning: str | None = None
    alignment_hints: tuple[RetrievalAlignmentHint, ...] | Iterable[RetrievalAlignmentHint] = ()
    conflicts: tuple[tuple[str, str, str], ...] | Iterable[tuple[str, str, str]] = ()
    run_hash: str = ""
    reason_code_version: str = ""
    condition: RetrievalCondition = RetrievalCondition.R1
    initial_candidate_pool_hash: str = ""
    stage_trace: tuple[str, ...] | Iterable[str] = ()
    ranking_score_kind: str = "RANKING"
    ranking_score_scope: str = "QUERY_LOCAL"
    ranking_score_calibrated: bool = False
    quality_scores: Mapping[str, float] = field(default_factory=dict)
    quality_score_kind: str = "UNKNOWN"
    quality_score_scope: str = "UNKNOWN"
    quality_score_calibrated: bool = False

    def __post_init__(self) -> None:
        _require_nonblank(self.query_id, "query_id")
        _require_nonblank(self.index_version, "index_version")
        _require_nonblank(self.corpus_version, "corpus_version")
        _require_nonblank(self.rerank_config_version, "rerank_config_version")
        if not isinstance(self.status, SearchStatus):
            raise ValueError("status must be a SearchStatus")
        object.__setattr__(
            self,
            "selected_chunks",
            _normalize_typed_collection(self.selected_chunks, EvidenceChunk, "selected_chunks"),
        )
        object.__setattr__(self, "rank_log", _normalize_typed_collection(self.rank_log, RankLog, "rank_log"))
        object.__setattr__(self, "degradation_reasons", _normalize_terms(self.degradation_reasons, "degradation_reasons"))
        object.__setattr__(self, "degradation_codes", _normalize_terms(self.degradation_codes, "degradation_codes"))
        _require_nonnegative_finite(self.latency_ms, "latency_ms")
        object.__setattr__(self, "stage_latency_ms", _normalize_latency_map(self.stage_latency_ms))
        if self.retrieval_warning is not None and (
            not isinstance(self.retrieval_warning, str) or not self.retrieval_warning.strip()
        ):
            raise ValueError("retrieval_warning must be a nonblank string or None")
        object.__setattr__(
            self,
            "alignment_hints",
            _normalize_typed_collection(self.alignment_hints, RetrievalAlignmentHint, "alignment_hints"),
        )
        conflicts = tuple(self.conflicts)
        if any(
            not isinstance(item, tuple) or len(item) != 3
            or any(not isinstance(part, str) or not part.strip() for part in item)
            for item in conflicts
        ):
            raise ValueError("conflicts must be a sequence of (evidence_id, evidence_id, reason) triples")
        object.__setattr__(self, "conflicts", conflicts)
        if not isinstance(self.run_hash, str):
            raise ValueError("run_hash must be a string")
        if not isinstance(self.reason_code_version, str):
            raise ValueError("reason_code_version must be a string")
        if not isinstance(self.condition, RetrievalCondition):
            raise ValueError("condition must be a RetrievalCondition")
        if not isinstance(self.initial_candidate_pool_hash, str):
            raise ValueError("initial_candidate_pool_hash must be a string")
        object.__setattr__(self, "stage_trace", _normalize_terms(self.stage_trace, "stage_trace"))
        if self.ranking_score_kind != "RANKING" or self.ranking_score_scope != "QUERY_LOCAL":
            raise ValueError("A4 relevance scores must remain query-local ranking scores")
        if self.ranking_score_calibrated is not False:
            raise ValueError("A4 ranking scores must not be marked calibrated")
        quality_scores = dict(self.quality_scores)
        for chunk_id, score in quality_scores.items():
            _require_nonblank(chunk_id, "quality_scores key")
            if not _is_float_representable_finite(score) or not 0.0 <= float(score) <= 1.0:
                raise ValueError("quality_scores values must be finite probabilities in [0, 1]")
        object.__setattr__(self, "quality_scores", MappingProxyType(quality_scores))
        if quality_scores:
            if (
                self.quality_score_kind != "QUALITY"
                or self.quality_score_scope != "CROSS_QUERY"
                or self.quality_score_calibrated is not True
            ):
                raise ValueError("quality scores require explicit calibrated cross-query semantics")
        elif (
            self.quality_score_kind != "UNKNOWN"
            or self.quality_score_scope != "UNKNOWN"
            or self.quality_score_calibrated is not False
        ):
            raise ValueError("missing quality scores must remain UNKNOWN and uncalibrated")


def _normalize_latency_map(value: Mapping[str, int]) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError("stage_latency_ms must be a mapping")
    normalized = dict(value)
    for stage, latency in normalized.items():
        if not isinstance(stage, str) or not stage.strip():
            raise ValueError("stage_latency_ms keys must be nonblank strings")
        if not isinstance(latency, int) or isinstance(latency, bool) or latency < 0:
            raise ValueError("stage_latency_ms values must be nonnegative integers")
    return MappingProxyType(normalized)
