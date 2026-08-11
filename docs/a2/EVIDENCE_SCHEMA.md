# A2 Evidence Schema

`a2.models.evidence.A2Evidence` is frozen as `a2-evidence-v1` and uses Pydantic
v2 with `extra="forbid"`. It contains source identity, title/source text,
authors, publication time, traceable native identifiers, optional explicit
PICO/evidence level, fetch time, SHA-256 content hash, and source metadata.

Missing upstream values remain `None` or `[]`. A2 never infers PICO, evidence
level, retrieval score, span, page, DOI, PMID, NCT ID, URL, or guideline ID.
Connector IDs are source-native: `PMID:<pmid>`, `NCT:<nct>`,
`EPMC:<source>:<native-id>`, and
`GUIDELINE:<manifest-id>:<version>:PAGE:<page>`.

The stable content hash excludes fetch/request/cache/latency data. Canonical
deduplication is DOI, then PMID, NCT ID, guideline stable ID, then source/native
ID. Conservative merge keeps the existing non-null value, fills missing data,
and records alternatives in `source_metadata.dedup_conflicts`.
