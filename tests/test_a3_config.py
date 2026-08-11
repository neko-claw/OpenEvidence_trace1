import shutil
from pathlib import Path

import pytest
import yaml

from a3.cli.build_all import build
from a3.config import ConfigLoader

ROOT = Path(__file__).resolve().parents[1]


def _temporary_config(tmp_path: Path, max_chars: int) -> Path:
    raw = yaml.safe_load((ROOT / "config/a3.yaml").read_text(encoding="utf-8"))
    shutil.copyfile(ROOT / "data/fixtures/a3_mock_evidence.jsonl", tmp_path / "fixture.jsonl")
    raw.update(database="runtime/custom.db", mock_fixture="fixture.jsonl")
    raw["chunk_policy"].update(max_chars=max_chars, overlap_chars=10)
    raw["bm25"]["root"] = "runtime/lexical"
    raw["vector"]["root"] = "runtime/vector"
    raw["wiki"]["root"] = "runtime/wiki-pages"
    raw["wiki"]["topics"] = [{"slug": "configured-topic", "title": "Configured Topic",
        "synonyms": ["configured alias"], "mesh": ["Configured Mesh"]}]
    path = tmp_path / "a3.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def test_config_changes_paths_topic_and_real_build_chunking(tmp_path):
    path = _temporary_config(tmp_path, max_chars=90)
    first = build(real_embedding=False, config_path=path, project_root=tmp_path)
    assert (tmp_path / "runtime/custom.db").is_file()
    assert (tmp_path / "runtime/wiki-pages/_index.md").is_file()
    assert (tmp_path / "runtime/wiki-pages/configured-topic.md").is_file()
    assert "Configured Topic" in (tmp_path / "runtime/wiki-pages/_index.md").read_text(encoding="utf-8")
    assert list((tmp_path / "runtime/lexical").glob("*/manifest.json"))
    assert first["manifest"]["chunk_policy"]["max_chars"] == 90
    assert first["manifest"]["effective_config"]["wiki"]["topics"][0]["slug"] == "configured-topic"
    assert first["bm25_document_count"] == first["chunk_count"] + 1

    again = build(real_embedding=False, config_path=path, project_root=tmp_path)
    assert (first["corpus_version"], first["index_version"], first["chunk_count"],
            first["bm25_document_count"], first["vector_document_count"]) == (
            again["corpus_version"], again["index_version"], again["chunk_count"],
            again["bm25_document_count"], again["vector_document_count"])

    raw = yaml.safe_load(path.read_text(encoding="utf-8")); raw["chunk_policy"]["max_chars"] = 45
    path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    smaller = build(real_embedding=False, config_path=path, project_root=tmp_path)
    assert smaller["chunk_count"] > first["chunk_count"]
    assert smaller["index_version"] != first["index_version"]


def test_config_loader_is_strict(tmp_path):
    path = _temporary_config(tmp_path, max_chars=90)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")); raw["unexpected"] = True
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected"):
        ConfigLoader.load(path, project_root=tmp_path)
