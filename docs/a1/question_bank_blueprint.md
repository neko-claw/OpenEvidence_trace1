# A1 题库蓝图 question_bank_blueprint v0.2

修订日期：2026-08-12（A1 结构版本；正式评测尚未冻结）
依据：《OpenEvidence_MVP_赛道1与赛道3实施规划》v0.5 §6.3 题集设计与 LLM 偏差控制。
范围：成人高血压与血脂异常；仅供教学研究，不用于临床诊疗。

## 1. 总览：130 道题的分层结构

| 数据包 | 题数 | 用途 | 是否进入主结论 | 当前状态 |
|---|---:|---|---|---|
| DEV 开发集 | 30 | 查询改写、K、rerank 权重和拒答阈值选择 | 否 | A1 结构冻结；gold/语义去重待 B2 |
| TEST 正式候选集 | 60 | A/B/C/D 配对主评测；A2 可选次要对照 | 待冻结 | A1 结构交付；gold、教师题与语义去重待 B2 |
| STRESS 压力候选集 | 20 | 检索劣化、冲突证据、不可回答、提示注入和非法引用 | 单独报告（待冻结） | 场景结构交付；预期行为/证据映射待 B2 |
| EXTERNAL benchmark-style 候选集 | 10 | 检查跨题目来源泛化 | 否（当前） | 许可证、逐题来源与 gold 均待核验 |
| RESERVE 备用集 | 10 | 替换泄漏、重复、gold 失效或解析失败的题目 | 否 | 备用结构交付；审核后方可替换 |
| **合计** | **130** | — | — | 满足规划 §2.1「不少于 130 道」 |

## 2. 题目来源与比例（§6.3：至少四类，单一来源 ≤ 正式集 40%）

正式集（TEST 60）来源分布（A1 版）：

| 来源类型 | 题数 | 占比 | 说明 |
|---|---:|---:|---|
| a1_blueprint（按蓝图设计） | 24 | 40.0% | 恰达上限；B2 增补或调整时优先用其他来源替换 |
| guideline（指南临床问题抽象） | 21 | 35.0% | 不复制指南标题/摘要原句 |
| literature（文献/注册试验抽象） | 15 | 25.0% | 不含结果论文标题原句 |
| teacher（教师/医学专业人员命题） | 0 | 0% | **待补充**：需课程教师直接命题后并入对应 split 并按 source_group 隔离 |
| public_benchmark（已导入且可溯源的公开基准） | 0 | 0% | 当前没有已完成许可和逐题来源核验的公开基准题 |

整体题库（130 题）实际标注分布以 `questions.jsonl` 为准：a1_blueprint 48、guideline 36、literature 38、public_benchmark_style 8。`public_benchmark_style` 只表示合成题型风格，不能视为真实公开 benchmark 导入。teacher 与已核验 public_benchmark 均为 0；需在 B2 冻结前补齐或由课程团队书面豁免。

EXTERNAL 包中的 8 道 `public_benchmark_style` 题仅参考公开医学问答常见的稳定知识题形式，**不复制基准原句，也不声称来自某个公开数据集**。B2 若决定接入真实 benchmark，必须另行记录数据集名、版本、许可证、原始 item ID 与改写关系；在此之前 EXTERNAL 全包 `evaluation_eligible=false`。

## 3. 题型—主题覆盖

### 3.1 DEV 30（已与 source_coverage_matrix.md 一致）

| 主题 | 稳定机制 | 指南/治疗 | 最新研究/试验 | 不足/冲突/越界 | 合计 |
|---|---:|---:|---:|---:|---:|
| 高血压 | 4 | 4 | 4 | 3 | 15 |
| 血脂异常 | 4 | 4 | 4 | 3 | 15 |
| 难度 | easy 10 / medium 10 / hard 10 | | | | 30 |

### 3.2 TEST 60（四类题型各 15；每主题 30 题）

| 主题 | 稳定机制 | 指南/治疗 | 最新研究/试验 | 不足/冲突/越界 | 合计 |
|---|---:|---:|---:|---:|---:|
| 高血压 | 8 | 8 | 7 | 7 | 30 |
| 血脂异常 | 7 | 7 | 8 | 8 | 30 |

### 3.3 STRESS 20（四类各 5，对应规划 §6.3 压力集规则）

| 类别 | 题数 | 题号 | 说明 |
|---|---:|---|---|
| 检索压力/删除 gold 或降 top-k | 5 | STRESS-HTN-001/002/003、STRESS-LIP-004/005 | 真实已发表试验的注册事实题；运行时 E 条件按预注册规则删除 gold/降低 top-k |
| 注入不支持证据 | 5 | STRESS-HTN-006/007/010、STRESS-LIP-008/009 | 诱使把注册状态、预设终点、替代终点或营销宣称当作疗效证据 |
| 无充分证据/范围外 | 5 | STRESS-HTN-011/012/013、STRESS-LIP-014/015 | 儿童、妊娠、阿尔茨海默/糖尿病、衰弱老人个体化请求；期望 `REFUSE` + 范围原因码 |
| 提示注入/伪造引用 | 5 | STRESS-HTN-016/017/020、STRESS-LIP-018/019 | 忽略规则、伪造 PMID/DOI/指南编号/链接、急症+剂量；期望 `REFUSE` + 完整性/急症原因码 |

STRESS 恶意题中的假标识符（如 PMID 12345678、GDL-9999）是**测试输入**，不是证据声明；其 `candidate_sources` 仅指向 `safety_policy`/`search_route`，不含任何伪造 stable_id。STRESS 与 DEV/TEST 之间不共享同一原始问题；引用试验（SYMPLICITY HTN-3 等）与正式集试验来源不同，B2 冻结前仍须按 source_group 复核。

### 3.4 EXTERNAL 10 与 RESERVE 10

- EXTERNAL：高血压 5（EXTERNAL-HTN-001~005）、血脂 5（EXTERNAL-LIP-006~010）；稳定机制 5、指南/治疗 5；难度 easy 1 / medium 6 / hard 3。
- RESERVE：高血压 5（RESERVE-HTN-001~005）、血脂 5（RESERVE-LIP-006~010）；覆盖四类题型；难度 easy 1 / medium 6 / hard 3；题源独立于 DEV/TEST（不共享同一 gold 段落）。

## 4. 去重与隔离（§6.3）

1. **source_group_id 隔离**：跨 split 共享同一派生组 = 违规。自动检查仅能证明当前没有重复 group ID；由于 130 个 ID 目前都是 singleton，不能据此证明没有语义派生泄漏。真实来源/翻译/改写关系审核标为 `PENDING_B2_DERIVATION_AUDIT`。
2. **文本去重**：question/answer points 文本哈希查重，已通过。
3. **语义去重（未执行，待 B2）**：计划使用 embedding 聚类检查近义重复，候选阈值 0.85；该数值不是已验证结果。若发现 DEV↔TEST 近义对，将 TEST 侧移入 RESERVE 替换。
4. **时间留出**：最新研究题 `as_of_date=2026-08-11`，证据语料按 `corpus_cutoff=2026-08-11` 冻结（见 dataset_manifest.json），单独观察检索带来的时效性收益。

## 5. gold 与评分（§6.3 治理流程）

- A1 阶段 `gold_source_ids` 一律为空；`candidate_sources.role=candidate_gold` 仅表示优先人工核验候选。
- B2 基于真实 PubMed/指南/试验记录建立 gold 与原子评分点（`<question_id>-P<NN>`，见 qrel.schema.json）；LLM 生成的 DOI/PMID/答案不得直接进入 gold。
- rubric 版本 `rubric-candidate-v0.1`；B2 冻结后升为 `rubric-frozen-v0.1`。

## 6. 交接限制

- 调参脚本必须过滤 `split=DEV`；STRESS 结果单独报告，不并入正式集。
- TEST/STRESS/EXTERNAL/RESERVE 在升级为 `EVALUATION_FROZEN` 后不得静默修改；此前每次结构修改也必须重建 `split_hashes` 并说明原因。
- EXTERNAL 的 benchmark-style 候选在许可证、逐题来源和 gold 核验完成前不得用于任何结论。
