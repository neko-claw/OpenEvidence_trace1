"""Synthetic smoke 评测运行器：网格调参 → 冻结 → 消融 → 逐题运行 → smoke 报告。

这是 A4 管道的 **pipeline smoke** 入口，只使用合成数据（``data/dev``，全部
``mock=true``、MOCK-A4-* 内部 ID）。这些数据与指标**不是**人工 gold、**不是**
正式评测：正式 qrels 依赖 A1/B2 冻结标注与 A3 真实 Span Schema（pending）。
正式题运行前必须调用 ``require_frozen`` 校验冻结配置。所有输出写入
``artifacts/``（runs/*.jsonl、evaluation/*.csv、reports/*.md）。

用法：
    python -m scripts.run_dev_eval                 # 完整流程
    python -m scripts.run_dev_eval --no-grid       # 跳过网格（仅冻结+消融+报告）

设计约定：
- 双路召回均可用：chunk 向量与查询向量来自 ``data/dev/vectors.json``
  （scripts/build_dev_vectors.py 生成的确定性 hash 占位向量）。
- 冻结配置：``config/retrieval-p0-v1.yaml``（config_io 严格解析，漂移即失败）。
- Recall@50 在融合候选池（rank_log 全量）上计算；nDCG@8 在重排输入上计算。
  这些是 smoke 指标，仅证明管道可运行，不得用来证明正式检索质量。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from retrieval.ablation import decide, run_ablation, write_ablation_csv
from retrieval.bm25 import BM25Index
from retrieval.config import RetrievalConfig
from retrieval.config_io import config_matches_yaml, load_config_yaml
from retrieval.evaluation import (
    context_tokens,
    evaluate_ranking,
    evaluate_span_proxy_metrics,
    write_run_jsonl,
)
from retrieval.models import EvidenceChunk, Query, SearchResult
from retrieval.service import RetrievalService
from retrieval.tuning import (
    grid_details,
    verify_frozen,
    write_freeze_record,
    write_grid_details_csv,
)
from retrieval.vector import InMemoryVectorSearch

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "dev"
CONFIG_PATH = ROOT / "config" / "retrieval-p0-v1.yaml"
RUNS_DIR = ROOT / "artifacts" / "runs"
EVALUATION_DIR = ROOT / "artifacts" / "evaluation"
REPORTS_DIR = ROOT / "artifacts" / "reports"

_POOL_RECALL_K = 50
_RANKING_NDCG_K = 8

_PER_QUESTION_FIELDS = (
    "question_id", "question_type", "status", "recall_at_50_pool", "ndcg_at_8_ranking",
    "mrr_ranking", "span_proxy_recall_at_8", "span_proxy_ndcg_at_8", "claim_chunk_coverage_at_8",
    "selected_count", "context_tokens", "latency_ms", "warning",
)


def load_corpus() -> tuple[EvidenceChunk, ...]:
    chunks: list[EvidenceChunk] = []
    for line in (DATA_DIR / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        chunks.append(EvidenceChunk(**json.loads(line)))
    return tuple(chunks)


def load_questions() -> tuple[tuple[Query, dict[str, float], dict[str, tuple[str, str, float]]], ...]:
    qrels = json.loads((DATA_DIR / "qrels.json").read_text(encoding="utf-8"))
    questions: list[tuple[Query, dict[str, float], dict[str, tuple[str, str, float]]]] = []
    for line in (DATA_DIR / "questions.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        question_id = raw["question_id"]
        query = Query(
            query_id=question_id,
            text=raw["text"],
            topic=raw["topic"],
            question_type=raw["question_type"],
            freshness=raw["freshness"],
            domain=raw["domain"],
            english_terms=tuple(raw.get("english_terms", ())),
            pico_population=tuple(raw.get("pico_population", ())),
            pico_intervention=tuple(raw.get("pico_intervention", ())),
            pico_comparator=tuple(raw.get("pico_comparator", ())),
            pico_outcome=tuple(raw.get("pico_outcome", ())),
            atomic_claims=tuple(raw.get("atomic_claims", ())),
        )
        chunk_qrels = {str(key): float(grade) for key, grade in qrels["synthetic_smoke_qrels"].get(question_id, {}).items()}
        span_qrels = {
            str(span_id): (str(value[0]), str(value[1]), float(value[2]))
            for span_id, value in qrels["span_proxy_qrels"].get(question_id, {}).items()
        }
        questions.append((query, chunk_qrels, span_qrels))
    return tuple(questions)


def load_vectors() -> tuple[dict[str, tuple[float, ...]], dict[str, tuple[float, ...]]]:
    raw = json.loads((DATA_DIR / "vectors.json").read_text(encoding="utf-8"))
    return (
        {chunk_id: tuple(vector) for chunk_id, vector in raw["chunks"].items()},
        {question_id: tuple(vector) for question_id, vector in raw["queries"].items()},
    )


def build_service(
    chunks: tuple[EvidenceChunk, ...],
    chunk_vectors: dict[str, tuple[float, ...]],
    query_vectors: dict[str, tuple[float, ...]],
    config: RetrievalConfig,
) -> RetrievalService:
    return RetrievalService(
        bm25_index=BM25Index(chunks),
        vector_search=InMemoryVectorSearch({chunk.chunk_id: (chunk, chunk_vectors[chunk.chunk_id]) for chunk in chunks}),
        query_vector_provider=lambda query: query_vectors[query.query_id],
        config=config,
    )


def run_frozen_config(
    config: RetrievalConfig,
    chunks: tuple[EvidenceChunk, ...],
    chunk_vectors: dict[str, tuple[float, ...]],
    query_vectors: dict[str, tuple[float, ...]],
) -> tuple[list[dict[str, Any]], list[SearchResult]]:
    """Run every dev question once under the frozen config.

    Returns per-question metric rows and the raw ``SearchResult`` values (the
    latter feed the report's counterexample analysis).  Run logs are appended
    to ``artifacts/runs/<question_id>.jsonl``.
    """
    service = build_service(chunks, chunk_vectors, query_vectors, config)
    rows: list[dict[str, Any]] = []
    results: list[SearchResult] = []
    for query, chunk_qrels, span_qrels in load_questions():
        result = service.search(query)
        results.append(result)
        pool_ids = [log.candidate.chunk.chunk_id for log in result.rank_log if log.candidate is not None]
        ranking_ids = pool_ids[: config.rerank_top_k]
        pool_metrics = evaluate_ranking(pool_ids, chunk_qrels, _POOL_RECALL_K)
        ranking_metrics = evaluate_ranking(ranking_ids, chunk_qrels, _RANKING_NDCG_K)
        span_metrics = evaluate_span_proxy_metrics(pool_ids, span_qrels, _RANKING_NDCG_K)
        rows.append(
            {
                "question_id": query.query_id,
                "question_type": query.question_type,
                "status": result.status.value,
                "recall_at_50_pool": float(pool_metrics["recall_at_k"]),
                "ndcg_at_8_ranking": float(ranking_metrics["ndcg_at_k"]),
                "mrr_ranking": float(ranking_metrics["mrr"]),
                "span_proxy_recall_at_8": float(span_metrics["span_proxy_recall_at_k"]),
                "span_proxy_ndcg_at_8": float(span_metrics["span_proxy_ndcg_at_k"]),
                "claim_chunk_coverage_at_8": float(span_metrics["claim_chunk_coverage_at_k"]),
                "selected_count": len(result.selected_chunks),
                "context_tokens": context_tokens(result.selected_chunks),
                "latency_ms": result.latency_ms,
                "warning": result.retrieval_warning or "",
            }
        )
        write_run_jsonl(RUNS_DIR / f"{query.query_id}.jsonl", result)
    return rows, results


def write_rows_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        output.write(",".join(fields) + "\n")
        for row in rows:
            output.write(",".join(str(row[field]) for field in fields) + "\n")


def main(include_grid: bool = True) -> None:
    chunks = load_corpus()
    questions = load_questions()
    chunk_vectors, query_vectors = load_vectors()
    questions_with_qrels = [(query, qrels) for query, qrels, _ in questions]

    # 2) 冻结配置：config/retrieval-p0-v1.yaml 是唯一权威冻结副本。
    frozen = load_config_yaml(CONFIG_PATH)
    if not config_matches_yaml(frozen, CONFIG_PATH):
        raise SystemExit("frozen YAML does not match itself; config drift")

    # 1) K 网格调参（只用于开发题；选择完成后冻结）。网格必须使用与冻结记录
    # 相同的索引/语料版本，否则全部候选都会被版本过滤排除。
    if include_grid:
        details = grid_details(
            questions_with_qrels,
            chunks,
            k0_values=(30, 50, 80),
            k1_values=(20, 25),
            k2_values=(6, 8),
            query_vectors=query_vectors,
            config=frozen,
        )
        write_grid_details_csv(EVALUATION_DIR / "grid_details_dev.csv", details)

    # 3) 冻结配置下的逐题运行（先跑，让冻结记录里写入真实开发集指标）。
    rows, results = run_frozen_config(frozen, chunks, chunk_vectors, query_vectors)
    write_rows_csv(EVALUATION_DIR / "per_question_frozen.csv", rows, _PER_QUESTION_FIELDS)

    chosen = grid_details(
        questions_with_qrels,
        chunks,
        k0_values=(frozen.fusion_top_k,),
        k1_values=(frozen.rerank_top_k,),
        k2_values=(frozen.selection_top_k,),
        query_vectors=query_vectors,
        config=frozen,
    )[0]
    write_freeze_record(
        EVALUATION_DIR / "freeze.json",
        chosen=chosen,
        config=frozen,
        dev_summary={
            "recall_at_50_pool_mean": mean(float(row["recall_at_50_pool"]) for row in rows),
            "ndcg_at_8_ranking_mean": mean(float(row["ndcg_at_8_ranking"]) for row in rows),
            "span_proxy_recall_at_8_mean": mean(float(row["span_proxy_recall_at_8"]) for row in rows),
            "claim_chunk_coverage_at_8_mean": mean(float(row["claim_chunk_coverage_at_8"]) for row in rows),
        },
        note="frozen on 8 dev questions; formal questions must run under require_frozen",
    )
    if not verify_frozen(EVALUATION_DIR / "freeze.json", frozen):
        raise SystemExit("freeze record does not match frozen config")

    # 4) 消融 R0–R3。
    ablation_rows = run_ablation(questions_with_qrels, chunks, query_vectors=query_vectors, config=frozen)
    write_ablation_csv(EVALUATION_DIR / "ablation.csv", ablation_rows)
    decisions = decide(ablation_rows)

    # 5) smoke 报告（消融表、决策、反例、逐题表、局限与职责边界）。
    from scripts.report import find_old_but_authoritative, find_relevant_but_not_supporting, render_report

    claim_supports = tuple(hint for result in results for hint in result.alignment_hints)
    candidates = [
        log.candidate.chunk
        for result in results
        for log in result.rank_log
        if log.candidate is not None
    ]
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    markdown = render_report(
        ablation_rows,
        decisions,
        candidates,
        claim_supports,
        generated_at=generated_at,
    )
    report_path = REPORTS_DIR / "acceptance-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(markdown, encoding="utf-8")
    _append_dev_tables(report_path, rows)
    _append_counterexamples(report_path, candidates, claim_supports)

    recall_mean = mean(float(row["recall_at_50_pool"]) for row in rows)
    ndcg_mean = mean(float(row["ndcg_at_8_ranking"]) for row in rows)
    span_recall_mean = mean(float(row["span_proxy_recall_at_8"]) for row in rows)
    coverage_mean = mean(float(row["claim_chunk_coverage_at_8"]) for row in rows)
    print(f"== dev eval summary ({generated_at}) ==")
    print(f"Recall@50 (fusion pool, smoke) mean : {recall_mean:.3f}")
    print(f"nDCG@8 (rerank input) mean   : {ndcg_mean:.3f}")
    print(f"span proxy Recall@8 mean    : {span_recall_mean:.3f}")
    print(f"claim chunk coverage@8 mean : {coverage_mean:.3f}")
    print("decisions:", json.dumps(decisions, ensure_ascii=False))
    print(f"report: {report_path}")


def _append_dev_tables(report_path: Path, rows: list[dict[str, Any]]) -> None:
    """Append the per-question and span-granularity tables to the report."""
    lines = ["", "## 6. 冻结配置逐题 smoke 结果（Recall@50 / nDCG@8）", "",
             "| 题号 | 题型 | 状态 | Recall@50 | nDCG@8 | span proxy Recall@8 | 主张覆盖@8 | 选中数 | tokens | 延迟(ms) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        lines.append(
            f"| {row['question_id']} | {row['question_type']} | {row['status']} | "
            f"{float(row['recall_at_50_pool']):.3f} | {float(row['ndcg_at_8_ranking']):.3f} | "
            f"{float(row['span_proxy_recall_at_8']):.3f} | {float(row['claim_chunk_coverage_at_8']):.3f} | "
            f"{row['selected_count']} | {row['context_tokens']} | {float(row['latency_ms']):.1f} |"
        )
    lines.append(
        f"| 均值 | - | - | {mean(float(row['recall_at_50_pool']) for row in rows):.3f} | "
        f"{mean(float(row['ndcg_at_8_ranking']) for row in rows):.3f} | "
        f"{mean(float(row['span_proxy_recall_at_8']) for row in rows):.3f} | "
        f"{mean(float(row['claim_chunk_coverage_at_8']) for row in rows):.3f} | - | - | - |"
    )
    lines.append("")
    lines.append("> smoke 口径：Recall@50 在融合候选池（Top-50）上计算；nDCG@8 在重排输入上计算；")
    lines.append("> span_proxy 指标是 chunk 级代理，正式 evidence-span recall 依赖 A3 Span Schema（pending）；")
    lines.append("> 本表全部数据为 MOCK-A4-* 合成 fixture，不构成正式检索质量或临床效果声明。")
    with report_path.open("a", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")


def _append_counterexamples(
    report_path: Path,
    candidates: list[EvidenceChunk],
    claim_supports: tuple,
) -> None:
    """Append the two mandated counterexample classes to the report."""
    from scripts.report import find_old_but_authoritative, find_relevant_but_not_supporting

    relevant = find_relevant_but_not_supporting(candidates, claim_supports)
    old = find_old_but_authoritative(candidates)
    lines = [
        "",
        "## 7. 反例核查（两类强制反例）",
        "",
        "### 7.1 相关但不支持主张",
        *relevant,
        "",
        "### 7.2 旧但权威",
        *old,
        "",
    ]
    with report_path.open("a", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    import sys

    main(include_grid="--no-grid" not in sys.argv)
