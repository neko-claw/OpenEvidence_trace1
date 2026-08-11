from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from a3.domain.models import Chunk, Evidence, SearchHit
from a3.indexing.embeddings import EmbeddingProvider


def vector_text(e: Evidence, c: Chunk) -> str:
    values = [("Title", e.title), ("Evidence", c.text), ("Population", e.population),
              ("Intervention", e.intervention), ("Comparator", e.comparator),
              ("Outcome", e.outcome), ("Evidence level", e.evidence_level)]
    return "\n".join(f"{label}: {value}" for label, value in values if value is not None)


class ChromaVectorIndex:
    def __init__(self, path: str | Path, index_version: str, provider: EmbeddingProvider) -> None:
        import chromadb
        self.index_version = index_version
        self.provider = provider
        self.client = chromadb.PersistentClient(path=str(path))
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", index_version[:24])
        self.collection = self.client.get_or_create_collection(
            name=f"oe_a3_{safe}", metadata={"hnsw:space": "cosine", "index_version": index_version})

    def sync(self, evidence: list[Evidence], chunks: list[Chunk]) -> int:
        by_id = {e.id: e for e in evidence}
        selected = [c for c in chunks if c.evidence_id in by_id]
        if not selected:
            return self.collection.count()
        texts = [vector_text(by_id[c.evidence_id], c) for c in selected]
        metadata: list[dict[str, str | int | float | bool]] = []
        for c in selected:
            e = by_id[c.evidence_id]
            raw = {"chunk_id": c.chunk_id, "evidence_id": e.id, "evidence_content_hash": e.content_hash,
                "source_type": e.source_type, "stable_id": e.stable_id, "title": e.title,
                "evidence_level": e.evidence_level, "page": c.page, "section": c.section,
                "index_version": self.index_version, "mock": e.mock,
                "population": e.population, "intervention": e.intervention,
                "comparator": e.comparator, "outcome": e.outcome,
                "published_at": e.published_at.isoformat() if e.published_at else None}
            metadata.append({k: v for k, v in raw.items() if v is not None})
        self.collection.upsert(ids=[c.chunk_id for c in selected], embeddings=self.provider.encode_documents(texts),
            documents=[c.text for c in selected], metadatas=metadata)
        return self.collection.count()

    def search(self, query: str, top_k: int, filters: dict[str, Any] | None = None) -> list[SearchHit]:
        count = self.collection.count()
        if count == 0 or top_k <= 0:
            return []
        where = {k: v for k, v in (filters or {}).items() if k in {"source_type", "evidence_level"}}
        has_date_filter = any(key in (filters or {}) for key in ("date_from", "date_to"))
        result = self.collection.query(query_embeddings=self.provider.encode_queries([query]),
            n_results=count if has_date_filter else min(top_k, count), where=where or None,
            include=["documents", "metadatas", "distances"])
        hits: list[SearchHit] = []
        for rank, (chunk_id, text, meta, distance) in enumerate(zip(result["ids"][0], result["documents"][0],
                result["metadatas"][0], result["distances"][0]), start=1):
            if not _matches_date(meta.get("published_at"), filters):
                continue
            hits.append(SearchHit(channel="vector", rank=len(hits) + 1, distance=float(distance), chunk_id=chunk_id,
                evidence_id=str(meta["evidence_id"]), title=str(meta["title"]), text=text,
                source_type=str(meta["source_type"]), evidence_level=meta.get("evidence_level"),
                population=meta.get("population"), intervention=meta.get("intervention"),
                comparator=meta.get("comparator"), outcome=meta.get("outcome"),
                published_at=meta.get("published_at"), page=meta.get("page"), section=meta.get("section"),
                index_version=self.index_version, metadata=dict(meta)))
            if len(hits) >= top_k:
                break
        return hits


def _matches_date(published_at: Any, filters: dict[str, Any] | None) -> bool:
    if not filters or not any(key in filters for key in ("date_from", "date_to")):
        return True
    if published_at is None:
        return False
    value = datetime.fromisoformat(str(published_at).replace("Z", "+00:00")).date()
    if filters.get("date_from") and value < datetime.fromisoformat(str(filters["date_from"])).date():
        return False
    if filters.get("date_to") and value > datetime.fromisoformat(str(filters["date_to"])).date():
        return False
    return True
