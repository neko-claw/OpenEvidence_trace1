from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from a3.config import WikiTopicConfig
from a3.domain.models import Evidence, EvidenceSpan, IndexManifest
from a3.wiki.generator import WikiBundle, WikiGenerator, WikiLexicalDocument, WikiPage
from a3.wiki.validation import validate_wiki_pages

SECTIONS = (("Guidelines", {"guideline_fixture", "guideline"}),
            ("Systematic reviews", {"systematic_review", "review"}),
            ("RCTs", {"rct"}), ("Clinical trials", {"trial", "clinical_trial"}))


class DeterministicOfflineWikiGenerator:
    def __init__(self, builder_version: str) -> None:
        self.builder_version = builder_version

    @property
    def identifier(self) -> str:
        return f"deterministic-offline-wiki@{self.builder_version}"

    def generate(self, *, evidence: Sequence[Evidence], spans: Sequence[EvidenceSpan],
                 manifest: IndexManifest, topics: Sequence[WikiTopicConfig]) -> WikiBundle:
        if any(not item.mock for item in evidence):
            raise RuntimeError("deterministic offline Wiki accepts mock evidence only; configure a reviewed generator")
        span_by_evidence: dict[str, list[EvidenceSpan]] = {}
        for span in spans:
            span_by_evidence.setdefault(span.evidence_id, []).append(span)
        pages = [self._index_page(topics, manifest)]
        documents: list[WikiLexicalDocument] = []
        for index, topic in enumerate(topics):
            selected = [item for item in evidence if item.provenance.get("topic") == topic.slug]
            next_topic = topics[index + 1] if index + 1 < len(topics) else None
            pages.append(self._topic_page(topic, selected, span_by_evidence, manifest, next_topic))
            terms = [topic.title, *topic.synonyms, *topic.mesh]
            documents.append(WikiLexicalDocument(slug=topic.slug, title=topic.title,
                text="\n".join(terms), relative_path=f"{topic.slug}.md"))
        return WikiBundle(pages=pages, lexical_documents=documents)

    def _index_page(self, topics: Sequence[WikiTopicConfig], manifest: IndexManifest) -> WikiPage:
        lines = ["# Evidence Wiki Index", "", "> MOCK / OFFLINE FIXTURE — NOT MEDICAL EVIDENCE", "",
            "Navigation pages only; final support must return to whitelisted Evidence/Span records.", ""]
        lines.extend(f"- [{topic.title}]({topic.slug}.md)" for topic in topics)
        lines.extend(["", "## Provenance", "", f"- corpus version: `{manifest.corpus_version}`",
            f"- index version: `{manifest.index_version}`", f"- builder: `{self.identifier}`", ""])
        return WikiPage(slug="_index", title="Evidence Wiki Index", content="\n".join(lines))

    def _topic_page(self, topic: WikiTopicConfig, evidence: Sequence[Evidence],
                    span_by_evidence: dict[str, list[EvidenceSpan]], manifest: IndexManifest,
                    next_topic: WikiTopicConfig | None) -> WikiPage:
        lines = [f"# {topic.title}", "", "> MOCK / OFFLINE FIXTURE — NOT MEDICAL EVIDENCE", ""]
        if next_topic:
            lines.extend([f"Next topic: [{next_topic.title}]({next_topic.slug}.md)", ""])
        lines.extend(["## Synonyms / MeSH", ""])
        terms = [*(f"Synonym: {term}" for term in topic.synonyms), *(f"MeSH: {term}" for term in topic.mesh)]
        lines.extend(f"- {term}" for term in terms)
        if not terms:
            lines.append("- UNKNOWN — no reviewed aliases supplied.")
        lines.extend(["", "## Clinical questions and population", "",
            "- Engineering navigation only; missing fields remain UNKNOWN.", "",
            "## Evidence-backed fixture excerpts", ""])
        for item in evidence:
            available = span_by_evidence.get(item.id, [])
            if available:
                span = available[0]
                lines.append(f"- {span.text} [Evidence: {item.id}] [Span: {span.span_id}]")
        for heading, types in SECTIONS:
            lines.extend(["", f"## {heading}", ""])
            matches = [item for item in evidence if item.source_type in types]
            lines.extend(f"- {item.title} [Evidence: {item.id}]" for item in matches)
            if not matches:
                lines.append("- None in current corpus.")
        lines.extend(["", "## Conflicts and uncertainty", "",
            "- Synthetic fixtures cannot establish clinical agreement or conflict.", "", "## Provenance", "",
            f"- corpus version: `{manifest.corpus_version}`", f"- index version: `{manifest.index_version}`",
            f"- generation/builder version: `{self.identifier}`", "- review status: `MOCK / UNREVIEWED`", ""])
        return WikiPage(slug=topic.slug, title=topic.title, content="\n".join(lines))


def build_wiki(output: str | Path, evidence: list[Evidence], spans: list[EvidenceSpan],
               manifest: IndexManifest, topics: Sequence[WikiTopicConfig],
               generator: WikiGenerator) -> tuple[list[Path], list[WikiLexicalDocument]]:
    root = Path(output); root.mkdir(parents=True, exist_ok=True)
    bundle = generator.generate(evidence=evidence, spans=spans, manifest=manifest, topics=topics)
    validate_wiki_pages(bundle.pages, evidence, spans)
    paths: list[Path] = []
    for page in bundle.pages:
        path = root / f"{page.slug}.md"
        path.write_text(page.content, encoding="utf-8", newline="\n")
        paths.append(path)
    return paths, bundle.lexical_documents
