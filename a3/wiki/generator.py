from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from pydantic import Field

from a3.config import WikiTopicConfig
from a3.domain.models import Evidence, EvidenceSpan, IndexManifest, StrictModel


class WikiPage(StrictModel):
    slug: str
    title: str
    content: str


class WikiLexicalDocument(StrictModel):
    slug: str
    title: str
    text: str
    relative_path: str


class WikiBundle(StrictModel):
    pages: list[WikiPage]
    lexical_documents: list[WikiLexicalDocument]


class WikiGenerator(Protocol):
    @property
    def identifier(self) -> str: ...

    def generate(self, *, evidence: Sequence[Evidence], spans: Sequence[EvidenceSpan],
                 manifest: IndexManifest, topics: Sequence[WikiTopicConfig]) -> WikiBundle: ...


class LLMWikiEntry(StrictModel):
    text: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    span_id: str = Field(min_length=1)


class LLMWikiTopicOutput(StrictModel):
    slug: str
    title: str
    entries: list[LLMWikiEntry]


class LLMWikiOutput(StrictModel):
    topics: list[LLMWikiTopicOutput]


class LLMWikiGeneratorAdapter:
    """Future structured-LLM seam; no model or prompt execution is bundled here."""

    def __init__(self, generate_json: Callable[[dict[str, Any]], dict[str, Any]], *,
                 prompt_path: str | Path, schema_path: str | Path, version: str) -> None:
        self._generate_json = generate_json
        self.prompt_path = Path(prompt_path)
        self.schema_path = Path(schema_path)
        self.version = version

    @property
    def identifier(self) -> str:
        return f"llm-wiki@{self.version}"

    def generate_structured(self, payload: dict[str, Any]) -> LLMWikiOutput:
        return LLMWikiOutput.model_validate(self._generate_json(payload))
