# A3 数据契约与边界（compatibility v0.3）

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

Evidence SearchHit 的 BM25/Vector 两通道均强类型保留 Mock/live 状态、Chunk/Evidence hash、
Span refs/locator、corpus/index/chunk/tokenizer、Embedding source 和 Wiki/config 版本；缺失值
显式为 `None`/`UNKNOWN`。`wiki_navigation` 必须 `evidence_id=None`，不能进入 A5 Evidence。

`IndexManifest` 冻结 schema、corpus、index、Chunk policy、BM25 tokenizer、Embedding
provider/model/revision/source kind/mode、向量距离和 Wiki builder 版本。`requested_config`
保留请求的 YAML；`runtime_effective_config` 是实际运行快照并参与语义 index hash。存储路径
仍不参与语义 hash。

唯一 A3→A5 兼容入口是 `a5/adapters/a3.py::adapt_a3_selection`。它只消费 A4 本轮已选
Chunk，不消费 SearchHit，不制造 normalized retrieval score；逐 Span provenance 和所有 A3
版本保存在 A5 `source_metadata`/retriever diagnostics，供 AgentRun/Trace 留痕。

契约路径：`contracts/a3/v0.3/`。LLM Wiki 接缝位于 `a3/wiki/generator.py`，其 Prompt
和结构化输出 Schema 位于 `a3/wiki/prompts/` 与 `a3/wiki/schemas/`；Adapter 已实现注入式
结构化调用、白名单校验与 fail-closed 转换，但未绑定真实 provider，Issue #4 仍 pending。

## 安装方式

`pip install -e .` 安装严格 YAML 配置和核心契约；`pip install -e .[retrieval]`
增加 BM25/Chroma；`pip install -e .[retrieval,embedding]` 增加真实 BGE-M3 runtime。
未安装 embedding extra 时，构造真实 provider 会返回稳定的安装提示，而不会让基础 A3
import 崩溃。Pixi 环境包含全部 profile；`pixi run a3-build-offline` 始终是 deterministic
工程 embedder，不能解释为 BGE 效果。
