# A6 产品体验层

应用界面使用简体中文。`PASS/WARN/REFUSE`、Evidence ID 和版本字段等 A5 稳定契约值不会被翻译或重写。

A6 是 A5 `AgentRun` 公共契约的 Streamlit Viewer。它不分类问题、不调用 MCP、不检索或 rerank、不生成 Claim、不审计引用，也不决定 `PASS/WARN/REFUSE`。

## 架构

```text
用户 → A6 UI → app/services/agent_service.py
                    ↓
       deployment.track1_backend.BackendService
                    ↓
             A5 answer() → AgentRun
                    ↓
             展示模型与页面组件
```

只有 `app/services/agent_service.py` 可以导入 A5 或 A1–A5 部署门面。其他 A6 模块不导入 A1、A2、A3、A4、A5、检索模块或部署模块。服务层只把 A5 的 `AgentRun` 和安全的 `AgentRunView` 投影成不可变 A6 数据类，不复制 Agent 决策。

## 运行

```powershell
pixi install --locked
pixi run app
```

也可在已激活环境中执行：`streamlit run app/main.py`。

## 默认运行模式

本地应用默认使用 `research` 组合：用户问题经 A1 范围与安全检查后，由 A5 规划并调用 A2 公开来源工具，经 A3 证据/span 结构与 A4 检索排序后，执行 Gate2、原子主张生成、Gate5 引用审计和 Gate6 发布。当前公开来源包括 PubMed、Europe PMC 与 ClinicalTrials.gov；指南专用连接器只消费审核过的本地 manifest，不会临时抓取未知来源。

无本地结构化生成模型时，系统使用“逐字支持片段抽取 + 回答相关性过滤”作为
保守降级：背景、研究目的和方法不作为答案。可选中文展示模型只在 Gate5 后
运行，且必须通过术语、数字、方向与引用约束；否则展示经核验英文原句。若
Ollama 与配置模型可用，会自动启用结构化 Claim 生成和独立 Gate5 检查；
Evidence ID 与 Span ID 白名单始终由代码强制执行。`live` 模式仍要求显式注入
经批准的生产依赖并保持 fail-closed。

自动化测试可设置 `OPENEVIDENCE_APP_MODE=replay` 使用版本化 A5 fixture；该入口不在页面显示。测试记录会标注“测试数据”，不会带伪造医学标识。

## 状态与缓存

Session State 保存当前问题、当前 AgentRun 投影、历史记录、选中证据、分页与 UI 错误。A6 只用 `st.cache_resource` 缓存无状态后端服务对象，只用 `st.cache_data` 缓存本地 Wiki 导航数据；最终答案和 AgentRun 永不缓存。

## 测试

执行 `pixi run a6-test`。AppTest 覆盖启动、真实问题入口、PASS、WARN、REFUSE、安全错误、Evidence、分页、Wiki、测试数据标识、空 Evidence、长文本、上游导入边界和投影契约。

## Streaming 兼容性

当前 Trace 只在 A5 返回最终 AgentRun 后展示。时间线消费展示事件，未来可以在不把控制逻辑移入 A6 的前提下替换为 A5 event-stream adapter。界面不会伪造实时进度。
