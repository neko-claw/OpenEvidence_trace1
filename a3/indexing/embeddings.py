from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

DEFAULT_BGE_M3_MODEL_ID = "BAAI/bge-m3"
DEFAULT_BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
LOCAL_MODEL_ENV = "A3_BGE_M3_MODEL_PATH"
_LOCAL_REQUIRED_FILES = ("config.json", "pytorch_model.bin", "tokenizer_config.json")


def resolve_bge_m3_source(model_id: str = DEFAULT_BGE_M3_MODEL_ID) -> str:
    local_value = os.getenv(LOCAL_MODEL_ENV)
    if not local_value:
        return model_id
    path = Path(local_value).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"{LOCAL_MODEL_ENV} does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"{LOCAL_MODEL_ENV} is not a directory: {path}")
    missing = [name for name in _LOCAL_REQUIRED_FILES if not (path / name).is_file()]
    if missing:
        raise RuntimeError(f"Incomplete local BGE-M3 model directory. Missing: {missing}")
    return str(path.resolve())


class EmbeddingProvider(Protocol):
    @property
    def model_id(self) -> str: ...
    @property
    def revision(self) -> str | None: ...
    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def encode_queries(self, texts: Sequence[str]) -> list[list[float]]: ...


class BgeM3EmbeddingProvider:
    def __init__(self, model_id: str = DEFAULT_BGE_M3_MODEL_ID,
                 revision: str | None = DEFAULT_BGE_M3_REVISION,
                 *, use_fp16: bool = False) -> None:
        from FlagEmbedding import BGEM3FlagModel
        self._model_id = model_id
        self._revision = revision
        source = resolve_bge_m3_source(model_id)
        self._source_kind = "local" if source != model_id else "hub"
        kwargs = {"use_fp16": use_fp16, "normalize_embeddings": True}
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
