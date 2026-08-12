# A2 frozen integration contract v1

Runtime source of truth:

- `a2.models.evidence.A2Evidence`
- `a2.models.tool_response.ToolResponse`

`schemas/` is generated from those Pydantic models by `python -m a2.export_schemas`.
`fixtures/` contains explicit offline mock records only. They are not medical
evidence and intentionally contain no PMID, DOI, NCT, URL, or guideline ID.

The A2→A3 boundary is `a2.adapters.A2ToA3Normalizer`. It preserves A2 hash and
source metadata as provenance but does not synthesize A3 chunks, spans, PICO,
evidence level, trust status, or semantic support.
