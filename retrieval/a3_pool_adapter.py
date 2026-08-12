"""A3 SearchHit -> A4 frozen candidate-pool adapter.

The adapter consumes A3's already-built lexical/vector indexes.  It never
loads an embedding model and therefore keeps Embedding ownership in A3.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from math import isfinite
from numbers import Real
from .config import RetrievalConfig
from .fusion import fuse_rrf
from .models import Candidate, EvidenceChunk, InitialCandidatePool, Query, ScoredChunk


def build_initial_pool_from_a3_hits(
    query: Query,
    lexical_hits: Sequence[object],
    vector_hits: Sequence[object],
    config: RetrievalConfig,
    *,
    content_vectors: Mapping[str, Sequence[float]] | None = None,
) -> InitialCandidatePool:
    """Validate two A3 result channels and freeze one RRF pool.

    ``content_vectors`` is optional and must come from the same frozen A3
    index.  When absent, MMR still enforces document/source caps but records no
    semantic redundancy; A4 never creates replacement embeddings.
    """
    if not isinstance(query, Query) or not isinstance(config, RetrievalConfig):
        raise ValueError("query/config must use A4 native contracts")
    vectors = content_vectors or {}
    lexical = _map_hits(lexical_hits, "lexical", "bm25", config, vectors)
    semantic = _map_hits(vector_hits, "vector", "vector", config, vectors)
    fused = fuse_rrf(
        bm25=lexical,
        vector=semantic,
        rrf_k=config.rrf_k,
        candidate_limit=config.fusion_top_k,
    )
    pool_hash = _hash(query, lexical, semantic, fused)
    return InitialCandidatePool(
        query_id=query.query_id,
        index_version=config.index_version,
        corpus_version=config.corpus_version,
        bm25_candidates=tuple(lexical),
        vector_candidates=tuple(semantic),
        fused_candidates=tuple(fused),
        stage_latency_ms={"bm25": 0, "vector": 0, "fusion": 0},
        pool_hash=pool_hash,
    )


def _map_hits(
    hits: Sequence[object],
    expected_channel: str,
    stage: str,
    config: RetrievalConfig,
    content_vectors: Mapping[str, Sequence[float]],
) -> list[ScoredChunk]:
    if isinstance(hits, (str, bytes)) or not isinstance(hits, Sequence):
        raise ValueError(f"{expected_channel} hits must be a sequence")
    mapped: list[ScoredChunk] = []
    seen: set[str] = set()
    for hit in hits:
        if _read(hit, "document_kind", "evidence") != "evidence":
            continue  # Wiki navigation is not medical Evidence.
        if _read(hit, "channel") != expected_channel:
            raise ValueError(f"A3 hit channel mismatch: expected {expected_channel}")
        if _read(hit, "index_version") != config.index_version or _read(hit, "corpus_version") != config.corpus_version:
            raise ValueError("A3 SearchHit index/corpus version mismatch")
        if _read(hit, "live_state") != "live" or _read(hit, "tombstone") is not False:
            raise ValueError("A3 SearchHit must be live and non-tombstoned")
        chunk_id = _required_text(hit, "chunk_id")
        if chunk_id in seen:
            raise ValueError(f"duplicate A3 SearchHit chunk_id: {chunk_id}")
        seen.add(chunk_id)
        evidence_id = _required_text(hit, "evidence_id")
        metadata = _mapping(_read(hit, "metadata", {}))
        mock = bool(_read(hit, "mock", False))
        stable_id = str(metadata.get("stable_id") or "").strip()
        if not stable_id:
            if not mock:
                raise ValueError("production A3 SearchHit requires metadata.stable_id")
            stable_id = f"upstream:MOCK:{evidence_id}"
        if mock and any(metadata.get(name) for name in ("url", "pmid", "doi", "nct_id", "guideline_name")):
            raise ValueError("mock A3 SearchHit must not carry external citation identifiers")
        chunk_hash = _required_text(hit, "chunk_content_hash")
        evidence_hash = _required_text(hit, "evidence_content_hash")
        span_refs = tuple(_span_mapping(item, chunk_id, chunk_hash, evidence_hash) for item in (_read(hit, "span_refs", ()) or ()))
        chunk = EvidenceChunk(
            chunk_id=chunk_id,
            evidence_id=evidence_id,
            stable_id=stable_id,
            text=_required_text(hit, "text"),
            title=_required_text(hit, "title"),
            source_type=_required_text(hit, "source_type"),
            url=str(metadata.get("url") or ""),
            published_at=_iso_datetime(_read(hit, "published_at")),
            evidence_level=str(_read(hit, "evidence_level") or "unknown"),
            topic=str(metadata.get("topic") or ""),
            pico_population=_terms(_read(hit, "population")),
            pico_intervention=_terms(_read(hit, "intervention")),
            pico_comparator=_terms(_read(hit, "comparator")),
            pico_outcome=_terms(_read(hit, "outcome")),
            content_vector=_vector(content_vectors.get(chunk_id, ())),
            content_hash=chunk_hash,
            page=str(_read(hit, "raw_page") or _read(hit, "page") or ""),
            section=str(_read(hit, "section") or ""),
            span_refs=span_refs,
            fetched_at=str(metadata.get("fetched_at")) if metadata.get("fetched_at") else None,
            evidence_content_hash=evidence_hash,
            chunk_policy_version=_required_text(hit, "chunk_policy_version"),
            embedding_model=str(_read(hit, "embedding_model") or ""),
            embedding_revision=str(_read(hit, "embedding_revision") or ""),
            mock=mock,
            is_tombstoned=False,
            index_version=config.index_version,
            corpus_version=config.corpus_version,
        )
        score = _score(hit, expected_channel)
        raw_score = _read(hit, "raw_score")
        distance = _read(hit, "distance")
        mapped.append(
            ScoredChunk(
                chunk=chunk,
                score=score,
                rank=int(_read(hit, "rank")),
                stage=stage,
                feature_scores={
                    "a3_raw_score": _finite_or_none(raw_score),
                    "a3_distance": _finite_or_none(distance),
                },
            )
        )
    mapped.sort(key=lambda item: item.rank)
    return mapped


def _score(hit: object, channel: str) -> float:
    raw = _read(hit, "raw_score")
    if raw is not None:
        # BM25 implementations may emit negative raw values on tiny corpora.
        # RRF consumes the frozen rank, not this magnitude.  Preserve the raw
        # value in feature_scores and expose only a nonnegative stage score.
        value = _finite_or_none(raw)
        if value is None:
            raise ValueError("A3 raw_score must be finite")
        return max(0.0, value)
    if channel == "vector":
        distance = _read(hit, "distance")
        if distance is not None:
            # A3 manifest freezes cosine distance.  This is a ranking
            # transformation only, never a calibrated quality probability.
            return max(0.0, 1.0 - _nonnegative(distance, "distance"))
    raise ValueError(f"A3 {channel} SearchHit is missing a ranking score")


def _finite_or_none(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, Real) or isinstance(value, bool) or not isfinite(float(value)):
        raise ValueError("A3 ranking diagnostic must be a finite number or null")
    return float(value)


def _span_mapping(item: object, chunk_id: str, chunk_hash: str, evidence_hash: str) -> Mapping[str, object]:
    if hasattr(item, "model_dump"):
        data = item.model_dump(mode="json")
    else:
        data = dict(_mapping(item))
    if data.get("chunk_id") != chunk_id:
        raise ValueError("A3 span_ref chunk_id mismatch")
    if data.get("chunk_content_hash") != chunk_hash or data.get("evidence_content_hash") != evidence_hash:
        raise ValueError("A3 span_ref hash mismatch")
    return data


def _read(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("A3 metadata/span must be a mapping")
    return value


def _required_text(value: object, name: str) -> str:
    text = str(_read(value, name) or "").strip()
    if not text:
        raise ValueError(f"A3 SearchHit missing {name}")
    return text


def _terms(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item).strip())
    raise ValueError("A3 PICO value must be string/sequence/null")


def _vector(value: Sequence[float]) -> tuple[float, ...]:
    result = tuple(float(item) for item in value)
    if any(not isfinite(item) for item in result):
        raise ValueError("A3 content vector contains a non-finite value")
    return result


def _nonnegative(value: object, name: str) -> float:
    if not isinstance(value, Real) or isinstance(value, bool) or not isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"A3 {name} must be finite and nonnegative")
    return float(value)


def _iso_datetime(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError as error:
        raise ValueError("A3 published_at must be ISO datetime") from error


def _hash(query: Query, lexical: Sequence[ScoredChunk], vector: Sequence[ScoredChunk], fused: Sequence[Candidate]) -> str:
    canonical = "\x1f".join((
        query.query_id,
        query.text,
        ",".join(f"{item.chunk.chunk_id}:{item.rank}" for item in lexical),
        ",".join(f"{item.chunk.chunk_id}:{item.rank}" for item in vector),
        ",".join(f"{item.chunk.chunk_id}:{item.rrf_score:.17g}" for item in fused),
    ))
    return sha256(canonical.encode("utf-8")).hexdigest()
