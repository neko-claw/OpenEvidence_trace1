from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from a2.connectors.base import A2HTTPClient
from a2.models.errors import A2Error, A2ErrorCode, A2Exception
from a2.models.evidence import A2Evidence, SourceType
from a2.storage.dedup import compute_content_hash, normalize_doi


class EuropePMCConnector:
    """Europe PMC REST core-result connector."""

    def __init__(self, http: A2HTTPClient, base_url: str) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")

    def search(self, query: str, limit: int = 10, cursor_mark: str | None = None) -> list[A2Evidence]:
        """Search Europe PMC core JSON results."""
        params: dict[str, Any] = {"query": query, "format": "json", "resultType": "core", "pageSize": limit}
        if cursor_mark:
            params["cursorMark"] = cursor_mark
        payload = self.http.get_json(f"{self.base_url}/search", params=params)
        results = payload.get("resultList", {}).get("result")
        if not isinstance(results, list):
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source="europe_pmc", message="Europe PMC response missing result list"))
        return [self._parse(item) for item in results[:limit]]

    def get(self, source: str, native_id: str) -> A2Evidence:
        """Fetch one exact Europe PMC source/native identifier."""
        records = self.search(f"EXT_ID:{native_id} AND SRC:{source}", 1)
        if not records:
            raise A2Exception(A2Error(code=A2ErrorCode.NOT_FOUND, source="europe_pmc", message="Europe PMC record not found", http_status=404))
        return records[0]

    def get_full_text(self, pmcid: str) -> str:
        """Explicitly retrieve full-text XML; search never calls this."""
        response = self.http.request("GET", f"{self.base_url}/{pmcid}/fullTextXML")
        return response.text

    def _parse(self, item: dict[str, Any]) -> A2Evidence:
        source = str(item.get("source") or "MED")
        native_id = str(item.get("id") or item.get("pmid") or item.get("pmcid") or "").strip()
        title = str(item.get("title") or "").strip()
        if not native_id or not title:
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source="europe_pmc", message="Europe PMC record missing required identity/title"))
        pmid = str(item["pmid"]) if item.get("pmid") else None
        pmcid = str(item["pmcid"]) if item.get("pmcid") else None
        content = str(item.get("abstractText") or title).strip()
        authors = [str(author.get("fullName")) for author in item.get("authorList", {}).get("author", []) if author.get("fullName")]
        published = _parse_date(item.get("firstPublicationDate") or item.get("electronicPublicationDate"))
        url_id = pmcid or pmid or native_id
        data: dict[str, Any] = {
            "id": f"EPMC:{source}:{native_id}", "source_type": SourceType.EUROPE_PMC,
            "title": title, "abstract_or_chunk": content, "authors": authors,
            "published_at": published, "url": f"https://europepmc.org/article/{source}/{url_id}",
            "pmid": pmid, "doi": normalize_doi(item.get("doi")),
            "source_metadata": {"pmcid": pmcid, "journal": item.get("journalTitle"), "is_open_access": item.get("isOpenAccess"), "native_source": source, "native_id": native_id},
        }
        data["content_hash"] = compute_content_hash(data)
        return A2Evidence.model_validate(data)


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
