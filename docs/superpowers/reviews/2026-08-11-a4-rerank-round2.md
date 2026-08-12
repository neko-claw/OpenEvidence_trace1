# A4 Rerank/RRF 第二轮审查：与《实施规划》§4.2–4.5 的偏差清单

> 审查对象：`origin/A4` @ `15c4f9b`（A4 修复：数据契约、Gate1、A5 桥接、开发集评测与冻结配置）
> 对照基线：《OpenEvidence_MVP_赛道1与赛道3实施规划.md》§4.2–4.6、A4 设计文档
> `docs/superpowers/specs/2026-08-11-a4-retrieval-rerank-design.md`、仓库 `AGENTS.md`
> 验证方式：`/tmp/a4-review` worktree 上 `python3.11 -m pytest tests/` → **282 passed**；针对下述行为的独立探针脚本已实测
> 日期：2026-08-11（第二轮）

## 0. 总体结论

A4 当前实现与《实施规划》的级联 rerank 架构**高度一致**：RRF 融合（`rrf_k=60`，纯排名）→ 可解释特征重排（0.30/0.20/0.15/0.15/0.10/0.10）→ MMR（λ=0.75，单文献 ≤2 chunk、单来源 ≤4 chunk、证据类型 bonus）→ Claim-Evidence 预检；自适应 K、R0–R3 消融、K 网格调参、冻结配置 `config/retrieval-p0-v1.yaml`、OK/PARTIAL/EMPTY/FAILED 降级状态、`out_of_scope` 显式移交、`ports.py` 适配器边界全部落地，282 个测试通过。

以下 **5 项偏差**是第二轮审查新发现，需 A4 开发者确认或修改。第 1、2、3 项建议在冻结评审中裁决/修复；第 4、5 项为文档化建议。

---

## 1. 【P1】加权特征公式与《实施规划》§4.2 不一致（redundancy / source_quality 未参与排序）

**位置**：`retrieval/rerank.py::_weighted_score`、`retrieval/config.py::FeatureWeights.validate`

**事实**：
- 规划 §4.2 公式为 `0.30*semantic + 0.20*lexical + 0.15*pico_match + 0.15*evidence_level + 0.10*freshness + 0.10*source_quality − 0.15*redundancy`。
- 实现只对 6 个特征加权：`semantic / lexical / pico_match / evidence_level / freshness / source_reliability`，且 `FeatureWeights.validate()` **强制权重和为 1**。
- 实测（探针验证）：`rrf`、`title_abstract`、`source_quality`、`fulltext`、`redundancy` 共 5 个特征被计算并写入 `feature_scores` 日志，但**完全不进入排序分数**。

**两个子问题**：

1a. **redundancy 不进静态分**：与 A4 设计文档 §6.6"MMR 是顺序选择过程，冗余惩罚不应提前塞入静态 feature_score"一致，但与规划 §4.2 公式的 `−0.15*redundancy` 不同。且规划公式权重和≠1（为 0.85），实现的归一化约束在数学上更规范。→ **请 A4 在冻结评审中明确采用哪个口径，并将结论写入 `rerank_config_version` 变更说明**（目前 `rerank-p0-v1` 未记录该决策）。

1b. **source_quality 表对排序零影响**：`config/retrieval-p0-v1.yaml` 已配置 `source_quality_table`（guideline 1.0 > pubmed 0.9 > trials 0.85 > europepmc 0.8）并被 `_source_quality()` 计算，但不在 `_weighted_score` 的 `configured` 集合内。规划 §4.2 公式用 `source_quality`，A4 设计 §6.4 用 `source_reliability`（来源完整性）；当前活特征是 `source_reliability`。→ **请明确 `source_quality` 是活特征还是仅审计字段**；若仅审计，请在 YAML 中标注 `audit_only` 防止后续误读。

**建议修复**：二选一——
- 若按规划公式：将 `source_quality` 纳入加权（替换或并列 `source_reliability`），并放宽"权重和为 1"约束以容纳 `−redundancy` 项；
- 若维持现状：在 `rerank_config_version` 变更说明中记录"冗余惩罚由 MMR 承担、来源类型表仅审计留档"的口径，并更新《实施规划》公式备注。

---

## 2. 【P1】索引版本不一致时返回 PARTIAL 而非 FAILED（与设计 §9 不符）

**位置**：`retrieval/service.py::_intake_candidates`、`RetrievalService.search`

**事实**：
- A4 设计文档 §9 错误处理表："索引版本不一致 → **停止执行，状态设为 failed**"。
- 实现按通道过滤 `index_version`/`corpus_version` 不匹配的 chunk，把被过滤数量并入 `degradation_reasons`（"bm25 channel excluded N invalid or stale candidate(s)"）。当整库过期时，`bm25` 与 `vector` 均空，走 `not bm25 and not vector` 分支；因 `reasons` 非空，最终状态为 **PARTIAL**（而不是 FAILED）。

**影响**：整库索引过期时下游（A5/B5）收到 PARTIAL，可能被解释为"部分可用"而继续生成，与 `AGENTS.md` 的 fail-closed 原则（Gate0/Gate6：UNKNOWN 数据不得静默变为 ALLOW）存在张力。

**建议修复**：将"版本不匹配导致全部候选被过滤"识别为 FAILED 并给出专门原因码（如 `index_version_mismatch`），仅当部分候选过期时保持 PARTIAL；或在文档中明确说明该降级是有意选择及其依据。

---

## 3. 【P1】rerank 题型分类与 Query 契约字段存在二义性

**位置**：`retrieval/rerank.py::_classify_query`、`retrieval/query_plan.py::_detect_question_type`

**事实**：
- `Query.question_type` 是冻结契约字段（`Query.__post_init__` 校验其枚举），`query_plan` 已据此设置 `topic` 并决定 `freshness`。
- 但 `FeatureReranker._classify_query` **从 `query.text` 原文重新推导题型**，忽略契约字段。正常路径（query_plan 产出）二者一致；当评测方（B4）直接构造 `Query(question_type="latest_trial")` 而文本不含"最新/试验"关键词时，实测 `_classify_query` 返回 `generic`：
  - `freshness` 特征为 `None` → 最新试验题的 freshness 权重提升（`freshness_weight_latest_trial=0.20`）不生效；
  - `_EVIDENCE_SCORES` 退回 `generic` 映射（rct=0.80 而非 latest_trial 的 1.00）。

**建议修复**：让 `Query.question_type` 契约字段优先，`_classify_query` 仅作文本回退（或删除该函数改用契约字段），并补充一条契约测试：`question_type="latest_trial"` 的 Query 在文本无关键词时仍走 latest_trial 权重。

---

## 4. 【P2】多 PICO 自适应增大的是 K1 而非 K0，且未按原子主张分路召回

**位置**：`retrieval/adaptive.py::adapt_k`、`retrieval/service.py`

**事实**：
- 规划 §4.3.4："宽泛综述或多 PICO 问题：**按原子主张分别召回，再合并候选，适当增大 K0**"。
- 实现：多 PICO（≥3 个 PICO 字段非空）时返回 `(k1=30, k2=8)`，仅放大 rerank 输入；RRF 候选池仍为 `fusion_top_k=80`；`Query.atomic_claims` 只用于事后 `check_claims` 支持性检查，未参与分路召回。

**影响**：多 PICO 问题的召回机会与单路全文本检索相同，未获得"按主张分别召回"带来的召回增益；规划意图未完全落地。

**建议修复**：P0 可接受并在文档记录差异；P1 在 `service` 内按 `atomic_claims`（或 PICO 字段）分路召回后并入候选池（仍受 `fusion_top_k` 上限约束），并评估 `Recall@K0` 增量。

---

## 5. 【P2】`RetrievalConfig` 默认值与冻结 YAML 不一致

**位置**：`retrieval/config.py`（默认 `selection_top_k=6`）、`config/retrieval-p0-v1.yaml`（冻结值 `selection_top_k: 8`）

**事实**：
- 冻结配置（`rerank-p0-v1`）的最终上下文上限为 8；但直接 `RetrievalConfig()`（不经 `config_io` 加载）得到 `selection_top_k=6`。
- 两者都在规划 §4.3.2 的 K2=5–8 区间内，但**同一配置版本存在两套取值**，破坏可复现性（正式题运行若绕过 YAML，上下文预算与冻结配置不符）。

**建议修复**：让 `config.py` 默认值与 `config/retrieval-p0-v1.yaml` 完全一致；或将 `RetrievalConfig()` 改为强制从 `config/` 加载（缺失即报错），杜绝"默认值漂移"。

---

## 附：已确认符合、无需改动的部分（第二轮复核）

- RRF：`1/(rrf_k+rank)` 双路纯排名融合、`rrf_k=60`、保留原始分数、chunk 去重、`MAX_RRF_OPERAND` 校验 ✅
- 级联阶段：metadata/latest 过滤 → BM25 Top-50 + Vector Top-50 → RRF Top-80 → 特征重排（K1 默认 25，指南 10 / 多 PICO 30 / 最新 20）→ MMR（K2=8，指南 3 / 最新 5，硬上限 8）→ Claim-Evidence 预检 ✅
- latest_trial freshness 权重提升 0.20、freshness="latest" 硬窗口 1826 天（缺日期 fail-closed）✅
- 自适应 K 只缩不扩（k2 ≤ selection_top_k）、`out_of_scope` 显式 EMPTY 移交 A1/A5 ✅
- R0–R3 消融隔离（R0=RRF 直取、R2=Cross-Encoder α 混合 `BAAI/bge-reranker-v2-m3`）、K 网格 (20,50,80,100,150)×(10,20,30,50)×(3,5,8,10) ✅
- 指标：Success/Recall@K、nDCG@K、MRR、Hit@K、source_diversity、duplicate_rate、citation_precision/coverage、claim_support_rate、conflict_rate、延迟/token/成本 ✅
- 冻结版本（`rerank-p0-v1` / `idx-20260811-v1` / `corpus-20260811-v1`）写入 `SearchResult`；`ports.py` 遵守 `a5.ports.EvidenceRetriever` 适配器边界 ✅
- 中文支持性预检经 CJK n-gram 分词有效（实测 overlap 0.51 → `supported`）；权重缺失按 query 内重新归一化而非计零 ✅
- `pytest`：282 通过 ✅
