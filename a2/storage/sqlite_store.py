from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from a2.models.evidence import A2_EVIDENCE_SCHEMA_VERSION, A2Evidence
from a2.storage.dedup import canonical_key, conservative_merge, normalize_doi


class SQLiteStore:
    """SQLite persistence for evidence, aliases, schema metadata, and HTTP cache."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY, canonical_key TEXT NOT NULL, source_type TEXT NOT NULL,
                    pmid TEXT, doi TEXT, nct_id TEXT, content_hash TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_evidence_canonical ON evidence(canonical_key);
                CREATE INDEX IF NOT EXISTS ix_evidence_source ON evidence(source_type);
                CREATE INDEX IF NOT EXISTS ix_evidence_pmid ON evidence(pmid);
                CREATE INDEX IF NOT EXISTS ix_evidence_doi ON evidence(doi);
                CREATE INDEX IF NOT EXISTS ix_evidence_nct ON evidence(nct_id);
                CREATE INDEX IF NOT EXISTS ix_evidence_hash ON evidence(content_hash);
                CREATE TABLE IF NOT EXISTS source_alias (alias_id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL, source_type TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS schema_meta (name TEXT PRIMARY KEY, version TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS http_cache (
                    cache_key TEXT PRIMARY KEY, source TEXT NOT NULL, created_at TEXT NOT NULL,
                    status_code INTEGER NOT NULL, body BLOB NOT NULL, content_hash TEXT NOT NULL,
                    content_type TEXT
                );
            """)
            db.execute("INSERT OR REPLACE INTO schema_meta(name,version) VALUES(?,?)", ("a2_evidence", A2_EVIDENCE_SCHEMA_VERSION))

    def put(self, record: A2Evidence) -> A2Evidence:
        """Persist or conservatively merge one evidence record."""
        key = canonical_key(record)
        with self.connect() as db:
            row = db.execute("SELECT payload FROM evidence WHERE canonical_key=? ORDER BY id LIMIT 1", (key,)).fetchone()
            final = conservative_merge(A2Evidence.model_validate_json(row["payload"]), record) if row else record
            if row:
                old_id = A2Evidence.model_validate_json(row["payload"]).id
                db.execute("DELETE FROM evidence WHERE id=?", (old_id,))
            db.execute(
                "INSERT OR REPLACE INTO evidence(id,canonical_key,source_type,pmid,doi,nct_id,content_hash,payload) VALUES(?,?,?,?,?,?,?,?)",
                (final.id, key, final.source_type.value, final.pmid, normalize_doi(final.doi), final.nct_id, final.content_hash, final.model_dump_json()),
            )
            for alias in set(final.source_metadata.get("aliases", []) + [record.id, final.id]):
                db.execute("INSERT OR REPLACE INTO source_alias(alias_id,evidence_id,source_type) VALUES(?,?,?)", (alias, final.id, record.source_type.value))
        return final

    def get(self, evidence_id: str) -> A2Evidence | None:
        """Get evidence by primary or source alias ID."""
        with self.connect() as db:
            row = db.execute(
                "SELECT e.payload FROM evidence e LEFT JOIN source_alias a ON a.evidence_id=e.id WHERE e.id=? OR a.alias_id=? LIMIT 1",
                (evidence_id, evidence_id),
            ).fetchone()
        return A2Evidence.model_validate_json(row["payload"]) if row else None

    def list_evidence(self) -> list[A2Evidence]:
        """List evidence in deterministic ID order."""
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM evidence ORDER BY id").fetchall()
        return [A2Evidence.model_validate_json(row["payload"]) for row in rows]

    def cache_get(self, cache_key: str) -> sqlite3.Row | None:
        """Return one cached HTTP response row."""
        with self.connect() as db:
            return db.execute("SELECT * FROM http_cache WHERE cache_key=?", (cache_key,)).fetchone()

    def cache_put(self, cache_key: str, source: str, created_at: str, status_code: int, body: bytes, content_type: str | None) -> None:
        """Persist a cached HTTP response and body hash."""
        digest = hashlib.sha256(body).hexdigest()
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO http_cache(cache_key,source,created_at,status_code,body,content_hash,content_type) VALUES(?,?,?,?,?,?,?)",
                (cache_key, source, created_at, status_code, body, digest, content_type),
            )
