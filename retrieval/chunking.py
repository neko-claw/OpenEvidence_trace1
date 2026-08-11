from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

from core.models import Chunk, Evidence


@dataclass(frozen=True)
class ChunkPolicy:
    """
    A3 v0.1 的固定切块策略。

    max_chars:
        一个 chunk 最多包含多少字符。

    overlap_chars:
        相邻两个 chunk 之间保留多少字符的重叠。

    min_boundary_ratio:
        尝试寻找句号等自然边界时，
        至少保留 max_chars 的多少比例。
    """

    max_chars: int = 800
    overlap_chars: int = 120
    min_boundary_ratio: float = 0.60

    def to_dict(self) -> dict:
        return asdict(self)


TOKEN_PATTERN = re.compile(
    r"[A-Za-z0-9]+(?:[-_./:][A-Za-z0-9]+)*"
    r"|[\u4e00-\u9fff]"
)


def count_tokens(text: str) -> int:
    """
    轻量 token 计数。

    这里不是 LLM tokenizer 的精确 token 数，
    而是供数据库记录和调试使用的近似值。
    """

    return len(
        TOKEN_PATTERN.findall(text)
    )


def normalize_text(text: str) -> str:
    """
    清理多余空白，但不改变实际文字内容。
    """

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def split_text(
    text: str,
    policy: ChunkPolicy,
) -> list[str]:
    """
    将一段长文本切成多个 chunk。

    优先尝试在句号、问号等自然边界切开。
    如果找不到合适的句子边界，
    就按照 max_chars 强制切分。
    """

    text = normalize_text(text)

    if not text:
        return []

    if policy.max_chars <= 0:
        raise ValueError(
            "max_chars must be > 0"
        )

    if not (
        0 <= policy.overlap_chars
        < policy.max_chars
    ):
        raise ValueError(
            "overlap_chars must satisfy "
            "0 <= overlap_chars < max_chars"
        )

    chunks: list[str] = []

    start = 0
    text_length = len(text)

    boundaries = (
        "。",
        "！",
        "？",
        ".",
        "!",
        "?",
        ";",
        "；",
    )

    while start < text_length:
        hard_end = min(
            start + policy.max_chars,
            text_length,
        )

        end = hard_end

        # 如果不是最后一块，
        # 尝试向前寻找自然句子边界。
        if hard_end < text_length:
            candidate = text[
                start:hard_end
            ]

            boundary_positions = [
                candidate.rfind(mark)
                for mark in boundaries
            ]

            best_boundary = max(
                boundary_positions
            )

            minimum_position = int(
                policy.max_chars
                * policy.min_boundary_ratio
            )

            if best_boundary >= minimum_position:
                end = (
                    start
                    + best_boundary
                    + 1
                )

        chunk_text = text[start:end].strip()

        if chunk_text:
            chunks.append(chunk_text)

        if end >= text_length:
            break

        next_start = (
            end - policy.overlap_chars
        )

        if next_start <= start:
            next_start = end

        start = next_start

    return chunks


def make_chunk_hash(text: str) -> str:
    """
    为每个 chunk 生成内容指纹。
    """

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def chunk_evidence(
    evidence: Evidence,
    policy: ChunkPolicy | None = None,
) -> list[Chunk]:
    """
    将一条 Evidence 转换成 Chunk[]。

    chunk_id 同时包含：
    Evidence ID
    Evidence 内容 hash
    chunk 序号

    因此当 Evidence 内容更新时，
    新旧版本不会撞 ID。
    """

    if policy is None:
        policy = ChunkPolicy()

    pieces = split_text(
        evidence.abstract_or_chunk,
        policy,
    )

    chunks: list[Chunk] = []

    evidence_hash = (
        evidence.content_hash
        or evidence.calculate_content_hash()
    )

    short_hash = evidence_hash[:12]

    for index, text in enumerate(
        pieces,
        start=1,
    ):
        chunk = Chunk(
            chunk_id=(
                f"{evidence.id}:"
                f"{short_hash}:"
                f"{index:03d}"
            ),
            evidence_id=evidence.id,
            text=text,
            page=evidence.page,
            section=None,
            token_count=count_tokens(text),
            content_hash=make_chunk_hash(text),
        )

        chunks.append(chunk)

    return chunks
