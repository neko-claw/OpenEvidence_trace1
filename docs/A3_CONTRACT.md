# A3 数据契约与边界（v0.2）

本契约是 A3 对下游的冻结接口，不代表 A3 替 A2 宣布最终 Evidence Schema。
A2 后续真实采集结果应通过显式 Adapter 映射并保留其生产 provenance；A3 不实现
A2 MCP/采集，也不修改 A5 FSM、Gate、Verifier 或 `answer(...)->AgentRun` API。

## 字段约定

JSON Schema 中 `required` 是机器可校验的必填集合；具有 `null` 分支或默认值的字段
可选。未知的 PICO、证据等级、发布时间、页码和标识符保持 `null`/`UNKNOWN`，不得猜测。
`mock=true` 仅允许离线工程 fixture，且禁止携带 PMID、DOI、NCT、指南身份或 URL。
生产数据必须 `mock=false`，保留来源 ID、抓取时间及来源特定 provenance；其真实性和
许可由 A2/数据治理流程负责。

`Chunk.char_start/char_end` 的 `offset_scope=document`，相对
`Evidence.abstract_or_chunk`。`EvidenceSpan.char_start/char_end` 的
`offset_scope=chunk`，另有 `document_char_start/document_char_end` 回到原文。
所有区间为左闭右开，必须满足 end > start；Span 文本必须严格等于 Chunk 和原文切片。
Chunk、Span 均保留 Evidence/Chunk content hash。数字页写入 `page`，原始定位符始终写入
`raw_page`；`S12`、`appendix-A` 等不会伪装成整数。

`SearchHit.document_kind=wiki_navigation` 只表示主题标题、synonym、MeSH/明确别名导航，
不属于原始医学证据，也不会进入 Chroma。Wiki 中的 Evidence ID/Span ID 必须属于当前
SQLite corpus 白名单；Mock Wiki 始终显示
`MOCK / OFFLINE FIXTURE — NOT MEDICAL EVIDENCE`。

`IndexManifest` 冻结 schema、corpus、index、Chunk policy、BM25 tokenizer、Embedding
provider/model/revision/mode、向量距离、Wiki builder 版本和实际生效配置。存储路径不参与
语义 index version 哈希，但仍记录在 `effective_config` 中。

契约路径：`contracts/a3/v0.2/`。未来 LLM Wiki 接缝位于 `a3/wiki/generator.py`，其 Prompt
和结构化输出 Schema 位于 `a3/wiki/prompts/` 与 `a3/wiki/schemas/`；当前并未绑定或冒充
任何真实 LLM 生成器。
