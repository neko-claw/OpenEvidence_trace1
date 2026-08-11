"""Build deterministic stand-in embeddings for the offline dev corpus.

A3 的真实 embedding 索引尚未冻结，因此开发集使用一个确定性的
hash bag-of-words 向量作为语义通道的占位实现：同一 token 永远映射到同一
向量坐标，余弦相似度等价于加权的词项重叠。该实现仅用于离线评测与流程
验证，不用于生产；接入 A3 的真实 embedding 后，只需替换 ``vectors.json``
的数值，评测脚本无需改动。

用法：``python -m scripts.build_dev_vectors``
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from retrieval.bm25 import tokenize

DIM = 64
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "dev"


def embed_text(text: str, dim: int = DIM) -> list[float]:
    """Deterministic L2-normalized hashed bag-of-words vector."""
    vector = [0.0] * dim
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def main() -> None:
    corpus = [
        json.loads(line)
        for line in (DATA_DIR / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    questions = [
        json.loads(line)
        for line in (DATA_DIR / "questions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    vectors = {
        "chunks": {
            chunk["chunk_id"]: embed_text(f"{chunk['title']} {chunk['text']}")
            for chunk in corpus
        },
        "queries": {
            question["question_id"]: embed_text(
                f"{question['text']} {' '.join(question.get('english_terms', []))}"
            )
            for question in questions
        },
    }
    destination = DATA_DIR / "vectors.json"
    destination.write_text(json.dumps(vectors, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {destination} ({len(vectors['chunks'])} chunks, {len(vectors['queries'])} queries)")


if __name__ == "__main__":
    main()
