"""Tests for claim-evidence alignment pre-check and conflict detection (4.2 step 6).

The pre-check is token-overlap only and must NEVER emit A5's SUPPORTED
verdict: decisions are ALIGNED | BACKGROUND | MISMATCH | INSUFFICIENT |
UNKNOWN, with method=token_overlap_heuristic recorded.
"""

from __future__ import annotations

from retrieval.models import EvidenceChunk, Query
from retrieval.support_check import check_alignment, detect_conflicts


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


def test_claim_is_aligned_when_chunk_covers_its_tokens() -> None:
    selected = (
        _chunk("c1", "Amlodipine reduced systolic blood pressure in older adults with hypertension."),
    )
    hints = check_alignment(
        _query(),
        ("amlodipine reduces blood pressure in older adults",),
        selected,
    )

    assert hints[0].decision == "ALIGNED"
    assert hints[0].evidence_ids == ("evidence-c1",)
    assert hints[0].method == "token_overlap_heuristic"
    assert hints[0].threshold_version


def test_alignment_never_emits_a5_supported_verdict() -> None:
    selected = (
        _chunk("c1", "Amlodipine reduced systolic blood pressure in older adults with hypertension."),
    )
    hints = check_alignment(
        _query(),
        ("amlodipine reduces blood pressure in older adults",),
        selected,
    )

    assert hints[0].decision == "ALIGNED"
    assert hints[0].decision != "SUPPORTED"


def test_claim_is_insufficient_when_no_chunk_overlaps() -> None:
    selected = (_chunk("c1", "Statistical methods for clinical trials."),)
    hints = check_alignment(_query(), ("他汀降低 LDL 胆固醇",), selected)

    assert hints[0].decision == "INSUFFICIENT"
    assert hints[0].evidence_ids == ()


def test_claim_is_background_only_on_partial_overlap() -> None:
    selected = (_chunk("c1", "Hypertension is common in older adults."),)
    hints = check_alignment(
        _query(),
        ("amlodipine reduces blood pressure in older adults",),
        selected,
    )

    assert hints[0].decision == "BACKGROUND"


def test_claim_is_mismatch_on_population_conflict() -> None:
    query = _query(pico_population=("older adults",))
    selected = (
        _chunk("c1", "Amlodipine reduced blood pressure in children.", pico_population=("children",)),
    )
    hints = check_alignment(
        query,
        ("amlodipine reduces blood pressure in older adults",),
        selected,
    )

    assert hints[0].decision == "MISMATCH"
    assert "population" in hints[0].reason


def test_unknown_when_claim_has_no_content_tokens() -> None:
    hints = check_alignment(_query(), ("，",), ())

    assert hints[0].decision == "UNKNOWN"


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
