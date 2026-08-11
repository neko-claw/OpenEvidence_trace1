from __future__ import annotations

import re


def validate_wiki(text: str, evidence_ids: set[str], span_ids: set[str]) -> None:
    cited_evidence = set(re.findall(r"\[Evidence: ([^\]]+)\]", text))
    cited_spans = set(re.findall(r"\[Span: ([^\]]+)\]", text))
    unknown_evidence = cited_evidence - evidence_ids
    unknown_spans = cited_spans - span_ids
    if unknown_evidence or unknown_spans:
        raise ValueError(f"Wiki citation outside whitelist: evidence={unknown_evidence}, spans={unknown_spans}")
    if re.search(r"\[Wiki:", text, re.I):
        raise ValueError("Wiki-to-Wiki factual citations are forbidden")
