"""Tests for the Evidence Mixer (4.3 可信池) and its service wiring."""

from __future__ import annotations

from dataclasses import replace

import pytest

from retrieval.adaptive import compute_verified_ratio
from retrieval.bm25 import BM25Index
from retrieval.config import RetrievalConfig
from retrieval.evidence_mixer import mix_evidence
from retrieval.models import Candidate, EvidenceChunk, Query, SearchStatus
from retrieval.service import RetrievalService
from retrieval.vector import InMemoryVectorSearch


def _chunk(chunk_id: str, *, trust_tier: str = "discovery") -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        evidence_id=f"evidence-{chunk_id}",
        stable_id=f"PMID:{chunk_id}",
        text="Clinical evidence snippet for the query.",
        source_type="pubmed",
        evidence_level="rct",
        trust_tier=trust_tier,
    )


def _candidate(chunk_id: str, *, trust_tier: str = "discovery") -> Candidate:
    return Candidate(chunk=_chunk(chunk_id, trust_tier=trust_tier), rrf_score=0.01)


def _query(**changes: object) -> Query:
    values: dict[str, object] = {"query_id": "q1", "text": "hypertension treatment"}
    values.update(changes)
    return Query(**values)  # type: ignore[arg-type]


# --- mix_evidence ----------------------------------------------------------


def test_mix_takes_ratio_from_verified_pool_and_rest_from_discovery() -> None:
    verified = [_candidate(f"v{i}", trust_tier="verified") for i in range(80)]
    discovery = [_candidate(f"d{i}") for i in range(80)]
    mixed, log = mix_evidence([*verified, *discovery], 0.9, 80)
    assert [candidate.chunk.chunk_id for candidate in mixed[:72]] == [f"v{i}" for i in range(72)]
    assert [candidate.chunk.chunk_id for candidate in mixed[72:]] == [f"d{i}" for i in range(8)]
    assert len(mixed) == 80
    assert log.verified_target == 72 and log.discovery_target == 8
    assert log.verified_taken == 72 and log.discovery_taken == 8
    assert log.shortfall == 0


def test_mix_preserves_each_pool_rrf_order() -> None:
    candidates: list[Candidate] = []
    for i in range(10):
        candidates.append(_candidate(f"v{i}", trust_tier="verified"))
        candidates.append(_candidate(f"d{i}"))
    mixed, log = mix_evidence(candidates, 0.5, 20)
    assert log.verified_target == 10 and log.discovery_target == 10
    assert [candidate.chunk.chunk_id for candidate in mixed] == [
        *[f"v{i}" for i in range(10)],
        *[f"d{i}" for i in range(10)],
    ]


def test_verified_shortfall_is_filled_from_discovery() -> None:
    verified = [_candidate(f"v{i}", trust_tier="verified") for i in range(5)]
    discovery = [_candidate(f"d{i}") for i in range(20)]
    mixed, log = mix_evidence([*verified, *discovery], 0.8, 10)
    assert log.verified_target == 8 and log.verified_taken == 5 and log.shortfall == 3
    assert log.discovery_target == 2 and log.discovery_taken == 5
    assert len(mixed) == 10
    assert [candidate.chunk.chunk_id for candidate in mixed[:5]] == [f"v{i}" for i in range(5)]
    assert [candidate.chunk.chunk_id for candidate in mixed[5:]] == [f"d{i}" for i in range(5)]


def test_empty_verified_pool_degrades_to_discovery_not_empty() -> None:
    discovery = [_candidate(f"d{i}") for i in range(6)]
    mixed, log = mix_evidence(discovery, 0.9, 5)
    assert len(mixed) == 5
    assert all(candidate.chunk.trust_tier == "discovery" for candidate in mixed)
    assert log.verified_available == 0 and log.shortfall == 4


def test_ratio_zero_and_one_select_single_pool() -> None:
    verified = [_candidate(f"v{i}", trust_tier="verified") for i in range(5)]
    discovery = [_candidate(f"d{i}") for i in range(5)]
    all_discovery, log0 = mix_evidence([*verified, *discovery], 0.0, 5)
    assert all(candidate.chunk.trust_tier == "discovery" for candidate in all_discovery)
    assert log0.verified_target == 0
    all_verified, log1 = mix_evidence([*verified, *discovery], 1.0, 5)
    assert all(candidate.chunk.trust_tier == "verified" for candidate in all_verified)
    assert log1.discovery_target == 0


def test_mix_is_capped_at_candidate_limit() -> None:
    verified = [_candidate(f"v{i}", trust_tier="verified") for i in range(100)]
    mixed, log = mix_evidence(verified, 0.9, 80)
    assert len(mixed) == 72
    assert log.discovery_taken == 0


def test_mix_rejects_bad_inputs() -> None:
    candidate = _candidate("v1", trust_tier="verified")
    with pytest.raises(ValueError):
        mix_evidence([candidate], -0.1, 5)
    with pytest.raises(ValueError):
        mix_evidence([candidate], 1.5, 5)
    with pytest.raises(ValueError):
        mix_evidence([candidate], 0.5, 0)
    with pytest.raises(ValueError):
        mix_evidence([candidate], 0.5, 5.0)
    with pytest.raises(ValueError):
        mix_evidence([object()], 0.5, 5)


# --- compute_verified_ratio ------------------------------------------------


def test_verified_ratio_base_by_question_type() -> None:
    config = RetrievalConfig()
    expected = {
        "guideline": 0.9,
        "latest_trial": 0.85,
        "therapy": 0.8,
        "generic": 0.65,
        "diagnosis": 0.65,
        "prognosis": 0.65,
    }
    for question_type, ratio in expected.items():
        assert compute_verified_ratio(_query(question_type=question_type), config)[0] == ratio


def test_verified_ratio_freshness_bump_and_cap() -> None:
    config = RetrievalConfig()
    base, _ = compute_verified_ratio(_query(question_type="generic"), config)
    current, actions = compute_verified_ratio(
        _query(question_type="generic", freshness="current"), config
    )
    latest, _ = compute_verified_ratio(_query(question_type="generic", freshness="latest"), config)
    assert base == 0.65
    assert current == pytest.approx(0.7) and latest == pytest.approx(0.7)
    assert any("freshness" in action for action in actions)

    tight = RetrievalConfig(verified_ratio_max=0.90)
    capped, capped_actions = compute_verified_ratio(
        _query(question_type="guideline", freshness="latest"), tight
    )
    assert capped == 0.90
    assert any("capped" in action for action in capped_actions)


# --- EvidenceChunk trust tier ----------------------------------------------


def test_trust_tier_is_validated_and_promotion_keeps_content_hash() -> None:
    with pytest.raises(ValueError):
        _chunk("bad", trust_tier="promoted")
    with pytest.raises(ValueError):
        EvidenceChunk(
            chunk_id="c1",
            evidence_id="e1",
            stable_id="PMID:1",
            text="t",
            verification_method=123,  # type: ignore[arg-type]
        )
    base = _chunk("v1", trust_tier="discovery")
    promoted = replace(base, trust_tier="verified", verification_method="pubmed_pmid_resolution")
    assert promoted.verified is True
    assert base.verified is False
    assert promoted.content_hash == base.content_hash


# --- service wiring --------------------------------------------------------


def _config() -> RetrievalConfig:
    return RetrievalConfig(
        bm25_top_k=15,
        vector_top_k=15,
        fusion_top_k=12,
        rerank_top_k=12,
        selection_top_k=2,
        index_version="index-20260811",
        corpus_version="corpus-20260811",
        rerank_config_version="rerank-20260811",
    )


def _indexed(chunks: tuple[EvidenceChunk, ...]) -> tuple[EvidenceChunk, ...]:
    return tuple(
        replace(chunk, index_version="index-20260811", corpus_version="corpus-20260811")
        for chunk in chunks
    )


def test_service_mixes_verified_and_discovery_before_rerank() -> None:
    verified = [
        EvidenceChunk(
            chunk_id=f"v{i}",
            evidence_id=f"evidence-v{i}",
            stable_id=f"PMID:{1000 + i}",
            text=f"hypertension treatment reduces blood pressure in trial {i}.",
            source_type="pubmed",
            evidence_level="rct",
            trust_tier="verified",
        )
        for i in range(10)
    ]
    discovery = [
        EvidenceChunk(
            chunk_id=f"d{i}",
            evidence_id=f"evidence-d{i}",
            stable_id=f"PMID:{2000 + i}",
            text=f"unrelated disease mechanisms discussion {i}.",
            source_type="web",
            evidence_level="unknown",
            trust_tier="discovery",
        )
        for i in range(5)
    ]
    chunks = _indexed((*verified, *discovery))
    vectors = {
        chunk.chunk_id: (chunk, (0.9, 0.1 + index * 0.001))
        for index, chunk in enumerate(chunks[:10])
    }
    vectors.update(
        {
            chunk.chunk_id: (chunk, (0.1, 0.9 + index * 0.001))
            for index, chunk in enumerate(chunks[10:])
        }
    )
    service = RetrievalService(
        BM25Index(chunks),
        InMemoryVectorSearch(vectors),
        lambda _query: (1.0, 0.0),
        _config(),
    )
    result = service.search(
        Query(query_id="q-mix", text="hypertension", question_type="therapy")
    )
    assert result.status is SearchStatus.OK
    assert "mix" in result.stage_latency_ms
    tiers = [log.candidate.chunk.trust_tier for log in result.rank_log]
    # therapy ratio 0.8 on a 12-candidate limit -> 10 verified / 2 discovery;
    # the 12 fused candidates are exactly the 10 verified + top-2 discovery.
    assert tiers.count("verified") == 10
    assert tiers.count("discovery") == 2
    assert "mix verified/discovery=10/2" in result.retrieval_warning
