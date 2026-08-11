import json
from pathlib import Path

from a3.contracts.export import MODELS, export_schemas
from a3.domain.models import Evidence
from a3.domain.models import Chunk, EvidenceSpan, IndexManifest, SearchHit

ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_json_schemas_are_current(tmp_path):
    generated = export_schemas(tmp_path)
    checked_in = ROOT / "contracts/a3/v0.3/schemas"
    assert {path.name for path in generated} == {f"{name}.schema.json" for name in MODELS}
    for path in generated:
        assert json.loads(path.read_text(encoding="utf-8")) == json.loads(
            (checked_in / path.name).read_text(encoding="utf-8"))


def test_versioned_fixture_is_mock_and_has_no_real_world_identifiers():
    path = ROOT / "contracts/a3/v0.3/fixtures/mock_evidence.jsonl"
    evidence = [Evidence.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(evidence) == 6
    assert all(item.mock and item.id.startswith("MOCK-") for item in evidence)
    assert all(not any((item.url, item.pmid, item.doi, item.nct_id, item.guideline_name)) for item in evidence)


def test_workflow_does_not_import_a3_concrete_implementation():
    workflow = (ROOT / "a5/agent/workflow.py").read_text(encoding="utf-8")
    assert "import a3" not in workflow and "from a3" not in workflow


def test_contract_models_keep_merge_blocking_field_surface():
    assert {"provenance", "mock", "tombstone"} <= set(Evidence.model_fields)
    assert isinstance(Evidence.content_hash, property)
    assert {"evidence_content_hash", "raw_page", "offset_scope", "content_hash"} <= set(Chunk.model_fields)
    assert {"document_char_start", "document_char_end", "chunk_content_hash",
            "evidence_content_hash"} <= set(EvidenceSpan.model_fields)
    assert {"mock", "tombstone", "live_state", "chunk_content_hash",
            "evidence_content_hash", "span_refs", "corpus_version", "index_version",
            "embedding_source_kind"} <= set(SearchHit.model_fields)
    assert {"requested_config", "runtime_effective_config", "embedding_source_kind"} <= set(IndexManifest.model_fields)
