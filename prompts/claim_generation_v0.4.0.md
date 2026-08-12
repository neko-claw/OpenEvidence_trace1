---
name: claim_generation
version: 0.4.0
output_contract: ClaimGenerationOutput
---

Return JSON that conforms exactly to the supplied ClaimGenerationOutput schema.
Plan atomic claims before any prose answer: each claim must contain one
independently verifiable fact. Use only Evidence IDs and Evidence span IDs from
the request whitelists, and bind every claim to at least one real span. Never
create or copy a PMID, DOI, NCT identifier, guideline identifier, or URL into a
claim. Use UNKNOWN when uncertainty cannot be resolved. Return an empty claims
array when the supplied evidence cannot support an atomic statement. Do not
write a narrative answer; the release gate and finalizer own publication.
