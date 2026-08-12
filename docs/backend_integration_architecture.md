# 赛道一后端协同架构与方法依据

## 规范基线

本仓库以 `docs/OpenEvidence_MVP_赛道1与赛道3实施规划.md` 为唯一实施基线。
外部交付文件 `OpenEvidence_MVP_赛道1与赛道3实施规划(2).md` 与仓库版本逐行规范化比较后内容一致，
因此不制造仅换行符不同的整文件变更。后端组合层固定遵循以下调用关系：

```text
Question
  -> A5 Gate0 asks A1 safety/scope policy
  -> A5 selects a versioned Skill and a bounded source plan
  -> A2 executes a read-only MCP evidence tool
  -> A2 Evidence is normalized into A3 Evidence/Chunk/Span provenance
  -> A4 retrieves and reranks the A3 candidate pool
  -> A5 Gate2 checks calibrated evidence quality
  -> A5 generates atomic Claim[] and audits citations at Gate5
  -> A5 Gate6 returns PASS / WARN / REFUSE
  -> one AgentRun contract is consumed by A6 and B4
```

职责边界保持不变：A1 不执行检索，A2 不决定答案，A3 不决定发布，A4 的相关性排序不等于医学支持性，
A5 不重写采集、索引或 rerank 实现。

## 关键工程决策

### 1. 检索质量与排序分离

A4 保存 BM25、向量、RRF、特征重排、可选 Cross-Encoder 和 MMR 的可审计排名信号。
这些信号回答“候选相对当前查询排得怎样”，不能直接当作跨查询可比较的证据充分性概率。
只有显式注入、带版本且经过校准的质量评估器，才能为 A5 Gate2 产生
`QUALITY + CROSS_QUERY + calibrated=true` 的分数；缺失时保持 `UNKNOWN` 并 fail closed。

该控制流借鉴 CRAG 的“先评价检索质量，再继续、纠正或停止”模式，但不复制其训练系统：
[Corrective Retrieval Augmented Generation](https://arxiv.org/abs/2401.15884)。

### 2. 原子主张与相邻证据支持

A5 先形成原子 `Claim[]`，再逐条检查 Evidence ID 白名单、Span、PICO、时间、数字/单位、冲突和独立语义支持。
Finalizer 只发布通过门禁的主张。设计分别借鉴：

- [FActScore](https://arxiv.org/abs/2305.14251) 的原子事实分解；
- [ALCE](https://arxiv.org/abs/2305.14627) 的引用存在性、支持性与覆盖度区分；
- [RAGChecker](https://arxiv.org/abs/2408.08067) 的检索错误与生成错误分层诊断。

这些方法只提供架构原型，不能替代医学人工 gold、独立 verifier 校准或临床安全审查。

### 3. MCP 是工具边界，不是业务核心

A2 使用只读 MCP server/client 暴露检索和引用校验；A5 只依赖 Port，并通过组合层调用。
本地离线回归使用同一个 MCP 调用协议和明确标记的 Mock connector，真实运行再替换 connector，
而不是绕过 MCP 直接读取测试答案。实现模式参考
[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)。

### 4. Embedding 与 Cross-Encoder 的归属

Embedding provider、模型 ID、revision 和索引 manifest 由 A3 冻结并记录。A4 只消费 A3 的候选池或显式注入的向量服务，
不得再次隐式加载另一份模型。BGE-M3 只是规划允许的候选之一，不是默认真理模型；没有独立开发集 Recall@50、
延迟和跨语言结果时不能把它标记为生产能力。

Cross-Encoder 属于 P1。它只提供 query-document 相关性，不能给出 Claim-Evidence 医学蕴含结论。
若未提供可复现模型/revision和校准结果，R2/R3 必须显示 `PENDING/UNKNOWN`，不能把 raw logit 压缩成伪概率。

### 5. A6 与 B4 只消费稳定输出

A6 和 B4 不 import 任一 Mock Adapter，也不自行解析内部 Trace 文本。它们消费版本化 `AgentRun`/下游 envelope：

- A6 展示 decision、final answer、Evidence cards、warnings/refusal、Gate/Tool Trace；
- B4 保存原始 AgentRun JSON，批量聚合 latency、budget、retrieval failure 与 claim verification failure；
- replay fixture 必须通过同一 JSON Schema，且清楚标记为 Mock，不作为医学效果证据。

## 完成判定

只有以下项目同时通过才可宣布“后端架构完成，可开始 A6 前端接入”：

1. 一条离线协同测试真实经过 A1、A2 MCP、A3 Schema/Span、A4 retrieval/rerank 与 A5 Gate0–Gate6；
2. 达到 Tool Budget 后不会发生额外工具调用，检索充分时提前停止；
3. A4 排名分不会绕过校准要求进入 Gate2；
4. A5 生成与 verifier 都不能引用本轮白名单外 ID/Span；
5. `pixi run test` 和 `pixi run demo` 全部通过，并生成 JSON/文本 Trace；
6. A6/B4 契约 Schema 与 PASS/WARN/REFUSE/ERROR replay fixture 可验证；
7. 真实网络、真实模型或独立医学 verifier 未配置时，live 模式明确失败或拒答，不伪装成功。

## 当前验收结果（2026-08-12）

- `pixi run test`：505 passed，3 个 opt-in live-network 测试 skipped；
- `pixi run demo`：PASS / WARN / REFUSE 三条 A5 路径通过；
- `pixi run backend-demo`：A1→A2 MCP→A3→A4→A5 协同路径 PASS；
- A6/B4 契约：`contracts/a5/v0.4.0/` 的 AgentRun、AgentRunView 与
  PASS/WARN/REFUSE/ERROR replay fixture 通过一致性校验；
- 协同 Trace：`artifacts/backend_demo_trace.json` 与 `.txt`。

因此，后端架构与 A6/B4 契约接入条件已经满足。尚未完成的真实网络部署、模型评测与医学级验证
不影响 A6 使用 replay/mock 构建前端，但仍阻止“临床验证完成”或“live 生产可用”的声明。
