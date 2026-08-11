# A1 来源覆盖矩阵 v0.2

冻结日期：2026-08-11  
范围：成人高血压与血脂异常；仅供教学研究，不用于临床诊疗。

## 路由规则

| 题型 | 首选来源 | 备选来源 | 最低充分性 | 缺口处理 |
|---|---|---|---|---|
| 稳定机制 | PubMed 系统综述/高质量综述 | Europe PMC 全文、当前指南背景章节 | 至少 1 条直接支持该原子主张的高质量综述；重要主张优先 2 个独立来源 | 降低结论强度；不能用患者教育页代替研究证据 |
| 指南/治疗证据 | 当前官方指南及其正式期刊版本 | PubMed 指南记录、官方勘误、系统综述/RCT | 治疗建议至少 1 套当前指南；若无当前指南，则需 2 条独立高质量研究并标为 `WARN` | 明示适用人群、年份和地区；有冲突时并列而不强行合并 |
| 最新研究/试验 | ClinicalTrials.gov 当前记录 | PubMed 已发表结果、Europe PMC 全文 | 试验状态/设计可由注册记录支持；疗效结论必须有已发布结果，不能从方案推断 | 无结果时只回答设计、状态和预设终点，并显示 `results_not_posted` |
| 证据不足/冲突/越界 | 安全策略或至少两个冲突来源 | 所有白名单来源 | 个体诊断、剂量、处方和急症问题不进入普通回答；指南冲突至少检索双方当前版本 | `WARN`、`REFUSE` 或急症安全提示；不能用更多低质量资料填空 |

## 主题—题型覆盖

| 主题 | 稳定机制 | 指南/治疗 | 最新研究/试验 | 证据不足/冲突/越界 | 合计 |
|---|---:|---:|---:|---:|---:|
| 高血压 | 4 | 4 | 4 | 3 | 15 |
| 血脂异常 | 4 | 4 | 4 | 3 | 15 |
| 合计 | 8 | 8 | 8 | 6 | 30 |

每个主题均含简单、中等、困难各 5 题；全体题集三个难度各 10 题。

以上表格对应 DEV 30 题。TEST 60 题的分布为四类各 15 题、高血压与血脂各 30 题；STRESS 20 / EXTERNAL 10 / RESERVE 10 的设计与分布详见 `question_bank_blueprint.md`。TEST 候选不得用于调参，必须完成 B2 gold/qrels 与语义去重后才能冻结；STRESS 结果单独报告；EXTERNAL 的公开基准题须先通过许可证核验。

## 已核对的 P0 权威入口

| 来源 | 用途 | 稳定标识/版本 | A1 处理决定 |
|---|---|---|---|
| PubMed | 指南、综述、已发表试验 | PMID | 可入候选集；必须由 A2 转为 Evidence ID，再由 B2 定 gold |
| ClinicalTrials.gov | 试验设计、状态、日期、结果发布状态 | NCT ID | 可回答注册事实；没有结果时禁止推断疗效 |
| 2025 AHA/ACC 成人高血压指南 | 高血压分类、风险评估、治疗、居家监测 | PMID 40811497；DOI 10.1161/CIR.0000000000001356 | 当前美国指南候选 gold；必须保留发布日期和适用地区 |
| 2026 ACC/AHA 血脂异常指南 | 血脂筛查、PREVENT-ASCVD、风险增强因素、治疗框架 | PMID 41824552；DOI 10.1161/CIR.0000000000001423 | 当前美国指南候选 gold；必须同时摄入 2026-06-22 勘误 PMID 42330109 |
| 2024 ESC 高血压指南 | 跨地区指南冲突题 | 2024 版；2025-02-11 corrigendum | 仅保留元数据/链接作为待授权候选；官网明确要求软件/生成式 AI 使用需许可，未获许可不得把正文入库或转换 |
| Europe PMC | PubMed 全文补充和降级检索 | PMCID/DOI/PMID | 只在许可证允许时摄入正文；否则只保留元数据 |

## 题目到来源的路由

| 题号 | 主题 | 题型 | 首选路由 | 备选路由 |
|---|---|---|---|---|
| DEV-HTN-01—04 | 高血压 | 稳定机制 | PubMed Review/Systematic Review | Europe PMC、指南背景章节 |
| DEV-HTN-05—08 | 高血压 | 指南/治疗 | 2025 AHA/ACC 指南 | PubMed 指南记录；有授权时加入 2024 ESC |
| DEV-HTN-09—12 | 高血压 | 最新试验 | ClinicalTrials.gov | PubMed 结果论文 |
| DEV-HTN-13—15 | 高血压 | 越界/冲突 | 安全策略；双方指南元数据 | 当前指南、官方急症教育页 |
| DEV-LIP-16—19 | 血脂异常 | 稳定机制 | PubMed Review/Systematic Review | Europe PMC、指南背景章节 |
| DEV-LIP-20—23 | 血脂异常 | 指南/治疗 | 2026 ACC/AHA 指南 + 勘误 | PubMed 指南记录、当前官方摘要 |
| DEV-LIP-24—27 | 血脂异常 | 最新试验 | ClinicalTrials.gov | PubMed 结果论文（若已发布） |
| DEV-LIP-28—30 | 血脂异常 | 越界/恶意 | 安全策略、当前指南 | 官方患者教育页仅作解释性补充 |

## 交接限制

- 合并后的 `questions.jsonl` 共 130 题（DEV 30 + TEST 60 + STRESS 20 + EXTERNAL 10 + RESERVE 10），其中 `candidate_sources` 只是检索入口，不是 gold；任何调参脚本必须过滤 `split=DEV`，压力题单独报告。
- `gold_source_ids` 在 A1 版本中必须为空；A2 完成摄入、切块和 Evidence ID 后，由 B2 人工核验并冻结。
- 问题不得复制指南标题、摘要原句或试验官方标题；`source_group_id` 用于后续防止同义改写跨 split 泄漏（当前 130 题已校验无跨 split 泄漏）。
- 正式集不能由这些开发题直接改写生成，也不能共享同一 gold 段落；题库冻结哈希见 `data/processed/dataset_manifest.json`。

## 在线核对记录

- 2025 AHA/ACC 高血压指南：https://pubmed.ncbi.nlm.nih.gov/40811497/
- AHA 2025 高血压指南摘要：https://professional.heart.org/en/science-news/2025-high-blood-pressure-guideline/top-things-to-know
- 2026 ACC/AHA 血脂异常指南：https://pubmed.ncbi.nlm.nih.gov/41824552/
- 2026 血脂指南勘误：https://pubmed.ncbi.nlm.nih.gov/42330109/
- 2024 ESC 高血压指南及许可说明：https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/elevated-blood-pressure-and-hypertension/
- ClinicalTrials.gov API：https://clinicaltrials.gov/data-api/api
