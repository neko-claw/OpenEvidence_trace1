from __future__ import annotations

import re
from collections.abc import Sequence

from a3.domain.models import Evidence, EvidenceSpan
from a3.wiki.generator import WikiPage

_EVIDENCE = re.compile(r"\[Evidence: ([^\]]+)\]")
_SPAN = re.compile(r"\[Span: ([^\]]+)\]")
_LINK = re.compile(r"\[[^\]]+\]\(([^)#]+\.md)(?:#[^)]+)?\)")


def validate_wiki_pages(pages: Sequence[WikiPage], evidence: Sequence[Evidence],
                        spans: Sequence[EvidenceSpan]) -> dict[str, set[str]]:
    evidence_ids = {item.id for item in evidence}
    span_to_evidence = {span.span_id: span.evidence_id for span in spans}
    page_slugs = {page.slug for page in pages}
    if len(page_slugs) != len(pages):
        raise ValueError("duplicate Wiki page slug")
    graph: dict[str, set[str]] = {page.slug: set() for page in pages}
    for page in pages:
        cited_evidence = set(_EVIDENCE.findall(page.content))
        cited_spans = set(_SPAN.findall(page.content))
        unknown_evidence = cited_evidence - evidence_ids
        unknown_spans = cited_spans - set(span_to_evidence)
        if unknown_evidence or unknown_spans:
            raise ValueError(f"Wiki citation outside current corpus whitelist: evidence={unknown_evidence}, spans={unknown_spans}")
        for line in page.content.splitlines():
            line_evidence = _EVIDENCE.findall(line)
            line_spans = _SPAN.findall(line)
            if line_spans and (len(line_evidence) != 1 or any(span_to_evidence[item] != line_evidence[0] for item in line_spans)):
                raise ValueError("Wiki Span must belong to the Evidence cited on the same entry")
        raw_links = _LINK.findall(page.content)
        targets = [target[:-3] for target in raw_links]
        if len(targets) != len(set(targets)):
            raise ValueError(f"duplicate Wiki link in {page.slug}")
        unknown_targets = set(targets) - page_slugs
        if unknown_targets:
            raise ValueError(f"unknown Wiki link target in {page.slug}: {sorted(unknown_targets)}")
        graph[page.slug].update(targets)
    _reject_cycles(graph)
    return graph


def _reject_cycles(graph: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f"cyclic Wiki link graph at {node}")
        if node in visited:
            return
        visiting.add(node)
        for target in graph[node]:
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
