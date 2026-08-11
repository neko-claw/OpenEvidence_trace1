from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import TracebackType

from a3.domain.models import Chunk, Evidence, EvidenceSpan, IndexManifest


class SQLiteEvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.init_schema()

    def __enter__(self) -> "SQLiteEvidenceStore":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()

    def init_schema(self) -> None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS evidence_versions (
          version_id INTEGER PRIMARY KEY, source_type TEXT NOT NULL, stable_id TEXT NOT NULL,
          content_hash TEXT NOT NULL, evidence_id TEXT NOT NULL, payload_json TEXT NOT NULL,
          tombstone INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(source_type, stable_id, content_hash));
        CREATE TABLE IF NOT EXISTS chunks (
          chunk_id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL, evidence_content_hash TEXT NOT NULL,
          payload_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS spans (
          span_id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL, chunk_id TEXT NOT NULL,
          payload_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS index_versions (
          index_version TEXT PRIMARY KEY, corpus_version TEXT NOT NULL,
          embedding_provider TEXT NOT NULL, embedding_model TEXT NOT NULL,
          embedding_revision TEXT, chunk_policy TEXT NOT NULL,
          bm25_tokenizer_version TEXT NOT NULL, created_at TEXT NOT NULL,
          manifest_json TEXT NOT NULL);
        """)
        self.connection.commit()

    def insert_evidence(self, evidence: Evidence) -> bool:
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO evidence_versions(source_type,stable_id,content_hash,evidence_id,payload_json,tombstone) VALUES(?,?,?,?,?,?)",
            (evidence.source_type, evidence.stable_id, evidence.content_hash, evidence.id,
             evidence.model_dump_json(), int(evidence.tombstone)))
        self.connection.commit()
        return cursor.rowcount == 1

    def list_current_evidence(self) -> list[Evidence]:
        rows = self.connection.execute("""
          SELECT payload_json FROM evidence_versions e
          WHERE version_id=(SELECT version_id FROM evidence_versions x
            WHERE x.source_type=e.source_type AND x.stable_id=e.stable_id
            ORDER BY version_id DESC LIMIT 1) AND tombstone=0 ORDER BY stable_id
        """).fetchall()
        return [Evidence.model_validate_json(row[0]) for row in rows]

    def replace_chunks(self, evidence: Evidence, chunks: list[Chunk], spans: list[EvidenceSpan]) -> None:
        self.connection.execute("DELETE FROM spans WHERE evidence_id=?", (evidence.id,))
        self.connection.execute("DELETE FROM chunks WHERE evidence_id=?", (evidence.id,))
        self.connection.executemany("INSERT INTO chunks VALUES(?,?,?,?)",
            [(c.chunk_id, c.evidence_id, c.evidence_content_hash, c.model_dump_json()) for c in chunks])
        self.connection.executemany("INSERT INTO spans VALUES(?,?,?,?)",
            [(s.span_id, s.evidence_id, s.chunk_id, s.model_dump_json()) for s in spans])
        self.connection.commit()

    def list_current_chunks(self) -> list[Chunk]:
        hashes = {e.content_hash for e in self.list_current_evidence()}
        rows = self.connection.execute("SELECT evidence_content_hash,payload_json FROM chunks ORDER BY chunk_id").fetchall()
        return [Chunk.model_validate_json(r[1]) for r in rows if r[0] in hashes]

    def list_spans_for_evidence(self, evidence_id: str) -> list[EvidenceSpan]:
        rows = self.connection.execute("SELECT payload_json FROM spans WHERE evidence_id=? ORDER BY span_id", (evidence_id,)).fetchall()
        return [EvidenceSpan.model_validate_json(r[0]) for r in rows]

    def list_current_spans(self) -> list[EvidenceSpan]:
        chunk_ids = {c.chunk_id for c in self.list_current_chunks()}
        rows = self.connection.execute("SELECT chunk_id,payload_json FROM spans ORDER BY span_id").fetchall()
        return [EvidenceSpan.model_validate_json(r[1]) for r in rows if r[0] in chunk_ids]

    def record_index(self, manifest: IndexManifest) -> None:
        self.connection.execute("""INSERT OR IGNORE INTO index_versions VALUES(?,?,?,?,?,?,?,?,?)""",
            (manifest.index_version, manifest.corpus_version, manifest.embedding_provider,
             manifest.embedding_model, manifest.embedding_revision,
             json.dumps(manifest.chunk_policy, sort_keys=True), manifest.bm25_tokenizer_version,
             manifest.created_at.isoformat(), manifest.model_dump_json()))
        self.connection.commit()

    def counts(self) -> dict[str, int]:
        return {table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("evidence_versions", "chunks", "spans", "index_versions")}
