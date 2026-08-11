# OpenEvidence MVP：赛道一 A4 检索与重排

这是赛道一的 A4 模块：它从 A3 已建立的本地证据索引中检索、融合、重排并去重证据片段，交给 A5 生成带引用的回答。模块不采集远程资料、不生成医学结论，也不把检索分数当作医疗建议。

详细设计见 [A4 检索与 Rerank 技术设计](docs/superpowers/specs/2026-08-11-a4-retrieval-rerank-design.md)。

## 安装与验证

工程配置与主仓库保持一致（`openevidence-mvp`，Python >=3.11,<3.13，基础依赖
pydantic/requests）；核心检索和评测实现只依赖标准库，`sentence-transformers`
等重依赖放在可选 extras（`pip install -e .[bge]`）。测试需要 pytest：

```powershell
python -m pip install pytest
python -m pytest
python -m compileall retrieval a5
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
| `retrieval/rerank.py` | 4.2 十项特征 | semantic/lexical/rrf/title_abstract/pico/evidence_level/freshness/source_reliability/source_quality/fulltext（redundancy 仅作诊断特征，**不**计入静态分数，去冗余完全由 MMR 承担，见 6.6）；freshness 权重按题型调整（latest_trial 升到 0.20，机制题自动失效）；MMR 含证据类型多样性 bonus |
| `retrieval/support_check.py` | 4.2 步骤 6 | 规则式主张—证据预检（supported/background_only/insufficient/mismatch）+ 人群/时间冲突检测；完整 verifier 归 A5 |
| `retrieval/adaptive.py` | 4.3.4 自适应 K | 5 条确定性规则调整 K1/K2，预算上限不可突破 |
| `retrieval/tuning.py` | 4.3 调参 | K0×K1×K2 网格、**逐题明细 CSV（`grid_details`）**、**按题型召回曲线（`recall_curve_by_type`）**、冻结记录 + **防呆校验（`verify_frozen`/`require_frozen`，正式题前调用拒绝未冻结配置）** |
| `retrieval/config_io.py` | 4.3/AGENTS | 冻结配置的严格 YAML 子集读写：`write_config_yaml`/`load_config_yaml`/`config_matches_yaml`，未知键与结构错误显式失败 |
| `retrieval/gate.py` | 5.7 来源门禁 | Gate1：稳定 ID、来源类型、发布时间/版本、URL、抓取时间、内容 hash 齐全性校验（`check_source_gate`） |
| `retrieval/ports.py` | A5/A6 集成 | `a5.ports.EvidenceRetriever` 契约：`Question`/`SearchPlan`/`RetrievalRequest` → `RetrievalResult` |
| `a5/retrieval_bridge.py` | A5/A6 集成 | `A5EvidenceRetriever` 适配器：把 `RetrievalService.search()` 接到 A5 端口 |
| `scripts/run_dev_eval.py` | 4.3/4.6/8 交付 | 开发集评测入口：网格 → 冻结 → R0-R3 消融 → 逐题 JSONL 运行 → 验收报告（`artifacts/`） |
| `retrieval/ablation.py` | 4.6 消融 | R0–R3 对照运行器 + **citation_precision** + 决策日志 + CSV；R2 自动使用 `config.cross_encoder_alpha` |
| `retrieval/evaluation.py` | 指标与报告 | 检索指标 + **citation_precision** / citation coverage / claim support / conflict rate / context tokens（优先用标注 `token_count`）/ 成本估算 |
| `retrieval/models.py` | 4.1 片段表 | `EvidenceChunk` 含 **page/section/token_count**；store upsert 自动估算 token 数 |
| `scripts/report.py` | 指标与报告 | 验收报告 Markdown + 两类反例（相关但不支持、旧但权威） |

## 数据契约与上下游边界

- `Query`：查询 ID、原始问题、语言、可选 PICO 字段、固定 `as_of_date`，以及
  `out_of_scope` 范围标记。A4 不保存真实患者资料；对剂量/处方/诊断我/急症处置
  类问题，`RetrievalService` 返回 `empty` 并显式记录 `out_of_scope` 原因（范围
  门禁归 A1/A5，A4 只完成交接信号，不返回可能被当作建议的证据）。
- `EvidenceChunk`：`chunk_id`、`evidence_id`、`stable_id`、正文、来源、证据等级、
  可选 PICO、向量、`index_version/corpus_version`，以及 Gate1 来源契约字段：
  `pmid`/`doi`/`nct_id`（结构化稳定标识）、`authors`、`guideline_name`、
  `fetched_at`（抓取时间）、`content_hash`（内容版本）。`stable_id` 应为 PMID、
  DOI、NCT 或版本化指南标识，供引用和文献级去重使用。
- **Gate1 来源门禁（5.7）**：`retrieval.gate.check_source_gate(chunk)` 校验
  稳定 ID、来源类型、发布时间/版本（指南可用 `guideline_name` 替代日期）、URL、
  抓取时间、内容 hash 是否齐全，返回 `SourceGateVerdict(passed, missing)`。
  `EvidenceStore(..., enforce_source_gate=True)` 会在入库时跳过未通过门禁的
  chunk（计入 `UpsertStats.gate_skipped`）。
- `SearchResult`：`selected_chunks`、完整 `rank_log`、`index_version`、
  `corpus_version`、重排版本、阶段耗时、状态和降级原因。A5 只应根据
  `selected_chunks` 回答并执行引用审计。
- **A5/A6 集成桥接**：`retrieval/ports.py` 定义 `a5.ports.EvidenceRetriever` 契约
  （`Question`/`SearchPlan`/`RetrievalRequest` → `RetrievalResult`），
  `a5/retrieval_bridge.A5EvidenceRetriever` 将其适配到 `RetrievalService.search()`。
  `RetrievalResult` 只暴露 `selected_chunks` 与审计轨迹；`out_of_scope` 请求永远
  不返回 chunk。
- `RetrievalConfig`：候选数、RRF 参数、重排权重、MMR 参数、来源/文献上限和版本。
  冻结副本提交在 `config/retrieval-p0-v1.yaml`（`retrieval/config_io.py` 严格解析），
  正式评测前必须通过 `require_frozen` 与 `config_matches_yaml` 校验。

索引由 A3 提供；A4 只读取索引和 chunk 元数据。`VectorSearch` 是向量检索接口，
`InMemoryVectorSearch` 仅用于演示和测试。

## 运行状态与降级

| 状态 | 含义 |
|---|---|
| `ok` | BM25 和向量两路均成功，且得到可选证据。 |
| `partial` | 至少一路不可用、被降级；仍可能返回另一通道的结果。 |
| `empty` | 两路运行正常，但没有合格的证据候选（含 `out_of_scope` 范围外问题）。 |
| `failed` | 两路不可用或融合/重排流程无法安全完成。 |

`partial` 不会被静默伪装为 `ok`。下游必须显示或处理 `retrieval_warning` 与
`degradation_reasons`，不能把降级结果表述为完整证据综述。注意：按查询意图的
元数据过滤（领域/来源/证据等级/`latest` 日期窗口）是正常行为，不计入降级原因；
自适应 K 调整会以 `Adaptive K adjustments` 形式出现在 warning 中，同样不是降级。

## 时效性语义与索引约定

- `freshness=latest`（最新试验）：无 `published_at` 或超出窗口（默认 5 年）的 chunk
  在 RRF 前被硬过滤（fail-closed）。
- `freshness=current`（当前推荐，指南类问题）：**不再硬过滤无日期 chunk**，避免指南
  类问题因索引缺日期而整批误空；缺日期时 freshness 特征权重在该查询内重归一化。
  与 A3 的索引数据约定：A3 应尽量为 chunk 补齐 `published_at` 与 `fetched_at`。

## 已知局限与职责边界

- **PICO 匹配与支持性预检均为 token 重叠启发式**：对"相关但不支持主张"的证据
  区分能力有限；`claim_support` 只是预检信号，主张—证据的最终验证（NLI
  verifier）与发布门禁归 A5，A4 不据此作医学真伪判断。
- **中文→英文改写为固定词典而非 LLM 改写**：词典覆盖有限，语义桥较弱，中英
  同义表达召回依赖 A3 提供的 embedding 质量。
- **范围门禁交接**：`out_of_scope` 问题 A4 返回空结果并显式标记，最终拒答由
  A1/A5 执行。

## 离线评测与运行日志

`retrieval.evaluation` 提供纯函数评测，qrels 是 `{chunk_id: 非负有限相关性等级}`。相关性大于 0 才算相关；空 qrels 的所有相关性指标都明确返回 `0.0`。排名 ID 必须是非空字符串且不得重复。

### 3.1 Qrel 契约（evidence_span_id / atomic_point_id 粒度）

除 chunk 粒度外，`evaluation` 支持主张/证据片段粒度：`span_qrels` 将
`evidence_span_id` 映射到 `(chunk_id, atomic_point_id, grade)` 三元组。

- `aggregate_chunk_qrels(span_qrels)`：折叠为 chunk 粒度（每 chunk 取最大等级）；
- `span_success_at_k` / `span_recall_at_k` / `span_mrr` / `span_ndcg_at_k`：
  span 的 chunk 出现在前 K 即视为该 span 被召回，按 span 等级计算；
- `claim_coverage_at_k`：至少一个相关 span 被召回的原子主张占比（主张级评测）；
- `evaluate_span_ranking(ranked_ids, span_qrels, k)`：一次性返回上述五项。

### 开发集评测与验收交付物

`data/dev/` 提交了 8 道开发题、28 条 Gate1 齐全的语料 chunk 与人工 qrels（chunk
粒度和 span 粒度双份）。运行入口：

```powershell
python -m scripts.build_dev_vectors   # 生成确定性 hash 占位向量（一次）
python -m scripts.run_dev_eval        # 网格 → 冻结 → 消融 → 逐题 → 报告
```

输出（已提交为验收交付物）：

```text
config/retrieval-p0-v1.yaml        # 冻结配置（YAML 权威副本）
artifacts/evaluation/freeze.json   # 冻结记录（K 与版本，防呆校验）
artifacts/evaluation/ablation.csv  # R0–R3 消融
artifacts/evaluation/grid_details_dev.csv  # K 网格逐题明细
artifacts/evaluation/per_question_frozen.csv  # 逐题 Recall@50 / nDCG@8 / span 指标
artifacts/runs/dev-*.jsonl         # 逐题运行审计日志
artifacts/reports/acceptance-report.md  # 验收报告（含反例与局限）
```

当前开发集结果：Recall@50（融合候选池）均值 1.000（目标 ≥ 0.85），nDCG@8
（重排输入）均值约 0.69，span Recall@8 与主张覆盖@8 均为 1.000。指标口径与
局限（token 重叠启发式、词典改写、与 A5 NLI verifier 的职责边界）见报告第 5-7 节。

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
