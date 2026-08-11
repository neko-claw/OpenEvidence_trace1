from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from a3.domain.models import Chunk, Evidence, SearchHit
from a3.wiki.generator import WikiLexicalDocument

_LATIN = re.compile(r"(?:doi:)?10\.\d{4,9}/[-._;()/:a-z0-9]+|(?:nct|pmid):[a-z0-9-]+|[a-z0-9]+(?:-[a-z0-9]+)*", re.I)
_HAN = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    folded = text.casefold()
    tokens = _LATIN.findall(folded)
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if token.startswith(("nct:", "pmid:")):
            expanded.append(token.split(":", 1)[1])
    for run in _HAN.findall(folded):
        expanded.extend(run)
        expanded.extend(run[i:i + 2] for i in range(len(run) - 1))
    return expanded


def document(evidence: Evidence, chunk: Chunk) -> dict[str, Any]:
    fields = [evidence.title, chunk.text, evidence.source_type, evidence.stable_id,
              evidence.evidence_level, evidence.population, evidence.intervention,
              evidence.comparator, evidence.outcome]
    return {"document_kind": "evidence", "chunk": chunk.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"),
            "text": "\n".join(str(x) for x in fields if x is not None)}


class BM25Index:
    def __init__(self, documents: list[dict[str, Any]], index_version: str,
                 tokenizer_version: str) -> None:
        self.documents = documents
        self.index_version = index_version
        self.tokenizer_version = tokenizer_version
        self._model = BM25Okapi([tokenize(d["text"]) for d in documents]) if documents else None

    @classmethod
    def build(cls, evidence: list[Evidence], chunks: list[Chunk], index_version: str,
              tokenizer_version: str,
              wiki_documents: list[WikiLexicalDocument] | None = None) -> "BM25Index":
        by_id = {e.id: e for e in evidence}
        documents = [document(by_id[c.evidence_id], c) for c in chunks if c.evidence_id in by_id]
        for wiki in wiki_documents or []:
            documents.append({"document_kind": "wiki_navigation", "wiki": wiki.model_dump(mode="json"),
                              "text": wiki.text})
        return cls(documents, index_version, tokenizer_version)

    def save(self, root: str | Path) -> Path:
        target = Path(root) / self.index_version
        target.mkdir(parents=True, exist_ok=True)
        with (target / "documents.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for doc in self.documents:
                stream.write(json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n")
        (target / "manifest.json").write_text(json.dumps({"index_version": self.index_version,
            "tokenizer_version": self.tokenizer_version, "document_count": len(self.documents)},
            indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return target

    @classmethod
    def load(cls, target: str | Path) -> "BM25Index":
        path = Path(target)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        docs = [json.loads(line) for line in (path / "documents.jsonl").read_text(encoding="utf-8").splitlines() if line]
        return cls(docs, manifest["index_version"], manifest["tokenizer_version"])

    def search(self, query: str, top_k: int, filters: dict[str, Any] | None = None) -> list[SearchHit]:
        if not self._model or top_k <= 0 or not tokenize(query):
            return []
        query_tokens = tokenize(query)
        scores = self._model.get_scores(query_tokens)
        ranked = sorted(enumerate(scores), key=lambda x: (-float(x[1]), _document_id(self.documents[x[0]])))
        hits: list[SearchHit] = []
        for idx, score in ranked:
            doc = self.documents[idx]
            if not set(query_tokens).intersection(tokenize(doc["text"])):
                continue
            if doc.get("document_kind") == "wiki_navigation":
                if filters:
                    continue
                wiki = doc["wiki"]
                hits.append(SearchHit(document_kind="wiki_navigation", channel="lexical",
                    rank=len(hits) + 1, raw_score=float(score), chunk_id=f"wiki:{wiki['slug']}",
                    evidence_id=None, title=wiki["title"], text=wiki["text"],
                    source_type="wiki_navigation", index_version=self.index_version,
                    metadata={"relative_path": wiki["relative_path"], "navigation_only": True}))
            else:
                e = doc["evidence"]; c = doc["chunk"]
                if not _matches_filters(e, filters):
                    continue
                hits.append(SearchHit(channel="lexical", rank=len(hits) + 1, raw_score=float(score),
                    chunk_id=c["chunk_id"], evidence_id=e["id"], title=e["title"], text=c["text"],
                    source_type=e["source_type"], evidence_level=e.get("evidence_level"),
                    population=e.get("population"), intervention=e.get("intervention"),
                    comparator=e.get("comparator"), outcome=e.get("outcome"),
                    published_at=e.get("published_at"), page=c.get("page"), raw_page=c.get("raw_page"),
                    section=c.get("section"), index_version=self.index_version,
                    metadata={"stable_id": Evidence.model_validate(e).stable_id}))
            if len(hits) >= top_k:
                break
        return hits


def _document_id(document: dict[str, Any]) -> str:
    if document.get("document_kind") == "wiki_navigation":
        return f"wiki:{document['wiki']['slug']}"
    return str(document["chunk"]["chunk_id"])


def _matches_filters(evidence: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    if any(evidence.get(key) != value for key, value in filters.items()
           if key in {"source_type", "evidence_level"}):
        return False
    published = evidence.get("published_at")
    if not published and any(key in filters for key in ("date_from", "date_to")):
        return False
    if published:
        value = datetime.fromisoformat(str(published).replace("Z", "+00:00")).date()
        if filters.get("date_from") and value < datetime.fromisoformat(str(filters["date_from"])).date():
            return False
        if filters.get("date_to") and value > datetime.fromisoformat(str(filters["date_to"])).date():
            return False
    return True
