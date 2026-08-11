"""Synthetic smoke 评测冒烟测试：数据契约、冻结配置、mock 隔离（P1 交付物）。

这里的一切数据都是 MOCK-A4-* 合成 fixture（mock=true），指标是 pipeline
smoke/proxy，**不是**人工 gold、**不是**正式检索质量或临床效果声明。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from retrieval.config_io import config_matches_yaml, load_config_yaml
from retrieval.evaluation import evaluate_ranking, evaluate_span_proxy_metrics
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

_FABRICATED_PATTERNS = (
    "PMID:", "DOI:", "NCT0", "https://", "http://",
    "10.1000", "10.3760", "guideline/20", "clinicaltrials.gov",
    "pubmed.ncbi.nlm.nih.gov", "chinahbp.org", "chinalipid.org",
    "cds.org.cn", "europepmc.org",
)


@pytest.fixture(scope="module")
def dev_bundle():
    corpus = load_corpus()
    questions = load_questions()
    chunk_vectors, query_vectors = load_vectors()
    frozen = load_config_yaml(CONFIG_PATH)
    return corpus, questions, chunk_vectors, query_vectors, frozen


def test_dev_corpus_is_mock_and_gate_complete(dev_bundle) -> None:
    from retrieval.gate import check_source_gate

    corpus, *_ = dev_bundle
    assert len(corpus) >= 20
    for chunk in corpus:
        assert chunk.mock is True, chunk.chunk_id
        assert chunk.stable_id.startswith("MOCK-"), chunk.chunk_id
        assert check_source_gate(chunk).passed, chunk.chunk_id
    topics = {chunk.topic for chunk in corpus}
    assert {"hypertension", "lipid", "diabetes"} <= topics
    assert any(chunk.evidence_level == "guideline" and chunk.published_at < "2018-01-01" for chunk in corpus)


def test_mock_fixtures_never_contain_fabricated_identifiers(dev_bundle) -> None:
    """AGENTS: mock fixtures must not carry fabricated PMID/DOI/NCT/URL/指南编号。"""
    corpus, *_ = dev_bundle
    for chunk in corpus:
        serialized = json.dumps(
            {
                "stable_id": chunk.stable_id,
                "title": chunk.title,
                "text": chunk.text,
                "url": chunk.url,
                "pmid": chunk.pmid,
                "doi": chunk.doi,
                "nct_id": chunk.nct_id,
                "guideline_name": chunk.guideline_name,
                "authors": chunk.authors,
            },
            ensure_ascii=False,
        )
        for pattern in _FABRICATED_PATTERNS:
            assert pattern not in serialized, f"{chunk.chunk_id} contains {pattern!r}"


def test_dev_questions_carry_synthetic_smoke_qrels(dev_bundle) -> None:
    _, questions, *_ = dev_bundle
    assert len(questions) == 8
    for query, chunk_qrels, span_qrels in questions:
        assert chunk_qrels, query.query_id
        assert span_qrels, query.query_id
        assert all(grade > 0 for grade in chunk_qrels.values())
        assert query.atomic_claims, query.query_id
        assert all(chunk_id.startswith("MOCK-") for chunk_id in chunk_qrels)


def test_frozen_config_matches_committed_yaml(dev_bundle) -> None:
    *_, frozen = dev_bundle
    assert config_matches_yaml(frozen, CONFIG_PATH)
    assert frozen.rerank_config_version == "rerank-p0-v1"


def test_smoke_recall_at_50_runs_pipeline(dev_bundle) -> None:
    corpus, questions, chunk_vectors, query_vectors, frozen = dev_bundle
    service = build_service(corpus, chunk_vectors, query_vectors, frozen)

    recalls: list[float] = []
    for query, chunk_qrels, span_qrels in questions:
        result = service.search(query)
        pool_ids = [log.candidate.chunk.chunk_id for log in result.rank_log if log.candidate is not None]
        metrics = evaluate_ranking(pool_ids, chunk_qrels, POOL_RECALL_K)
        recalls.append(float(metrics["recall_at_k"]))

    # smoke 目标：管道可运行且合成语料上 Recall@50 >= 0.85；这不是正式评测。
    assert sum(recalls) / len(recalls) >= 0.85


def test_span_proxy_metrics_are_chunk_level_only(dev_bundle) -> None:
    corpus, questions, chunk_vectors, query_vectors, frozen = dev_bundle
    service = build_service(corpus, chunk_vectors, query_vectors, frozen)

    for query, chunk_qrels, span_qrels in questions:
        result = service.search(query)
        pool_ids = [log.candidate.chunk.chunk_id for log in result.rank_log if log.candidate is not None]
        metrics = evaluate_span_proxy_metrics(pool_ids, span_qrels, RANKING_NDCG_K)
        assert "span_proxy_recall_at_k" in metrics
        assert "claim_chunk_coverage_at_k" in metrics
        # 正式 span 语义由 A3 提供；proxy 指标命名不得冒充正式 span recall。
        assert "span_recall_at_k" not in metrics


def test_mock_runs_are_not_marked_formal(dev_bundle) -> None:
    raw_qrels = json.loads((DATA_DIR / "qrels.json").read_text(encoding="utf-8"))
    assert "synthetic_smoke_qrels" in raw_qrels
    assert "qrels" not in raw_qrels
    assert "span_proxy_qrels" in raw_qrels
    assert "span_qrels" not in raw_qrels
    comment = raw_qrels.get("_comment", "")
    assert "synthetic" in comment.casefold() or "SYNTHETIC" in comment
    # 明确声明不是人工 gold / 不是正式评测
    assert "非人工" in comment or "not human" in comment.casefold()
    assert "pending" in comment.casefold()


def test_dev_dataset_files_are_committed() -> None:
    for name in ("corpus.jsonl", "questions.jsonl", "qrels.json", "vectors.json"):
        assert (DATA_DIR / name).is_file(), name


def test_smoke_report_artifact_exists_and_is_labeled_smoke() -> None:
    report = Path(__file__).resolve().parent.parent / "artifacts" / "reports" / "acceptance-report.md"
    assert report.is_file(), "run: python -m scripts.run_dev_eval"
    text = report.read_text(encoding="utf-8")
    assert "Recall@50" in text
    assert "局限与职责边界" in text
    assert "smoke" in text.casefold() or "合成" in text
