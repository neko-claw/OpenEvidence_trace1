# Design references

These sources informed control-flow and contract patterns only. No retrieval
stack, model, benchmark, or large external implementation was copied.

- [CRAG](https://arxiv.org/abs/2401.15884): evaluate retrieval quality before
  generation and select a corrective action. A5 maps this to structured Gate2
  `SUFFICIENT/INSUFFICIENT/CONFLICTED` plus `CONTINUE/RETRY/REFUSE`.
- [FActScore](https://arxiv.org/abs/2305.14251) and its
  [official repository](https://github.com/shmsw25/FActScore): split candidate
  statements into atomic facts and verify each one independently.
- [ALCE](https://arxiv.org/abs/2305.14627) and its
  [official repository](https://github.com/princeton-nlp/ALCE): distinguish
  citation validity, coverage and support. Gate5 binds every claim to the
  current Evidence/Span whitelist.
- [RAGChecker](https://arxiv.org/abs/2408.08067) and its
  [official repository](https://github.com/amazon-science/RAGChecker): diagnose
  retrieval and generation failures separately. A5 uses reason prefixes such
  as `retrieval_insufficient`, `illegal_citation`, `missing_span`,
  `pico_mismatch`, `unsupported_claim`, and `budget_exhausted`.
- [OpenAI Agents SDK guardrails](https://openai.github.io/openai-agents-python/guardrails/)
  and [tracing](https://openai.github.io/openai-agents-python/tracing/): explicit
  tripwires and structured run events. A5 keeps a lightweight internal FSM and
  trace rather than adding the SDK.
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk): tools as
  standardized boundaries. A5 defines a retriever port and leaves A2's real MCP
  implementation upstream.
- [LangGraph](https://github.com/langchain-ai/langgraph): explicit state and
  transitions. A5 uses pure Python because the required graph is small and
  bounded.
- [Pydantic](https://docs.pydantic.dev/): runtime contracts and JSON Schema.
  A5 validates fixtures with Pydantic and tests Schema root consistency.
- [Reciprocal Rank Fusion](https://research.google/pubs/reciprocal-rank-fusion-outperforms-condorcet-and-individual-rank-learning-methods/):
  rank-based fusion motivates keeping an RRF/ranking value distinct from a
  calibrated retrieval-quality probability.
- [SentenceTransformers CrossEncoder documentation](https://www.sbert.net/docs/package_reference/cross_encoder/model.html):
  output activation and range depend on the model configuration. A5 therefore
  refuses to interpret an uncalibrated CrossEncoder/rerank value as Gate2
  sufficiency or Gate5 entailment.
- [BGE-M3](https://arxiv.org/abs/2402.03216) and its
  [official implementation](https://github.com/FlagOpen/FlagEmbedding): model
  capability is not project-specific validation. A5 keeps the capability off
  until A3 supplies reproducible dev Recall@50, latency and version evidence.

`ExactSpanTextualSupportEvaluator` is deliberately limited. It does not
reproduce NLI or medical inference from any referenced project.
