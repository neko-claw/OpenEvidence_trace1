# A1–A5 换机执行提示词

## 使用前说明

把整个 `A_demo` 目录复制到新机器，但不要直接在唯一副本上执行破坏性 Git 操作。

当前目录来自 Git worktree，`.git` 是一个文本链接，内容指向原机器的：

```text
D:/lenovo/Desktop/A5_demo/.git/worktrees/A_demo
```

该路径在新机器上通常不存在，因此直接复制后 `git status` 可能失败。当前本地稳定提交
`bb5218f17d9f73b878c2a6337423a602c5421d85` 也尚未成功推送到 GitHub。新机器必须先保护
原副本，再恢复 Git 工作目录；不得因为远程找不到该提交而用旧分支覆盖复制来的新代码。

推荐准备：

- Windows 10/11、PowerShell；
- Git 和 GitHub CLI；
- Pixi；
- 可以访问 conda-forge、PyPI、GitHub、NCBI、Europe PMC、ClinicalTrials；
- 足够磁盘空间用于 `.pixi`、模型快照、Chroma 和评测工件；
- 如运行大型 Embedding/Cross-Encoder，准备可用 GPU；CPU 可以运行基础测试，但完整模型评测可能较慢；
- 不复制 `.env`、API key、访问令牌或个人缓存；在新机器重新设置环境变量。

下面整段可以直接复制给新机器上的代码执行助手。

## 可直接复制的完整提示词

```text
你现在接手 OpenEvidence 赛道一 A1、A2、A3、A4、A5 的换机续作。你的目标是在不开发 A6
界面的前提下，完成 A6 接入前 A1–A5 所有能够被工程测试、live 测试和正式评测证明的工作，
并提供冻结的 A6/B4 下游契约。不得用 Mock、README 声明、字段占位或未经校准的分数冒充完成。

一、已知上下文

1. 复制来的目录名为 A_demo。先解析它的绝对路径，后续不要写死旧机器的 D:\A_demo。
2. 规范基线：docs/OpenEvidence_MVP_赛道1与赛道3实施规划.md。
3. 后续任务与目录建议：ready.md。
4. 架构说明：docs/backend_integration_architecture.md。
5. 集成边界：INTEGRATION.md。
6. Review 与验收：docs/review_compliance.md、docs/merge_readiness_report.md。
7. 当前稳定代码提交标识：bb5218f17d9f73b878c2a6337423a602c5421d85。
8. 当前稳定离线结果：505 passed、3 个 opt-in live-network 测试 skipped；A5 demo 的
   PASS/WARN/REFUSE 通过；A1→A2 MCP→A3→A4→A5 后端协同 demo PASS。
9. 该提交尚未成功推送，不能假定远程存在。
10. 不开启多 Agent；在当前任务单线程持续执行，避免并行修改同一工作目录。

二、第一阶段：安全恢复换机工作目录

复制来的 `.git` 很可能是 Git worktree 链接，指向旧机器：
D:/lenovo/Desktop/A5_demo/.git/worktrees/A_demo。

严格执行：

1. 不删除、不覆盖复制来的唯一 A_demo。先创建一个完整备份或在同级创建新的工作目录。
2. 读取 `.git` 类型和内容；运行 `git status`。如果 Git 可用且 HEAD 为 bb5218f，则继续。
3. 如果 `.git` 是失效 worktree 链接：
   - 保留原 A_demo 作为只读源码快照；
   - 尝试从远程仓库 https://github.com/neko-claw/OpenEvidence_trace1.git 克隆到新的工作目录；
   - 远程可能没有 bb5218f，所以不能用远程旧代码覆盖源码快照；
   - 将源码快照中除 `.git`、`.pixi`、`__pycache__`、`.pytest_cache`、`.tmp`、本地数据库、
     模型缓存和 log.md 以外的项目文件复制/同步到新工作目录；
   - 在新工作目录创建独立分支，例如 feature/a1-a5-live-completion；
   - 比对关键文件 backend/、a1/ports/、a2/adapters/a3_evidence.py、
     retrieval/a3_pool_adapter.py、a5/facade.py、contracts/a5/v0.4.0/ 和 ready.md 均存在；
   - 先提交一个“恢复复制快照”的本地基线提交，再继续开发；
   - 不运行 reset --hard、clean -fd、checkout -- .，不删除用户唯一副本。
4. 如果无法访问远程，允许在一个新的空目录 `git init` 后导入源码快照并创建本地基线提交；
   记录原始远程 URL 和 bb5218f 标识，网络恢复后再做历史对比。不要因此停止代码和离线测试。
5. 检查 `log.md` 被根 `.gitignore` 忽略。每次任务结束更新它，永不暂存或提交。
6. 读取根 AGENTS.md 和任何 AGENTS.override.md；其规则高于本提示词中的普通建议。
7. 输出“换机恢复报告”：工作目录、Git 恢复方式、当前 HEAD、与源码快照差异、缺失文件、
   Python/Pixi/Git/GPU/网络状态。确认无源码丢失后才能继续。

三、环境建立与基线复验

1. 检查 Git、gh、Pixi，不要假定全局 Python 依赖可用。
2. 使用仓库 pixi.lock 安装锁定环境：优先 `pixi install --locked`。如果锁文件或平台不兼容，
   记录原因后做最小兼容修复，不随意升级大依赖。
3. 不复制旧机器 `.pixi` 环境和模型缓存；在新机器重建。
4. 先运行：
   - pixi run test
   - pixi run demo
   - pixi run backend-demo
5. 若失败，先区分环境问题、路径问题、Schema 漂移和真实代码回归。修复基线后再开发。
6. 验证 contracts/a2、contracts/a3、contracts/a5 与 Pydantic runtime model 一致；必要时调用仓库
   exporter 后检查无意外漂移。
7. 检查所有 Mock 数据：必须 mock=true，不能携带伪造 PMID、DOI、NCT、URL 或指南编号。

四、不可改变的架构边界

保持以下唯一控制关系：

Question
  -> A5 Gate0 调 A1 safety/scope
  -> A5 分类、Skill Router、SearchPlan、ToolBudget
  -> A2 只读 MCP 工具
  -> A2 Evidence 归一化为 A3 Evidence/Chunk/Span
  -> A3 BM25/Vector SearchHit 和 IndexManifest
  -> A4 同一 InitialCandidatePool 上检索/排序/消融
  -> A5 Gate2 证据充分性
  -> A5 Gate3 原子主张计划
  -> A5 Gate4 结构化 Claim 生成和白名单约束
  -> A5 ClaimSplitter/citation_audit/Gate5
  -> A5 Gate6 PASS/WARN/REFUSE
  -> AgentRun/AgentRunView 给 A6，完整 AgentRun 给 B4

职责：

- A1 只做问题范围、安全、拒答和终止，不检索证据。
- A2 只做真实工具、采集、缓存、去重、标准化和错误 envelope，不决定答案。
- A3 只做 Evidence/PICO/Span/Chunk、存储、索引、Embedding 和 provenance。
- A4 只做候选检索、RRF、特征重排、MMR、可选 Cross-Encoder 和显式质量评估。
- A5 只通过 Port/Adapter 使用上游，并负责充分性、Claim、Citation Audit 和发布决策。
- backend/ 只做组合和转换，不复制 A1/A2/A3/A4 算法。
- 保持 A5 FSM 和公开 answer(...)->AgentRun、AgentRunView 契约稳定；优先新增 Adapter。
- Gate0、Gate1、Gate2、Gate5、Gate6 fail closed。UNKNOWN 不得变成 ALLOW/SUPPORTED/高质量。

五、完成 A1：自由文本安全分类与策略冻结

目标目录：a1/classifiers/；测试放在 tests/a1/ 或现有 A1 测试体系。

必须完成：

1. 实现可注入的正式 SafetySignalClassifier；输入只含 question_id/text，输出严格
   SafetyPolicyInput 或明确 UNKNOWN，禁止让 A5 用关键词自行补安全规则。
2. 对急症、个人诊断、个体化用药/剂量、提示注入/伪造引用、可识别隐私、特殊人群和普通
   证据问题建立行为测试。
3. 任何超时、异常、低置信度、字段缺失、枚举外值均 UNKNOWN→REFUSE，且工具调用次数为 0。
4. 冻结 question type、安全范围、拒答规则、Agent termination policy 和版本；版本进入 AgentRun。
5. 如果使用模型分类，Prompt/JSON Schema/version 放入资产目录，transport 通过 Port 注入，不在代码中
   绑定密钥/厂商 SDK。没有模型时保留严格 fail-closed，不得用临时关键词宣称正式完成。
6. 需要医学安全负责人审查的规则列入明确签字清单。未获审查时工程实现可完成，但临床政策状态必须
   标为 PENDING_REVIEW。

A1 完成证据：契约、行为测试、Gate0 零工具调用测试、版本快照、review checklist。

六、完成 A2：真实 Connector、MCP 与来源治理

运行代码保留 a2/connectors/；部署配置单列 deployment/a2/；live 测试放 tests/live/a2/。

新机器环境变量从 `.env.example` 重新配置，至少包括 NCBI_EMAIL、NCBI_TOOL、可选 NCBI_API_KEY；
不要提交 `.env`。只有用户明确提供或已配置的普通项目凭据才可使用，禁止从其他目录提取凭据。

必须完成：

1. PubMed、Europe PMC、ClinicalTrials live 调用；Guidelines 只能使用批准 manifest 中的来源，不能任意抓站。
2. 每个 Connector 有超时、限流、有限重试、分页、缓存、HTTP/解析异常和结构化错误测试。
3. MCP stdio/HTTP 部署方式、health/readiness、Tool Schema 和错误 envelope 版本化。
4. 每次 A5 source request 最多对应一次可观察 MCP tool call；Connector 内部 HTTP 重试必须记录计数，
   不能隐形突破 A5 工具预算。
5. 真实 Evidence 保留来源 URL、抓取时间、content hash、稳定真实 ID、许可/provenance；空结果与错误分开。
6. 运行现有 opt-in live 测试：设置 A2_LIVE_TESTS=1 后执行 tests/test_a2_live.py，并扩展 Guidelines
   允许来源测试。网络不可用时不得把 skipped 当 PASS；记录 BLOCKED_NETWORK。
7. 不大规模抓取；只用小规模、可核验的公开记录做连接与契约验收。

A2 完成证据：live 测试结果、MCP discovery/call/cache/error Trace、来源许可/manifest、无密钥扫描。

七、完成 A3：Embedding 选型、索引冻结和复现

运行实现保留 a3/indexing/；评测单列 evaluation/a3_embedding/。

必须完成：

1. 不默认采用 BGE-M3。它只是候选，必须与 lexical-only 和至少一个合理候选/基线在同一冻结 DEV/qrel
   上比较。若只有一个模型可运行，明确记录选择不足，不能宣称最优。
2. 数据和 qrel 必须有来源、许可、版本、人工/构造方法说明；Mock smoke qrel 不能作为正式模型结论。
3. 报告总体及中文、英文、医学术语子集：Recall@50、延迟 p50/p95、吞吐、内存/显存、索引大小、
   构建耗时、两次重建的一致性。
4. 固定 model ID、revision、provider、source_kind、precision、normalize、vector distance、chunk/tokenizer
   版本；写入 IndexManifest/runtime-effective snapshot。
5. 模型文件可通过 A3_BGE_M3_MODEL_PATH 等显式本地路径注入，但绝对路径不得进入索引语义 hash 或提交。
6. A4 不得加载模型或创建第二套向量。A3 通过 EmbeddingProvider 和 SearchHit 把结果交给 A4。
7. 未达阈值或模型不可用时，保留 lexical-only/UNKNOWN 降级并阻止 production vector capability。

A3 完成证据：可重复评测脚本、冻结配置、逐题结果、manifest、重建 hash、模型选择报告。真实阈值必须
由规划/负责人冻结；不存在冻结阈值时只能报告结果和 PENDING_APPROVAL，不能自定医学生产标准。

八、完成 A4：检索、质量校准和 R0–R3

运行实现保留 retrieval/；评测单列 evaluation/a4_ablation/。

必须完成：

1. 每题只调用 retrieve_initial_pool 一次，R0/R1/R2/R3 共享 immutable InitialCandidatePool/pool_hash。
2. R0=BM25+Vector+RRF；R1=R0+feature rerank+MMR；R2=R1+显式已校准 Cross-Encoder；
   R3=R2+Claim-Evidence support filter，全部删除时返回 EMPTY，不恢复候选。
3. ranking 与 quality 严格分开：query-local rerank 只能是 RANKING/QUERY_LOCAL/calibrated=false；
   A5 Gate2 只能消费显式 CalibratedQualityScorer 的 QUALITY/CROSS_QUERY/calibrated=true。
4. raw Cross-Encoder logit 不得直接使用 sigmoid 冒充概率。必须有独立校准集、校准方法、可靠性曲线/
   ECE 或 Brier 等结果、版本和测试。否则 R2/R3 维持 PENDING/UNKNOWN。
5. Cross-Encoder 只做 query-document relevance，不得承担 Claim-Evidence 医学蕴含。
6. 正式同池消融报告 Recall@50、nDCG@K、证据支持率、冲突率、R3 全删率、p50/p95 latency 和资源成本；
   Mock smoke 指标与正式结果分开。
7. 实现并验证 Gate2 所需 CalibratedQualityScorer；如果没有合法校准数据，live 不允许 PASS，不能用固定
   0.9、排名归一化或 fixture scorer。

A4 完成证据：同池 Trace、逐题/聚合报告、校准报告、R2/R3 capability 状态、ranking/quality 防串线测试。

九、完成 A5：生产结构化生成、独立验证和发布门禁

实现放 a5/adapters/live_generation/、a5/adapters/live_verification/；评测放 evaluation/a5_verification/。

必须完成：

1. 保持 versioned Skill/Prompt/JSON Schema/fixture/implementation。Prompt 不写在 Python 大字符串中。
2. Claim generator 使用结构化 transport Port；只输出 Atomic Claim；Evidence ID 和 Span ID 只能从本轮
   白名单选择；禁止生成 PMID/DOI/NCT/URL。
3. generator Schema 漂移、额外字段、非法 ID、无 Span、异常或超时 fail closed。
4. verifier 与 generator 使用独立调用和配置；UNKNOWN、缺失 score、缺 span/PICO/time 或明确冲突
   不能变 SUPPORTED。
5. Composite verifier 必须保留 deterministic Evidence whitelist、Span、PICO、time、numeric/unit、conflict
   检查；语义模型不能覆盖这些硬失败。
6. Claim.uncertainty 继续参与 Gate6；critical HIGH/UNKNOWN 不得 PASS。
7. Finalizer 只发布 SUPPORTED Claim；非关键不足可 WARN 并删除，关键不足/冲突/非法引用 REFUSE。
8. 建立独立人工标注 verification 集，报告 precision、recall、critical false-support rate、校准、失败案例。
   若没有合格人工 gold，只能把 transport/Port/失败门禁标为 ENGINEERING_READY，医学验证标 PENDING。
9. Runtime config snapshot 记录 Agent/Skill/Prompt/Gate/model/threshold/verifier 版本，不记录秘密。

A5 完成证据：生产 Adapter 契约测试、独立验证评测、PASS/WARN/REFUSE/ERROR、非法引用/Span/PICO/time/
uncertainty/冲突测试、完整 Trace。

十、建立 A1–A5 live composition，但不开发 A6

目录：deployment/track1_backend/；测试：tests/live/backend/。

必须完成：

1. 从版本化配置和环境构造 A1 classifier/policy、A2 MCP client、A3 approved Embedding/index、A4
   RetrievalService/CalibratedQualityScorer、A5 generator/verifier/workflow。
2. replay/mock/live 三种模式隔离。live 缺依赖时拒绝启动或返回结构化 REFUSE/ERROR，绝不自动切 mock。
3. 启动检查 Schema、Prompt/Skill/Gate version、model revision、index manifest、MCP endpoint 和 calibration。
4. 提供供 A6 调用的稳定服务入口及 health/readiness；不要实现 A6 页面。
5. 实现请求超时/取消、大小/并发上限、安全日志、Trace 持久化接口；错误信息对外清洗。
6. 至少一个小规模 live 请求经过 A1→A2 MCP→A3→A4→A5；同时覆盖 DENY/UNKNOWN、空结果、单来源、
   冲突、过时、预算耗尽、非法引用、缺 Span、模型/MCP 不可用。
7. mock Evidence 无论如何不能进入 live PASS。

十一、A6 接入前最终验收

全部运行并保存原始摘要：

1. pixi run test
2. pixi run demo
3. pixi run backend-demo
4. A2_LIVE_TESTS=1 的 A2 live tests（若网络和来源可用）
5. A3 正式 embedding evaluation
6. A4 正式 quality calibration 与同池 ablation
7. A5 verification evaluation
8. tests/live/backend/ 的端到端测试
9. compileall、Schema exporter/drift、git diff --check
10. 扫描密钥、绝对本地路径、伪造医学标识、Mock 泄漏和生成工具品牌字样

更新并生成：

- ready.md：每项 DONE / PARTIAL / BLOCKED、测试结果、外部阻断、下一任务；
- docs/a1_a5_final_readiness.md：A1–A5 分模块验收矩阵；
- docs/a6_handoff.md：A6 服务入口、AgentRunView Schema、四类 replay、live health、错误码和示例；
- artifacts/live_acceptance/：配置快照、Trace、评测摘要，不含秘密和大模型文件；
- 本地 log.md：完整进度，但永不提交。

只有以下条件全部满足，才可写“A1–A5 ENGINEERING READY FOR A6 LIVE INTEGRATION”：

- A1 正式 classifier/policy 审查完成，或明确限定为已审查的允许范围；
- A2 真实来源 live 工具和结构化失败通过；
- A3 选定 Embedding/索引有冻结、可复现的正式 DEV 结果；
- A4 有合法的 Gate2 calibrated quality，ranking 未串线；
- A5 生产 generator/verifier Adapter 与 fail-closed 门禁通过；
- live composition 无依赖时不 mock fallback；
- 全量 offline 和 live 验收通过；
- A6 契约无 Schema 漂移。

只有医学专家 gold、政策审查和正式医学评测也完成时，才可以进一步写“MEDICALLY VALIDATED”。
如果缺少专家、正式 gold、网络、凭据、GPU/模型授权或冻结阈值，不得自行编造。此时：

- 完成其余所有工程项；
- 将缺失项精确标为 BLOCKED_EXTERNAL；
- 写清负责人、所需文件/权限、接入目录、可执行命令和解除阻断后的回归范围；
- 不把 skipped、fixture、固定分或 smoke metric 算作正式通过。

十二、执行纪律

1. 先给出 Phase 计划，再修改代码；每完成一 Phase 更新计划和最小测试结果。
2. 不停在分析阶段；持续完成所有不依赖外部输入的工作。
3. 不新增大型生产依赖，除非已有架构确实需要、锁文件可复现并说明收益。
4. 不复制外部仓库大段实现；引用方法时记录论文/官方仓库和许可证，只借鉴模式。
5. 不覆盖用户无关改动；不 force-push；不直接提交 main；提交前自审完整 diff。
6. 每次提交聚焦一个阶段。所有 blocking item 通过前不得宣称 MERGE READY。
7. GitHub 上传的代码、提交信息、PR 和文档不要出现代码执行助手的品牌名称或自动生成署名。
8. 最终回复必须列出：工作目录、branch、commit、push/PR、A1–A5 状态、每项测试实际结果、live Trace、
   A6 handoff 路径、外部阻断及精确下一命令。

现在从“安全恢复换机工作目录”开始。不要询问可以从本地文件、环境检查或规范中确定的信息。
如果确实缺外部授权/数据，先完成所有其他工作，再一次性汇报精确阻断；禁止用假实现伪通过。
```

## 新机器必须额外提供的外部输入

仅复制 `A_demo` 不能保证完成 live/医学验收。至少还需要按实际目标准备：

1. 网络与依赖源访问；
2. GitHub 仓库权限（用于最后推送，不影响本地开发）；
3. NCBI email/tool 和可选 API key；
4. 批准的 Guidelines 来源清单、使用许可和必要访问方式；
5. Embedding/Cross-Encoder 模型的合法下载权限或本地快照；
6. 冻结的 DEV questions/qrels 与来源/许可；
7. A1 医疗安全规则审查负责人；
8. A5 Claim-Evidence 人工标注与医学验证负责人；
9. 项目认可的正式指标阈值。若阈值尚未冻结，只能产出评测结果和待审批状态。

缺少第 6–9 项时，工程代码可以完成并 fail closed，但不能诚实地宣布医学级或正式生产验证完成。
