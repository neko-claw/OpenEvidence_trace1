from __future__ import annotations

from math import log2
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from retrieval import evaluate_ranking as public_evaluate_ranking
from retrieval.evaluation import (
    duplicate_rate,
    evaluate_ranking,
    hit_at_k,
    mrr,
    ndcg_at_k,
    recall_at_k,
    source_diversity,
    success_at_k,
    write_run_jsonl,
)
from retrieval.models import Candidate, RankLog, SearchResult, SearchStatus


def test_success_at_k_is_one_when_a_relevant_document_is_in_the_cutoff() -> None:
    assert success_at_k(("not-relevant", "relevant"), {"relevant": 2}, 2) == 1.0


def test_rank_metrics_use_positive_graded_qrels_and_known_values() -> None:
    ranked = ("weak", "strong", "irrelevant")
    qrels = {"weak": 1, "strong": 3, "missing": 2, "irrelevant": 0}

    assert recall_at_k(ranked, qrels, 2) == pytest.approx(2 / 3)
    assert mrr(ranked, qrels) == 1.0
    assert hit_at_k(ranked, qrels, 2) == 1.0
    expected_ndcg = (1 + 3 / log2(3)) / (3 + 2 / log2(3))
    assert ndcg_at_k(ranked, qrels, 2) == pytest.approx(expected_ndcg)


@pytest.mark.parametrize(
    ("ranked_ids", "qrels", "k"),
    (
        (("a", "a"), {"a": 1}, 1),
        (("a",), {"a": -1}, 1),
        (("a",), {"a": float("inf")}, 1),
        (("a",), {"a": True}, 1),
        (("a",), {"a": 1}, 0),
    ),
)
def test_rank_metrics_reject_invalid_inputs(ranked_ids: object, qrels: object, k: object) -> None:
    with pytest.raises(ValueError):
        recall_at_k(ranked_ids, qrels, k)


def test_metrics_return_zero_for_empty_qrels_or_no_relevant_items() -> None:
    assert success_at_k(("a",), {}, 1) == 0.0
    assert recall_at_k(("a",), {}, 1) == 0.0
    assert mrr(("a",), {}) == 0.0
    assert ndcg_at_k(("a",), {"a": 0}, 1) == 0.0


def test_ndcg_keeps_absolute_qrel_grade_when_only_a_weaker_item_is_retrieved() -> None:
    assert ndcg_at_k(("weak",), {"weak": 1, "strong": 3}, 1) == pytest.approx(1 / 3)


def test_source_diversity_and_duplicate_rate_use_chunk_provenance(
    evidence_chunks: tuple[object, ...],
) -> None:
    first, second, third = evidence_chunks
    duplicate_document = replace(second, stable_id=first.stable_id)

    assert source_diversity((first, second, third)) == pytest.approx(2 / 3)
    assert duplicate_rate((first, duplicate_document, third)) == pytest.approx(1 / 3)
    assert source_diversity(()) == 0.0
    assert duplicate_rate(()) == 0.0


def test_evaluate_ranking_returns_immutable_bounded_metrics_and_chunk_provenance(
    evidence_chunks: tuple[object, ...],
) -> None:
    first, second, third = evidence_chunks
    duplicate_document = replace(second, stable_id=first.stable_id)

    metrics = evaluate_ranking((first, duplicate_document, third), {first.chunk_id: 2, third.chunk_id: 1}, 2)

    assert metrics["success_at_k"] == 1.0
    assert metrics["recall_at_k"] == pytest.approx(1 / 2)
    assert metrics["mrr"] == 1.0
    assert metrics["source_diversity"] == pytest.approx(2 / 3)
    assert metrics["duplicate_rate"] == pytest.approx(1 / 3)
    assert all(isinstance(value, float) and 0.0 <= value <= 1.0 for value in metrics.values())
    with pytest.raises(TypeError):
        metrics["mrr"] = 0.0  # type: ignore[index]


def test_evaluate_ranking_uses_zero_provenance_metrics_when_only_ids_are_available() -> None:
    metrics = evaluate_ranking(("chunk-1",), {"chunk-1": 1}, 1)

    assert metrics["source_diversity"] == 0.0
    assert metrics["duplicate_rate"] == 0.0


def test_evaluation_entry_point_is_exported_from_the_package() -> None:
    assert public_evaluate_ranking is evaluate_ranking


def test_readme_documents_commands_architecture_and_safety_boundary() -> None:
    """A4 集成文档（含设计说明与运行命令）必须存在并覆盖关键内容。

    main 仓库的 README.md 归 A5 所有，A4 不覆盖它；本测试检查 A4 自己的
    设计文档与脚本入口是否齐备。
    """
    design = Path("docs/superpowers/specs/2026-08-11-a4-retrieval-rerank-design.md")
    assert design.is_file()
    text = design.read_text(encoding="utf-8")
    for required_text in (
        "BM25",
        "向量",
        "RRF",
        "MMR",
        "selected_chunks",
        "corpus_version",
        "rank_log",
        "不构成医疗建议",
    ):
        assert required_text in text
    assert (Path("scripts/run_dev_eval.py")).is_file()
    assert (Path("retrieval/evaluation.py")).is_file()


def test_write_run_jsonl_creates_parent_and_roundtrips_safe_audit_fields(
    tmp_path: Path, evidence_chunks: tuple[object, ...]
) -> None:
    chunk = evidence_chunks[0]
    candidate = Candidate(chunk=chunk, rrf_score=0.02, rerank_score=0.8, feature_scores={"semantic": 0.9})
    result = SearchResult(
        query_id="patient=张三;dob=1970-01-01",
        index_version="idx-v1",
        corpus_version="corpus-v1",
        rerank_config_version="rerank-v1",
        status=SearchStatus.PARTIAL,
        selected_chunks=(chunk,),
        rank_log=(
            RankLog(
                candidate=candidate,
                feature_scores=candidate.feature_scores,
                final_rank=1,
                selected=True,
                rerank_config_version="rerank-v1",
            ),
        ),
        degradation_reasons=("vector_unavailable",),
        latency_ms=12.5,
        stage_latency_ms={"bm25": 3, "vector": 0, "total": 12},
    )
    destination = tmp_path / "artifacts" / "runs" / "run.jsonl"

    returned = write_run_jsonl(destination, result)

    assert returned == destination
    record = json.loads(destination.read_text(encoding="utf-8").strip())
    assert "query_id" not in record
    assert record["query_id_hash"] == sha256("patient=张三;dob=1970-01-01".encode("utf-8")).hexdigest()
    assert record["index_version"] == "idx-v1"
    assert record["corpus_version"] == "corpus-v1"
    assert record["rerank_config_version"] == "rerank-v1"
    assert record["status"] == "partial"
    assert record["degradation_reasons"] == ["vector_unavailable"]
    assert record["timing_ms"] == {"bm25": 3, "vector": 0, "total": 12}
    assert record["selected_chunk_ids"] == [chunk.chunk_id]
    assert record["rank_log"][0]["candidate"]["chunk_id"] == chunk.chunk_id
    serialized = destination.read_text(encoding="utf-8")
    assert "secret-query" not in serialized
    assert "patient=张三;dob=1970-01-01" not in serialized


def test_write_run_jsonl_rejects_non_utf8_contract_strings_before_creating_a_file(tmp_path: Path) -> None:
    result = SearchResult(
        query_id="patient\ud800",
        index_version="idx-v1",
        rerank_config_version="rerank-v1",
        status=SearchStatus.EMPTY,
    )
    destination = tmp_path / "not-created" / "run.jsonl"

    with pytest.raises(ValueError, match="UTF-8"):
        write_run_jsonl(destination, result)

    assert not destination.exists()
    assert not destination.parent.exists()


# --- synthetic span-proxy qrels（chunk 级代理；正式 A3 Span Schema pending）---


def test_aggregate_chunk_qrels_takes_max_grade_per_chunk() -> None:
    from retrieval.evaluation import aggregate_chunk_qrels

    aggregated = aggregate_chunk_qrels(
        {
            "span-1": ("chunk-a", "point-1", 3.0),
            "span-2": ("chunk-a", "point-2", 1.0),
            "span-3": ("chunk-b", "point-1", 2.0),
        }
    )

    assert aggregated == {"chunk-a": 3.0, "chunk-b": 2.0}


def test_span_proxy_recall_at_k_counts_spans_whose_chunk_is_in_top_k() -> None:
    from retrieval.evaluation import span_proxy_recall_at_k

    span_qrels = {
        "s1": ("chunk-a", "point-1", 3.0),
        "s2": ("chunk-b", "point-1", 2.0),
        "s3": ("chunk-c", "point-2", 0.0),  # irrelevant span ignored
    }
    assert span_proxy_recall_at_k(["chunk-a", "chunk-b"], span_qrels, 1) == 0.5
    assert span_proxy_recall_at_k(["chunk-a", "chunk-b"], span_qrels, 2) == 1.0


def test_span_proxy_ndcg_at_k_uses_chunk_position_for_its_spans() -> None:
    from retrieval.evaluation import span_proxy_ndcg_at_k

    span_qrels = {"s1": ("chunk-a", "point-1", 3.0), "s2": ("chunk-b", "point-1", 1.0)}
    # chunk-a 在 rank1、chunk-b 在 rank2 → 完美排序，nDCG=1
    assert span_proxy_ndcg_at_k(["chunk-a", "chunk-b"], span_qrels, 2) == 1.0
    # 倒序 → nDCG < 1（且明显低于完美排序）
    reversed_ndcg = span_proxy_ndcg_at_k(["chunk-b", "chunk-a"], span_qrels, 2)
    assert 0.5 < reversed_ndcg < 1.0


def test_span_proxy_mrr_returns_reciprocal_rank_of_first_relevant_span_chunk() -> None:
    from retrieval.evaluation import span_proxy_mrr

    span_qrels = {"s1": ("chunk-a", "point-1", 3.0)}
    assert span_proxy_mrr(["chunk-a"], span_qrels) == 1.0
    assert span_proxy_mrr(["other", "chunk-a"], span_qrels) == 0.5
    assert span_proxy_mrr(["other"], span_qrels) == 0.0


def test_claim_chunk_coverage_at_k_covers_atomic_points() -> None:
    from retrieval.evaluation import claim_chunk_coverage_at_k

    span_qrels = {
        "s1": ("chunk-a", "point-1", 3.0),
        "s2": ("chunk-b", "point-2", 2.0),
        "s3": ("chunk-c", "point-2", 1.0),
    }
    # top-1 只覆盖 point-1
    assert claim_chunk_coverage_at_k(["chunk-a"], span_qrels, 1) == 0.5
    # top-2 覆盖两个原子主张
    assert claim_chunk_coverage_at_k(["chunk-a", "chunk-b"], span_qrels, 2) == 1.0


def test_evaluate_span_proxy_metrics_returns_bounded_metrics() -> None:
    from retrieval.evaluation import evaluate_span_proxy_metrics

    metrics = evaluate_span_proxy_metrics(
        ["chunk-a", "chunk-b"],
        {"s1": ("chunk-a", "point-1", 3.0), "s2": ("chunk-b", "point-1", 2.0)},
        2,
    )

    assert set(metrics) == {
        "span_proxy_success_at_k",
        "span_proxy_recall_at_k",
        "span_proxy_mrr",
        "span_proxy_ndcg_at_k",
        "claim_chunk_coverage_at_k",
    }
    assert all(0.0 <= value <= 1.0 for value in metrics.values())
    assert metrics["span_proxy_recall_at_k"] == 1.0
    assert metrics["claim_chunk_coverage_at_k"] == 1.0


def test_span_proxy_qrels_validation_rejects_malformed_values() -> None:
    from retrieval.evaluation import span_proxy_recall_at_k

    for bad in (
        {"s1": ("chunk-a",)},  # 元组长度不足
        {"s1": ("", "point-1", 3.0)},  # 空 chunk_id
        {"s1": ("chunk-a", "point-1", -1.0)},  # 负等级
        {"": ("chunk-a", "point-1", 3.0)},  # 空 span_id
    ):
        try:
            span_proxy_recall_at_k(["chunk-a"], bad, 1)
            raise AssertionError("malformed span proxy qrels must be rejected")
        except ValueError:
            pass
