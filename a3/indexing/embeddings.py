from __future__ import annotations

import os
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

DEFAULT_BGE_M3_MODEL_ID = "BAAI/bge-m3"
DEFAULT_BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
LOCAL_MODEL_ENV = "A3_BGE_M3_MODEL_PATH"
_LOCAL_REQUIRED_FILES = ("config.json", "tokenizer_config.json")
_WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")
_WEIGHT_INDEX_FILES = ("model.safetensors.index.json", "pytorch_model.bin.index.json")


class EmbeddingDependencyError(RuntimeError):
    """Stable packaging error when the optional embedding runtime is absent."""


def resolve_bge_m3_source(model_id: str = DEFAULT_BGE_M3_MODEL_ID,
                          local_path_env: str = LOCAL_MODEL_ENV) -> str:
    local_value = os.getenv(local_path_env)
    if not local_value:
        return model_id
    path = Path(local_value).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"{local_path_env} does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"{local_path_env} is not a directory: {path}")
    missing = [name for name in _LOCAL_REQUIRED_FILES if not (path / name).is_file()]
    if missing:
        raise RuntimeError(f"Incomplete local BGE-M3 model directory. Missing: {missing}")
    direct_weights = [name for name in _WEIGHT_FILES if (path / name).is_file()]
    indexes = [name for name in _WEIGHT_INDEX_FILES if (path / name).is_file()]
    if not direct_weights and not indexes:
        raise RuntimeError("Incomplete local BGE-M3 model directory. Missing model weights "
                           "(safetensors/bin file or shard index)")
    for index_name in indexes:
        payload = json.loads((path / index_name).read_text(encoding="utf-8"))
        shards = set(payload.get("weight_map", {}).values())
        missing_shards = sorted(name for name in shards if not (path / name).is_file())
        if not shards or missing_shards:
            raise RuntimeError(f"Incomplete local BGE-M3 shard index {index_name}; "
                               f"missing shards: {missing_shards or 'weight_map empty'}")
    return str(path.resolve())


class EmbeddingProvider(Protocol):
    @property
    def model_id(self) -> str: ...
    @property
    def revision(self) -> str | None: ...
    @property
    def source_kind(self) -> str: ...
    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def encode_queries(self, texts: Sequence[str]) -> list[list[float]]: ...


class BgeM3EmbeddingProvider:
    def __init__(self, model_id: str = DEFAULT_BGE_M3_MODEL_ID,
                 revision: str | None = DEFAULT_BGE_M3_REVISION,
                 *, use_fp16: bool = False, local_path_env: str = LOCAL_MODEL_ENV,
                 normalize: bool = True) -> None:
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ModuleNotFoundError as exc:
            raise EmbeddingDependencyError(
                "BGE-M3 support is optional; install with `pip install -e .[embedding]` "
                "or use the Pixi environment") from exc
        self._model_id = model_id
        self._revision = revision
        source = resolve_bge_m3_source(model_id, local_path_env)
        self._source_kind = "local" if source != model_id else "hub"
        kwargs = {"use_fp16": use_fp16, "normalize_embeddings": normalize}
        if revision and self._source_kind == "hub":
            kwargs["revision"] = revision
        self._model = BGEM3FlagModel(source, **kwargs)

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def revision(self) -> str | None:
        return self._revision

    @property
    def source_kind(self) -> str:
        return self._source_kind

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        output = self._model.encode(list(texts), return_dense=True, return_sparse=False, return_colbert_vecs=False)
        return output["dense_vecs"].tolist()

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(texts)

    def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(texts)
