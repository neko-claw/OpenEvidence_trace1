# A4 检索与 Rerank Pipeline Smoke 报告

> 生成时间：2026-08-12T07:19:34+00:00
>
> **SMOKE 声明**：本报告基于 data/dev 的 MOCK-A4-* 合成 fixture（mock=true，
> 无 PMID/DOI/NCT/URL/指南编号）。所有指标为 pipeline smoke/proxy，**不是**
> 人工 gold、**不是**正式检索质量或临床效果声明；正式评测待 A1/A2/A3/B2
> 上游契约（pending）。

## 1. 消融对照（R0–R3）

| 条件 | Recall@K0 | nDCG@K1 | MRR | 来源多样性 | 重复率 | 引用覆盖(proxy) | 主张对齐率(proxy) | 冲突率 | 上下文 tokens | 成本(USD) | 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 0.771 | 0.742 | 0.917 | 0.000 | 0.000 | 0.688 | 0.000 | 0.067 | 10418 | 0.020836 | 0.6 |
| R1 | 0.833 | 0.833 | 1.000 | 0.000 | 0.000 | 0.688 | 0.000 | 0.067 | 11284 | 0.022568 | 1.8 |

## 2. 决策记录

- （无）

## 3. 反例分析

### 3.1 相关但不支持（relevant but not supporting）

- `MOCK-A4-E001`（MOCK-A4-E001，guideline，等级 guideline）：高分入选但无 ALIGNED 主张对齐
- `MOCK-A4-E002`（MOCK-A4-E002，pubmed，等级 systematic_review）：高分入选但无 ALIGNED 主张对齐
- `MOCK-A4-E010`（MOCK-A4-E010，europepmc，等级 meta_analysis）：高分入选但无 ALIGNED 主张对齐

### 3.2 旧但高证据等级（synthetic: old but high evidence level）

- `MOCK-A4-E002`（MOCK-A4-E002，2020-03-10，等级 systematic_review，距今 6.4 年）：高证据等级但可能过时（合成）
- `MOCK-A4-E010`（MOCK-A4-E010，2021-04-18，等级 meta_analysis，距今 5.3 年）：高证据等级但可能过时（合成）

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

## 6. 冻结配置逐题 smoke 结果（Recall@50 / nDCG@8）

| 题号 | 题型 | 状态 | Recall@50 | nDCG@8 | span proxy Recall@8 | 主张覆盖@8 | 选中数 | tokens | 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|
| dev-001 | guideline | ok | 1.000 | 0.981 | 1.000 | 1.000 | 3 | 1443 | 7.0 |
| dev-002 | latest_trial | ok | 1.000 | 0.679 | 1.000 | 1.000 | 3 | 705 | 2.0 |
| dev-003 | therapy | ok | 1.000 | 0.712 | 1.000 | 1.000 | 8 | 2876 | 3.0 |
| dev-004 | therapy | ok | 1.000 | 0.933 | 1.000 | 1.000 | 8 | 2891 | 4.0 |
| dev-005 | guideline | ok | 1.000 | 0.566 | 1.000 | 1.000 | 3 | 547 | 4.0 |
| dev-006 | therapy | ok | 1.000 | 0.908 | 1.000 | 1.000 | 8 | 1706 | 5.0 |
| dev-007 | therapy | ok | 1.000 | 0.790 | 1.000 | 1.000 | 8 | 1330 | 4.0 |
| dev-008 | guideline | ok | 1.000 | 0.443 | 1.000 | 1.000 | 3 | 581 | 3.0 |
| 均值 | - | - | 1.000 | 0.751 | 1.000 | 1.000 | - | - | - |

> smoke 口径：Recall@50 在融合候选池（Top-50）上计算；nDCG@8 在重排输入上计算；
> span_proxy 指标是 chunk 级代理，正式 evidence-span recall 依赖 A3 Span Schema（pending）；
> 本表全部数据为 MOCK-A4-* 合成 fixture，不构成正式检索质量或临床效果声明。

## 7. 反例核查（两类强制反例）

### 7.1 相关但不支持主张
- `MOCK-A4-E001`（MOCK-A4-E001，guideline，等级 guideline）：高分入选但无 ALIGNED 主张对齐
- `MOCK-A4-E002`（MOCK-A4-E002，pubmed，等级 systematic_review）：高分入选但无 ALIGNED 主张对齐
- `MOCK-A4-E010`（MOCK-A4-E010，europepmc，等级 meta_analysis）：高分入选但无 ALIGNED 主张对齐

### 7.2 旧但权威
- `MOCK-A4-E002`（MOCK-A4-E002，2020-03-10，等级 systematic_review，距今 6.4 年）：高证据等级但可能过时（合成）
- `MOCK-A4-E010`（MOCK-A4-E010，2021-04-18，等级 meta_analysis，距今 5.3 年）：高证据等级但可能过时（合成）

