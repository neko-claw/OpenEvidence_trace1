# A4 Contract Integration — Review Compliance Matrix

Branch: `fix/a4-contract-integration` (based on `origin/main` a68ef8f)
Base commit for A4 integration: `15c4f9b` (A4 branch fixes) incrementally ported.

## DoD items

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | 基于 clean main 的新分支，增量移植 A4 实现与 15c4f9bd | PASS | 分支从 origin/main 创建；main 的 a5/、README、AGENTS、pixi.toml、config/*.yaml 零 diff；pyproject 仅 +`retrieval*`,`scripts*` |
| 2 | 不覆盖/复制 main 的 A5 public contracts | PASS | `a5/domain/models.py`、`a5/ports/*` 未改动；A4 无任何同名的自建 Question/SearchPlan/RetrievalRequest/RetrievalResult |
| 3 | 真实 A5 Adapter 契约测试 | PASS | `a5/adapters/a4_evidence_retriever.py` 实现三参数 `retrieve(question, plan, request) -> a5.domain.models.RetrievalResult`；`tests/test_a4_adapter.py` 含 `isinstance(adapter, EvidenceRetriever)`、source_type 过滤、tool_call_index、不升级、EvidenceRecord 映射 |
| 4 | 合成医学 fixture 与正式来源彻底隔离 | PASS | `data/dev/*` 全部 `mock=true` + `MOCK-A4-*` ID，无 PMID/DOI/NCT/URL/指南编号/虚构作者；`tests/test_dev_eval.py::test_mock_fixtures_never_contain_fabricated_identifiers` 扫描 |
| 5 | span proxy 不再冒充正式 span evaluation | PASS | chunk 级指标命名为 `span_proxy_*`/`claim_chunk_coverage_at_k`；A3 v0.2 落地后：adapter 通过可选 `span_provider`（chunk_id -> a3 EvidenceSpan）映射真实 span（span_id/text/chunk_id/page/section），`span_status=A3_AVAILABLE`；无 provider 时 `UNKNOWN_A3_PENDING`；`evaluation.span_recall_at_k`/`span_ndcg_at_k` 为真实 A3 span 粒度；不合成 span ID |
| 6 | token overlap 不再冒充医学支持验证 | PASS | `RetrievalAlignmentHint`（ALIGNED/BACKGROUND/MISMATCH/INSUFFICIENT/UNKNOWN，method=token_overlap_heuristic + threshold_version）；仅进 diagnostics；`tests/test_a4_adapter.py::test_alignment_hints_never_become_verification_supported` 用 A5 RuleBasedClaimVerifier 证明不产生 SUPPORTED |
| 7 | A3 provenance/hash 保持可追溯 | PASS | `content_hash`/`evidence_content_hash` 保留调用方值不覆盖；`content_hash_mismatch` 显式标记；`chunk_policy_version`/`embedding_model`/`embedding_revision` 保留；round-trip 与 mismatch 测试 |
| 8 | smoke 指标不标记 formal/human gold | PASS | qrels 键为 `synthetic_smoke_qrels`/`span_proxy_qrels`；报告标题与声明改为 Smoke；README/data/dev 声明 pending A1/B2/A3 |
| 9 | 结构化 status/reason code + 版本化配置 | PASS | `ReasonCode` 枚举 + `SearchResult.degradation_codes`；阈值（low_top_rerank_score/default_as_of_date/citation_id_rule/alignment 阈值）移入 `config/retrieval-p0-v1.yaml`；`config_io` 严格解析、`config_matches_yaml` 防漂移；adapter diagnostics 含 config snapshot+hash、run_hash、版本 |
| 10 | out_of_scope 防御性交接 | PASS | A4 返回 empty + `out_of_scope` reason code + warning；A5 Gate0 负责正式拦截（INTEGRATION.md 记录） |

## 测试矩阵（评审要求）

| Required test | File |
|---|---|
| adapter 符合 main 的 a5.ports.EvidenceRetriever | tests/test_a4_adapter.py::test_adapter_satisfies_real_evidence_retriever_protocol |
| retrieve(question, plan, request) 三参数真实执行 | test_retrieve_uses_three_parameter_signature_and_returns_a5_result |
| request.source_type 限制本次调用来源 | test_request_source_type_limits_this_tool_call |
| tool_call_index 进入 diagnostics | test_tool_call_index_enters_diagnostics |
| partial/empty/failed 不被升级 | test_partial_empty_failed_are_never_upgraded |
| selected chunk 正确转为 A5 EvidenceRecord | test_selected_chunks_map_to_evidence_records |
| 缺 span 保持空/UNKNOWN，不合成 ID | test_spans_stay_empty_and_never_synthesized |
| 上游 content hash round-trip 不被覆盖 | test_upstream_content_hash_is_preserved_not_overwritten + tests/test_store.py |
| mock fixture 不含 PMID/DOI/NCT/URL/指南编号 | tests/test_dev_eval.py::test_mock_fixtures_never_contain_fabricated_identifiers |
| mock qrels/metrics 不标记 formal/human gold | test_mock_runs_are_not_marked_formal |
| token overlap 永不产生 A5 SUPPORTED | test_alignment_hints_never_become_verification_supported |
| YAML/运行 config snapshot 一致且阈值真实生效 | tests/test_config_io.py（round-trip/未知键/漂移）+ adapter config_snapshot/config_hash |

## 命令结果

- `python -m pytest -q`：全量通过（main 30+ 遗留测试 + A4 测试 + 新增契约测试）
- `python main.py`（等价 pixi run demo）：PASS/REFUSE 控制流完整，demo_trace artifacts 生成
- 合并 origin/main（含 A3 v0.2 提交 604d4ee 等）后全量 pytest 再次通过
- 本机未安装 pixi（无 pixi.toml 环境），以 `python -m pytest` 与 `python main.py` 执行等价命令；CI 可运行 `pixi run test` / `pixi run demo` 复核

## 仍待上游（P1，不阻塞 Adapter/Mock/contract tests）

- A1：正式 question type、freshness/source policy、冻结 dev/test split、正式范围门禁（Gate0 数据）
- A2：真实 Evidence/MCP Schema、合法来源 fixture
- A3：~~真实 Chunk/Span/PICO/hash/index manifest~~ **LANDED**（contracts/a3/v0.2，2026-08-11）；A4 adapter 已接入 span provider；剩余：A3 正式 BM25/向量索引接入 A4 双路召回（当前 dev 用 hash 占位向量）
- B2：人工 qrels 与 adjudication（当前 synthetic_smoke_qrels）
- A5：最终 Gate2/Gate5 语义（A4 alignment hints 仅 diagnostics）
