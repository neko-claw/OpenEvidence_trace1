from __future__ import annotations

from collections.abc import Callable, Sequence
import json
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
        try:
            return LLMWikiOutput.model_validate(self._generate_json(payload))
        except Exception as exc:
            raise RuntimeError("structured LLM Wiki generation failed closed") from exc

    def generate(self, *, evidence: Sequence[Evidence], spans: Sequence[EvidenceSpan],
                 manifest: IndexManifest, topics: Sequence[WikiTopicConfig]) -> WikiBundle:
        if not evidence or any(item.mock or item.tombstone for item in evidence):
            raise RuntimeError("LLM Wiki requires live non-Mock Evidence; offline fixtures use the Mock generator")
        try:
            prompt = self.prompt_path.read_text(encoding="utf-8")
            schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError("LLM Wiki prompt/schema asset loading failed closed") from exc
        output = self.generate_structured({"prompt": prompt, "schema": schema,
            "manifest": manifest.model_dump(mode="json"),
            "topics": [topic.model_dump(mode="json") for topic in topics],
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "spans": [span.model_dump(mode="json") for span in spans]})
        configured = {topic.slug: topic for topic in topics}
        if len(output.topics) != len(configured) or {item.slug for item in output.topics} != set(configured):
            raise RuntimeError("LLM Wiki output topics do not match configured topics")
        by_evidence = {item.id: item for item in evidence}
        by_span = {span.span_id: span for span in spans}
        pages = [WikiPage(slug="_index", title="Evidence Wiki Index", content="\n".join([
            "# Evidence Wiki Index", "", "> LLM-GENERATED NAVIGATION — REQUIRES HUMAN REVIEW",
            "", *[f"- [{topic.title}]({topic.slug}.md)" for topic in topics], ""]))]
        documents: list[WikiLexicalDocument] = []
        output_by_slug = {item.slug: item for item in output.topics}
        for position, topic in enumerate(topics):
            generated = output_by_slug[topic.slug]
            if generated.title != topic.title:
                raise RuntimeError(f"LLM Wiki title mismatch for {topic.slug}")
            lines = [f"# {topic.title}", "",
                "> LLM-GENERATED NAVIGATION — REQUIRES HUMAN REVIEW — NOT MEDICAL ADVICE", ""]
            if position + 1 < len(topics):
                next_topic = topics[position + 1]
                lines.extend([f"Next topic: [{next_topic.title}]({next_topic.slug}.md)", ""])
            lines.extend(["## Evidence-linked entries", ""])
            for entry in generated.entries:
                span = by_span.get(entry.span_id)
                if entry.evidence_id not in by_evidence or span is None \
                        or span.evidence_id != entry.evidence_id or entry.text != span.text:
                    raise RuntimeError("LLM Wiki output escaped the Evidence/Span whitelist")
                lines.append(f"- {entry.text} [Evidence: {entry.evidence_id}] [Span: {entry.span_id}]")
            lines.extend(["", "## Provenance", "", f"- corpus version: `{manifest.corpus_version}`",
                f"- index version: `{manifest.index_version}`", f"- generator: `{self.identifier}`",
                "- review status: `UNREVIEWED`", ""])
            pages.append(WikiPage(slug=topic.slug, title=topic.title, content="\n".join(lines)))
            documents.append(WikiLexicalDocument(slug=topic.slug, title=topic.title,
                text="\n".join([topic.title, *topic.synonyms, *topic.mesh]),
                relative_path=f"{topic.slug}.md"))
        return WikiBundle(pages=pages, lexical_documents=documents)
