"""Acceptance report generator and counterexample finder (4.2/指标与报告).

Produces a Markdown report from ablation rows, freeze records, and
per-question runs, and locates the two mandated counterexample classes:
\"relevant but not supporting\" and \"old but authoritative\".
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from retrieval.ablation import AblationRow
from retrieval.models import EvidenceChunk, Query
from retrieval.models import RetrievalAlignmentHint

_TEMPLATE = """# A4 检索与 Rerank Pipeline Smoke 报告

> 生成时间：{generated_at}
>
> **SMOKE 声明**：本报告基于 data/dev 的 MOCK-A4-* 合成 fixture（mock=true，
> 无 PMID/DOI/NCT/URL/指南编号）。所有指标为 pipeline smoke/proxy，**不是**
> 人工 gold、**不是**正式检索质量或临床效果声明；正式评测待 A1/A2/A3/B2
> 上游契约（pending）。

## 1. 消融对照（R0–R3）

| 条件 | Recall@K0 | nDCG@K1 | MRR | 来源多样性 | 重复率 | 引用覆盖(proxy) | 主张对齐率(proxy) | 冲突率 | 上下文 tokens | 成本(USD) | 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|
{ablation_rows}

## 2. 决策记录

{decisions}

## 3. 反例分析

### 3.1 相关但不支持（relevant but not supporting）

{relevant_but_not_supporting}

### 3.2 旧但高证据等级（synthetic: old but high evidence level）

{old_but_authoritative}

## 4. 结论与限制

- 本报告指标为冻结配置下的 **smoke** 目标（合成数据），不等同于临床有效性或诊疗安全性，也不构成正式检索质量声明。
- 检索排序靠前仅表示在冻结规则下更适合作为候选证据。
- 最终医学表述必须经过 A5 的引用审计与发布门禁。

## 5. 局限与职责边界

### 5.1 启发式匹配的局限

- **PICO 匹配为 token 重叠启发式**：对"相关但不支持主张"的证据区分能力有限——
  同一主题但结论相反、或人群不匹配的证据仍可能获得较高 PICO 分。
- **主张—证据对齐预检（alignment_hints）为 token 重叠启发式**：`ALIGNED` 判定只说明
  候选证据与主张共享较多词项，不表示医学结论成立；`MISMATCH` 只覆盖人群/时间
  两类明显冲突。
- **中文→英文改写为固定词典而非 LLM 改写**：词典覆盖有限，语义桥较弱；
  中英同义表达的召回依赖 A3 提供的 embedding 质量。

### 5.2 与 A5 NLI verifier（Gate5）的职责边界

- A4 的 `alignment_hints` 是廉价、确定性的**对齐预检信号**（method=token_overlap_heuristic，阈值版本见冻结配置），不阻断检索与生成，且绝不映射为 A5 的 SUPPORTED；
- 主张与证据的**最终验证（NLI verifier）与发布门禁归 A5**，A4 不据此作医学真伪判断；
- A5 只应基于 `selected_chunks` 生成回答并执行引用审计（对接约定）。

### 5.3 时效性语义

- `freshness=latest`（最新试验）对无 `published_at` 或超出窗口的 chunk 硬过滤；
- `freshness=current`（当前推荐，如指南题）不再硬过滤无日期 chunk（缺失日期时
  freshness 特征权重在查询内重归一化），避免指南类问题因索引缺日期而误空结果；
- 索引数据约定：A3 应尽量为 chunk 补齐 `published_at` 与 `fetched_at`。

### 5.4 范围门禁交接

- A4 对 `out_of_scope`（剂量/处方/诊断我/急症处置等）问题返回空结果并显式记录
  `out_of_scope` 原因，不返回可能被当作建议的证据；
- 最终的范围拒答与安全门禁由 A1/A5 执行，A4 只完成交接信号。
"""


def find_relevant_but_not_supporting(
    candidates: Sequence[EvidenceChunk],
    claim_supports: Sequence[RetrievalAlignmentHint],
    *,
    top_n: int = 3,
) -> list[str]:
    """Chunks that rank high but never appear in any supported claim's evidence."""
    supported_ids = {
        evidence_id for support in claim_supports if support.decision == "ALIGNED" for evidence_id in support.evidence_ids
    }
    rows: list[str] = []
    for chunk in candidates[:top_n]:
        if chunk.evidence_id not in supported_ids:
            rows.append(f"- `{chunk.chunk_id}`（{chunk.evidence_id}，{chunk.source_type}，等级 {chunk.evidence_level}）：高分入选但无 ALIGNED 主张对齐")
    return rows or ["- （无）"]


def find_old_but_authoritative(
    candidates: Sequence[EvidenceChunk],
    *,
    as_of: date | None = None,
    max_age_years: int = 5,
    top_n: int = 3,
) -> list[str]:
    """High-evidence-level chunks older than the freshness window."""
    as_of = as_of or date(2026, 8, 11)
    rows: list[str] = []
    for chunk in candidates[:top_n]:
        if chunk.published_at is None or chunk.evidence_level not in {"guideline", "systematic_review", "meta_analysis"}:
            continue
        try:
            published = date.fromisoformat(chunk.published_at)
        except ValueError:
            continue
        age_years = (as_of - published).days / 365.25
        if age_years > max_age_years:
            rows.append(
                f"- `{chunk.chunk_id}`（{chunk.evidence_id}，{chunk.published_at}，等级 {chunk.evidence_level}，"
                f"距今 {age_years:.1f} 年）：高证据等级但可能过时（合成）"
            )
    return rows or ["- （无）"]


def render_report(
    ablation_rows: Sequence[AblationRow],
    decisions: dict[str, str],
    candidates: Sequence[EvidenceChunk],
    claim_supports: Sequence[RetrievalAlignmentHint],
    *,
    generated_at: str = "2026-08-11",
) -> str:
    """Render the full acceptance report Markdown."""
    ablation_markdown = "\n".join(
        f"| {row.condition} | {row.recall_at_k0:.3f} | {row.ndcg_at_k1:.3f} | {row.mrr:.3f} | "
        f"{row.source_diversity:.3f} | {row.duplicate_rate:.3f} | {row.citation_proxy_coverage:.3f} | "
        f"{row.claim_alignment_proxy_rate:.3f} | {row.conflict_rate:.3f} | {row.context_tokens} | "
        f"{row.estimated_cost_usd:.6f} | {row.latency_ms:.1f} |"
        for row in ablation_rows
    )
    decisions_markdown = "\n".join(f"- {name}: {reason}" for name, reason in decisions.items()) or "- （无）"
    relevant = find_relevant_but_not_supporting(candidates, claim_supports)
    old_authoritative = find_old_but_authoritative(candidates)
    return _TEMPLATE.format(
        generated_at=generated_at,
        ablation_rows=ablation_markdown,
        decisions=decisions_markdown,
        relevant_but_not_supporting="\n".join(relevant),
        old_but_authoritative="\n".join(old_authoritative),
    )


def write_report(
    path: str | Path,
    ablation_rows: Sequence[AblationRow],
    decisions: dict[str, str],
    candidates: Sequence[EvidenceChunk],
    claim_supports: Sequence[RetrievalAlignmentHint],
) -> Path:
    """Write the acceptance report to ``path`` and return it."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_report(ablation_rows, decisions, candidates, claim_supports),
        encoding="utf-8",
    )
    return destination
