import json

from scripts.import_evidence import import_jsonl


def test_import_jsonl_handles_valid_duplicate_and_invalid(
    tmp_path,
):
    jsonl_path = tmp_path / "evidence.jsonl"
    db_path = tmp_path / "test.db"
    error_path = tmp_path / "errors.jsonl"

    valid = {
        "id": "E001",
        "source_type": "pubmed",
        "title": "Hypertension study",
        "abstract_or_chunk": "Valid abstract",
        "pmid": "12345678",
    }

    missing_title = {
        "id": "E002",
        "source_type": "pubmed",
        "abstract_or_chunk": "Missing title",
    }

    lines = [
        json.dumps(valid),
        json.dumps(valid),          # duplicate
        json.dumps(missing_title),  # schema error
        "{bad json",                # JSON error
    ]

    jsonl_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    report = import_jsonl(
        input_path=jsonl_path,
        db_path=db_path,
        error_report_path=error_path,
    )

    assert report["total"] == 4
    assert report["inserted"] == 1
    assert report["duplicates"] == 1
    assert report["invalid"] == 2

    assert error_path.exists()

    errors = [
        json.loads(line)
        for line in error_path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]

    assert len(errors) == 2
