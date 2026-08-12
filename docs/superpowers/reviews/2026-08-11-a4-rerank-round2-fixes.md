# A4 Rerank Round 2 审查修复记录（2026-08-11）

对照《OpenEvidence_MVP_赛道1与赛道3实施规划.md》§4.2–4.6 复核 origin/A4 @ 15c4f9b
后发现的 5 项偏差，本轮修复如下。验证：`pytest` 全量 384 通过（原 380 + 新增 4）。

## 【P1】加权特征公式与规划 §4.2 不一致 — 已修复

- `retrieval/rerank.py::_weighted_score` 加权项从
  `{semantic, lexical, pico_match, evidence_level, freshness, source_reliability}`
  改为与规划 §4.5 公式一致的
  `{semantic, lexical, pico_match, evidence_level, freshness, source_quality}`：
  `source_quality_table`（guideline 1.0 / pubmed 0.9 / trials 0.85 / europepmc 0.8）
  真正参与排序，不再零影响。
- `feature_weights.source_reliability`（0.10）槽位承载规划公式的 w6*source_quality
  （config 键名不变，避免冻结 YAML 与 config_io 契约变更）。

### rerank-p0-v1 口径裁决（写入 rerank_config_version 变更说明）

1. **redundancy 由 MMR 承担**：静态加权不重复扣 −0.15。MMR 已用
   `(1−lambda)*max_similarity` 惩罚 + 单文献 2 / 单来源 4 硬上限去冗余；静态分再扣
   会造成双重惩罚（6.6 消融决策，测试
   `test_redundancy_feature_is_diagnostic_only_and_mmr_owns_dedup` 固化该口径）。
2. **rrf / title_abstract / fulltext / source_reliability 仅计算留档，不参与加权**：
   规划 §4.2 步骤 3 的候选特征列表与步骤 4 公式存在差异，公式为准；
   留档特征供诊断与审计。
3. 本次为修正实现使其与 v1 宣称口径一致，`rerank_config_version` 保持 `rerank-p0-v1`，
   冻结资产（freeze.json 等）不重发。

## 【P1】索引版本不一致返回 PARTIAL 而非 FAILED — 已修复

- `retrieval/service.py`：`_intake_candidates` 区分 `version_excluded` 与 `excluded`；
  任一通道返回非冻结索引/语料版本的候选即
  **停止执行，`SearchStatus.FAILED`**，新 `ReasonCode.INDEX_VERSION_MISMATCH`，
  与设计文档 §9（"索引版本不一致 → failed"）和 AGENTS.md fail-closed 对齐。
- tombstoned / malformed / duplicate 仍走静默排除（不升级为 FAILED）。
- 测试：`test_search_fails_closed_on_index_version_mismatch`（新增）、
  `test_search_excludes_tombstoned_candidates_and_keeps_partial`（拆分）。

## 【P1】rerank 题型分类与 Query 契约字段二义 — 已修复

- `retrieval/rerank.py::_classify_query` **契约字段优先**：
  `query.question_type != "generic"` 时直接采用契约值（P0 无 diagnosis/prognosis
  证据表，映射 generic）；原文关键词推导仅作回退。
- `_is_freshness_requested` 同步契约优先：`freshness in {current, latest}` 或
  `question_type == "latest_trial"` 即启用时效特征，即使文本无关键词。
- 补契约测试（tests/test_rerank.py）：
  `test_question_type_contract_field_wins_over_text_derivation`、
  `test_question_type_contract_drives_freshness_feature_for_latest_trial`、
  `test_question_type_contract_wins_for_guideline_without_keywords`。

## 【P2】多 PICO 自适应增大 K1 而非 K0，未按原子主张分路召回 — 记录差异

- 行为不变（P0 记录差异）：`retrieval/adaptive.py` Rule 2 注释记录——
  规划 §4.3.4 意图是"按原子主张分路召回后增大 K0"；P0 融合池受
  `fusion_top_k` 硬上限约束，增大的是 K1（rerank 输入）。P1 按
  `atomic_claims` 分路召回后再改为增大 K0。

## 【P2】RetrievalConfig 默认值与冻结 YAML 不一致 — 已修复

- `retrieval/config.py`：`selection_top_k` 默认 6 → **8**，与
  `config/retrieval-p0-v1.yaml` 冻结值一致；绕过 config_io 直接构造配置时
  可复现性不再破坏。
- 连锁更新：`test_models.py`、`test_adaptive_cross_encoder.py` 默认值断言。

## 验证

```powershell
python -m pytest          # 384 passed
python -m scripts.run_dev_eval   # 冻结配置 smoke 评测（指标口径不变）
```

## Round 3 修正（2026-08-12，合并至 main 后）

### 【P1】round2 修复 ③ 的副作用：freshness 激活范围过大导致"旧但权威"指南被反超 — 已修正

- **现象**：round2 把 `_is_freshness_requested` 激活范围扩大到所有
  `freshness in {current, latest}` 查询；而 `query_plan` 因"指南"字样把
  纯指南类问题映射为 `freshness="current"`，使指南类问题意外启用 10 年线性
  衰减。实测"高血压指南推荐的治疗"下 2015 权威指南（evidence_level=1.0、
  source_quality=1.0，得分 0.882）被 2024 RCT（0.7/0.9，得分 0.909）反超；
  修复前（freshness=None、权重重分配）指南 1.0 > RCT 0.927。与规划 §4.2
  "证据等级与时效性不是对所有问题一刀切"及"旧但权威"反例要求冲突。
- **修正**：`retrieval/rerank.py::_is_freshness_requested` 仅在
  1) `freshness="latest"`（最新试验硬时效）、2) `question_type="latest_trial"`
  （契约驱动，即使原文无关键词）、3) 原文含最新/近期/当前/新近等时效词
  （覆盖"最新指南"类）时激活；纯指南类问题（文本无时效词）不再触发衰减，
  证据等级恢复主导。
- **回归测试**：`tests/test_rerank.py::test_old_authoritative_guideline_keeps_lead_over_recent_rct`
  （断言 2015 指南排名在 2024 RCT 之前且 freshness 均为 None）。
- **遗留口径**："最新指南"类问题（含时效词 + 指南）仍启用时效特征，与
  纯指南类行为的差异是刻意的；如需为指南类设置更缓的衰减窗口（而非禁用），
  列为 P1 增强项，须在开发集上验证。

## 【round3 P1】时效特征激活范围过宽 — 已修复（2026-08-12）

round2 契约优先改动把 `_is_freshness_requested` 激活范围扩大到所有
`freshness=current` 查询；`query_plan` 将纯指南类问题映射为
`freshness=current`，导致 0.10 的 freshness 权重把 2015 权威指南压到
2024 RCT 之后（0.882 < 0.909）。

修正：仅在 `freshness=latest` / `question_type=latest_trial` / 原文含时效词时
激活衰减；纯指南类问题恢复证据等级主导（规划 §4.2“旧但权威”反例要求）。
新增回归测试
`tests/test_rerank.py::test_old_authoritative_guideline_keeps_lead_over_recent_rct`；
同步重生成 smoke 评测 artifacts。385 tests passed（main 侧）。

## 【backport 记录】all_A12345_try 快照恢复缺失 round2/round3 修复 — 已同步

`all_A12345_try` 分支是工作区迁移后的 A1-A5 整合快照，其 `retrieval/` 恢复的是
round2/round3 修复前的旧口径代码。本轮按 main（a4850e2）口径回补三处 P1：

1. `_weighted_score` 加权槽位从 `source_reliability`（provenance 完整性）改回
   `source_quality`（`source_quality_table` 表驱动），与规划 §4.2/§4.5 公式
   w6*source_quality 一致；`test_rank_reallocates_unavailable_pico_weight_*`
   断言同步更新。
2. `_classify_query` 契约 `question_type` 优先于原文关键词推导（round2 P1）。
3. `_is_freshness_requested` 仅在明确时效需求（契约 latest/latest_trial 或原文
   时效词）时激活（round3 P1）。

同时移植 5 条契约/回归测试（索引版本不一致 fail-closed 测试拆分，见
`tests/test_service.py::test_search_fails_closed_on_index_version_mismatch`）并重生成
smoke 评测 artifacts。验证：全量 `540 passed, 3 skipped`（3 项为 live API 跳过）。
