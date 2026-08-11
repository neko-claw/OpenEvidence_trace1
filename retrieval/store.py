"""SQLite-backed evidence store: hash dedup, tombstone, versions, filters (4.1).

P0 storage keeps ``EvidenceChunk`` rows in SQLite so metadata, versions, and
audit state are queryable and incremental.  The public ``load_chunks`` /
``upsert_chunks`` contract is stable so the corpus can migrate to
PostgreSQL + pgvector / OpenSearch later without touching ``search()``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from .models import EvidenceChunk


@dataclass(frozen=True)
class UpsertStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicates_skipped: int = 0
    tombstoned_skipped: int = 0


_PICO_FIELDS = ("pico_population", "pico_intervention", "pico_comparator", "pico_outcome")


class EvidenceStore:
    """SQLite evidence store with content-hash dedup and immutable versions."""

    def __init__(
        self,
        path: str | Path,
        *,
        index_version: str = "v1",
        corpus_version: str = "v1",
        embedding_model: str = "unknown",
        chunk_policy: str = "v1",
    ) -> None:
        if not isinstance(index_version, str) or not index_version.strip():
            raise ValueError("index_version must be a nonblank string")
        if not isinstance(corpus_version, str) or not corpus_version.strip():
            raise ValueError("corpus_version must be a nonblank string")
        self._index_version = index_version
        self._corpus_version = corpus_version
        self._connection = sqlite3.connect(str(path))
        self._connection.row_factory = sqlite3.Row
        self._create_schema()
        self._migrate_schema()
        self.record_version(index_version, corpus_hash=None, embedding_model=embedding_model, chunk_policy=chunk_policy)

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL,
                stable_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                published_at TEXT,
                evidence_level TEXT NOT NULL DEFAULT 'unknown',
                topic TEXT NOT NULL DEFAULT '',
                pico_population TEXT NOT NULL DEFAULT '[]',
                pico_intervention TEXT NOT NULL DEFAULT '[]',
                pico_comparator TEXT NOT NULL DEFAULT '[]',
                pico_outcome TEXT NOT NULL DEFAULT '[]',
                content_hash TEXT NOT NULL UNIQUE,
                is_tombstoned INTEGER NOT NULL DEFAULT 0,
                page TEXT NOT NULL DEFAULT '',
                section TEXT NOT NULL DEFAULT '',
                token_count INTEGER NOT NULL DEFAULT 0,
                index_version TEXT NOT NULL,
                corpus_version TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS versions (
                version TEXT PRIMARY KEY,
                corpus_hash TEXT,
                embedding_model TEXT,
                chunk_policy TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    def _migrate_schema(self) -> None:
        """Add columns introduced after v0.1 to pre-existing databases."""
        columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(chunks)").fetchall()
        }
        for column, definition in (
            ("page", "TEXT NOT NULL DEFAULT ''"),
            ("section", "TEXT NOT NULL DEFAULT ''"),
            ("token_count", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if column not in columns:
                self._connection.execute(f"ALTER TABLE chunks ADD COLUMN {column} {definition}")
        self._connection.commit()

    def upsert_chunks(self, chunks: Iterable[EvidenceChunk]) -> UpsertStats:
        """Insert new chunks, update changed ones, and skip duplicates by hash.

        A chunk whose ``stable_id`` is tombstoned is skipped; a chunk whose
        ``content_hash`` already exists anywhere in the store is skipped.
        """
        stats = UpsertStats()
        for chunk in chunks:
            if not isinstance(chunk, EvidenceChunk):
                raise ValueError("chunks must contain only EvidenceChunk values")
            if self._is_tombstoned(chunk.stable_id):
                stats = _bump(stats, "tombstoned_skipped")
                continue
            existing_hash = self._find_hash(chunk.content_hash)
            if existing_hash is not None and existing_hash != chunk.chunk_id:
                stats = _bump(stats, "duplicates_skipped")
                continue
            existing = self._find_chunk(chunk.chunk_id)
            if existing is None:
                self._insert(chunk)
                stats = _bump(stats, "inserted")
            elif existing["content_hash"] != chunk.content_hash:
                self._update(chunk)
                stats = _bump(stats, "updated")
            else:
                stats = _bump(stats, "unchanged")
        self._connection.commit()
        return stats

    def tombstone(self, stable_id: str) -> bool:
        """Mark every live chunk of a stable evidence id as withdrawn."""
        if not isinstance(stable_id, str) or not stable_id.strip():
            raise ValueError("stable_id must be a nonblank string")
        cursor = self._connection.execute(
            "UPDATE chunks SET is_tombstoned = 1 WHERE stable_id = ? AND is_tombstoned = 0",
            (stable_id,),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def load_chunks(
        self,
        *,
        topic: str | None = None,
        source_types: Iterable[str] | None = None,
        evidence_levels: Iterable[str] | None = None,
        published_after: str | None = None,
        require_versions: tuple[str, str] | None = None,
    ) -> tuple[EvidenceChunk, ...]:
        """Load live chunks with optional metadata filters, newest first."""
        if require_versions is not None:
            expected_index, expected_corpus = require_versions
            if (expected_index, expected_corpus) != (self._index_version, self._corpus_version):
                raise ValueError(
                    f"corpus version mismatch: store is ({self._index_version}, {self._corpus_version}), "
                    f"requested ({expected_index}, {expected_corpus})"
                )
        where = ["is_tombstoned = 0"]
        params: list[object] = []
        if topic:
            where.append("topic = ?")
            params.append(topic)
        if source_types:
            normalized = tuple(source_types)
            placeholders = ",".join("?" for _ in normalized)
            where.append(f"source_type IN ({placeholders})")
            params.extend(normalized)
        if evidence_levels:
            normalized = tuple(evidence_levels)
            placeholders = ",".join("?" for _ in normalized)
            where.append(f"evidence_level IN ({placeholders})")
            params.extend(normalized)
        if published_after:
            where.append("published_at > ?")
            params.append(published_after)
        cursor = self._connection.execute(
            f"SELECT * FROM chunks WHERE {' AND '.join(where)} ORDER BY published_at DESC",
            params,
        )
        rows = cursor.fetchall()
        return tuple(_row_to_chunk(row, self._index_version, self._corpus_version) for row in rows)

    def record_version(
        self,
        version: str,
        *,
        corpus_hash: str | None = None,
        embedding_model: str | None = None,
        chunk_policy: str | None = None,
    ) -> None:
        """Record an immutable index/corpus version row (INSERT OR REPLACE)."""
        if not isinstance(version, str) or not version.strip():
            raise ValueError("version must be a nonblank string")
        self._connection.execute(
            "INSERT OR REPLACE INTO versions(version, corpus_hash, embedding_model, chunk_policy, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                version,
                corpus_hash,
                embedding_model,
                chunk_policy,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        self._connection.commit()

    def get_version(self, version: str) -> dict[str, str] | None:
        row = self._connection.execute("SELECT * FROM versions WHERE version = ?", (version,)).fetchone()
        if row is None:
            return None
        return {key: row[key] for key in ("version", "corpus_hash", "embedding_model", "chunk_policy", "created_at")}

    def close(self) -> None:
        self._connection.close()

    def _find_chunk(self, chunk_id: str) -> sqlite3.Row | None:
        return self._connection.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()

    def _find_hash(self, content_hash: str) -> str | None:
        row = self._connection.execute("SELECT chunk_id FROM chunks WHERE content_hash = ?", (content_hash,)).fetchone()
        return row["chunk_id"] if row is not None else None

    def _is_tombstoned(self, stable_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM chunks WHERE stable_id = ? AND is_tombstoned = 1 LIMIT 1", (stable_id,)
        ).fetchone()
        return row is not None

    def _insert(self, chunk: EvidenceChunk) -> None:
        self._connection.execute(
            "INSERT INTO chunks(chunk_id, evidence_id, stable_id, title, text, source_type, url, "
            "published_at, evidence_level, topic, pico_population, pico_intervention, pico_comparator, "
            "pico_outcome, content_hash, is_tombstoned, page, section, token_count, index_version, "
            "corpus_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _chunk_row(chunk, self._index_version, self._corpus_version),
        )

    def _update(self, chunk: EvidenceChunk) -> None:
        self._connection.execute(
            "UPDATE chunks SET evidence_id = ?, stable_id = ?, title = ?, text = ?, source_type = ?, "
            "url = ?, published_at = ?, evidence_level = ?, topic = ?, pico_population = ?, "
            "pico_intervention = ?, pico_comparator = ?, pico_outcome = ?, content_hash = ?, "
            "is_tombstoned = 0, page = ?, section = ?, token_count = ?, index_version = ?, "
            "corpus_version = ? WHERE chunk_id = ?",
            (
                chunk.evidence_id,
                chunk.stable_id,
                chunk.title,
                chunk.text,
                chunk.source_type,
                chunk.url,
                chunk.published_at,
                chunk.evidence_level,
                chunk.topic,
                json.dumps(list(chunk.pico_population), ensure_ascii=False),
                json.dumps(list(chunk.pico_intervention), ensure_ascii=False),
                json.dumps(list(chunk.pico_comparator), ensure_ascii=False),
                json.dumps(list(chunk.pico_outcome), ensure_ascii=False),
                chunk.content_hash,
                chunk.page,
                chunk.section,
                _token_count(chunk),
                self._index_version,
                self._corpus_version,
                chunk.chunk_id,
            ),
        )


def _chunk_row(chunk: EvidenceChunk, index_version: str, corpus_version: str) -> tuple[object, ...]:
    return (
        chunk.chunk_id,
        chunk.evidence_id,
        chunk.stable_id,
        chunk.title,
        chunk.text,
        chunk.source_type,
        chunk.url,
        chunk.published_at,
        chunk.evidence_level,
        chunk.topic,
        json.dumps(list(chunk.pico_population), ensure_ascii=False),
        json.dumps(list(chunk.pico_intervention), ensure_ascii=False),
        json.dumps(list(chunk.pico_comparator), ensure_ascii=False),
        json.dumps(list(chunk.pico_outcome), ensure_ascii=False),
        chunk.content_hash,
        0,
        chunk.page,
        chunk.section,
        _token_count(chunk),
        index_version,
        corpus_version,
    )


def _row_to_chunk(row: sqlite3.Row, index_version: str, corpus_version: str) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=row["chunk_id"],
        evidence_id=row["evidence_id"],
        stable_id=row["stable_id"],
        title=row["title"],
        text=row["text"],
        source_type=row["source_type"],
        url=row["url"],
        published_at=row["published_at"],
        evidence_level=row["evidence_level"],
        topic=row["topic"],
        pico_population=tuple(json.loads(row["pico_population"])),
        pico_intervention=tuple(json.loads(row["pico_intervention"])),
        pico_comparator=tuple(json.loads(row["pico_comparator"])),
        pico_outcome=tuple(json.loads(row["pico_outcome"])),
        content_hash=row["content_hash"],
        is_tombstoned=bool(row["is_tombstoned"]),
        page=row["page"],
        section=row["section"],
        token_count=row["token_count"],
        index_version=index_version,
        corpus_version=corpus_version,
    )


def _token_count(chunk: EvidenceChunk) -> int:
    """Use the annotated token count, or estimate it deterministically."""
    if chunk.token_count > 0:
        return chunk.token_count
    from .bm25 import tokenize

    return len(tokenize(f"{chunk.title} {chunk.text}"))


def _bump(stats: UpsertStats, field_name: str) -> UpsertStats:
    values = {name: getattr(stats, name) for name in stats.__dataclass_fields__}
    values[field_name] += 1
    return UpsertStats(**values)
