"""Tests for the Gate1 source-provenance gate (5.7 来源门禁)."""

from __future__ import annotations

from retrieval.gate import SourceGateVerdict, check_source_gate
from retrieval.models import EvidenceChunk


def _chunk(**changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": "c1",
        "evidence_id": "e1",
        "stable_id": "PMID:100001",
        "text": "A randomized trial result.",
        "source_type": "pubmed",
        "url": "https://pubmed.ncbi.nlm.nih.gov/100001/",
        "published_at": "2024-01-15",
        "fetched_at": "2026-08-10T09:00:00Z",
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


def test_complete_chunk_passes_gate() -> None:
    verdict = check_source_gate(_chunk())

    assert verdict.passed is True
    assert verdict.missing == ()


def test_missing_fetched_at_fails_gate() -> None:
    verdict = check_source_gate(_chunk(fetched_at=None))

    assert verdict.passed is False
    assert "fetched_at" in verdict.missing


def test_missing_url_and_source_type_fail_gate() -> None:
    verdict = check_source_gate(_chunk(url="", source_type=""))

    assert verdict.passed is False
    assert "url" in verdict.missing
    assert "source_type" in verdict.missing


def test_missing_published_at_fails_gate_for_non_guideline() -> None:
    verdict = check_source_gate(_chunk(published_at=None))

    assert verdict.passed is False
    assert "published_at" in verdict.missing


def test_guideline_with_versioned_name_passes_without_date() -> None:
    chunk = _chunk(
        source_type="guideline",
        stable_id="GUIDELINE:CN-Hypertension-2024",
        guideline_name="中国高血压防治指南（2024年修订版）",
        published_at=None,
    )

    assert check_source_gate(chunk).passed is True


def test_guideline_without_version_name_fails_gate() -> None:
    chunk = _chunk(source_type="guideline", published_at=None)

    assert check_source_gate(chunk).passed is False
    assert "published_at" in check_source_gate(chunk).missing


def test_gate_rejects_non_iso_dates() -> None:
    verdict = check_source_gate(_chunk(published_at="not-a-date"))

    assert verdict.passed is False
    assert "published_at" in verdict.missing


def test_gate_accepts_iso_datetime_for_published_at() -> None:
    verdict = check_source_gate(_chunk(published_at="2024-01-15T10:00:00Z"))

    assert verdict.passed is True


def test_verdict_contract_validation() -> None:
    assert SourceGateVerdict(passed=True).missing == ()
    try:
        SourceGateVerdict(passed=True, missing=("stable_id",))
        raise AssertionError("passing verdict must not list missing fields")
    except ValueError:
        pass
    try:
        SourceGateVerdict(passed=False, missing=("",))
        raise AssertionError("missing fields must be nonblank")
    except ValueError:
        pass
