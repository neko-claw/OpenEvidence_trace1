# OpenEvidence 后续任务就绪清单

更新时间：2026-08-12  
当前分支：`feature/backend-integration`  
当前提交：`bb5218f17d9f73b878c2a6337423a602c5421d85`

## 1. 当前结论

当前状态应分成三个层级理解：

| 层级 | 状态 | 说明 |
|---|---|---|
| 后端架构与契约 | READY | A1→A2 MCP→A3→A4→A5 的离线协同链路、Gate0–Gate6、A6/B4 Schema 和 replay fixture 已通过测试 |
| Live 工程部署 | NOT READY | 仍缺生产安全分类、真实连接器部署、正式 Embedding 评测、校准质量分和 live 组合根 |
| 临床可信与正式效果评测 | NOT READY | 仍缺医学专家审查、正式 gold/qrel、独立语义验证器校准和临床安全验证 |

因此，A6 现在可以直接使用 replay/mock 契约开发和测试前端，但不能把 replay/mock 结果展示为真实医学证据，也不能宣称 live 或临床可用。

当前已验证：

- `pixi run test`：505 passed，3 个 opt-in live-network 测试 skipped；
- `pixi run demo`：PASS / WARN / REFUSE；
- `pixi run backend-demo`：A1→A5 协同 PASS；
- A6/B4 契约：`contracts/a5/v0.4.0/`；
- 协同 Trace：`artifacts/backend_demo_trace.json` 和 `.txt`。

## 2. 推荐执行顺序

以下顺序按“阻塞关系优先”，不是要求所有任务只能串行执行。标记为“可独立”的任务可在不等待 live 后端的情况下单独完成。

### T0 — 推送当前集成分支并建立 Draft PR

- 优先级：P0
- 状态：本地已完成，远程未完成
- 原因：GitHub HTTPS 连接重置或 443 不可达；代码和认证无异常。
- 操作：

```powershell
git -C D:\A_demo push -u origin feature/backend-integration
gh pr create --repo neko-claw/OpenEvidence_trace1 --base main --head feature/backend-integration --draft --fill
```

- 完成标准：远程分支存在；Draft PR 指向 `main`；CI 通过；PR 内容不包含本地日志、密钥、伪造医学标识或工具品牌字样。

### T1 — A6 replay/mock 前端

- 优先级：P0
- 可独立：是，现在即可开始
- 建议独立目录：`apps/a6_streamlit/`
- 输入：
  - `a5.facade.answer_text()`；
  - `a5.facade.to_ui_view()`；
  - `contracts/a5/v0.4.0/schemas/AgentRunView.schema.json`；
  - PASS/WARN/REFUSE/ERROR replay fixtures。
- 必须实现：
  - 问题输入与 replay case 切换；
  - PASS/WARN/REFUSE 清晰分色但不只依赖颜色；
  - 最终答案、warnings、limitations、Evidence cards、Trace；
  - REFUSE 时不展示候选 Claim 为事实答案；
  - mock Evidence 显著标注“测试数据，非医学证据”，隐藏 URL；
  - ERROR 使用清洗后的用户信息，不泄露内部异常。
- 测试目录：`tests/a6/`
- 完成标准：四类 replay 全部可展示；Schema 校验通过；无直接 import Mock Adapter；没有解析 Trace 文本来获取结构化字段。

### T2 — B4 批量调用与运行日志

- 优先级：P0
- 可独立：是，可与 T1 同时开始
- 建议独立目录：`b4/`
- 必须实现：
  - 批量读取问题；
  - 每题调用稳定入口并保存完整 `AgentRun` JSON；
  - 断点续跑、run_id 去重、结构化错误记录；
  - 聚合 decision、latency、tool budget、retrieval failure 和 verification failure；
  - replay/mock/live 模式明确分开。
- 测试目录：`tests/b4/`
- 工件目录：`artifacts/b4_runs/`，并在需要时配置忽略大体积运行数据。
- 完成标准：PASS/WARN/REFUSE/ERROR 四类输入可批量运行；单题失败不终止整批；输出通过 AgentRun Schema。

### T3 — A1 正式自由文本安全分类器与政策冻结

- 优先级：P1，阻塞通用 live 问题
- 可独立：大部分可以
- 建议独立目录：`a1/classifiers/`
- 必须实现：
  - `SafetySignalClassifier` 的正式实现；
  - 输出仅限冻结的 `SafetyPolicyInput` 信号；
  - 缺失、异常、低置信度一律 UNKNOWN；
  - 最终 question type、safety scope、拒答规则、termination policy 版本化；
  - prompt injection、个体化诊疗/剂量、急症、隐私和特殊人群测试。
- 契约测试目录：`tests/a1/`
- 完成标准：未知或异常不能变成 ALLOW；Gate0 在任何工具调用前终止；政策版本进入 AgentRun；由 A1 负责人/医学安全负责人审查。

### T4 — A2 live Connector 部署与来源治理

- 优先级：P1，阻塞真实证据检索
- 可独立：是，但需要网络和来源配置
- 现有实现目录：`a2/connectors/`
- 建议将部署组合单列：`deployment/a2/`
- 必须实现：
  - PubMed、Europe PMC、ClinicalTrials 和批准的 Guidelines 连接器 live 配置；
  - 超时、限流、重试上限、缓存、分页和结构化错误；
  - 来源许可、抓取日期、内容 hash、稳定 ID 和 tombstone；
  - 凭据只来自环境，不写入仓库；
  - MCP stdio/HTTP 部署方式和 health check。
- live 测试目录：`tests/live/a2/`
- 完成标准：每次 A5 source request 最多对应一次可观察 MCP 调用；错误 envelope 不会变成空成功；真实记录通过 A2 Schema，mock 记录仍禁止携带外部标识。

### T5 — A3 Embedding 选型、索引评测与冻结

- 优先级：P1，阻塞正式 Vector Search 声明
- 可独立：是，依赖冻结 DEV 集
- 运行实现保留：`a3/indexing/`
- 建议评测独立目录：`evaluation/a3_embedding/`
- 必须实现：
  - 至少比较 lexical-only、候选 Embedding 与可接受基线；
  - 在同一 DEV/qrel 上报告 Recall@50、延迟、内存、索引大小和重建一致性；
  - 中英文及医学术语子集分别报告；
  - 固定 model ID、revision、provider、vector distance、chunk/tokenizer 版本；
  - 失败或未达到阈值时保留 lexical 降级，不伪装 vector 可用。
- 特别约束：BGE-M3 仅是候选，不能预设为默认或优秀模型；是否采用必须由可复现评测决定。
- 完成标准：评测脚本、冻结配置、manifest、逐题结果和结论可以由另一台机器复现。

### T6 — A4 Gate2 质量校准与可选 R2/R3 消融

- 优先级：P1；校准质量分阻塞 live PASS，Cross-Encoder 本身不阻塞 R1
- 可独立：部分可独立，但依赖 T5 的冻结候选池和 B2/qrel
- 运行实现保留：`retrieval/`
- 建议评测独立目录：`evaluation/a4_ablation/`
- 分成两个子任务：
  1. 必需：实现并验证 `CalibratedQualityScorer`，输出跨查询可比较的 `[0,1]` 质量概率；
  2. 可选 P1：在同一 `InitialCandidatePool` 上比较 R0/R1/R2/R3。
- 必须报告：Recall@50、nDCG@K、支持率、冲突率、延迟、校准误差，以及 R3 全部删除的比例。
- 特别约束：
  - query-local rerank 分不能进入 Gate2；
  - raw Cross-Encoder logit 不能通过 sigmoid 冒充已校准概率；
  - Cross-Encoder 只评估 query-document relevance，不承担 Claim-Evidence 医学蕴含；
  - R2/R3 缺少已校准能力时继续保持 PENDING/UNKNOWN。
- 完成标准：质量分语义、版本和校准数据进入 SearchResult/Trace；阈值变化有行为测试；同一题的 R0–R3 只检索一次。

### T7 — A5 生产 Claim Generator 与独立语义 Verifier

- 优先级：P1，阻塞非 exact-span 的 live 可信回答
- 可独立：接口实现可独立，正式校准依赖真实 Evidence 与 gold
- 建议独立目录：
  - `a5/adapters/live_generation/`
  - `a5/adapters/live_verification/`
- 必须实现：
  - 结构化 transport，不在 Adapter 内绑定厂商 SDK、密钥或全局客户端；
  - Claim 只能选本轮 Evidence/Span 白名单；
  - 禁止生成 PMID、DOI、NCT、URL；
  - 生成异常、Schema 漂移或未知字段 fail closed；
  - verifier 与 generator 使用独立调用/模型配置；
  - verifier 的 UNKNOWN/缺失不能变 SUPPORTED；
  - 与 deterministic span/PICO/time/numeric/conflict 检查组合，而不是覆盖它们。
- 评测目录：`evaluation/a5_verification/`
- 完成标准：对独立人工标注集报告 precision/recall、critical false-support rate、校准结果和失败案例；Gate6 仍只发布通过 Claim。

### T8 — Live 组合根、配置检查与服务入口

- 优先级：P1，依赖 T3、T4、T5、T6 的最小生产能力；T7 可先以严格 exact-span 模式接入
- 可独立：否，属于跨模块集成
- 建议独立目录：`deployment/track1_backend/`
- 必须实现：
  - 从环境和版本化配置构造 A1/A2/A3/A4/A5 Dependencies；
  - replay/mock/live 三种模式物理和配置隔离；
  - 启动时检查模型 revision、Schema、MCP endpoint、索引 manifest 和 Gate 版本；
  - health/readiness endpoint；
  - A6 使用的稳定 `answer` 服务入口；
  - 安全日志、超时、取消、请求大小和并发上限；
  - 未配置或版本不匹配时拒绝启动或 REFUSE，不自动退回 mock。
- 测试目录：`tests/live/backend/`
- 完成标准：最小 live 请求经过全部真实边界；依赖缺失时给结构化安全错误；mock 数据无法进入 live PASS。

### T9 — Live 端到端验收与 A6 live 切换

- 优先级：P2，依赖 T8
- 可独立：否
- 建议验收目录：`evaluation/live_acceptance/`
- 必须覆盖：
  - ALLOW / DENY / UNKNOWN；
  - 有结果、空结果、单来源、冲突、过时、预算耗尽；
  - 非法 Evidence ID、缺 Span、PICO/time mismatch、语义 UNKNOWN；
  - PASS/WARN/REFUSE/ERROR；
  - MCP 超时、索引版本漂移、模型不可用；
  - Trace 与 A6 展示一致。
- 完成标准：测试报告包含配置快照、数据版本、失败分层和人工复核；A6 默认仍可回退到 replay 展示，但不能把 replay 当 live。

### T10 — 正式医学效果、安全与合规评测

- 优先级：P3，最后执行
- 可独立：否，需要医学专家、A1/B2/B4 共同参与
- 建议独立目录：`evaluation/medical/`
- 必须实现：正式 gold/qrel、证据充分性、引用正确性、关键 Claim 支持率、安全拒答、亚组/时效性、失败案例和人工审查流程。
- 完成标准：明确数据来源、许可、盲评方法、统计口径和版本；在此之前不得使用“医学级验证完成”或“临床可用”的表述。

## 3. 可单独落目录解决的任务

这些目录应各自拥有 README、配置、测试和完成标准，避免把独立能力塞进 `backend/` 或 A5 workflow：

```text
apps/a6_streamlit/                 # A6 replay/live UI
b4/                                # 批量调用与 AgentRun 日志
a1/classifiers/                    # A1 自由文本安全信号分类
deployment/a2/                     # A2 live MCP/connector 部署配置
evaluation/a3_embedding/           # Embedding 选型与索引复现
evaluation/a4_ablation/            # R0–R3 与质量校准评测
a5/adapters/live_generation/       # 生产结构化 Claim generator
a5/adapters/live_verification/     # 独立语义 verifier
evaluation/a5_verification/        # Claim verification 标注与评测
deployment/track1_backend/         # 跨模块 live composition root
tests/live/                        # opt-in live tests
evaluation/live_acceptance/        # live 端到端验收
evaluation/medical/                # 最后阶段正式医学评测
```

目录约束：

- A1 只决定范围/安全/终止，不直接检索；
- A2 只采集和标准化，不生成答案；
- A3 只负责数据、Span、索引和 Embedding；
- A4 只负责候选检索、排序和显式质量评估；
- A5 只通过 Port 调用上游并决定充分性、Claim、审计和发布；
- A6/B4 只消费版本化输出，不 import Mock Adapter 或内部实现；
- `backend/` 只保留组合与转换，不复制任何成员模块算法。

## 4. 依赖关系

```text
T0 发布当前基线

T1 A6 replay ───────────────┐
T2 B4 batch ────────────────┤  可立即独立进行
                            │
T3 A1 classifier ───────────┐
T4 A2 live connectors ──────┤
T5 A3 embedding freeze ──┐  ├──> T8 live composition ──> T9 live acceptance
                         └─> T6 A4 quality/calibration ─┘
T7 A5 generator/verifier ───────────────────────────────┘

T9 + 医学 gold/专家审查 ──> T10 正式医学评测
```

最短可用路径：先完成 T1/T2；live 最短路径为 T3→T4→T5→T6 必需部分→T8→T9。R2/R3 Cross-Encoder 消融和高级语义 verifier 可以在严格 fail-closed 的 R1/exact-span 基线上后续增强，但缺少校准质量分时 live 不允许 PASS。

## 5. 每个任务的统一验收规则

每完成一个任务都必须：

1. 先读取根目录 `AGENTS.md`、规划文档和相关模块契约；
2. 不修改不属于该任务的用户改动；
3. 优先新增 Adapter/独立目录，不重写 A5 状态机；
4. Mock 必须 `mock=true`，不得携带伪造 PMID/DOI/NCT/URL/指南编号；
5. UNKNOWN 不得默认变成 ALLOW/SUPPORTED/高质量；
6. 阈值和版本来自配置/资产并记录到 Run；
7. 先跑最小相关测试，再跑 `pixi run test`；
8. 后端变化还要跑 `pixi run demo` 和 `pixi run backend-demo`；
9. 更新 `ready.md` 和本地 `log.md`；`log.md` 永不提交；
10. 检查 diff、密钥、伪标识、无关文件和文档承诺与实际实现的一致性；
11. 未满足完成标准时明确写 NOT READY，不允许伪通过。

## 6. 可直接复制使用的提示词

如需把目录复制到另一台机器，并让对方一次完成 A6 接入前的 A1–A5 全部工程工作，
优先使用根目录 `HANDOFF_A1_A5.md`。该文件额外处理了本目录 `.git` 为旧机器 worktree
链接、稳定提交尚未推送、换机环境重建、live 外部依赖和正式验收边界。下面的提示词适合
在当前机器或 Git 已正常恢复后的单项续作。

```text
你现在负责继续完成 OpenEvidence 赛道一后端与 A6/B4 接入工作。

工作目录：D:\A_demo
规范基线：docs/OpenEvidence_MVP_赛道1与赛道3实施规划.md
任务清单：ready.md
当前稳定提交：bb5218f17d9f73b878c2a6337423a602c5421d85

执行约束：
1. 不开启多 Agent；在当前任务中单线程完成。
2. 先完整阅读 AGENTS.md、ready.md、README.md、INTEGRATION.md、
   docs/backend_integration_architecture.md、docs/review_compliance.md 和
   docs/merge_readiness_report.md，再检查 git status、当前分支和现有测试命令。
3. 从 ready.md 中选择尚未完成且依赖已满足的最高优先级任务；不得跳过依赖，
   不得把多个所有权不同的模块混写在一起。
4. 可独立解决的能力必须放入 ready.md 指定的独立目录，并包含 README、配置、
   Port/Adapter、行为测试和完成标准。backend/ 只做组合，不复制 A1/A2/A3/A4 算法。
5. 保持 A5 有限状态机和公开 AgentRun/AgentRunView 契约稳定；优先新增 Adapter，
   不推倒重写。
6. Gate0、Gate2、Gate5、Gate6 全部 fail closed。UNKNOWN 不得成为 ALLOW、
   SUPPORTED 或已校准质量。A4 query-local rerank 分不得进入 Gate2。
7. Embedding 由 A3 所有。不得在 A4 再加载模型；BGE-M3 仅作为候选，必须由同一
   DEV/qrel 上可复现的 Recall@50、延迟、内存和索引重建结果决定是否采用。
8. Cross-Encoder 属于可选 P1。raw logit 不得通过 sigmoid 冒充校准概率；它只做
   query-document relevance，不做 Claim-Evidence 医学蕴含。
9. Mock 数据必须 mock=true，且不得带伪造 PMID、DOI、NCT、URL 或指南编号；
   不得用 fixture 预埋支持标签冒充 verifier。
10. 版本、Prompt、模型 ID/revision 和阈值必须来自版本化配置/资产，并保存到
    AgentRun/Trace。凭据只允许来自环境变量，不得写入仓库或日志。
11. 每完成一个小阶段先运行最小相关测试并修复，再继续。最终必须运行：
    pixi run test
    pixi run demo
    pixi run backend-demo
12. 更新 ready.md：标记完成项、实际测试结果、剩余依赖和下一任务；同时更新本地
    log.md，但绝不暂存或提交 log.md。
13. 提交前检查 git diff、git status、Schema 漂移、密钥、伪医学标识、无关改动，
    以及文档承诺是否有真实代码和测试支撑。
14. 未通过全部相关测试时不得宣称 READY。不得把 mock/offline 通过描述成 live、
    临床有效或医学级验证完成。

本轮执行步骤：
A. 根据 ready.md 输出所选任务、依赖、独立目录和 Definition of Done。
B. 检查现有实现，形成最小增量计划。
C. 实现代码、配置、契约和测试。
D. 运行定向测试并修复。
E. 运行完整测试和相关 demo。
F. 更新文档、ready.md 与本地 log.md。
G. 自审 diff。只有全部通过后才创建聚焦提交；未经明确要求不要直接合入 main，
   不要 force-push。

如果某项依赖外部交付，完成所有不依赖外部输入的部分，保留正式 Port/Adapter 和
契约测试，精确记录阻断字段/接口；不得用假实现冒充生产能力。
```

## 7. 下一步建议

当前最合理的下一步是：

1. 网络恢复后先完成 T0；
2. A6 立即按 T1 使用 replay fixture 开发前端；
3. B4 按 T2 建立批量日志能力；
4. 后端团队从 T3 开始推进 live 最短路径；
5. 每完成一项就在本文件中将状态、测试结果和下一依赖更新一次。
