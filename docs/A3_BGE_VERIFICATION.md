# BGE-M3 verification status

Checked on 2026-08-12 (Asia/Shanghai) for configured model `BAAI/bge-m3` at
revision `5617a9f61b028005a4858fdac845db406aefb181`.

Status: **PENDING — external/local-model blocker**.

- `A3_BGE_M3_MODEL_PATH` is not set.
- The matching Hugging Face snapshot directory exists at
  `C:\Users\26224\.cache\huggingface\hub\models--BAAI--bge-m3\snapshots\5617a9f61b028005a4858fdac845db406aefb181`.
- Configuration/tokenizer files exist, but no `model.safetensors`,
  `pytorch_model.bin`, shard index, or referenced weight shards are present.
- No complete ModelScope BGE-M3 snapshot was found under the local cache.
- Therefore `a3-embedding-smoke` was not run against a real model: model
  dimension, real latency, device memory, and retrieval quality are not claimed.

The local validator now accepts complete safetensors or PyTorch single-file and
sharded snapshots and verifies that every shard referenced by an index exists.
Once a complete snapshot is available, set `A3_BGE_M3_MODEL_PATH` and run
`pixi run a3-embedding-smoke`; the command reports model, fixed revision,
source kind, device/precision, dimension, latency, and vector norms.

The deterministic offline embedder verifies plumbing and reproducibility only.
