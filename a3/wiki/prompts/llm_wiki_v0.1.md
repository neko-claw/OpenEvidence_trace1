# LLM Wiki structured generation prompt v0.1

Generate navigation entries only from the supplied Evidence and exact Span
whitelist. Every entry must contain one supplied `evidence_id` and one supplied
`span_id`. Do not add identifiers, clinical conclusions, recommendations, or
Wiki-to-Wiki factual support. Return JSON matching the versioned output schema.
