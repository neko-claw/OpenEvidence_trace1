"""Tests for the acceptance report generator and counterexamples."""

from __future__ import annotations

from retrieval.ablation import AblationRow
from retrieval.models import EvidenceChunk, Query
from retrieval.support_check import ClaimSupport
from scripts.report import find_old_but_authoritative, find_relevant_but_not_supporting, render_report


def _chunk(chunk_id: str, **changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": chunk_id,
        "evidence_id": f"evidence-{chunk_id}",
        "stable_id": f"PMID:{chunk_id}",
        "text": "Clinical evidence snippet.",
        "source_type": "pubmed",
        "evidence_level": "rct",
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


def test_find_relevant_but_not_supporting_flags_high_ranked_unsupported_chunk() -> None:
    candidates = (_chunk("c1"), _chunk("c2"))
    supports = (
        ClaimSupport(claim_index=0, claim_text="claim", decision="supported", evidence_ids=("evidence-c1",)),
    )

    rows = find_relevant_but_not_supporting(candidates, supports)

    assert any("c2" in row for row in rows)
    assert all("c1" not in row for row in rows)


def test_find_old_but_authoritative_flags_old_guidelines() -> None:
    candidates = (
        _chunk("old-guide", published_at="2015-01-01", evidence_level="guideline"),
        _chunk("new-rct", published_at="2024-01-01", evidence_level="rct"),
    )

    rows = find_old_but_authoritative(candidates, max_age_years=5)

    assert any("old-guide" in row for row in rows)
    assert all("new-rct" not in row for row in rows)


def test_render_report_includes_sections_and_decisions() -> None:
    row = AblationRow(
        condition="R1",
        recall_at_k0=0.9,
        ndcg_at_k1=0.7,
        mrr=0.6,
        source_diversity=0.5,
        duplicate_rate=0.1,
        citation_precision=0.85,
        citation_coverage=0.8,
        claim_support_rate=0.75,
        conflict_rate=0.0,
        context_tokens=1200,
        estimated_cost_usd=0.0024,
        latency_ms=42.0,
    )
    report = render_report(
        [row],
        {"cross_encoder": "not_required: R1 already meets targets"},
        (_chunk("c1"),),
        (ClaimSupport(claim_index=0, claim_text="c", decision="supported", evidence_ids=("evidence-c1",)),),
    )

    assert "| R1 | 0.900 |" in report
    assert "not_required" in report
    assert "相关但不支持" in report
    assert "旧但权威" in report
    assert "验收报告" in report
