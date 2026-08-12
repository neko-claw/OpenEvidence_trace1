# data/dev/

**Synthetic smoke fixtures（非人工 gold、非正式评测）。**

本目录是 A4 管道的 pipeline smoke 数据，用于离线验证 BM25/向量/RRF/重排/MMR
与评测脚本可运行。所有记录均满足 AGENTS 的 Mock 约束：

- 全部 `mock=true`，ID 使用内部 `MOCK-A4-E001..E028`；
- **不含**伪造 PMID/DOI/NCT/URL/指南编号/虚构作者/医学效果数字；
- 文本为 "人工/Artificial ..." 合成描述，仅保留领域关键词（高血压/血脂/
  糖尿病等）供检索链路演练，不构成医学证据。

| 文件 | 内容 |
|---|---|
| `corpus.jsonl` | 28 条合成 chunk（3 领域 × 指南/系统综述/RCT/试验/队列/观察）。 |
| `questions.jsonl` | 8 道合成问题（`synthetic=true`），含题型/时效/PICO/原子主张。 |
| `qrels.json` | `synthetic_smoke_qrels`（chunk 粒度）与 `span_proxy_qrels`（chunk 级代理）。正式 qrels 依赖 A1/B2 人工冻结标注（pending）。 |
| `vectors.json` | 确定性 hash bag-of-words 占位向量（`scripts/build_dev_vectors.py` 生成）。 |

运行入口：`python -m scripts.run_dev_eval`。产出指标为 **smoke/proxy**，
不得用于证明正式检索质量或临床效果；正式评测待 A1/A2/A3/B2 上游契约。
