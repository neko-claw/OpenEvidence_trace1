from __future__ import annotations

import hashlib
import json
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class Evidence(BaseModel):
    """
    OpenEvidence 统一证据数据模型。

    A2 负责采集数据；
    A3 使用这个模型统一检查和整理数据。
    """

    id: str
    source_type: str
    title: str
    abstract_or_chunk: str

    authors: list[str] = Field(default_factory=list)
    published_at: Optional[str] = None
    url: Optional[str] = None

    pmid: Optional[str] = None
    doi: Optional[str] = None
    nct_id: Optional[str] = None

    guideline_name: Optional[str] = None
    page: Optional[str] = None

    evidence_level: Optional[str] = None

    # PICO
    population: Optional[str] = None
    intervention: Optional[str] = None
    comparator: Optional[str] = None
    outcome: Optional[str] = None

    fetched_at: Optional[str] = None
    content_hash: Optional[str] = None

    @property
    def stable_id(self) -> str:
        """
        尽量找到一个来自原始来源的稳定标识。

        优先级：
        PMID -> DOI -> NCT ID -> 指南信息 -> 系统内部 Evidence ID
        """

        if self.pmid:
            return f"pmid:{self.pmid}"

        if self.doi:
            return f"doi:{self.doi.lower()}"

        if self.nct_id:
            return f"nct:{self.nct_id.upper()}"

        if self.guideline_name:
            page = self.page or "unknown"
            return f"guideline:{self.guideline_name}:{page}"

        return f"id:{self.id}"

    def calculate_content_hash(self) -> str:
        """
        根据“真正的证据内容”计算 SHA256。

        fetched_at 不参与 hash：
        因为重新下载同一篇文献，不应该被误判成内容变化。
        """

        content = {
            "title": self.title.strip(),
            "abstract_or_chunk": self.abstract_or_chunk.strip(),
            "published_at": self.published_at,
            "pmid": self.pmid,
            "doi": self.doi,
            "nct_id": self.nct_id,
            "guideline_name": self.guideline_name,
            "page": self.page,
        }

        canonical = json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        return hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()

    @model_validator(mode="after")
    def fill_content_hash(self) -> "Evidence":
        """
        如果 A2 已经提供 content_hash，就直接保留。

        如果没有，则由 A3 自动计算。
        """

        if not self.content_hash:
            self.content_hash = self.calculate_content_hash()

        return self


class Chunk(BaseModel):
    """
    后续切块时使用的数据结构。
    """

    chunk_id: str
    evidence_id: str
    text: str

    page: Optional[str] = None
    section: Optional[str] = None
    token_count: Optional[int] = None

    content_hash: Optional[str] = None


class IndexVersion(BaseModel):
    """
    保存每一次索引构建所使用的版本配置。
    """

    index_version: str
    corpus_version: str
    embedding_model: str
    chunk_policy: dict
    created_at: str
