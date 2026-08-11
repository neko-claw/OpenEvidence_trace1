# A3 compatibility contract v0.3

This provisional downstream bundle extends v0.2 with typed SearchHit provenance
and a non-contradictory requested/runtime IndexManifest. It remains an A3
compatibility contract, not A2's final Evidence schema.

The fixture is deterministic, `mock=true`, and contains no PMID, DOI, NCT,
URL, or guideline identity. Regenerate schemas with
`python -m a3.contracts.export`.
