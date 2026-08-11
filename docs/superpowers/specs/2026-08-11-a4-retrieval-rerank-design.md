# 赛道一 A4：检索与 Rerank 模块技术设计文档

> 项目：OpenEvidence MVP（赛道一）  
> 模块：A4 检索与创新 Rerank  
> 版本：v0.1  
> 日期：2026-08-11  
> 状态：设计冻结前草案

## 1. 模块定位

A4 负责将 A2 采集、A3 索引后的临床证据，按当前问题的临床相关性、证据适配性和来源多样性筛选为一组可供 A5 生成与引用审计的证据片段。

模块不负责采集远程数据、不维护向量库、不生成最终医学回答，也不作个体化诊疗判断。其职责是提供可复现、可解释、可评测的 `search()` 与 `rerank()` 能力。

## 2. 目标与边界

### 2.1 P0 目标

- 对中文临床证据问题完成 BM25 与向量双路召回。
- 通过 RRF 融合候选，再使用归一化特征进行可解释重排。
- 使用 MMR 选择最终 5--8 个去冗余证据片段。
- 返回标准化证据、逐项排序特征、版本号、耗时和降级原因。
- 在开发题上完成参数选择；正式题只做冻结配置评测。

### 2.2 非目标

- 不训练学习排序模型，不将 LLM listwise rerank 用作在线主排序。
- 不在 P0 强制加载 Cross-Encoder、本地 NLI 或大规模 OpenSearch。
- 不根据检索分数直接判断医学真伪；A5/A1 负责主张支持性和安全发布门禁。
- 不支持真实患者数据、诊断、处方、剂量调整或紧急处置问题。

### 2.3 验收标准

| 项目 | P0 验收要求 |
|---|---|
| 功能 | `search()`、`rerank()` 可由 A5 和评测脚本调用 |
| 召回 | 开发集 `Recall@50` 目标值不低于 0.85；未达标需记录原因 |
| 排序 | 报告 `nDCG@8`、MRR、Hit@8，并同 RRF 基线比较 |
| 多样性 | 最终上下文中单篇文献不超过 2 个 chunk，单来源不超过 4 个 chunk |
| 可追溯 | 每个候选保留原始排名、特征、最终排名、索引和配置版本 |
| 稳定性 | 空结果、索引不可用、单路检索失败时返回可机器识别的降级状态 |

上述阈值是 MVP 的目标值，不等同于临床有效性或诊疗安全性保证。

## 3. 上下游协作与职责边界

| 协作方 | A4 输入/输出 | 对接约定 |
|---|---|---|
| A1 场景与题集 | 输入：问题类型、主题、时间要求、开发题及 gold/qrels | A1 提供冻结版问题及人工核验的可接受证据集合 |
| A2 数据与 MCP | 输入：标准化 `Evidence`、来源与稳定 ID | A4 不直接依赖远程 API；检索只读 A3 建成的本地索引 |
| A3 索引与 Wiki | 输入：BM25、向量索引和 chunk 元数据；输出：可查的 `search_bm25`、`search_vector` | 索引和 chunk ID 必须版本化，A4 不自行改变 chunk 策略 |
| A5 Agent/生成 | 输出：最终证据片段、候选日志、检索充分性信号 | A5 只用 A4 返回的 `selected_chunks` 生成，不接受模型编造的引用 |
| A6 应用 | 输出：检索结果卡片、特征摘要、耗时、降级信息 | UI 默认展示简化轨迹；调试模式可展示完整特征 |
| B4/B5 评测 | 输出：冻结系统版本、逐题排名与消融日志 | 评测脚本不得在正式题上重新调权重 |

## 4. 总体架构与数据流

```mermaid
flowchart LR
  Q["用户问题 / 固定评测题"] --> P["查询解析\n主题、PICO、时效、题型"]
  P --> F["Metadata filter"]
  F --> B["BM25 Top-50"]
  F --> V["Vector Top-50"]
  B --> R["RRF 融合与去重\n候选池 Top-80"]
  V --> R
  R --> S["归一化特征重排\nTop-20"]
  S --> M["MMR 多样性选择\nTop-5 至 8"]
  M --> O["SelectedEvidence + RankLog"]
  O --> A5["A5 生成与引用审计"]
  O --> E["评测与消融"]
```

数据流的关键原则：事实文本与元数据由 A3 的 Evidence/Chunk store 管理；A4 只读取索引和元数据，并将排序结果写为不可变的运行日志。最终生成必须回到原始 chunk，而不是引用 Wiki 的二次总结。

## 5. 输入、输出与数据契约

### 5.1 查询输入

```json
{
  "question_id": "dev-001",
  "query": "老年高血压患者的一线降压治疗证据是什么？",
  "topic": "hypertension",
  "question_type": "guideline_or_treatment",
  "freshness": "current",
  "population": ["older adults", "hypertension"],
  "intervention": [],
  "comparator": [],
  "outcome": [],
  "index_version": "idx-20260811-v1"
}
```

`population/intervention/comparator/outcome` 可为空。解析器不能将不确定的字段伪装为确定事实；字段缺失时保留空值并降低相应匹配特征的权重。

### 5.2 依赖的 Chunk 最小字段

`EvidenceChunk` 除稳定 ID、来源、文本、PICO、向量、版本字段外，还需：

- `trust_tier`：`verified` 或 `discovery`，表示该条证据被验证到什么程度，而不是它来自哪里（“来自网页的 PubMed 页”和“PubMed API 验证的 PMID”不是一回事）。A2 在入库/提升阶段写入，A4 只读取，绝不从 `source_type` 推断。
- `verification_method`：如 `pubmed_api`、`pubmed_pmid_resolution`；`discovery` 证据留空。
- 提升（Promotion）是行为不是等级：A2 完成 PMID/DOI/NCT 解析后 `replace(trust_tier="verified")`，content hash 不因验证状态变化而改变。

```text
chunk_id, evidence_id, text, title, source_type, stable_id, url,
published_at, evidence_level, population, intervention, comparator,
outcome, page, section, corpus_version, index_version, tombstone
```

`evidence_id` 是当前证据实体的内部 ID；`stable_id` 可为 PMID、DOI、NCT ID 或指南版本标识。文献实体与抓取版本应分开保存：稳定实体用于去重和跨源映射，`content_hash` 用于识别其内容版本。

### 5.3 检索输出

```json
{
  "query_id": "dev-001",
  "index_version": "idx-20260811-v1",
  "rerank_config_version": "rerank-v0.1",
  "status": "ok",
  "degradation_reasons": [],
  "selected_chunks": [],
  "rank_log": [],
  "latency_ms": {
    "parse": 20,
    "bm25": 15,
    "vector": 40,
    "rerank": 25,
    "total": 100
  }
}
```

`status` 取值为 `ok`、`partial`、`empty` 或 `failed`。`partial` 必须记录哪一路检索失败，禁止静默把单路结果当作完整双路检索结果。

### 5.4 排序日志字段

每条进入候选池的 chunk 记录：

```text
chunk_id, evidence_id, bm25_rank, bm25_raw_score, vector_rank,
vector_raw_score, rrf_score, semantic_norm, lexical_norm, pico_match,
evidence_level_score, freshness_score, source_reliability_score,
feature_score, mmr_similarity_penalty, final_rank, selected,
filter_decisions, index_version, rerank_config_version
```

## 6. P0 算法设计

### 6.1 查询解析与过滤

1. 保留原始中文问题。
2. 从固定术语表或受限解析器抽取主题、题型、时间要求及可识别 PICO 字段。
3. 生成英文检索式作为召回辅助，但记录原句与改写版本。
4. 应用可解释的 metadata filter：排除 `tombstone=true`、缺稳定标识或范围外主题；对于“最新”问题增加发表日期下限。

解析输出只能影响召回和排序，不能代替 A1 的题目意图与 A5 的安全判断。

### 6.2 双路召回

| 通道 | 初始参数 | 用途 |
|---|---:|---|
| BM25 | `k_bm25=50` | 精确匹配药名、疾病名、指南编号、PMID/DOI/NCT |
| 向量检索 | `k_vector=50` | 处理同义表达、中文问题与英文证据的语义接近 |
| 合并候选池 | `candidate_pool_size=80` | RRF 后去重保留的最大候选数 |

每路召回均返回 `chunk_id`、原始分数、排名和索引版本。两个通道不可用时返回 `failed`；一个通道不可用时返回 `partial` 并记录原因。

### 6.3 RRF 融合

对候选 `d` 使用：

```text
RRF(d) = 1 / (rrf_k + rank_bm25(d))
       + 1 / (rrf_k + rank_vector(d))
```

P0 使用 `rrf_k=60`。不存在于某一路的候选不贡献该路项。RRF 仅融合“相对排名”，不应被误解为医学证据质量分。

### 6.4 证据可信池混合（Evidence Mixer）

在 RRF 与特征重排之间插入可信池混合（`retrieval/evidence_mixer.py`），而不是在 rerank 之后再按比例硬切：让可信数据和广域数据都有机会参加真正的排序。

```text
BM25 + Vector -> RRF -> EvidenceMixer(n) -> 特征重排 -> MMR
```

1. `compute_verified_ratio(query, config)` 只由题型与时效性决定 n（A5 的 Claim 在检索时还不存在，不能用 ClaimCriticality 算 n）：

   | 题型 | 基础 n | 时效加成 | 上限 |
   |---|---|---|---|
   | guideline | 0.90 | current/latest +0.05 | 0.95 |
   | latest_trial | 0.85 | 同上 | 0.95 |
   | therapy | 0.80 | 同上 | 0.95 |
   | generic（含 diagnosis/prognosis 回退） | 0.65 | 同上 | 0.95 |

2. `mix_evidence(candidates, n, candidate_limit)` 按 `trust_tier` 拆池，各取 `round(limit*n)` 与 `limit - round(limit*n)`，池内保持 RRF 序；可信池不足时从广域池补齐（缺口记入 `MixLog.shortfall`），广域池为空时退化为纯可信池，反之亦然，绝不因混合产生空结果。

3. `MixLog` 与 `mix` 阶段耗时写入 `SearchResult` 审计轨迹（rank_log / stage_latency_ms / retrieval_warning）。

n 只约束召回池形状；最终上下文的选择仍由 rerank + MMR 决定（K2=5--8），不再机械按 n 切。

### 6.5 特征重排

对 RRF 候选池中的前 20--30 条计算以下特征，并全部缩放到 `[0, 1]`：

| 特征 | 计算方法 | P0 权重 |
|---|---|---:|
| `semantic_norm` | 向量相似度 min-max 或 rank percentile | 0.30 |
| `lexical_norm` | BM25 分数的 query 内 percentile | 0.20 |
| `pico_match` | 人群、干预、对照、结局字段的可解释匹配 | 0.15 |
| `evidence_level_score` | 由题型对应的固定规则映射 | 0.15 |
| `freshness_score` | 对需时效题按发布日期衰减；稳定机制题置低权重 | 0.10 |
| `source_reliability_score` | 稳定标识、可访问 URL、来源完整性和版本信息 | 0.10 |

P0 特征分为：

```text
feature_score = 0.30 * semantic_norm
              + 0.20 * lexical_norm
              + 0.15 * pico_match
              + 0.15 * evidence_level_score
              + 0.10 * freshness_score
              + 0.10 * source_reliability_score
```

`source_reliability_score` 不等同于研究质量；研究设计与证据等级只能由 `evidence_level_score` 表达。全部权重、归一化方法、题型规则和术语表必须写入 `rerank_config_version`。

### 6.6 PICO 匹配规则

PICO 字段不完整时不能强行扣分。对存在的字段计算匹配：

```text
pico_match = mean(available_field_matches)
```

`available_field_matches` 来自标题、摘要、人工标注或 A3 提供的结构化字段。若查询和证据均缺 PICO 字段，值为 `null`，相应权重在该 query 内重新归一化，而非当作零分。

### 6.7 MMR 去冗余选择

从特征重排后的前 20 条中，迭代选择最终 `k_final=5--8` 条：

```text
MMR(d) = λ * feature_score(d)
       - (1 - λ) * max_similarity(d, selected)
```

P0 从 `λ=0.75` 开始，在开发集上冻结。相似度取 chunk embedding cosine similarity，并附加硬规则：

- 每篇文献最多保留 2 个 chunk；
- 每种来源最多保留 4 个 chunk；
- 指南/系统综述/RCT 等不同证据类型在可用时优先覆盖；
- 被标为撤稿、无稳定 ID 或范围外的证据不得被选择。

MMR 是顺序选择过程，因此冗余惩罚不应提前塞入静态 `feature_score`。

### 6.8 检索充分性信号

A4 只输出信号，不做最终医学拒答。以下情况向 A5 返回 `retrieval_warning=true`：

- 两路均为空，或只剩单一来源；
- 第一名特征分低于开发集冻结阈值；
- 当前题型要求的证据等级缺失；
- 多篇高分证据在人群、时间或结论上明显冲突；
- 某个已识别的关键 PICO 字段没有候选支持。

## 7. 配置、版本与可复现性

```yaml
retrieval:
  k_bm25: 50
  k_vector: 50
  rrf_k: 60
  candidate_pool_size: 80
  rerank_input_size: 25
  final_context_size: 6
  max_chunks_per_document: 2
  max_chunks_per_source: 4
  mmr_lambda: 0.75
  verified_ratio_base:          # Evidence Mixer 可信池比例（按题型）
    guideline: 0.90
    latest_trial: 0.85
    therapy: 0.80
    generic: 0.65
  verified_ratio_freshness_bump: 0.05
  verified_ratio_max: 0.95
  weights:
    semantic: 0.30
    lexical: 0.20
    pico: 0.15
    evidence_level: 0.15
    freshness: 0.10
    source_reliability: 0.10
```

每次运行至少写入 `corpus_version`、`index_version`、`embedding_model`、`chunk_policy_version`、`rerank_config_version`、问题集版本和随机种子。正式评测开始前冻结以上全部配置；修复阻断错误以外不得改变权重、K 值或 chunk 策略。

## 8. 评测与消融实验

### 8.1 标注前提

A1/B2 必须为开发题和正式题提供人工核验的 qrels：每题对应一个或多个可接受 `evidence_id` 或 `chunk_id`，并标注相关性等级。只提供单篇“唯一 gold 文献”不足以可靠计算 nDCG。

### 8.2 对照条件

| 条件 | 目的 |
|---|---|
| R0 | BM25 + 向量 + RRF，验证双路融合基线 |
| R1 | R0 + 特征重排 + MMR，P0 主系统 |
| R2（P1） | R1 + Cross-Encoder，测量神经精排的边际收益 |
| R3（联调） | R2 或 R1 + A5 Claim-Evidence 门禁，区分排序收益与发布安全收益 |

### 8.3 指标

| 指标 | 意义 | 责任 |
|---|---|---|
| Success@50 / Recall@50 | gold 是否进入初检候选 | A4 |
| nDCG@8 / MRR / Hit@8 | 正确证据是否位于前排 | A4 |
| source diversity / duplicate rate | 上下文是否覆盖多源且不过度重复 | A4 |
| latency / context tokens | 是否可用于现场演示 | A4 |
| citation coverage / claim support rate | 最终回答是否被证据支持 | A5/B5，A4 提供检索日志 |

### 8.4 调参与报告规则

- 只在开发题上进行粗粒度调参；8 道开发题不足以支撑大规模网格搜索。
- 按顺序调节：先解决 Recall@50，再选择 `rerank_input_size` 和 `final_context_size`，最后才微调权重与 MMR 参数。
- 正式题报告逐题结果、均值和失败案例，不将小样本的一次胜出描述为普适结论。
- 至少保留两类反例：主题相关但不支持主张；旧但权威的指南或综述。

## 9. 错误处理与降级

| 场景 | A4 行为 | 传递给下游的信息 |
|---|---|---|
| BM25 或向量单路故障 | 使用可用通道，状态设为 `partial` | 失败通道、异常类型、召回数 |
| 双路无结果 | 状态设为 `empty`，不伪造候选 | 空检索原因、查询版本 |
| 索引版本不一致 | 停止执行，状态设为 `failed` | 期望/实际版本 |
| 候选均无有效稳定标识 | 过滤后返回 `empty` | 被过滤数量与规则 |
| 候选来源单一或冲突 | 正常返回但设置 `retrieval_warning` | 警告类型、冲突 evidence ID |

## 10. 测试方案

| 测试类型 | 最小案例 | 预期 |
|---|---|---|
| 契约测试 | A3 返回的 Chunk 字段缺失 | 明确报错，不产生无 ID 引用 |
| BM25 测试 | 药名/PMID 精确查询 | 对应 chunk 位于候选集 |
| 向量测试 | 中文同义问题 | 语义相关英文 chunk 位于候选集 |
| RRF 测试 | 双路不同排序 | 融合排名可复算 |
| 特征测试 | 人群不一致、过时研究、低等级证据 | 特征分与规则一致 |
| MMR 测试 | 同文献多个相近 chunk | 最终不超过 2 个 chunk |
| 回归测试 | 3 条演示题和 1 条空结果题 | 排名、状态和日志结构稳定 |
| 可复现测试 | 同配置重复运行 | 输出 ID 与排序一致或差异可解释 |

## 11. 三天实施安排与交付物

| 时间 | 工作 | 交付物 |
|---|---|---|
| 开工前/第 1 天上午 | 与 A2/A3 冻结 Chunk、检索接口和 5 条 fixture | schema、fixture、接口测试 |
| 第 1 天下午 | BM25/向量调用、RRF、基础日志 | 可运行 R0 |
| 第 2 天上午 | 归一化特征、MMR、降级状态和单元测试 | 可运行 R1、特征日志 |
| 第 2 天中午 | 用开发题冻结配置与索引版本 | `rerank_config_version`、开发集结果 |
| 第 2 天下午 | 正式题批量运行，交付 B4/B5/A5 | JSONL 运行记录、消融 CSV |
| 第 3 天 | 回归、离线演示、失败案例和答辩图表 | 演示截图/数据、技术说明 |

P0 最终交付：

```text
retrieval/search.py          # 双路检索与 RRF
retrieval/rerank.py          # 特征重排与 MMR
retrieval/config.yaml        # 冻结配置
retrieval/models.py          # 输入输出数据模型
artifacts/runs/*.jsonl       # 排名与运行日志
artifacts/evaluation/*.csv   # R0/R1 指标
tests/test_retrieval_*.py    # 契约与回归测试
```

## 12. P1 扩展与答辩创新点

### 12.1 P1 扩展

- 对前 20--30 条候选接入 Cross-Encoder，并与 R1 做延迟、显存与质量消融。
- 接入更完整的中英文医学术语表与查询改写。
- 在语料扩大且并发增加后迁移到 PostgreSQL + pgvector 或 OpenSearch，保持 `search()` 契约不变。
- 引入经人工校验的更多 qrels 后，再考虑学习排序或更细粒度题型权重。

### 12.2 可用于答辩的创新表达

本模块的创新不在于“使用了某个 reranker”，而在于将医学问题的证据适配要求显式编码进排序过程：

1. 将词法匹配与语义匹配通过 RRF 互补融合，减少医学术语和同义表达造成的漏召回。
2. 将 PICO、证据等级、时间要求和来源可追溯性作为可解释特征，而不是仅依据相似度排序。
3. 用 MMR 控制同源重复，提升最终上下文中指南、综述、试验等证据的覆盖。
4. 保留逐候选特征与版本日志，使“为什么选中这条证据”可追溯、可评测、可复跑。

## 13. 安全与声明

本模块用于教学研究中的公开临床证据检索与排序。它不构成医疗建议，不处理真实患者隐私信息，也不输出诊断、处方、剂量调整或急症处置结论。排序靠前只表示其在冻结规则下更适合作为候选证据，不表示该证据单独足以支持医疗决策；最终回答必须经过 A5 的引用审计与发布门禁。
