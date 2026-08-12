from __future__ import annotations

import re
from dataclasses import dataclass

from a3.domain.models import Chunk, Evidence, EvidenceSpan, canonical_hash

@dataclass(frozen=True)
class ChunkPolicy:
    version: str
    max_chars: int
    overlap_chars: int
    natural_boundary_ratio: float

    def as_dict(self) -> dict[str, int | float]:
        return {"max_chars": self.max_chars, "overlap_chars": self.overlap_chars,
                "natural_boundary_ratio": self.natural_boundary_ratio}


_BOUNDARY = re.compile(r"[。！？；.!?;\n]")
_SENTENCE = re.compile(r".+?(?:[。！？；]+|[.!?;]+(?=\s|$)|\n+|$)", re.S)


def _page_locator(raw_page: str | None) -> tuple[int | None, str | None]:
    if raw_page and raw_page.isdecimal() and int(raw_page) > 0:
        return int(raw_page), raw_page
    return None, raw_page


def chunk_evidence(evidence: Evidence, policy: ChunkPolicy) -> tuple[list[Chunk], list[EvidenceSpan]]:
    text = evidence.abstract_or_chunk
    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        target = min(start + policy.max_chars, len(text))
        end = target
        if target < len(text):
            floor = start + int(policy.max_chars * policy.natural_boundary_ratio)
            candidates = [m.end() for m in _BOUNDARY.finditer(text, floor, target)]
            if candidates:
                end = candidates[-1]
        body = text[start:end]
        index = len(chunks)
        chunk_id = f"{evidence.id}:{evidence.content_hash[:12]}:{index:04d}"
        page, raw_page = _page_locator(evidence.page)
        chunks.append(Chunk(chunk_id=chunk_id, evidence_id=evidence.id,
            evidence_content_hash=evidence.content_hash, text=body, page=page, raw_page=raw_page,
            section=evidence.section, char_start=start, char_end=end,
            token_count=len(re.findall(r"\w+|[\u4e00-\u9fff]", body)), content_hash=canonical_hash(body)))
        if end >= len(text):
            break
        start = max(start + 1, end - policy.overlap_chars)
    spans: list[EvidenceSpan] = []
    for chunk in chunks:
        for i, match in enumerate(_SENTENCE.finditer(chunk.text)):
            raw = match.group(0)
            left = len(raw) - len(raw.lstrip())
            right = len(raw.rstrip())
            if right <= left:
                continue
            local_start, local_end = match.start() + left, match.start() + right
            span_text = chunk.text[local_start:local_end]
            span_id = f"{chunk.chunk_id}:s{i:03d}"
            spans.append(EvidenceSpan(span_id=span_id, evidence_id=evidence.id, chunk_id=chunk.chunk_id,
                text=span_text, char_start=local_start, char_end=local_end,
                document_char_start=chunk.char_start + local_start,
                document_char_end=chunk.char_start + local_end,
                page=chunk.page, raw_page=chunk.raw_page, section=chunk.section,
                chunk_content_hash=chunk.content_hash, evidence_content_hash=evidence.content_hash,
                content_hash=canonical_hash(span_text)))
    return chunks, spans
