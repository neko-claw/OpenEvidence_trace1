from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from a1.dataset_contract import load_questions, source_group_audit, split_hashes


ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = ROOT / "data" / "processed" / "questions.jsonl"
MANIFEST_PATH = ROOT / "data" / "processed" / "dataset_manifest.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_130_questions_validate_against_contract() -> None:
    schema = _load_json(ROOT / "schemas" / "question.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    questions = load_questions(QUESTIONS_PATH)
    assert len(questions) == 130
    for question in questions:
        errors = sorted(validator.iter_errors(question), key=lambda error: list(error.path))
        assert not errors, f"{question['id']}: {[error.message for error in errors]}"


def test_manifest_validates_and_hashes_are_reproducible() -> None:
    schema = _load_json(ROOT / "schemas" / "dataset_manifest.schema.json")
    manifest = _load_json(MANIFEST_PATH)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
    assert split_hashes(load_questions(QUESTIONS_PATH)) == manifest["split_hashes"]


def test_routing_only_urls_use_null_not_empty_string() -> None:
    questions = load_questions(QUESTIONS_PATH)
    candidates = [
        candidate
        for question in questions
        for candidate in question["source_provenance"]["candidate_sources"]
    ]
    assert all(candidate["url"] != "" for candidate in candidates)
    assert all(
        candidate["role"] == "routing_only"
        for candidate in candidates
        if candidate["url"] is None
    )
    assert all(
        candidate["url"] is not None
        for candidate in candidates
        if candidate["role"] != "routing_only"
    )


def test_external_candidates_cannot_be_misrepresented_as_imported_benchmark() -> None:
    questions = load_questions(QUESTIONS_PATH)
    external = [question for question in questions if question["split"] == "EXTERNAL"]
    manifest = _load_json(MANIFEST_PATH)
    assert all(
        question["source_provenance"]["origin"] != "public_benchmark"
        for question in external
    )
    assert manifest["licenses"]["external_pack"]["evaluation_eligible"] is False
    assert manifest["split_lifecycle"]["EXTERNAL"]["evaluation_eligible"] is False


def test_planned_dedup_is_not_reported_as_executed() -> None:
    questions = load_questions(QUESTIONS_PATH)
    manifest = _load_json(MANIFEST_PATH)
    embedding = next(
        step
        for step in manifest["dedup_steps"]
        if step["method"] == "embedding_cluster_near_duplicate_review"
    )
    assert embedding["status"] == "PLANNED_NOT_EXECUTED"
    assert embedding["result"] is None
    normalized_texts = [question["question"].strip().casefold() for question in questions]
    assert len(normalized_texts) == len(set(normalized_texts))
    assert not any(
        question["source_provenance"]["origin"] == "teacher" for question in questions
    )
    assert any("teacher-authored questions: 0" in gap for gap in manifest["known_gaps"])


def test_source_group_audit_is_measured_and_not_overclaimed() -> None:
    questions = load_questions(QUESTIONS_PATH)
    manifest = _load_json(MANIFEST_PATH)
    measured = source_group_audit(questions)
    declared = manifest["source_group_audit"]
    assert {key: declared[key] for key in measured} == measured
    assert declared["status"] == "PENDING_B2_DERIVATION_AUDIT"
    assert measured["cross_split_collisions"] == 0


def test_split_counts_are_stable_but_not_evaluation_frozen() -> None:
    questions = load_questions(QUESTIONS_PATH)
    assert Counter(question["split"] for question in questions) == {
        "DEV": 30,
        "TEST": 60,
        "STRESS": 20,
        "EXTERNAL": 10,
        "RESERVE": 10,
    }
    manifest = _load_json(MANIFEST_PATH)
    assert all(
        state["status"] != "EVALUATION_FROZEN"
        for state in manifest["split_lifecycle"].values()
    )
