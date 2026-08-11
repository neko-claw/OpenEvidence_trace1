# A1 → A5 契约 Crosswalk v0.2

更新时间：2026-08-12
定位：说明 A1 的机器契约如何接入 A5；不替代 A2 Evidence、A3 PICO/span、A4 search/rerank。

## 1. Gate 与责任边界

| 阶段 | A1 提供 | A5 执行 | 仍待上游 |
|---|---|---|---|
| Gate0 | `SafetyPolicyInput/Output`、三态决策、原因码、引用实现 | 在检索/生成前调用 `SafetyPolicy`；`DENY/UNKNOWN` 都终止 | 后续文本分类器将自然语言归一化为安全信号 |
| Question contract | 题型、主题、时间截点、候选来源角色、题库生命周期 | 分类/规划可通过 Adapter 消费，不直接绑定 JSONL | A2 核验 stable source；B2 建 gold/qrel |
| Gate2 termination | 预算与充分性的优先级 | 使用 A4 的结构化充分性结果决定 CONTINUE/RETRY/REFUSE | 候选数、分数、来源覆盖、冲突由 A4 提供 |
| Gate5/6 | 顶层 `PASS/WARN/REFUSE` 与范围原因码 | A5 校验 claim/span/PICO/时间/不确定性并发布 | A3 提供正式 PICO/span；A2 提供证据完整性字段 |

## 2. SafetyPolicy 接口

输入/输出 schema：

- `schemas/a1/safety_policy_input.schema.json`
- `schemas/a1/safety_policy_output.schema.json`
- Pydantic source of truth：`a1/models.py`
- 可执行参考策略：`a1/policy.py::ReferenceSafetyPolicy`
- A5 Port Adapter：`a1/adapters/a5_safety.py::A1SafetyPolicyAdapter`

参考策略**只消费已归一化信号**，不从自由文本猜测医疗意图。没有
`question.metadata.a1_safety_signals`、字段缺失或值无效都会得到 `UNKNOWN`；A5
据此 fail closed。以后可替换归一化分类器，但不应修改 A5 状态机。

## 3. 决策与原因码

两个层次不得混用：

- SafetyDecision：`ALLOW | DENY | UNKNOWN`
- 最终 Decision：`PASS | WARN | REFUSE`

`REFUSE_EMERGENCY`、`REFUSE_SCOPE` 等旧值已退役，分别表达为
`decision=REFUSE` 与 `reason_codes=[safety_emergency|safety_outside_topic_scope|...]`。
这使 A6/B4 能按固定决策枚举聚合，同时保留审计细节。

## 4. Tool budget 语义

`tool_budget_exhausted` 只表示**禁止下一次工具调用**，并不自动否定已经取得的
证据。A5 应遵守以下优先级：

1. 未解决关键冲突 → `REFUSE`；
2. `evidence_sufficient=true` → `CONTINUE`，即使最后一次调用刚好耗尽预算；
3. 证据不充分/未知且预算耗尽 → `REFUSE`；
4. 证据不充分/未知且预算尚有 → `RETRY`。

机器契约和 fixture 位于 `docs/a1/agent_termination_rules.yaml` 与
`contracts/a1/v0.2/retrieval_termination_cases.json`。

## 5. 字段适配规则

| A1 字段 | 下游解释 | 规则 |
|---|---|---|
| `id` | Question ID | 不是 Evidence ID |
| `candidate_sources[].stable_id` | 上游可核验来源标识；routing_only 时为 routing key | A5 不得把 routing key 当引用 |
| `candidate_sources[].url` | 发现/展示元数据 | routing_only 可为 null；其他角色必须是 URI；URL 不是引用身份 |
| `as_of_date` | 问题时间截点 | 映射到 A4 freshness 与 A5 time check |
| `published_at/source_version` | 可选候选元数据 | 缺失保持 null；正式值由 A2/A3 Adapter 补齐 |
| `source_group_id` | 原始题/翻译/改写派生组 | 不得用 split 推导；当前仍待 B2 派生审核 |

## 6. 当前未关闭的上游依赖

- A1：自然语言 → 归一化 Safety 信号的正式分类器/规则集尚未冻结；参考实现不会冒充该能力。
- A2：Evidence Schema、来源稳定 ID、发布日期/版本、许可和 MCP 返回未接入。
- A3：正式 PICO、span/page/section 结构未接入。
- A4：Gate2 指标和 search/rerank 异常语义未接入。
- B2：gold/qrel、教师题来源、语义去重、source_group 派生审核、EXTERNAL 许可/出处未完成。

这些依赖通过 Adapter/状态字段保留；任何 pending/unknown 都不得自动升级为
`ALLOW`、`SUPPORTED` 或 `EVALUATION_FROZEN`。
