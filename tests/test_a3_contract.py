import json
from pathlib import Path

from a3.contracts.export import MODELS, export_schemas
from a3.domain.models import Evidence

ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_json_schemas_are_current(tmp_path):
    generated = export_schemas(tmp_path)
    checked_in = ROOT / "contracts/a3/v0.2/schemas"
    assert {path.name for path in generated} == {f"{name}.schema.json" for name in MODELS}
    for path in generated:
        assert json.loads(path.read_text(encoding="utf-8")) == json.loads(
            (checked_in / path.name).read_text(encoding="utf-8"))


def test_versioned_fixture_is_mock_and_has_no_real_world_identifiers():
    path = ROOT / "contracts/a3/v0.2/fixtures/mock_evidence.jsonl"
    evidence = [Evidence.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(evidence) == 6
    assert all(item.mock and item.id.startswith("MOCK-") for item in evidence)
    assert all(not any((item.url, item.pmid, item.doi, item.nct_id, item.guideline_name)) for item in evidence)
