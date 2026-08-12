# OpenEvidence 赛道一 MVP —— A4 检索与重排（核心）+ A3 证据库 + A5 可信生成

赛道一的离线工程 MVP。本仓库以 **A4 临床证据检索与重排** 为主，A3（版本化证据库/wiki）作为上游数据源，A5（可信生成控制层）作为下游消费方，通过适配器桥接。

本仓库是**离线工程 MVP**，不是临床系统，不采集远程资料、不生成医学结论、不把检索分数当作医疗建议。

## 目录结构

```text
retrieval/    A4 核心：双路召回、融合、重排、SQLite 证据库、门禁、评测（约 5.2k 行）
a3/           A3：版本化证据库、索引、wiki 生成（上游数据源）
a5/           A5：有限状态可信生成控制层（下游消费方，含 A4 适配器）
config/       运行配置与 A4 冻结配置 retrieval-p0-v1.yaml
data/dev/     A4 开发集：8 题 + 28 chunk + 双粒度 qrels（合成 smoke fixture）
scripts/      开发集评测 / 向量构建 / 报告生成
contracts/    A3 v0.2 契约（Chunk / Evidence / EvidenceSpan / IndexManifest）
tests/        380 个测试（A4 pipeline、A5 工作流、A3 存储、适配器契约）
docs/         设计规格、实施计划、评审合规矩阵
artifacts/    demo trace 与评测产物（freeze.json / ablation.csv / 验收报告）
```

## A4 检索与重排管线

```text
查询理解(QueryPlan: PICO/原子主张/中英检索词)
  -> 双路召回: BM25(词汇) + 向量(dense)
  -> RRF 融合(候选池 Top-80)
  -> 十项可解释特征重排(语义/词汇/PICO/证据级别/时效/来源可信度/MMR 去冗余)
  -> Gate1 来源门禁(可引用性认证)
  -> 支持性预检 + 冲突检测
  -> 自适应 K 选择(Top-8) -> A5 消费
```

- **双路召回**：确定性、零外部依赖的 BM25（`retrieval/bm25.py`）+ 向量检索（`retrieval/vector.py`、`retrieval/bge_m3.py` 本地 BGE-M3 集成），RRF 融合（`retrieval/fusion.py`）。
- **可解释重排**：十项特征加权 + MMR 去冗余（证据类型多样性 bonus），每项得分可溯源（`retrieval/rerank.py`）。
- **证据库**：SQLite 存储，content-hash 去重、tombstone、版本表、增量 upsert、metadata 过滤（`retrieval/store.py`）。
- **查询理解**：规则式 QueryPlan，解析 PICO、原子主张与中英文检索词（`retrieval/query_plan.py`）。
- **安全与门禁**：Gate1 来源门禁（`retrieval/gate.py`）校验 chunk 的可引用字段（稳定 ID、来源类型、日期或指南版本、URL、抓取时间、content hash），失败即拒绝，不参与打分。
- **自适应 K 与预算**：按证据充分度动态收敛，受预算上限保护（`retrieval/adaptive.py`）。
- **消融与调参**：R0–R3 消融、K 网格调参、配置冻结（`retrieval/ablation.py`、`retrieval/tuning.py`）。

## 配置与版本化

- `config/retrieval-p0-v1.yaml`：A4 冻结配置（`index_version=idx-20260811-v1`、`corpus_version=corpus-20260811-v1`、冻结 K：k0=80 / k1=25 / k2=8、特征权重、来源质量表、对齐阈值等）。由 `retrieval/config_io.py` 严格解析，`config_matches_yaml` 防漂移。
- 所有阈值与版本号落在 `config/`，运行时的 config snapshot 与 hash 写入每次评测与调用的 diagnostics。

## 开发集与评测（smoke，非正式）

`data/dev/` 是 pipeline smoke 数据：**全部 `mock=true`**，ID 为 `MOCK-A4-E001..E028`，不含伪造 PMID/DOI/NCT/URL/指南编号/虚构作者；正式 qrels 依赖 A1/B2 人工冻结标注（pending）。

冻结配置在开发集上的逐题结果（均值）：

| 指标 | 值 |
|---|---|
| Recall@50（融合候选池） | **1.000** |
| nDCG@8（重排输入） | 0.750（逐题 0.443–0.981） |
| span proxy Recall@8 / 主张覆盖@8 | 1.000 / 1.000 |
| 消融对照 | R0/R1 保持，R3（去掉部分特征）Recall 降至 0.417 |

> 以上均为 MOCK 合成 fixture 上的 smoke/proxy 指标，**不是**正式检索质量或临床效果声明。正式评测待 A1/A2/A3/B2 上游契约落地。

## 与 A3 / A5 的集成

- **A3（上游）**：`contracts/a3/v0.2/` 定义 Chunk / Evidence / EvidenceSpan / IndexManifest 契约；A4 消费 A3 数据并接入真实 A3 span（`span_status=A3_AVAILABLE`）。
- **A5（下游）**：`retrieval/ports.py` 只定义 A4 自己的端口；`a5/adapters/a4_evidence_retriever.py` 实现 A5 的 `EvidenceRetriever` 三参数契约（`retrieve(question, plan, request) -> a5.domain.models.RetrievalResult`），把 A4 的 diagnostics（reason codes、config hash、tool_call_index 等）映射进 A5 的 `RetrievalResult.diagnostics`。
- A4 不覆盖 A5 公共契约（`a5/domain/models.py`、`a5/ports/*` 未改动），集成方式详见 `INTEGRATION.md` 与 `docs/a4_review_compliance.md`。

## 运行与验证

```powershell
pixi run test          # 380 个测试全量回归
pixi run demo          # A5 demo：PASS/WARN/REFUSE 控制流，写入 artifacts/demo_trace.*
python -m scripts.run_dev_eval   # A4 开发集评测，产出 freeze.json / ablation.csv / 报告
```

## 边界与合规

- Mock fixture 永不冒充医学证据；token 重叠启发式仅进 diagnostics，不产生 A5 的 SUPPORTED 结论。
- Gate0/Gate6 fail-closed：UNKNOWN 不静默变成 ALLOW/SUPPORTED。
- 详细合规矩阵见 `docs/a4_review_compliance.md`；A5 集成契约见 `INTEGRATION.md`；设计文档见 `docs/superpowers/specs/2026-08-11-a4-retrieval-rerank-design.md`。
