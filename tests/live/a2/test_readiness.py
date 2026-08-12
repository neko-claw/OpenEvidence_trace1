from __future__ import annotations

import json

from a2.config import load_a2_config
from deployment.a2.health import check_a2_readiness


def test_a2_readiness_reports_external_requirements_without_secret_values(tmp_path) -> None:
    cfg = load_a2_config()
    manifest = tmp_path / "guidelines.json"
    manifest.write_text(json.dumps({"manifest_version": "1", "guidelines": []}), encoding="utf-8")
    cfg.sources["guidelines"]["manifest_path"] = str(manifest)
    status = check_a2_readiness(cfg, environ={})
    assert status.status == "BLOCKED_EXTERNAL"
    assert set(status.missing_requirements) == {
        "NCBI_EMAIL",
        "NCBI_TOOL",
        "APPROVED_GUIDELINE_SOURCES",
    }
    serialized = status.model_dump_json()
    assert "API_KEY" not in serialized


def test_a2_readiness_accepts_only_nonempty_approved_manifest(tmp_path) -> None:
    cfg = load_a2_config()
    manifest = tmp_path / "guidelines.json"
    manifest.write_text(
        json.dumps({"manifest_version": "1", "guidelines": [{"manifest_id": "approved"}]}),
        encoding="utf-8",
    )
    cfg.sources["guidelines"]["manifest_path"] = str(manifest)
    status = check_a2_readiness(
        cfg,
        environ={"NCBI_EMAIL": "project@example.invalid", "NCBI_TOOL": "OpenEvidence"},
    )
    assert status.ready is True
    assert status.approved_guideline_count == 1
