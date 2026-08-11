"""Tests for claim-evidence pre-check and conflict detection (4.2 step 6)."""

from __future__ import annotations

from retrieval.models import EvidenceChunk, Query
from retrieval.support_check import check_claims, detect_conflicts


def _chunk(chunk_id: str, text: str, **changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": chunk_id,
        "evidence_id": f"evidence-{chunk_id}",
        "stable_id": f"PMID:{chunk_id}",
        "text": text,
        "source_type": "pubmed",
        "evidence_level": "rct",
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


def _query(**changes: object) -> Query:
    values: dict[str, object] = {"query_id": "q1", "text": "老年高血压治疗"}
    values.update(changes)
    return Query(**values)  # type: ignore[arg-type]


def test_claim_is_supported_when_chunk_covers_its_tokens() -> None:
    selected = (
        _chunk("c1", "Amlodipine reduced systolic blood pressure in older adults with hypertension."),
    )
    supports = check_claims(
        _query(),
        ("amlodipine reduces blood pressure in older adults",),
        selected,
    )

    assert supports[0].decision == "supported"
    assert supports[0].evidence_ids == ("evidence-c1",)


def test_claim_is_insufficient_when_no_chunk_overlaps() -> None:
    selected = (_chunk("c1", "Statistical methods for clinical trials."),)
    supports = check_claims(_query(), ("他汀降低 LDL 胆固醇",), selected)

    assert supports[0].decision == "insufficient"
    assert supports[0].evidence_ids == ()


def test_claim_is_background_only_on_partial_overlap() -> None:
    selected = (_chunk("c1", "Hypertension is common in older adults."),)
    supports = check_claims(
        _query(),
        ("amlodipine reduces blood pressure in older adults",),
        selected,
    )

    assert supports[0].decision == "background_only"


def test_claim_is_mismatch_on_population_conflict() -> None:
    query = _query(pico_population=("older adults",))
    selected = (
        _chunk("c1", "Amlodipine reduced blood pressure in children.", pico_population=("children",)),
    )
    supports = check_claims(
        query,
        ("amlodipine reduces blood pressure in older adults",),
        selected,
    )

    assert supports[0].decision == "mismatch"
    assert "population" in supports[0].reason


def test_conflict_detection_finds_population_conflict() -> None:
    selected = (
        _chunk("c1", "trial", pico_population=("older adults",)),
        _chunk("c2", "trial", pico_population=("children",)),
    )

    conflicts = detect_conflicts(selected)

    assert any(reason == "population" for _, _, reason in conflicts)


def test_conflict_detection_finds_time_conflict() -> None:
    selected = (
        _chunk("c1", "trial", published_at="2010-01-01"),
        _chunk("c2", "trial", published_at="2024-01-01"),
    )

    conflicts = detect_conflicts(selected)

    assert any(reason == "time" for _, _, reason in conflicts)


def test_conflict_detection_ignores_compatible_evidence() -> None:
    selected = (
        _chunk("c1", "trial", pico_population=("older adults",), published_at="2020-01-01"),
        _chunk("c2", "trial", pico_population=("older adults",), published_at="2022-01-01"),
    )

    assert detect_conflicts(selected) == ()
