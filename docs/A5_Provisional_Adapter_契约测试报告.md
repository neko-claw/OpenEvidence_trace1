# A5 Provisional Adapter 与契约测试报告

> 初版日期：2026-08-11；复核日期：2026-08-12
> 工作分支：`feature/a5-trust-integration`
> 规划基线：`OpenEvidence MVP：赛道 1 与赛道 3 实施规划` v0.5
> Adapter 配置版本：`a5-upstream-adapters-v0.3.0`
> 当前状态：**REVIEWED BRANCH CONTRACTS / 尚未全部进入 main**

最新逐成员兼容性、rerank/Embedding 风险和 Gate1/分数语义实施结果见
`docs/A1_A2_A3_A4_A5_兼容性审查与实施报告.md`；本文件保留初版 Adapter
设计记录。

## 1. 报告结论

本轮已经为 A1、A2、A3、A4 建立可替换的 provisional Adapter、窄 Port、配置化字段/枚举映射和契约测试。A5 的有限状态机与公开 `answer(...)->AgentRun` API 未改变；上游正式契约到达后，应优先替换对应 Adapter 和测试 fixture，不重写 Agent 主流程。

本轮实现遵守赛道一的以下约束：

- A1 安全结论只有显式 `ALLOW` 才能通过；缺失、异常、未知均由 Gate0 fail-closed 拒绝。
- A2/A3/A4 数据进入 A5 前必须经过兼容模型和 Adapter，不允许 Workflow 直接 import 上游具体实现。
- Mock 数据必须显式 `mock=true`，不得携带伪造 PMID、DOI、NCT、URL 或指南编号。
- 缺失 page、span、PICO、时间、score 或 provenance 时保留 UNKNOWN/null，不补造默认真值。
- 检索不足属于 Gate2；主张支持不足属于 Gate5，二者在诊断与 Trace 中分开。
- 上游版本、配置状态和映射规则写入 `RuntimeConfigSnapshot.integrations`，保证 Run 可追溯。

## 2. 实现范围

```text
A1 Question / Safety evaluator
        ↓
A1QuestionAdapter / A1SafetyPolicyAdapter
        ↓
A5 Question + Gate0

A2 MCP client ──→ A2MCPRetriever ──┐
A3 Evidence/Chunk ─→ A3EvidenceAdapter ├─→ EvidenceRecord / EvidenceSpan
A4 SearchResult ──→ A4RAGRetriever ─┘
                                        ↓
                              Gate2 → Claim → Gate5 → Gate6
```

主要文件：

| 类型 | 文件 | 作用 |
|---|---|---|
| Adapter | `a5/adapters/provisional/a1.py` | A1 Question 与 Safety verdict 适配 |
| Adapter | `a5/adapters/provisional/a2.py` | A2 Evidence/MCP 临时边界与 Gate1 检查 |
| Adapter | `a5/adapters/provisional/a3.py` | A3 Evidence/Chunk 到 A5 Evidence/Span 映射 |
| Adapter | `a5/adapters/provisional/a4.py` | A4 Query/SearchResult 到 A5 RetrievalResult 映射 |
| Port | `a5/ports/a1_policy_evaluator.py` | 注入 A1 安全判定实现 |
| Port | `a5/ports/a2_mcp_client.py` | 注入 A2 MCP 客户端，不实现 MCP Server |
| Port | `a5/ports/a4_search_service.py` | 注入 A4 search/rerank 服务 |
| 配置 | `config/integrations.yaml` | 契约版本、来源、状态、工具名和枚举映射 |
| 测试 | `tests/test_provisional_upstream_adapters.py` | 上游兼容、fail-closed 与漂移检测 |

## 3. 契约测试策略

契约测试不是只验证“函数能够运行”，而是验证跨模块边界上的不可违反条件。

| 测试层 | 验证内容 | 失败时含义 |
|---|---|---|
| Schema | 必填字段、枚举、额外字段、JSON Schema 导出 | 上游契约发生漂移或输入非法 |
| Adapter | 字段、状态、span、PICO、版本和诊断映射 | A5 可能误读上游结果 |
| Fail-closed | UNKNOWN、安全异常、缺 provenance、FAILED 状态 | 不得继续检索、生成或发布 |
| Mock 合规 | `mock=true`、禁止真实样式标识符和 URL | Fixture 可能被误认为医学证据 |
| 可复现性 | index/corpus/rerank/config/contract version | AgentRun 无法重放或比较 |
| 架构边界 | Workflow 依赖 Protocol，而非上游或 Mock 具体类 | 后续接入可能需要重写主流程 |

当前新增测试覆盖：

- A1 严格 Schema 与可导出 JSON Schema。
- A1 question type 确实影响 Skill 搜索计划，而不是只保存字段。
- A1 Safety 只有有效显式 verdict 才能通过； evaluator 异常时检索调用次数保持为 0。
- A2 Gate1 provenance 缺失时拒绝生产映射；非法 Mock 标识符拒绝。
- A2 MCP 工具路由、非法 item 隔离及 FAILED 状态异常传播。
- A3 chunk 到可定位 span 的映射；非法 page 不猜测；fixture 缺 `mock=true` 时拒绝。
- A4 SearchResult 状态、版本、rank、span、冲突和诊断映射。
- A4 非法/未知 score 保留 `None`；FAILED 不伪装成空结果。
- A4 缺 index/corpus/rerank 版本时拒绝，以保护可复现性。
- Runtime config snapshot 保存 A1/A2/A3/A4 实际契约版本和 provisional 状态。
- Provisional Adapter 不直接 import A1/A3/A4 具体包，也不依赖 `MockEvidenceRetriever`。

## 4. A1 对 provisional Adapter 与契约测试的影响

### 4.1 当前 A1 输入

本轮参考的 A1 快照为：

- Question Schema：`question-v0.2`
- Agent termination rules：`agent-termination-v0.1`
- 来源分支：`agent/a1-core-deliverables-v2`

A1 当前题型枚举为：

- `stable_mechanism`
- `guideline_treatment`
- `latest_research_trial`
- `insufficient_conflict_out_of_scope`

### 4.2 对 Adapter 的直接影响

1. **问题分类不再只能依赖 A5 关键词规则。**
   `A1QuestionAdapter` 严格校验 A1 Question 后，将 `question_type` 和 `a1_contract_validated=true` 写入 A5 Question metadata。`EvidenceResearchSkill` 只有在该标记存在且题型位于已加载配置时，才采用 A1 的分类结果。

2. **A1 题型影响检索计划。**
   `config/skills.yaml` 为四类 A1 问题配置 preferred sources、expected evidence types、freshness 和 max tool calls。字段不只是被保存，而是真正影响 PLAN 与后续检索来源。

3. **A1 决定 Gate0 的权威输入，但当前没有可调用 evaluator。**
   因此 A5 只定义 `A1PolicyEvaluator` Port，并通过依赖注入调用。Adapter 不自行解释或补写医疗安全规则。

4. **安全状态必须三值化。**
   A1 返回 `ALLOW`、`DENY` 或 `UNKNOWN`；缺失字段、非法值、调用异常全部转换为 `UNKNOWN`。Gate0 对 `DENY/UNKNOWN` 均 REFUSE，且发生在检索之前。

5. **A1 termination rules 不能被 Adapter 静默替代。**
   当前 A5 仍执行自身已经测试的有限状态机终止条件。待 A1 提供可执行终止策略或稳定 reason-code 契约后，应新增 termination policy Adapter；不能把 YAML 描述直接当成已接入能力。

### 4.3 对契约测试的影响

| A1 风险 | 对应测试保证 |
|---|---|
| Question 字段或枚举漂移 | 严格 Pydantic validation 与 JSON Schema 属性集合测试 |
| question type 只记录、不执行 | 验证其实际改变 `SearchPlan` |
| evaluator 异常后继续检索 | 验证决策 REFUSE 且 retriever 未被调用 |
| 非法安全值被默认放行 | 验证非法/异常均为 UNKNOWN |
| A1 元数据被未验证输入伪造 | 仅认可 `a1_contract_validated=true` 且配置存在的题型 |

### 4.4 A1 后续交付后的接入动作

- 将正式 evaluator 实现注入 `A1SafetyPolicyAdapter`。
- 对比 Question Schema 字段和枚举，更新 A1 compatibility model 与 schema-drift 测试。
- 将稳定的 refusal reason、scope 和 termination policy 映射到 A5 Trace/Decision。
- 删除已经被正式契约取代的临时题型配置；保持 Workflow 与 `AgentRun` 外层结构不变。

## 5. A3 对 provisional Adapter 与契约测试的影响

### 5.1 当前 A3 输入

本轮参考快照为 `feature/a3-data-wiki@1c3520b`。当前可见能力主要包括 Evidence、Chunk、IndexVersion、SQLite、确定性切块和 BM25 相关结构；PR 仍存在 fixture 合规、向量索引、Wiki、打包、tombstone 与版本管理等阻断项。

### 5.2 对 Adapter 的直接影响

1. **A3 的 `abstract_or_chunk` 必须映射为 A5 最小内容视图。**
   Adapter 将其映射为 `EvidenceRecord.content`，不要求 A5 核心绑定 A3 数据类。

2. **A3 决定 Gate5 能否进行 span 定位。**
   `chunk_id` 映射到 `EvidenceSpan.span_id/chunk_id`，page、section 和 text 原样保留。page 只有为正整数时才接受，否则保持 UNKNOWN，不推断页码。

3. **A3 决定 PICO/证据等级检查的数据完整度。**
   population、intervention、comparator、outcome、evidence level 和 content hash 被保留；缺失值不会默认 match。Gate5 后续只能基于实际存在的 metadata 判断。

4. **A3 fixture 现状影响 Mock 安全边界。**
   当前部分 fixture 可能缺 `mock=true` 或包含真实样式标识符。Adapter 会拒绝“看起来像 fixture 但未明确声明 Mock”的记录；Mock 路径禁止 PMID、DOI、NCT、URL 和指南编号。

5. **A3 不是 A2 provenance 的替代品。**
   A3 可以提供 chunk/span/index 元数据，但正式 Evidence 来源完整性仍以 A2 冻结 Schema 和采集链路为准。A5 不把 A3 当前模型升级为项目正式 Evidence Schema。

### 5.3 对契约测试的影响

| A3 风险 | 对应测试保证 |
|---|---|
| chunk 无法定位到原证据 | 验证 evidence_id、chunk_id/span_id、page、section 映射 |
| page/section 缺失时伪造定位 | 验证非法 page 保持 UNKNOWN |
| PICO 缺失被默认视为一致 | Adapter 只保存实际值；缺失值不生成 `True` |
| fixture 被当作真实证据 | 缺 `mock=true` 或包含禁用标识符时拒绝 |
| A3 模型变化迫使重写 Workflow | 架构测试确保 A5 只依赖自身 domain model/Port |

### 5.4 A3 后续交付后的接入动作

- 对比冻结后的 Evidence/Chunk/Span/PICO/IndexVersion，输出 Integration Diff。
- 若字段仅重命名或嵌套变化，只修改 `A3EvidenceAdapter`。
- 增加 content hash、tombstone、index/corpus version 与 provenance 的正式契约测试。
- 使用 A3 正式 fixture 替换临时测试输入；仍要求 Mock 与真实证据严格隔离。
- Gate5 只在正式 span/PICO 数据存在时增强检查，不把 UNKNOWN 自动提升为 SUPPORTED。

## 6. A4 对 provisional Adapter 与契约测试的影响

### 6.1 当前 A4 输入

本轮参考快照为 `A4-review@1d51f1d`。当前 A4 已提供 SearchResult、selected chunks、RankLog、degradation reasons、stage latency、index/corpus/rerank version、conflicts 和诊断性 claim support 等结构，但 Query 构造、字段词表和 provenance 尚未冻结。

### 6.2 对 Adapter 的直接影响

1. **A1 与 A4 词表不一致，需要配置映射。**
   例如 A1/A5 的 `current_guideline` 在 A4 侧应映射为 `guideline`。question type、freshness、source type 和 topic 的转换统一来自 `config/integrations.yaml`，不得散落硬编码。

2. **A4 决定 Gate2 可观察到的检索质量。**
   Adapter 将 selected chunks、rerank score、来源类型、证据等级、冲突、降级原因和 rank diagnostics 转换为 A5 RetrievalResult/EvidenceRecord。Gate2 再基于真实可用指标判断充分、重试或拒绝。

3. **Score 量纲未冻结时不能伪造归一化。**
   只有已是有限值且位于 `[0,1]` 的 selected rerank score 才映射为 `retrieval_score`；其他值保留 `None`。如果 A4 后续采用其他量纲，需要通过配置或正式 Adapter 明确归一化方法。

4. **A4 当前缺 `fetched_at`，影响生产 Gate1。**
   赛道一要求生产证据具备 id、source_type、published_at/version、URL、fetched_at 和 content_hash。当前 A4 chunk 未提供 `fetched_at`，因此 `allow_mock=false` 的生产映射会失败。这是有意的 fail-closed 阻断，不能由 A5 填入当前时间冒充采集时间。

5. **A4 的 `claim_support` 不得越权成为 Gate5 结论。**
   当前 claim support 属于检索/词项重叠诊断。Adapter 只把它放入 diagnostics，并标记 `diagnostic_only_never_gate5`；ClaimVerifier 不读取它来产生 SUPPORTED。

6. **SearchResult 版本字段影响可复现性。**
   index version、corpus version 和 rerank config version 缺失时 Adapter 拒绝结果，避免 AgentRun 保存无法解释的排序结果。

### 6.3 对契约测试的影响

| A4 风险 | 对应测试保证 |
|---|---|
| 枚举不一致导致合法结果被过滤 | 验证 `current_guideline -> guideline` 等配置路由 |
| FAILED 被当作空检索 | 验证 FAILED 抛出上游检索异常 |
| PARTIAL/EMPTY 的降级信息丢失 | 验证 status、degradation reasons 和 diagnostics 保留 |
| score 未知却被 Gate2 当成高分 | 非 `[0,1]` 或非有限 score 映射为 `None` |
| 缺 provenance 仍进入生成 | 生产路径验证 Gate1 required fields |
| 缺版本仍声称可重放 | 验证 index/corpus/rerank version 为必需字段 |
| token overlap 冒充语义支持 | 验证 claim support 只存在于 diagnostics，不改变 Gate5 |

### 6.4 A4 后续交付后的接入动作

- 由 A4 明确 Query、SearchResult、score 量纲、空/部分/失败格式和 feature log Schema。
- 由 A2/A3/A4 协调补齐或传递 `fetched_at` 等 provenance；在此之前生产路径继续 fail-closed。
- 用真实 A4 service 实现注入 `A4SearchService` Port，保持 Workflow 不变。
- 根据正式 score 说明调整 Gate2 配置阈值，并增加“修改阈值确实改变行为”的回归测试。
- 保持 Gate2 与 Gate5 职责分离：A4 检索诊断不能直接批准 Claim。

## 7. A1、A3、A4 的联动影响

```text
A1 question_type / safety / freshness
            ↓
      SearchPlan 与 Gate0
            ↓
A4 Query、检索状态、score、rank、冲突
            ↓
           Gate2
            ↓
A3 Evidence/Chunk/Span/PICO/provenance
            ↓
           Gate5
            ↓
      Gate6 PASS/WARN/REFUSE
```

三者不是可以互相替代的重复模块：

- A1 决定“是否允许回答、问题属于什么类型、需要什么时效与来源”。
- A4 决定“检索到了什么、排序质量如何、是否降级或冲突”。
- A3 决定“证据内容如何定位、有哪些 span/PICO/层级/索引元数据可供验证”。
- A5 负责把三者放入受限工作流，并在缺失或冲突时 fail-closed。

如果 A1 题型正确但 A4 结果不足，Gate2 应重试或拒绝；如果 A4 检索充分但 A3 缺少可验证 span/PICO，Gate5 不应产生虚假的 SUPPORTED；如果 A3/A4 数据完整但 A1 Safety 为 UNKNOWN，Gate0 必须在任何工具调用前终止。

## 8. 已知限制与风险

| 项目 | 当前状态 | A5 处理 |
|---|---|---|
| A1 callable Safety evaluator | 未交付 | Port 注入；缺失/异常为 UNKNOWN→REFUSE |
| A1 termination policy API | 未冻结 | 保持 A5 FSM；等待 Adapter 契约 |
| A3 PR/Schema | 尚未冻结且存在 blocker | compatibility model；不绑定具体包 |
| A3 fixture | 合规性尚未完全解决 | 强制 `mock=true`，禁止伪标识符 |
| A4 Query/score contract | 尚未冻结 | config mapping；未知 score 为 null |
| A4 `fetched_at` | 当前缺失 | 生产映射失败，不伪造 |
| A4 claim support | 仅诊断能力 | 禁止进入 Gate5 判定 |
| A2 正式 Evidence/MCP | 尚未交付 | 仅 Port/scaffold，不冒充正式实现 |

因此，本报告的结论是：**provisional Adapter 与契约测试已经可运行并能保护 A5 边界，但不代表 A1/A3/A4 正式接口已经冻结或完成生产联调。**

## 9. 验证结果

- Adapter/配置/架构定向测试：`21 passed`
- 完整测试：`66 passed in 0.37s`
- `pixi run demo`：PASS、WARN、REFUSE 均成功
- Trace：覆盖 Gate0、Skill、Tool Budget、Gate2、Claim、Gate5、Gate6
- compileall：通过
- `git diff --check`：通过，仅 Windows LF/CRLF 提示

Demo 产物：

- `artifacts/demo_trace.json`
- `artifacts/demo_trace.txt`

## 10. 方法与开源参考

- [Corrective Retrieval Augmented Generation (CRAG)](https://arxiv.org/abs/2401.15884)：借鉴“先评价检索质量，再继续、纠正或停止”的 Gate2 控制模式。
- [RAGChecker](https://arxiv.org/abs/2408.08067) 与其[官方仓库](https://github.com/amazon-science/RAGChecker)：借鉴检索错误与生成/主张错误分离诊断。
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)：借鉴窄 client/tool 边界；本轮未复制 SDK，也未实现 A2 MCP Server。
- [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/)：用于 runtime validation、Schema 导出与漂移测试。

以上资料只影响架构、控制流和契约测试方法；未复制外部系统实现，也不构成医学正确性或临床阈值依据。

## 11. 上游文件到达后的处理流程

1. 阅读 A1/A3/A4 新文件并记录精确版本或 commit。
2. 对比当前 compatibility model 与真实 Schema，输出 Integration Diff。
3. 判断可直接替换、需要 Adapter，还是存在 Schema 冲突。
4. 优先修改对应 Adapter/config/contract fixture，不修改 Workflow。
5. 对新增字段保持 UNKNOWN/null，直到上游提供明确语义。
6. 运行定向契约测试、完整 `pixi run test` 和 `pixi run demo`。
7. 删除已经被正式契约替代的 provisional 假设。
8. 更新 `config/integrations.yaml`、RuntimeConfigSnapshot 和本报告。
