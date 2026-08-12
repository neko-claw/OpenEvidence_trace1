"""Tests for the frozen-config YAML I/O (4.3 / AGENTS 版本化配置)."""

from __future__ import annotations

from pathlib import Path

import pytest

from retrieval.config import FeatureWeights, RetrievalConfig
from retrieval.config_io import (
    ConfigYamlError,
    config_matches_yaml,
    load_config_yaml,
    write_config_yaml,
)


def _frozen() -> RetrievalConfig:
    return RetrievalConfig(
        selection_top_k=8,
        index_version="idx-20260811-v1",
        corpus_version="corpus-20260811-v1",
        rerank_config_version="rerank-p0-v1",
    )


def test_yaml_round_trip_preserves_every_field(tmp_path) -> None:
    config = _frozen()
    path = write_config_yaml(tmp_path / "retrieval.yaml", config)

    loaded = load_config_yaml(path)

    assert loaded == config
    assert config_matches_yaml(config, path) is True


def test_committed_frozen_config_is_loadable_and_matches() -> None:
    """config/retrieval-p0-v1.yaml 是提交到仓库的冻结副本，必须可严格解析。"""
    repo_config = Path(__file__).resolve().parent.parent / "config" / "retrieval-p0-v1.yaml"
    if not repo_config.exists():
        pytest.skip("committed config not found")
    loaded = load_config_yaml(repo_config)

    assert loaded.rerank_config_version == "rerank-p0-v1"
    assert loaded.selection_top_k == 8


def test_weight_drift_is_detected(tmp_path) -> None:
    config = _frozen()
    path = write_config_yaml(tmp_path / "retrieval.yaml", config)
    drifted = RetrievalConfig(
        selection_top_k=8,
        index_version="idx-20260811-v1",
        corpus_version="corpus-20260811-v1",
        rerank_config_version="rerank-p0-v1",
        feature_weights=FeatureWeights(semantic=0.4, lexical=0.1),
    )

    assert config_matches_yaml(drifted, path) is False


def test_unknown_keys_are_rejected(tmp_path) -> None:
    config = _frozen()
    path = write_config_yaml(tmp_path / "retrieval.yaml", config)
    with path.open("a", encoding="utf-8") as output:
        output.write("  bogus_key: 1\n")

    with pytest.raises(ConfigYamlError, match="bogus_key"):
        load_config_yaml(path)


def test_missing_required_key_is_rejected(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("retrieval:\n  bm25_top_k: 50\n", encoding="utf-8")

    with pytest.raises(ConfigYamlError):
        load_config_yaml(path)


def test_malformed_structure_is_rejected(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("retrieval:\n  - not\n  - a\n  - map\n", encoding="utf-8")

    with pytest.raises(ConfigYamlError):
        load_config_yaml(path)


def test_invalid_indentation_is_rejected(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("retrieval:\n   bm25_top_k: 50\n", encoding="utf-8")

    with pytest.raises(ConfigYamlError):
        load_config_yaml(path)
