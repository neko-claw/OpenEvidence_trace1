# data/dev/

开发题 + 人工 qrels（P1 交付物）。只有这里的数据可用于参数选择与消融；
正式题不允许回退调参（`tuning.require_frozen`）。

| 文件 | 内容 |
|---|---|
| `corpus.jsonl` | 28 条证据 chunk（高血压/血脂/糖尿病 × 指南/系统综述/RCT/试验/队列/观察），全部满足 Gate1 来源门禁字段（稳定 ID、来源类型、发布日期或指南版本、URL、fetched_at、content hash）。 |
| `questions.jsonl` | 8 道开发题：题型（guideline / latest_trial / therapy）、时效、PICO、原子主张、中英检索词。 |
| `qrels.json` | 人工 qrels：chunk 粒度 `{chunk_id: 等级}` 与 3.1 Qrel 契约的 evidence-span 粒度（`span_id -> [chunk_id, atomic_point_id, grade]`）。 |
| `vectors.json` | 确定性 hash bag-of-words 占位向量（`scripts/build_dev_vectors.py` 生成）。A3 提供真实 embedding 后替换此文件即可，评测脚本无需改动。 |

运行入口：`python -m scripts.run_dev_eval`（网格 → 冻结 → 消融 → 逐题 → 报告）。
