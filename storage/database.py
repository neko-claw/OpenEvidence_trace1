from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from core.models import Evidence, IndexVersion


class EvidenceDatabase:
    """
    A3 的 SQLite 证据数据库。

    目前包含三张核心表：

    1. evidence
       保存规范化医学证据

    2. chunks
       保存后续切分出来的证据片段

    3. index_versions
       保存每次索引构建的版本信息
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

        # 如果 data/sqlite 还不存在，自动创建。
        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.conn = sqlite3.connect(
            self.db_path
        )

        # 查询时允许通过列名访问：
        # row["title"]
        self.conn.row_factory = sqlite3.Row

        # SQLite 外键约束默认不是强制开启的。
        self.conn.execute(
            "PRAGMA foreign_keys = ON"
        )

    def init_schema(self) -> None:
        """
        创建数据库表。

        IF NOT EXISTS 保证重复运行不会报错。
        """

        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS evidence (
                evidence_pk INTEGER PRIMARY KEY AUTOINCREMENT,

                id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                stable_id TEXT NOT NULL,

                title TEXT NOT NULL,
                abstract_or_chunk TEXT NOT NULL,

                authors_json TEXT NOT NULL DEFAULT '[]',
                published_at TEXT,
                url TEXT,

                pmid TEXT,
                doi TEXT,
                nct_id TEXT,

                guideline_name TEXT,
                page TEXT,

                evidence_level TEXT,

                population TEXT,
                intervention TEXT,
                comparator TEXT,
                outcome TEXT,

                fetched_at TEXT,

                content_hash TEXT NOT NULL,

                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(
                    source_type,
                    stable_id,
                    content_hash
                )
            );


            CREATE TABLE IF NOT EXISTS chunks (
                chunk_pk INTEGER PRIMARY KEY AUTOINCREMENT,

                chunk_id TEXT NOT NULL UNIQUE,
                evidence_id TEXT NOT NULL,
                evidence_content_hash TEXT,

                text TEXT NOT NULL,
                page TEXT,
                section TEXT,
                token_count INTEGER,

                content_hash TEXT,

                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            );


            CREATE TABLE IF NOT EXISTS index_versions (
                index_version TEXT PRIMARY KEY,

                corpus_version TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                chunk_policy_json TEXT NOT NULL,

                created_at TEXT NOT NULL
            );


            CREATE INDEX IF NOT EXISTS
                idx_evidence_id
            ON evidence(id);


            CREATE INDEX IF NOT EXISTS
                idx_evidence_stable_id
            ON evidence(stable_id);


            CREATE INDEX IF NOT EXISTS
                idx_evidence_hash
            ON evidence(content_hash);


            CREATE INDEX IF NOT EXISTS
                idx_chunks_evidence_id
            ON chunks(evidence_id);
            """
        )

        self.conn.commit()

    def insert_evidence(
        self,
        evidence: Evidence,
    ) -> bool:
        """
        插入一条 Evidence。

        返回：
        True  -> 新数据成功插入
        False -> 数据已经存在，被去重
        """

        cursor = self.conn.execute(
            """
            INSERT OR IGNORE INTO evidence (
                id,
                source_type,
                stable_id,
                title,
                abstract_or_chunk,
                authors_json,
                published_at,
                url,
                pmid,
                doi,
                nct_id,
                guideline_name,
                page,
                evidence_level,
                population,
                intervention,
                comparator,
                outcome,
                fetched_at,
                content_hash
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                evidence.id,
                evidence.source_type,
                evidence.stable_id,
                evidence.title,
                evidence.abstract_or_chunk,
                json.dumps(
                    evidence.authors,
                    ensure_ascii=False,
                ),
                evidence.published_at,
                evidence.url,
                evidence.pmid,
                evidence.doi,
                evidence.nct_id,
                evidence.guideline_name,
                evidence.page,
                evidence.evidence_level,
                evidence.population,
                evidence.intervention,
                evidence.comparator,
                evidence.outcome,
                evidence.fetched_at,
                evidence.content_hash,
            ),
        )

        self.conn.commit()

        return cursor.rowcount == 1

    def count_evidence(self) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM evidence
            """
        ).fetchone()

        return int(row["count"])

    def get_latest_evidence(
        self,
        evidence_id: str,
    ) -> Optional[dict]:
        """
        根据系统 Evidence ID 获取最新版本。
        """

        row = self.conn.execute(
            """
            SELECT *
            FROM evidence
            WHERE id = ?
            ORDER BY evidence_pk DESC
            LIMIT 1
            """,
            (evidence_id,),
        ).fetchone()

        if row is None:
            return None

        result = dict(row)

        result["authors"] = json.loads(
            result.pop("authors_json")
        )

        return result

    def add_index_version(
        self,
        version: IndexVersion,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO index_versions (
                index_version,
                corpus_version,
                embedding_model,
                chunk_policy_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                version.index_version,
                version.corpus_version,
                version.embedding_model,
                json.dumps(
                    version.chunk_policy,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                version.created_at,
            ),
        )

        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "EvidenceDatabase":
        return self

    def __exit__(
        self,
        exc_type,
        exc_val,
        exc_tb,
    ) -> None:
        self.close()
