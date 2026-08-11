---
name: question_classification
version: 0.2.0
output_contract: EvidenceResearchOutput.question_type
---

Classify the supplied question using only the configured A1-compatible question
types. Return structured JSON. If no configured type is supported, use the
configured fallback; do not invent a medical scope or safety decision.
