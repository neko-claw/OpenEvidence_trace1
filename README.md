# OpenEvidence MVP：赛道一 A4 检索与重排

这是赛道一的 A4 模块：它从 A3 已建立的本地证据索引中检索、融合、重排并去重证据片段，交给 A5 生成带引用的回答。模块不采集远程资料、不生成医学结论，也不把检索分数当作医疗建议。

详细设计见 [A4 检索与 Rerank 技术设计](docs/superpowers/specs/2026-08-11-a4-retrieval-rerank-design.md)。

## 安装与验证

运行环境为 Python 3.13+，核心检索和评测实现只依赖标准库；测试需要 pytest。

```powershell
python -m pip install pytest
python -m pytest
python -m compileall retrieval
```

也可只运行 A4 评测测试：

```powershell
python -m pytest tests/test_evaluation.py -q
```

## P0 架构：不依赖 LLM

P0 在线关键路径不需要生成式 LLM：

```text
中文问题
  → BM25 关键词召回（Top-K）
  → 向量 embedding 语义召回（Top-K）
  → RRF 融合
  → 可解释特征重排（语义、词法、PICO、证据等级、时效性、来源可追溯性）
  → MMR 去重与来源多样性控制
  → SearchResult：选中证据、排序日志、版本、耗时与降级状态
```

“向量”并不等于 LLM。本模块通过 `RetrievalService` 的 `query_vector_provider: Callable[[Query], Sequence[float]]` 接收查询 embedding，并通过 `VectorSearch.search()` 接收向量索引结果。A3 或部署层可以接入本地 embedding 模型、离线预计算向量或受控的 embedding API；A4 不绑定任何特定模型，也不会在检索路径调用文本生成模型。

## BGE-M3 本地向量接入

`retrieval.bge_m3.BgeM3Embedder` 是本地 dense embedding 实现：惰性加载 `SentenceTransformer("BAAI/bge-m3")`，对 chunk 的 `title + text` 批量编码（`normalize_embeddings=True`），并构建现有 `InMemoryVectorSearch` 可消费的向量记录。它是包内唯一了解 `sentence-transformers` 的组件；RRF、特征重排、MMR 与 `SearchResult` 契约均不改变。

```python
from retrieval import BgeM3Embedder, EvidenceChunk, Query, RetrievalConfig, RetrievalService
from retrieval.bm25 import BM25Index

embedder = BgeM3Embedder()                      # 首次编码时才加载模型
vector_search = embedder.build_vector_search(chunks)   # chunks: Iterable[EvidenceChunk]
service = RetrievalService(
    bm25_index=BM25Index(chunks),
    vector_search=vector_search,
    query_vector_provider=lambda query: embedder.encode_query(query),
    config=RetrievalConfig(),
)
result = service.search(Query(query_id="q1", text="老年高血压的一线降压治疗证据"))
```

运行说明：

- **首次下载**：模型文件由 Hugging Face 缓存管理，首次运行需要网络；可用环境变量控制缓存位置，如 `HF_HOME`、`HF_HUB_CACHE`，离线部署需预先填充缓存。
- **失败处理**：下载失败、缓存损坏或编码异常时抛出稳定的 `BgeM3EmbeddingError`，`RetrievalService` 按既有契约返回 `partial`（BM25 可用时）或 `failed`，不会静默回退到无说明的伪向量。
- **测试模式**：单元测试全部注入伪模型工厂，不访问网络、不下载权重；`BgeM3Embedder(model_factory=...)` 也可用于生产部署时固定缓存目录、设备与离线行为。
- **非目标**：不接入 Chroma/FAISS 等持久化向量库；不使用 BGE-M3 的 sparse/ColBERT 多向量能力；仅 dense embedding + 余弦相似度。

## 最小可运行内存示例

下面例子不访问网络，也不需要 LLM。它用内存 BM25 索引和 `InMemoryVectorSearch` 跑通全流程。

```python
from retrieval import (
    EvidenceChunk,
    Query,
    RetrievalConfig,
    RetrievalService,
)
from retrieval.bm25 import BM25Index
from retrieval.vector import InMemoryVectorSearch

chunk = EvidenceChunk(
    chunk_id="chunk-001",
    evidence_id="evidence-001",
    stable_id="PMID:100001",
    title="Amlodipine in older adults",
    text="A randomized trial evaluated amlodipine for hypertension in older adults.",
    source_type="pubmed",
    evidence_level="rct",
    content_vector=(1.0, 0.0),
    index_version="demo-index",
    corpus_version="demo-corpus",
)
config = RetrievalConfig(
    index_version="demo-index",
    corpus_version="demo-corpus",
    rerank_config_version="demo-rerank-v1",
)
service = RetrievalService(
    BM25Index((chunk,)),
    InMemoryVectorSearch({chunk.chunk_id: (chunk, chunk.content_vector)}),
    lambda query: (1.0, 0.0),  # 生产环境由 embedding 提供方实现
    config,
)
result = service.search(Query(query_id="demo-001", text="老年高血压的氨氯地平证据"))
print(result.status.value, [item.chunk_id for item in result.selected_chunks])
```

## 模块总览（4.1–4.6 落地）

| 模块 | 对应方案章节 | 职责 |
|---|---|---|
| `retrieval/query_plan.py` | 4.2 查询理解 | 规则式 QueryPlan：主题域、题型、时效、PICO 槽、原子主张、中英检索词（无 LLM） |
| `retrieval/store.py` | 4.1 存储与版本 | SQLite 证据库：content-hash 去重、tombstone、版本表、增量 upsert、metadata 过滤 |
| `retrieval/bge_m3.py` | 4.2 双路召回 | BGE-M3 dense embedding（惰性加载、可注入工厂） |
| `retrieval/cross_encoder.py` | 4.2/4.5 P1 | Cross-Encoder 重排，`s_final = α·CE + (1-α)·feature`，分数并列保留 |
| `retrieval/rerank.py` | 4.2 十项特征 | semantic/lexical/rrf/title_abstract/pico/evidence_level/freshness/source_reliability/source_quality/fulltext + redundancy 惩罚；freshness 权重按题型调整（latest_trial 升到 0.20，机制题自动失效）；MMR 含证据类型多样性 bonus |
| `retrieval/support_check.py` | 4.2 步骤 6 | 规则式主张—证据预检（supported/background_only/insufficient/mismatch）+ 人群/时间冲突检测；完整 verifier 归 A5 |
| `retrieval/adaptive.py` | 4.3.4 自适应 K | 5 条确定性规则调整 K1/K2，预算上限不可突破 |
| `retrieval/tuning.py` | 4.3 调参 | K0×K1×K2 网格、**逐题明细 CSV（`grid_details`）**、**按题型召回曲线（`recall_curve_by_type`）**、冻结记录 + **防呆校验（`verify_frozen`/`require_frozen`，正式题前调用拒绝未冻结配置）** |
| `retrieval/ablation.py` | 4.6 消融 | R0–R3 对照运行器 + **citation_precision** + 决策日志 + CSV；R2 自动使用 `config.cross_encoder_alpha` |
| `retrieval/evaluation.py` | 指标与报告 | 检索指标 + **citation_precision** / citation coverage / claim support / conflict rate / context tokens（优先用标注 `token_count`）/ 成本估算 |
| `retrieval/models.py` | 4.1 片段表 | `EvidenceChunk` 含 **page/section/token_count**；store upsert 自动估算 token 数 |
| `scripts/report.py` | 指标与报告 | 验收报告 Markdown + 两类反例（相关但不支持、旧但权威） |

## 数据契约与上下游边界

- `Query`：查询 ID、原始问题、语言、可选 PICO 字段和固定 `as_of_date`。A4 不保存真实患者资料。
- `EvidenceChunk`：`chunk_id`、`evidence_id`、`stable_id`、正文、来源、证据等级、可选 PICO、向量及 `index_version/corpus_version`。`stable_id` 应为 PMID、DOI、NCT 或版本化指南标识，供引用和文献级去重使用。
- `SearchResult`：`selected_chunks`、完整 `rank_log`、`index_version`、`corpus_version`、重排版本、阶段耗时、状态和降级原因。A5 只应根据 `selected_chunks` 回答并执行引用审计。
- `RetrievalConfig`：候选数、RRF 参数、重排权重、MMR 参数、来源/文献上限和版本。正式评测前必须冻结配置与索引版本。

索引由 A3 提供；A4 只读取索引和 chunk 元数据。`VectorSearch` 是向量检索接口，`InMemoryVectorSearch` 仅用于演示和测试。

## 运行状态与降级

| 状态 | 含义 |
|---|---|
| `ok` | BM25 和向量两路均成功，且得到可选证据。 |
| `partial` | 至少一路不可用、被过滤或降级；仍可能返回另一通道的结果。 |
| `empty` | 两路运行正常，但没有合格的证据候选。 |
| `failed` | 两路不可用或融合/重排流程无法安全完成。 |

`partial` 不会被静默伪装为 `ok`。下游必须显示或处理 `retrieval_warning` 与 `degradation_reasons`，不能把降级结果表述为完整证据综述。

## 离线评测与运行日志

`retrieval.evaluation` 提供纯函数评测，qrels 是 `{chunk_id: 非负有限相关性等级}`。相关性大于 0 才算相关；空 qrels 的所有相关性指标都明确返回 `0.0`。排名 ID 必须是非空字符串且不得重复。

| 指标 | 含义 |
|---|---|
| `success_at_k` / `hit_at_k` | 前 K 中是否至少命中一条正相关证据（0 或 1）。 |
| `recall_at_k` | 所有正相关 qrels 中有多少出现在前 K。 |
| `mrr` | 第一条正相关证据的倒数排名。 |
| `ndcg_at_k` | 使用线性 graded relevance 的归一化 DCG；越接近 1 越好。 |
| `source_diversity` | 结果中不同 `source_type` 的比例。 |
| `duplicate_rate` | 共享同一 `stable_id` 的重复 chunk 比例。 |

`evaluate_ranking(ranked_chunks_or_ids, qrels, k)` 返回不可变的指标映射。传入 `EvidenceChunk` 时才计算来源多样性和文献重复率；仅传入 ID 时两项为 `0.0`，避免凭空猜测来源。

使用 `write_run_jsonl(path, search_result)` 可以追加一行严格 JSON 的运行审计记录。记录包含固定长度的 SHA-256 `query_id_hash`（不写入原始查询 ID）、`index_version`、`corpus_version`、重排版本、状态、降级原因、耗时、选中 chunk ID 和完整排序诊断；为减少敏感信息扩散，它不写入查询正文、chunk 正文或异常对象。写入前会验证全部待记录字符串可 UTF-8 编码；包含孤立代理项等非法 Unicode 时会在创建目录或文件之前以 `ValueError` 失败。

## 安全边界

本项目用于公开临床证据的检索实验，输出是候选证据而非诊断或治疗方案。它是 non-diagnostic（非诊断性）工具：

- 不处理真实患者隐私数据；
- 不提供诊断、处方、剂量调整或急症处置建议；
- 排名靠前不等于证据为真、适用于个体患者或足以支持临床决策；
- 最终医学表述必须经 A5 的主张—证据引用审计和发布门禁。
