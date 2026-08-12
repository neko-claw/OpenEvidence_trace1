# A6 产品体验层交付与整合报告

## 已完成

- 全站采用简体中文产品文案；`PASS/WARN/REFUSE`、Evidence ID 与版本字段等稳定契约值保持原样。
- 提供 Apple 风格的浅色界面、问题分析、决策横幅、回答、局限说明、证据卡片、可读 Trace、Wiki、历史记录与分页。
- 明确显示 Demo/Mock 标识，不展示 Mock 外部医学标识。
- A6 只有 `app/services/agent_service.py` 可以进入 A1–A5 后端边界。
- 已接入 `deployment.track1_backend.BackendService`；默认由 `build_service("replay")` 组成后端，再由 A5 返回唯一事实来源 `AgentRun`。
- 保留显式依赖注入入口，供未来通过验收的 live 依赖接入；A6 不自行补齐任何上游能力。

## 架构边界证明

`tests/a6/test_agent_service.py::test_only_agent_service_imports_upstream_packages`
扫描所有 A6 模块。只有 `app/services/agent_service.py` 可导入 A5 或 A1–A5 部署门面；其余 A6 模块不导入 A1–A5、检索模块或部署模块。界面只渲染 A5 决策，不重新推断证据充分性或支持性。

## A6 未实现且不应实现

- A1 安全规则、A2 MCP 调用、A3 数据结构/存储、A4 检索与 rerank、A5 Agent 逻辑均保持在上游。
- 不猜测或自动拼装 live 模式。部署层必须显式注入经验证的依赖，并通过 readiness 检查。
- 不伪造实时流式状态；当前仅渲染完成后的 AgentRun Trace，并保留未来 streaming adapter 接口。
- Wiki 只是导航层，不直接访问 A3，也不建立第二套证据权威来源。

## 截图

截图位于 `artifacts/a6/screenshots/`：`home.png`、`answer_pass.png`、`evidence.png`、`trace.png`、`wiki.png`。

## 整合验收结果

- 原 `all_A12345_try` 快照：`534 passed, 3 skipped`。
- 接入 A6 后 `pixi run a6-test`：`23 passed`。
- 接入 A6 后 `pixi run test`：`557 passed, 3 skipped`。
- `pixi run demo`：PASS/WARN/REFUSE 全链路完成。
- `pixi run backend-demo`：PASS，返回 2 条 Evidence 与 1 条可发布 Claim。
- `pixi run a2-health`：按设计返回 `BLOCKED_EXTERNAL`，未用 Mock 冒充 live 能力。

## 就绪结论

**A1–A5 replay/mock 后端与 A6 本地产品体验：READY。**

**真实医学 live 部署：NOT READY（按 fail-closed 设计阻断）。** 当前仍需 A1 正式医学规则审批、A2 live 配置与获批指南源、A3 正式 embedding/qrels 验证、A4 校准质量分、A5 医学 Gold 验证。A6 没有用展示层逻辑掩盖这些缺口。
