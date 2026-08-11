# A4 检索与 Rerank 验收报告

> 生成时间：2026-08-11T10:39:39+00:00

## 1. 消融对照（R0–R3）

| 条件 | Recall@K0 | nDCG@K1 | MRR | 来源多样性 | 重复率 | 引用覆盖 | 主张支持率 | 冲突率 | 上下文 tokens | 成本(USD) | 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 0.729 | 0.645 | 0.708 | 0.000 | 0.000 | 0.625 | 0.125 | 0.040 | 9012 | 0.018024 | 2.4 |
| R1 | 0.729 | 0.645 | 0.708 | 0.000 | 0.000 | 0.625 | 0.125 | 0.009 | 8999 | 0.017998 | 2.9 |
| R3 | 0.250 | 0.283 | 0.625 | 0.000 | 0.000 | 0.625 | 0.125 | 0.000 | 6127 | 0.012254 | 2.1 |

## 2. 决策记录

- gate: accepted: gate improves or preserves support without more conflicts

## 3. 反例分析

### 3.1 相关但不支持（relevant but not supporting）

- `htn-guide-2024`（ev-htn-guide-2024，guideline，等级 guideline）：高分入选但无主张支持
- `htn-guide-2015`（ev-htn-guide-2015，guideline，等级 guideline）：高分入选但无主张支持
- `htn-meta-2021`（ev-htn-meta-2021，europepmc，等级 meta_analysis）：高分入选但无主张支持

### 3.2 旧但权威（old but authoritative）

- `htn-guide-2015`（ev-htn-guide-2015，2015-05-01，等级 guideline，距今 11.3 年）：权威但可能过时
- `htn-meta-2021`（ev-htn-meta-2021，2021-04-18，等级 meta_analysis，距今 5.3 年）：权威但可能过时

## 4. 结论与限制

- 本报告指标为冻结配置下的建议验收目标，不等同于临床有效性或诊疗安全性。
- 检索排序靠前仅表示在冻结规则下更适合作为候选证据。
- 最终医学表述必须经过 A5 的引用审计与发布门禁。

## 5. 局限与职责边界

### 5.1 启发式匹配的局限

- **PICO 匹配为 token 重叠启发式**：对"相关但不支持主张"的证据区分能力有限——
  同一主题但结论相反、或人群不匹配的证据仍可能获得较高 PICO 分。
- **主张—证据预检（claim_support）为 token 重叠启发式**：`supported` 判定只说明
  候选证据与主张共享较多词项，不表示医学结论成立；`mismatch` 只覆盖人群/时间
  两类明显冲突。
- **中文→英文改写为固定词典而非 LLM 改写**：词典覆盖有限，语义桥较弱；
  中英同义表达的召回依赖 A3 提供的 embedding 质量。

### 5.2 与 A5 NLI verifier 的职责边界

- A4 的 `claim_support` 是廉价、确定性的**预检信号**，不阻断检索与生成；
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

## 6. 冻结配置逐题结果（Recall@50 / nDCG@8）

| 题号 | 题型 | 状态 | Recall@50 | nDCG@8 | span Recall@8 | 主张覆盖@8 | 选中数 | tokens | 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|
| dev-001 | guideline | ok | 1.000 | 0.909 | 1.000 | 1.000 | 3 | 1139 | 4.0 |
| dev-002 | latest_trial | ok | 1.000 | 0.679 | 1.000 | 1.000 | 3 | 826 | 2.0 |
| dev-003 | therapy | ok | 1.000 | 0.769 | 1.000 | 1.000 | 8 | 1398 | 4.0 |
| dev-004 | therapy | ok | 1.000 | 0.520 | 1.000 | 1.000 | 8 | 1411 | 4.0 |
| dev-005 | guideline | ok | 1.000 | 0.630 | 1.000 | 1.000 | 3 | 678 | 2.0 |
| dev-006 | therapy | ok | 1.000 | 0.788 | 1.000 | 1.000 | 8 | 887 | 3.0 |
| dev-007 | therapy | ok | 1.000 | 0.614 | 1.000 | 1.000 | 8 | 1433 | 5.0 |
| dev-008 | guideline | ok | 1.000 | 0.619 | 1.000 | 1.000 | 3 | 1231 | 2.0 |
| 均值 | - | - | 1.000 | 0.691 | 1.000 | 1.000 | - | - | - |

> 验收口径：Recall@50 在融合候选池（Top-50）上计算；nDCG@8 在重排输入上计算；span 指标按 3.1 Qrel 契约的 evidence_span_id 粒度计算。

## 7. 反例核查（两类强制反例）

### 7.1 相关但不支持主张
- `htn-guide-2024`（ev-htn-guide-2024，guideline，等级 guideline）：高分入选但无主张支持
- `htn-guide-2015`（ev-htn-guide-2015，guideline，等级 guideline）：高分入选但无主张支持
- `htn-meta-2021`（ev-htn-meta-2021，europepmc，等级 meta_analysis）：高分入选但无主张支持

### 7.2 旧但权威
- `htn-guide-2015`（ev-htn-guide-2015，2015-05-01，等级 guideline，距今 11.3 年）：权威但可能过时
- `htn-meta-2021`（ev-htn-meta-2021，2021-04-18，等级 meta_analysis，距今 5.3 年）：权威但可能过时

