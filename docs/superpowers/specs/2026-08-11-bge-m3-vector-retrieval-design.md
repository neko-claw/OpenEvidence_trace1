# BGE-M3 向量检索接入设计

> 项目：OpenEvidence MVP（赛道一 A4）  
> 日期：2026-08-11  
> 状态：已确认，待实施

## 目标

将 A4 的向量召回从由调用方预先提供向量的演示实现，扩展为本地 BGE-M3 dense embedding 实现。继续复用既有 BM25、RRF、特征重排和 MMR，不引入持久化向量数据库或在线 LLM。

## 范围

- 新增 `BgeM3Embedder`：惰性加载 `SentenceTransformer("BAAI/bge-m3")`，首次调用允许 Hugging Face 下载并使用本地缓存。
- 对 evidence chunk 的 `title + text` 批量编码、L2 归一化，并构造现有 `InMemoryVectorSearch` 可消费的向量记录。
- 对 `Query.text` 编码为同维的查询向量；保留原始 Query，并由 `RetrievalService` 继续调用既有 `VectorSearch.search()` 协议。
- 新增明确的加载、编码和维度错误；服务层捕获这些错误后按既有契约返回 `partial` 或 `failed`，不静默回退到无说明的伪向量。
- 将 `sentence-transformers` 声明为运行时依赖，并在 README 说明首次下载、缓存位置由 Hugging Face 环境变量控制，以及纯内存测试模式。

## 非目标

- 不接入 Chroma、FAISS 或其他持久化向量库。
- 不实现 BGE-M3 sparse/ColBERT 多向量检索；本次仅使用 dense embedding + 余弦相似度。
- 不改变 RRF、rerank、MMR 的分数定义或对外 `SearchResult` 契约。
- 不在单元测试中下载模型；测试以依赖注入的轻量假编码器验证行为。

## 组件与数据流

```text
EvidenceChunk(title + text) --批量 encode--> BgeM3Embedder --dense vector--> InMemoryVectorSearch
Query.text ------------------encode----------> BgeM3Embedder --query vector--> RetrievalService
BM25 candidates + vector candidates --> RRF --> rerank --> MMR --> SearchResult
```

`BgeM3Embedder` 是唯一了解 `sentence-transformers` 的组件。它公开 `encode_query(query)` 与 `build_vector_search(chunks)`；两者均使用同一模型、相同 dense 向量维度和 `normalize_embeddings=True`。模型以惰性方式加载，避免未使用向量检索的调用触发下载。

## 失败处理

| 场景 | 行为 |
|---|---|
| 首次下载失败、缓存损坏或模型无法加载 | 编码器抛出稳定的 `BgeM3EmbeddingError`；服务记录 `vector_unavailable` 并在 BM25 可用时返回 `partial`。 |
| 空 evidence 集 | 建立空向量搜索对象，查询安全返回空结果。 |
| 编码数量与输入 chunk 数不一致、维度不一致、非有限值 | 在构建索引时明确失败，不产生部分错误索引。 |
| 单元测试 | 注入伪 `SentenceTransformer` 工厂；不访问网络、不下载权重。 |

## 验收与测试

1. 未安装或模型加载失败时，异常类型和消息稳定；`RetrievalService` 的 BM25-only 降级仍为 `partial`。
2. 伪模型返回的 dense 向量能建立检索器，语义更接近的 chunk 排名第一。
3. 查询和语料编码均请求归一化；编码输入分别为 query 文本、`title + text`。
4. 空语料、维度不一致和异常 embedding 输出均有单元测试。
5. 全量现有测试以及新增 BGE-M3 测试通过；测试运行不触发模型下载。

## 依赖与运行方式

运行环境使用 `sentence-transformers` 加载 `BAAI/bge-m3`。模型文件由 Hugging Face 缓存管理；部署环境须在首次运行时具备网络访问，或预先填充模型缓存。生产部署可通过传入同一协议的本地模型工厂控制缓存目录、设备与离线模式。
