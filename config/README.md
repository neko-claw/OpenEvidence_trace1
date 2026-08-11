# config/

版本化配置资产。AGENTS.md 要求版本号与阈值进入 `config/` 或版本化资产；
`RetrievalConfig` 的权威冻结副本在这里以 YAML 形式提交。

| 文件 | 内容 |
|---|---|
| `retrieval-p0-v1.yaml` | P0 冻结配置（K、RRF、权重、MMR、版本号）。由 `retrieval/config_io.py` 严格解析：未知键、缺失键、结构错误都会显式失败，不允许静默忽略。 |

校验方式：

```python
from retrieval.config_io import config_matches_yaml, load_config_yaml
frozen = load_config_yaml("config/retrieval-p0-v1.yaml")
assert config_matches_yaml(frozen, "config/retrieval-p0-v1.yaml")
```

重新生成冻结副本（仅当评审同意变更权重/K 后）：

```python
from retrieval.config import RetrievalConfig
from retrieval.config_io import write_config_yaml
write_config_yaml("config/retrieval-p0-v1.yaml", RetrievalConfig(selection_top_k=8, ...))
```

正式题运行前必须通过 `tuning.require_frozen(freeze_record, config)`。
