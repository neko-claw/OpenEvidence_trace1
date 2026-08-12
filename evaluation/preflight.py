from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvaluationDatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_version: str
    dataset_id: str
    purpose: str
    mock: bool
    questions_path: str | None = None
    qrels_path: str | None = None
    gold_path: str | None = None
    source: str | None = None
    license_or_permission: str | None = None
    annotation_method: str | None = None
    adjudication_status: Literal["PENDING", "REVIEWED", "ADJUDICATED"]
    threshold_status: Literal["PENDING_APPROVAL", "APPROVED"]
    approved_thresholds: dict[str, float] = Field(default_factory=dict)


class EvaluationPreflight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["READY", "BLOCKED_EXTERNAL", "PENDING_APPROVAL"]
    eligible_for_formal_claims: bool
    dataset_id: str
    blockers: list[str] = Field(default_factory=list)


def load_manifest(path: str | Path) -> EvaluationDatasetManifest:
    return EvaluationDatasetManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def check_manifest(manifest: EvaluationDatasetManifest) -> EvaluationPreflight:
    blockers: list[str] = []
    if manifest.mock:
        blockers.append("MOCK_DATASET")
    for field in ("source", "license_or_permission", "annotation_method"):
        if not getattr(manifest, field):
            blockers.append(f"MISSING_{field.upper()}")
    if manifest.adjudication_status not in {"REVIEWED", "ADJUDICATED"}:
        blockers.append("GOLD_OR_QREL_NOT_REVIEWED")
    paths = [manifest.questions_path, manifest.qrels_path, manifest.gold_path]
    if not any(paths):
        blockers.append("MISSING_DATA_PATH")
    if blockers:
        status = "BLOCKED_EXTERNAL"
    elif manifest.threshold_status != "APPROVED" or not manifest.approved_thresholds:
        status = "PENDING_APPROVAL"
        blockers.append("THRESHOLDS_NOT_APPROVED")
    else:
        status = "READY"
    return EvaluationPreflight(
        status=status,
        eligible_for_formal_claims=status == "READY",
        dataset_id=manifest.dataset_id,
        blockers=blockers,
    )


def write_preflight(manifest_path: str | Path, output_path: str | Path) -> EvaluationPreflight:
    result = check_manifest(load_manifest(manifest_path))
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return result
