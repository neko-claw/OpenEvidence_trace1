# A1 Contract Hardening Report v0.2

日期：2026-08-12
交付：A1 契约加固增量

## 已完成

1. 将 Gate0 安全边界从文档约定升级为 Pydantic/JSON Schema/fixture/引用实现四层一致的机器契约。
2. 统一最终决策为 `PASS | WARN | REFUSE`，将急症、范围、完整性等细分放入 `reason_codes[]`。
3. 修复预算语义：证据充分优先于预算状态；只有需要继续检索却没有预算时才因耗尽而拒答。
4. 增加 A1 → A5 `SafetyPolicy` Adapter；无归一化安全信号时保持 `UNKNOWN`，不做关键词猜测。
5. 收紧候选来源字段：routing-only 的 URL 使用 null；其他角色 URL 必须为 URI；routing key 不得当 Evidence ID。
6. 将 EXTERNAL 的 8 个误导性 `public_benchmark` 标签改为 `public_benchmark_style`，并禁止当前进入评测。
7. DatasetManifest v0.2 明确区分题目结构冻结、gold 待审、许可待审和正式评测冻结。
8. 将文本去重、source-group ID 碰撞检查与尚未执行的 embedding 语义去重分开记录。
9. 记录 130 个 source_group 当前全是 singleton；不再用“没有重复 ID”冒充“没有语义派生泄漏”。
10. 加入可复现 split hash、schema、fixture、生命周期和 A1→A5 兼容性测试。

## 主动未实现

- 没有用关键词或 LLM 冒充正式医疗安全分类器；只定义归一化信号契约和确定性策略。
- 没有替 A2 核验 Evidence/PMID/DOI/NCT/URL，也没有实现 MCP。
- 没有替 A3 决定 PICO/span/page/chunk 正式结构。
- 没有替 A4 实现 search/rerank 或制造 Gate2 分数。
- 没有生成教师题、真实 benchmark 导入、gold/qrel 或 embedding 去重结果。

## 上游接入点

- A1 classifier：输出 `SafetyPolicyInput`，再调用 `ReferenceSafetyPolicy`。
- A5：在 composition root 注入 `A1SafetyPolicyAdapter`，工作流无需重写。
- A4：把结构化 sufficiency 结果映射为 `RetrievalTerminationInput`。
- B2：完成已在 Manifest `known_gaps` 中声明的审核后，重算 hash 并逐 split 升级生命周期。

## 验证

- `pixi run test`：68 passed。
- `pixi run demo`：PASS/WARN/REFUSE 三条离线流程正常，A5 trace 完整。
- Mock demo 仍仅使用 `mock=true` 的人工证据，不作为医学结论。
