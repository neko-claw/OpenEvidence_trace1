from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pymupdf

from a2.models.errors import A2Error, A2ErrorCode, A2Exception
from a2.models.evidence import A2Evidence, SourceType
from a2.storage.dedup import compute_content_hash


class GuidelinesConnector:
    """Read only explicitly whitelisted, locally available guideline PDFs."""

    def __init__(self, manifest_path: Path | str) -> None:
        self.manifest_path = Path(manifest_path)
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise A2Exception(A2Error(code=A2ErrorCode.INVALID_REQUEST, source="guideline", message="invalid guideline manifest")) from exc
        if payload.get("manifest_version") != "1" or not isinstance(payload.get("guidelines"), list):
            raise A2Exception(A2Error(code=A2ErrorCode.INVALID_REQUEST, source="guideline", message="unsupported guideline manifest"))
        return payload

    def search(self, query: str, limit: int = 10) -> list[A2Evidence]:
        """Search approved manifest metadata and return natural PDF pages."""
        needle = query.casefold()
        selected = [item for item in self.manifest["guidelines"] if needle in " ".join(str(v) for v in item.values()).casefold()]
        records: list[A2Evidence] = []
        for item in selected:
            records.extend(self._read(item))
            if len(records) >= limit:
                break
        return records[:limit]

    def get(self, evidence_id: str) -> A2Evidence:
        """Fetch one exact whitelisted guideline page ID."""
        parts = evidence_id.split(":")
        if len(parts) != 5 or parts[0] != "GUIDELINE" or parts[3] != "PAGE":
            raise A2Exception(A2Error(code=A2ErrorCode.INVALID_REQUEST, source="guideline", message="invalid guideline evidence ID"))
        try:
            return self.get_page(parts[1], parts[2], int(parts[4]))
        except ValueError as exc:
            raise A2Exception(A2Error(code=A2ErrorCode.INVALID_REQUEST, source="guideline", message="invalid guideline page")) from exc

    def get_page(self, manifest_id: str, version: str, page: int) -> A2Evidence:
        """Fetch one approved manifest/version/page tuple."""
        item = next((entry for entry in self.manifest["guidelines"] if entry.get("manifest_id") == manifest_id and str(entry.get("version")) == version), None)
        if item is None:
            raise A2Exception(A2Error(code=A2ErrorCode.NOT_FOUND, source="guideline", message="guideline is not whitelisted"))
        records = self._read(item)
        if page < 1 or page > len(records):
            raise A2Exception(A2Error(code=A2ErrorCode.NOT_FOUND, source="guideline", message="guideline page not found"))
        return records[page - 1]

    def _read(self, item: dict[str, Any]) -> list[A2Evidence]:
        required = {"manifest_id", "guideline_name", "organization", "version", "published_at", "source_url", "local_path", "license_or_usage_note"}
        if not required.issubset(item):
            raise A2Exception(A2Error(code=A2ErrorCode.INVALID_REQUEST, source="guideline", message="guideline manifest entry missing required fields"))
        path = Path(item["local_path"])
        if not path.is_absolute():
            path = self.manifest_path.parent.parent / path
        if not path.is_file():
            raise A2Exception(A2Error(code=A2ErrorCode.NOT_FOUND, source="guideline", message="whitelisted guideline file is unavailable"))
        try:
            document = pymupdf.open(path)
            pages = [page.get_text().strip() for page in document]
            document.close()
        except (RuntimeError, ValueError, OSError) as exc:
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source="guideline", message="guideline PDF could not be parsed")) from exc
        published = _date(item.get("published_at"))
        records = []
        for index, text in enumerate(pages, 1):
            if not text:
                continue
            data: dict[str, Any] = {
                "id": f"GUIDELINE:{item['manifest_id']}:{item['version']}:PAGE:{index}",
                "source_type": SourceType.GUIDELINE, "title": item["guideline_name"],
                "abstract_or_chunk": text, "published_at": published,
                "url": item["source_url"], "guideline_name": item["guideline_name"], "page": index,
                "source_metadata": {"organization": item["organization"], "version": str(item["version"]), "license_or_usage_note": item["license_or_usage_note"], "manifest_id": item["manifest_id"]},
            }
            data["content_hash"] = compute_content_hash(data)
            records.append(A2Evidence.model_validate(data))
        return records


def _date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
