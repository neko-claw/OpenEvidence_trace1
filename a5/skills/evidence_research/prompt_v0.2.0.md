---
name: evidence_research
version: 0.2.0
input_schema: EvidenceResearchInput
output_schema: EvidenceResearchOutput
---

Produce a bounded search plan and an evidence summary. Use only configured
source types and the given evidence IDs. Missing score, level, date, provenance,
or conflict data must be returned as UNKNOWN/null. Never invent a PMID, DOI,
NCT identifier, URL, evidence score, or medical source. Evidence insufficiency
is a valid result and must remain visible to Gate2.
