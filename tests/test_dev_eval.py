"""开发集评测的冒烟测试：数据契约、冻结配置、验收指标（P1-1 交付物）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from retrieval.config_io import config_matches_yaml, load_config_yaml
from retrieval.evaluation import evaluate_ranking, evaluate_span_ranking
from scripts.run_dev_eval import (
    CONFIG_PATH,
    DATA_DIR,
    build_service,
    load_corpus,
    load_questions,
    load_vectors,
)

POOL_RECALL_K = 50
RANKING_NDCG_K = 8


@pytest.fixture(scope="module")
def dev_bundle():
    corpus = load_corpus()
    questions = load_questions()
    chunk_vectors, query_vectors = load_vectors()
    frozen = load_config_yaml(CONFIG_PATH)
    return corpus, questions, chunk_vectors, query_vectors, frozen


def test_dev_corpus_is_gate_complete(dev_bundle) -> None:
    from retrieval.gate import check_source_gate

    corpus, *_ = dev_bundle
    assert len(corpus) >= 20
    for chunk in corpus:
        assert check_source_gate(chunk).passed, chunk.chunk_id
    # 每个领域都有指南、RCT 与旧指南（反例）三类证据。
    topics = {chunk.topic for chunk in corpus}
    assert {"hypertension", "lipid", "diabetes"} <= topics
    assert any(chunk.evidence_level == "guideline" and chunk.published_at < "2018-01-01" for chunk in corpus)


def test_dev_questions_carry_qrels_at_both_granularities(dev_bundle) -> None:
    _, questions, *_ = dev_bundle
    assert len(questions) == 8
    for query, chunk_qrels, span_qrels in questions:
        assert chunk_qrels, query.query_id
        assert span_qrels, query.query_id
        assert all(grade > 0 for grade in chunk_qrels.values())
        assert query.atomic_claims, query.query_id


def test_frozen_config_matches_committed_yaml(dev_bundle) -> None:
    *_, frozen = dev_bundle
    assert config_matches_yaml(frozen, CONFIG_PATH)
    assert frozen.rerank_config_version == "rerank-p0-v1"


def test_dev_recall_at_50_meets_acceptance_target(dev_bundle) -> None:
    corpus, questions, chunk_vectors, query_vectors, frozen = dev_bundle
    service = build_service(corpus, chunk_vectors, query_vectors, frozen)

    recalls: list[float] = []
    for query, chunk_qrels, span_qrels in questions:
        result = service.search(query)
        pool_ids = [log.candidate.chunk.chunk_id for log in result.rank_log if log.candidate is not None]
        metrics = evaluate_ranking(pool_ids, chunk_qrels, POOL_RECALL_K)
        recalls.append(float(metrics["recall_at_k"]))
        assert float(metrics["success_at_k"]) == 1.0, query.query_id

    assert sum(recalls) / len(recalls) >= 0.85


def test_dev_span_metrics_are_reported(dev_bundle) -> None:
    corpus, questions, chunk_vectors, query_vectors, frozen = dev_bundle
    service = build_service(corpus, chunk_vectors, query_vectors, frozen)

    for query, chunk_qrels, span_qrels in questions:
        result = service.search(query)
        pool_ids = [log.candidate.chunk.chunk_id for log in result.rank_log if log.candidate is not None]
        metrics = evaluate_span_ranking(pool_ids, span_qrels, RANKING_NDCG_K)
        assert metrics["span_recall_at_k"] == 1.0, query.query_id


def test_dev_dataset_files_are_committed() -> None:
    for name in ("corpus.jsonl", "questions.jsonl", "qrels.json", "vectors.json"):
        assert (DATA_DIR / name).is_file(), name


def test_acceptance_report_artifact_exists() -> None:
    report = Path(__file__).resolve().parent.parent / "artifacts" / "reports" / "acceptance-report.md"
    assert report.is_file(), "run: python -m scripts.run_dev_eval"
    text = report.read_text(encoding="utf-8")
    assert "Recall@50" in text
    assert "局限与职责边界" in text
