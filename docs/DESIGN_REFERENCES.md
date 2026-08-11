# Design references

These sources informed architecture only. Their retrieval stacks, models, and
benchmarks are not copied into this MVP.

- [FActScore paper](https://arxiv.org/abs/2305.14251) motivates splitting an
  answer into atomic, individually checkable facts. It also warns that factual
  precision alone does not measure coverage and should be considered alongside
  abstention and fact counts. A5 therefore generates `Claim[]` before prose and
  records refusals and claim counts in `AgentRun`.
- [ALCE paper](https://arxiv.org/abs/2305.14627) and
  [official GitHub repository](https://github.com/princeton-nlp/ALCE) separate
  answer correctness from citation quality. A5 likewise separates Claim
  generation, evidence-ID validity, support verification, and final rendering.
- [RAGChecker paper](https://arxiv.org/abs/2408.08067) and
  [official GitHub repository](https://github.com/amazon-science/RAGChecker)
  use claim-level entailment and diagnose retrieval/generation separately. A5
  keeps retriever, generator, and verifier behind independent Protocols and
  emits stage-specific traces.

The current rule verifier does not reproduce entailment models from these
projects. Semantic and medical validation remain explicit future adapters.
