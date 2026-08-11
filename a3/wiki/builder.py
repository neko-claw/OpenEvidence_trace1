from __future__ import annotations

from pathlib import Path

from a3.domain.models import Evidence, EvidenceSpan, IndexManifest
from a3.wiki.validation import validate_wiki

SECTIONS = (("Guidelines", {"guideline_fixture", "guideline"}),
            ("Systematic reviews", {"systematic_review", "review"}),
            ("RCTs", {"rct"}), ("Clinical trials", {"trial", "clinical_trial"}))


def render_topic(topic: str, evidence: list[Evidence], spans: list[EvidenceSpan], manifest: IndexManifest) -> str:
    selected = [e for e in evidence if e.provenance.get("topic") == topic]
    span_by_evidence: dict[str, list[EvidenceSpan]] = {}
    for span in spans:
        span_by_evidence.setdefault(span.evidence_id, []).append(span)
    lines = [f"# {topic.replace('_', ' ').title()}", "", "> MOCK / OFFLINE FIXTURE — NOT MEDICAL EVIDENCE", "",
        "## Synonyms / MeSH", "", "- Not supplied by the mock fixture.", "",
        "## Clinical questions and population", "", "- Engineering navigation only; missing fields remain UNKNOWN.", "",
        "## Key evidence-backed conclusions", ""]
    for item in selected:
        available = span_by_evidence.get(item.id, [])
        if available:
            span = available[0]
            lines.append(f"- {span.text} [Evidence: {item.id}] [Span: {span.span_id}]")
    for heading, types in SECTIONS:
        lines.extend(["", f"## {heading}", ""])
        matches = [e for e in selected if e.source_type in types]
        lines.extend(f"- {e.title} [Evidence: {e.id}]" for e in matches)
        if not matches:
            lines.append("- None in current corpus.")
    lines.extend(["", "## Conflicts and uncertainty", "",
        "- These synthetic records cannot establish clinical agreement or conflict.", "",
        "## Provenance", "", f"- corpus version: `{manifest.corpus_version}`",
        f"- index version: `{manifest.index_version}`", "- data cutoff: `2026-01-01`",
        "- generated_at: `2026-01-01T00:00:00Z`", "- generation/builder version: `a3-wiki-v0.1`",
        "- review status: `MOCK / UNREVIEWED`", ""])
    return "\n".join(lines)


def build_wiki(output: str | Path, evidence: list[Evidence], spans: list[EvidenceSpan],
               manifest: IndexManifest) -> list[Path]:
    root = Path(output); root.mkdir(parents=True, exist_ok=True)
    paths = []
    for topic in ("hypertension", "dyslipidemia"):
        text = render_topic(topic, evidence, spans, manifest)
        validate_wiki(text, {e.id for e in evidence}, {s.span_id for s in spans})
        path = root / f"{topic}.md"; path.write_text(text, encoding="utf-8", newline="\n"); paths.append(path)
    return paths
