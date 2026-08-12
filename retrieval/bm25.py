"""Deterministic, dependency-free BM25 lexical retrieval."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from math import isfinite, log
from numbers import Real
import re

from .models import EvidenceChunk, ScoredChunk


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)


def tokenize(text: str) -> tuple[str, ...]:
    """Return lowercase Latin terms plus whole and contiguous CJK n-grams.

    Chinese components have a minimum length of two characters, preventing a
    reordered string from matching merely because it contains the same chars.
    """
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(text):
        token = match.group(0).lower()
        if _is_cjk_run(token):
            if len(token) >= 2:
                tokens.append(token)
                tokens.extend(_cjk_ngrams(token))
        else:
            tokens.append(token)
    return tuple(tokens)


def _is_cjk_run(token: str) -> bool:
    return bool(token) and all("\u4e00" <= character <= "\u9fff" for character in token)


def _cjk_ngrams(token: str) -> tuple[str, ...]:
    return tuple(
        token[start : start + width]
        for width in range(2, len(token))
        for start in range(len(token) - width + 1)
    )


class BM25Index:
    """An in-memory Okapi BM25 index over evidence titles and text."""

    def __init__(self, chunks: Iterable[EvidenceChunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        if (
            not isinstance(k1, Real)
            or isinstance(k1, bool)
            or not isfinite(k1)
            or k1 <= 0
            or not isinstance(b, Real)
            or isinstance(b, bool)
            or not isfinite(b)
            or not 0 <= b <= 1
        ):
            raise ValueError("k1 must be positive and b must be in [0, 1]")
        try:
            self._chunks = tuple(chunks)
        except TypeError as error:
            raise ValueError("chunks must be an iterable of EvidenceChunk") from error
        if any(not isinstance(chunk, EvidenceChunk) for chunk in self._chunks):
            raise ValueError("chunks must contain only EvidenceChunk values")

        chunk_ids = [chunk.chunk_id for chunk in self._chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("duplicate chunk_id in BM25 index")

        self._k1 = k1
        self._b = b
        self._term_frequencies = tuple(Counter(tokenize(f"{chunk.title} {chunk.text}")) for chunk in self._chunks)
        self._document_lengths = tuple(sum(term_frequencies.values()) for term_frequencies in self._term_frequencies)
        self._average_document_length = (
            sum(self._document_lengths) / len(self._document_lengths) if self._document_lengths else 0.0
        )
        document_frequencies: Counter[str] = Counter()
        for term_frequencies in self._term_frequencies:
            document_frequencies.update(term_frequencies.keys())
        self._inverse_document_frequency = {
            term: log(1.0 + (len(self._chunks) - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequencies.items()
        }

    def search(self, query: str, k: int) -> list[ScoredChunk]:
        """Return up to ``k`` positive-score documents in deterministic rank order."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a nonblank string")
        if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
            raise ValueError("k must be a positive integer")

        query_terms = tokenize(query)
        if not query_terms or not self._chunks:
            return []

        scores: list[tuple[EvidenceChunk, float]] = []
        for chunk, term_frequencies, document_length in zip(
            self._chunks, self._term_frequencies, self._document_lengths, strict=True
        ):
            score = self._score(query_terms, term_frequencies, document_length)
            if score > 0:
                scores.append((chunk, score))

        scores.sort(key=lambda item: (-item[1], item[0].chunk_id))
        return [
            ScoredChunk(chunk=chunk, score=score, rank=rank, stage="bm25")
            for rank, (chunk, score) in enumerate(scores[:k], start=1)
        ]

    def _score(self, query_terms: tuple[str, ...], term_frequencies: Counter[str], document_length: int) -> float:
        if self._average_document_length == 0:
            return 0.0
        length_normalizer = self._k1 * (1.0 - self._b + self._b * document_length / self._average_document_length)
        return sum(
            self._inverse_document_frequency.get(term, 0.0)
            * (frequency := term_frequencies.get(term, 0))
            * (self._k1 + 1.0)
            / (frequency + length_normalizer)
            for term in query_terms
            if term in term_frequencies
        )
