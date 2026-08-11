from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from core.models import Evidence
from storage.database import EvidenceDatabase


def import_jsonl(
    input_path: str | Path,
    db_path: str | Path,
    error_report_path: str | Path | None = None,
) -> dict:
    """
    将 Evidence JSONL 导入 SQLite。

    每一行独立处理：
    - 合法新数据 -> inserted
    - 已存在数据 -> duplicate
    - JSON 错误 / Schema 错误 -> invalid

    单条坏数据不会导致整个导入过程停止。
    """

    input_path = Path(input_path)
    db_path = Path(db_path)

    report = {
        "total": 0,
        "inserted": 0,
        "duplicates": 0,
        "invalid": 0,
        "errors": [],
    }

    if not input_path.exists():
        raise FileNotFoundError(
            f"Evidence file not found: {input_path}"
        )

    with EvidenceDatabase(db_path) as db:
        db.init_schema()

        with input_path.open(
            "r",
            encoding="utf-8",
        ) as f:
            for line_number, raw_line in enumerate(
                f,
                start=1,
            ):
                line = raw_line.strip()

                # 空行直接跳过，不算 Evidence。
                if not line:
                    continue

                report["total"] += 1

                try:
                    payload = json.loads(line)

                    evidence = Evidence.model_validate(
                        payload
                    )

                except json.JSONDecodeError as exc:
                    report["invalid"] += 1

                    report["errors"].append(
                        {
                            "line": line_number,
                            "type": "json_error",
                            "message": str(exc),
                        }
                    )

                    continue

                except ValidationError as exc:
                    report["invalid"] += 1

                    report["errors"].append(
                        {
                            "line": line_number,
                            "type": "schema_error",
                            "message": str(exc),
                        }
                    )

                    continue

                inserted = db.insert_evidence(
                    evidence
                )

                if inserted:
                    report["inserted"] += 1
                else:
                    report["duplicates"] += 1

    if (
        error_report_path is not None
        and report["errors"]
    ):
        error_report_path = Path(
            error_report_path
        )

        error_report_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with error_report_path.open(
            "w",
            encoding="utf-8",
        ) as f:
            for error in report["errors"]:
                f.write(
                    json.dumps(
                        error,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Import normalized Evidence JSONL "
            "into the OpenEvidence SQLite store."
        )
    )

    parser.add_argument(
        "input",
        help="Path to Evidence JSONL file",
    )

    parser.add_argument(
        "--db",
        default="data/sqlite/openevidence.db",
        help=(
            "SQLite database path "
            "(default: data/sqlite/openevidence.db)"
        ),
    )

    parser.add_argument(
        "--error-report",
        default="artifacts/import_errors.jsonl",
        help=(
            "Where invalid-record errors are written"
        ),
    )

    args = parser.parse_args()

    report = import_jsonl(
        input_path=args.input,
        db_path=args.db,
        error_report_path=args.error_report,
    )

    print()
    print("=== Evidence Import Report ===")
    print(f"Total:       {report['total']}")
    print(f"Inserted:    {report['inserted']}")
    print(f"Duplicates:  {report['duplicates']}")
    print(f"Invalid:     {report['invalid']}")
    print("==============================")

    if report["errors"]:
        print(
            f"Error report: {args.error_report}"
        )


if __name__ == "__main__":
    main()
