---
name: citation_audit
version: 0.2.0
input_schema: CitationAuditInput
output_schema: CitationAuditOutput
---

Split candidate statements into atomic claims before verification. For every
claim, audit citation validity, citation coverage, span alignment, PICO/time
consistency, conflicts, textual support, and uncertainty. Evidence and span IDs
must come from the current retrieval whitelist. Missing entailment or metadata
is INSUFFICIENT/UNKNOWN, never implicit support. Do not generate PMID, DOI, NCT,
URL, or conceal missing fields.
