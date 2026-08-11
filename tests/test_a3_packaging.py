import builtins
import tomllib
from pathlib import Path

import pytest

from a3.indexing.embeddings import BgeM3EmbeddingProvider, EmbeddingDependencyError

ROOT = Path(__file__).resolve().parents[1]


def test_declared_install_profiles_and_base_imports(monkeypatch):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    extras = project["project"]["optional-dependencies"]
    assert any(item.casefold().startswith("pyyaml") for item in dependencies)
    assert any(item.casefold().startswith("rank-bm25") for item in extras["retrieval"])
    assert any(item.casefold().startswith("chromadb") for item in extras["retrieval"])
    assert any(item.casefold().startswith("flagembedding") for item in extras["embedding"])

    import a3.config  # noqa: F401
    import a3.indexing.bm25  # noqa: F401
    import a3.indexing.vector  # noqa: F401

    real_import = builtins.__import__
    def without_embedding(name, *args, **kwargs):
        if name == "FlagEmbedding":
            raise ModuleNotFoundError("simulated optional dependency absence")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", without_embedding)
    with pytest.raises(EmbeddingDependencyError, match=r"\[embedding\]"):
        BgeM3EmbeddingProvider()
