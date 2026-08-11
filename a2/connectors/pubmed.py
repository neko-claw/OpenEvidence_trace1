from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from a2.connectors.base import A2HTTPClient
from a2.models.errors import A2Error, A2ErrorCode, A2Exception
from a2.models.evidence import A2Evidence, SourceType
from a2.storage.dedup import compute_content_hash, normalize_doi


MONTHS = {name: index for index, name in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


class PubMedConnector:
    """NCBI E-utilities PubMed search and retrieval connector."""

    def __init__(self, http: A2HTTPClient, base_url: str) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")

    def _params(self) -> dict[str, str]:
        params: dict[str, str] = {"tool": os.getenv("NCBI_TOOL", "OpenEvidence")}
        if os.getenv("NCBI_EMAIL"):
            params["email"] = os.environ["NCBI_EMAIL"]
        if os.getenv("NCBI_API_KEY"):
            params["api_key"] = os.environ["NCBI_API_KEY"]
        return params

    def search(self, query: str, limit: int = 10) -> list[A2Evidence]:
        """Search PubMed and batch-fetch normalized records."""
        params = {**self._params(), "db": "pubmed", "term": query, "retmode": "json", "retmax": str(limit)}
        payload = self.http.get_json(f"{self.base_url}/esearch.fcgi", params=params)
        error = payload.get("error") or payload.get("esearchresult", {}).get("ERROR")
        if error:
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source="pubmed", message="PubMed API returned an error body"))
        ids = payload.get("esearchresult", {}).get("idlist")
        if not isinstance(ids, list):
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source="pubmed", message="PubMed search response missing idlist"))
        return self._fetch([str(item) for item in ids]) if ids else []

    def get(self, pmid: str) -> A2Evidence:
        """Fetch one exact PMID without fuzzy fallback."""
        records = self._fetch([pmid])
        if not records:
            raise A2Exception(A2Error(code=A2ErrorCode.NOT_FOUND, source="pubmed", message="PubMed record not found", http_status=404))
        return records[0]

    def _fetch(self, pmids: list[str]) -> list[A2Evidence]:
        params = {**self._params(), "db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
        response = self.http.request("GET", f"{self.base_url}/efetch.fcgi", params=params)
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source="pubmed", message="invalid PubMed XML")) from exc
        if root.tag in {"ERROR", "ErrorList"} or root.find(".//ERROR") is not None:
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source="pubmed", message="PubMed API returned an XML error"))
        if root.tag != "PubmedArticleSet":
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source="pubmed", message="unexpected PubMed XML root"))
        return [self._parse_article(node) for node in root.findall("PubmedArticle")]

    def _parse_article(self, node: ET.Element) -> A2Evidence:
        pmid = _text(node.find(".//MedlineCitation/PMID"))
        title = "".join(node.find(".//ArticleTitle").itertext()).strip() if node.find(".//ArticleTitle") is not None else ""
        if not pmid or not title:
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source="pubmed", message="PubMed article missing required identity/title"))
        abstracts = []
        for part in node.findall(".//Abstract/AbstractText"):
            text = "".join(part.itertext()).strip()
            label = part.attrib.get("Label")
            if text:
                abstracts.append(f"{label}: {text}" if label else text)
        content = "\n".join(abstracts) or title
        authors = []
        for author in node.findall(".//AuthorList/Author"):
            collective = _text(author.find("CollectiveName"))
            name = collective or " ".join(filter(None, [_text(author.find("ForeName")), _text(author.find("LastName"))]))
            if name:
                authors.append(name)
        doi = None
        for article_id in node.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if article_id.attrib.get("IdType") == "doi":
                doi = normalize_doi(_text(article_id))
        published = _pubmed_date(node)
        data: dict[str, Any] = {
            "id": f"PMID:{pmid}", "source_type": SourceType.PUBMED, "title": title,
            "abstract_or_chunk": content, "authors": authors, "published_at": published,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "pmid": pmid, "doi": doi,
            "source_metadata": {"journal": _text(node.find(".//Article/Journal/Title"))},
        }
        data["content_hash"] = compute_content_hash(data)
        return A2Evidence.model_validate(data)


def _text(node: ET.Element | None) -> str | None:
    return "".join(node.itertext()).strip() if node is not None and "".join(node.itertext()).strip() else None


def _pubmed_date(node: ET.Element) -> datetime | None:
    date_node = node.find(".//Article/Journal/JournalIssue/PubDate") or node.find(".//DateCompleted")
    if date_node is None:
        return None
    year = _text(date_node.find("Year"))
    if not year:
        medline = _text(date_node.find("MedlineDate"))
        match = re.search(r"\b(18|19|20)\d{2}\b", medline or "")
        year = match.group(0) if match else None
    if not year:
        return None
    month_text = _text(date_node.find("Month")) or "1"
    month = MONTHS.get(month_text[:3].title(), int(month_text) if month_text.isdigit() else 1)
    day_text = _text(date_node.find("Day")) or "1"
    try:
        return datetime(int(year), month, int(day_text), tzinfo=timezone.utc)
    except ValueError:
        return datetime(int(year), month, 1, tzinfo=timezone.utc)
