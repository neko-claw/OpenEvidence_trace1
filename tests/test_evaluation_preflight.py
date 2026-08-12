from __future__ import annotations

from evaluation.preflight import EvaluationDatasetManifest, check_manifest, load_manifest


def test_pending_formal_manifests_fail_closed() -> None:
    for path in (
        "evaluation/a3_embedding/manifest.json",
        "evaluation/a4_ablation/manifest.json",
    ):
        result = check_manifest(load_manifest(path))
        assert result.status == "BLOCKED_EXTERNAL"
        assert result.eligible_for_formal_claims is False
        assert "MISSING_DATA_PATH" in result.blockers


def test_smoke_or_unapproved_data_cannot_be_formal() -> None:
    smoke = EvaluationDatasetManifest(
        manifest_version="1",
        dataset_id="smoke",
        purpose="test",
        mock=True,
        questions_path="questions.jsonl",
        qrels_path="qrels.json",
        source="synthetic",
        license_or_permission="self-generated",
        annotation_method="constructed",
        adjudication_status="REVIEWED",
        threshold_status="APPROVED",
        approved_thresholds={"Recall@50": 0.5},
    )
    assert "MOCK_DATASET" in check_manifest(smoke).blockers
    real = smoke.model_copy(update={"mock": False, "dataset_id": "real", "threshold_status": "PENDING_APPROVAL", "approved_thresholds": {}})
    result = check_manifest(real)
    assert result.status == "PENDING_APPROVAL"
    assert result.eligible_for_formal_claims is False


def test_only_reviewed_licensed_data_with_approved_thresholds_is_ready() -> None:
    manifest = EvaluationDatasetManifest(
        manifest_version="1",
        dataset_id="reviewed",
        purpose="test",
        mock=False,
        questions_path="questions.jsonl",
        qrels_path="qrels.json",
        source="owner supplied",
        license_or_permission="approved",
        annotation_method="dual review plus adjudication",
        adjudication_status="ADJUDICATED",
        threshold_status="APPROVED",
        approved_thresholds={"Recall@50": 0.8},
    )
    assert check_manifest(manifest).eligible_for_formal_claims is True
