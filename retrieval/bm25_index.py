from __future__ import annotations

import json
import re
from pathlib import Path

from rank_bm25 import BM25Okapi


EN_TOKEN_PATTERN = re.compile(
    r"[a-z0-9]+(?:[-_./:][a-z0-9]+)*"
)

ZH_PATTERN = re.compile(
    r"[\u4e00-\u9fff]+"
)


def tokenize(text: str) -> list[str]:
    """
    A3 v0.2 BM25 tokenizer。

    支持：
    - 英文医学术语
    - PMID / NCT / DOI 等标识符
    - 中文单字 + 双字组合
    - 对带前缀 stable_id 同时建立裸编号 token

    例如：
        nct:NCT01234567

    会产生：
        nct:nct01234567
        nct01234567

    因此用户直接搜索 NCT01234567 也能命中。
    """

    text = text.lower().strip()

    tokens: list[str] = []

    english_tokens = EN_TOKEN_PATTERN.findall(text)

    for token in english_tokens:
        tokens.append(token)

        # 让 nct:xxx / pmid:xxx / doi:xxx
        # 同时支持用户只输入 xxx。
        if ":" in token:
            _, suffix = token.split(":", 1)

            if suffix:
                tokens.append(suffix)

    # 简单中文支持：单字 + 双字
    for sequence in ZH_PATTERN.findall(text):
        chars = list(sequence)

        tokens.extend(chars)

        tokens.extend(
            sequence[i:i + 2]
            for i in range(len(sequence) - 1)
        )

    return tokens


def make_search_text(
    chunk: dict,
) -> str:
    """
    将 Chunk 和关键 metadata 拼成 BM25 文档。

    不只索引 chunk.text，
    也把 title / PICO / stable_id 等纳入关键词检索。
    """

    fields = [
        chunk.get("title"),
        chunk.get("text"),
        chunk.get("source_type"),
        chunk.get("stable_id"),
        chunk.get("evidence_level"),
        chunk.get("population"),
        chunk.get("intervention"),
        chunk.get("comparator"),
        chunk.get("outcome"),
    ]

    return " ".join(
        str(value)
        for value in fields
        if value
    )


class BM25Index:
    """
    OpenEvidence A3 的 BM25 索引。

    documents:
        SQLite 当前有效 Chunk 的元数据。

    corpus:
        每个 Chunk 对应的 token 列表。
    """

    def __init__(
        self,
        documents: list[dict],
    ):
        self.documents = documents

        self.corpus = [
            tokenize(
                make_search_text(document)
            )
            for document in documents
        ]

        self.model = (
            BM25Okapi(self.corpus)
            if self.corpus
            else None
        )

    @classmethod
    def from_chunks(
        cls,
        chunks: list[dict],
    ) -> "BM25Index":
        return cls(chunks)

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[dict]:
        """
        BM25 搜索。

        返回：
        rank
        score
        chunk_id
        evidence_id
        title
        text
        以及原始 metadata。
        """

        if (
            self.model is None
            or not self.documents
        ):
            return []

        query_tokens = tokenize(query)

        if not query_tokens:
            return []

        scores = self.model.get_scores(
            query_tokens
        )

        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )

        results: list[dict] = []

        for index in ranked_indices:
            score = float(scores[index])

            if score <= min_score:
                continue

            document = dict(
                self.documents[index]
            )

            document["score"] = score
            document["rank"] = (
                len(results) + 1
            )

            results.append(document)

            if len(results) >= top_k:
                break

        return results

    def save(
        self,
        directory: str | Path,
    ) -> None:
        """
        保存可重复构建所需的数据。

        不使用 pickle，
        避免 Python 版本之间出现兼容问题。

        load() 时重新构建 BM25Okapi。
        """

        directory = Path(directory)

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        corpus_path = (
            directory
            / "bm25_documents.jsonl"
        )

        with corpus_path.open(
            "w",
            encoding="utf-8",
        ) as f:
            for document in self.documents:
                f.write(
                    json.dumps(
                        document,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        manifest = {
            "index_type": "bm25",
            "document_count": len(
                self.documents
            ),
            "tokenizer_version": (
                "a3-bilingual-v0.2"
            ),
        }

        (
            directory
            / "bm25_manifest.json"
        ).write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(
        cls,
        directory: str | Path,
    ) -> "BM25Index":
        directory = Path(directory)

        corpus_path = (
            directory
            / "bm25_documents.jsonl"
        )

        if not corpus_path.exists():
            raise FileNotFoundError(
                f"BM25 corpus not found: "
                f"{corpus_path}"
            )

        documents: list[dict] = []

        with corpus_path.open(
            "r",
            encoding="utf-8",
        ) as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                documents.append(
                    json.loads(line)
                )

        return cls(documents)
