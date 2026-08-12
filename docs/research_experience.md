# 面向使用的公开证据研究链路

## 目标

本地产品入口不再根据预设场景返回固定答案。每个用户问题都会经过：

```text
问题 → A1 Gate0 → A5 规划/预算 → A2 公开来源 → A3 Evidence/Span
     → A4 检索与排序 → A5 Gate2 → 原子主张 → Gate5 → Gate6 → A6
```

当前范围限定为心血管病、脑血管病、高血压、血脂异常与糖尿病。系统面向
临床医生、医学生与科研人员，目标是生成带引用的直接回答，而不是把检索结果
堆叠为证据列表。仅供教学研究，不用于临床诊疗。

## 方法原型

- Gate2 采用 CRAG 的“先评估检索质量，再继续、纠正或停止”控制流，而非检索到内容就生成。
- 原子主张采用 FActScore 的细粒度事实拆分思想；无模型降级路径只选择完整句子，不把 `and/before/after` 机械切成短语。
- exact-span 只能证明句子来自原文；无模型路径还执行意图相关性检查，排除研究背景、目的与方法，并对比较题要求比较双方和结果表达。
- 引用审计采用 ALCE 的 citation validity / support / coverage 思路：引用必须来自本轮 Evidence 白名单，并能定位到 Span。
- Trace 区分 retrieval insufficient、illegal citation、missing span 等原因，避免把检索失败与生成失败混为一谈。

相关资料：

- CRAG: <https://arxiv.org/abs/2401.15884>
- FActScore: <https://arxiv.org/abs/2305.14251>；<https://github.com/shmsw25/FActScore>
- ALCE: <https://arxiv.org/abs/2305.14627>；<https://github.com/princeton-nlp/ALCE>
- RAGChecker: <https://arxiv.org/abs/2408.08067>
- Ollama structured outputs: <https://docs.ollama.com/capabilities/structured-outputs>

## 可信边界

- `research` 的 A4 分数是 query-local ranking，只用于该问题内候选排序，不冒充跨问题可比较的临床质量概率。
- 本地 HashingEmbeddingProvider 是可复现的候选召回实现，不是医学训练模型，也不替代 A3 最终 embedding 验收。
- 无结构化模型时，Claim 必须逐字出现在引用 Span 中；无法可靠验证的改写会是 INSUFFICIENT。
- 安全范围不清、证据不足、关键主张未知/高不确定、非法引用或关键冲突均不能静默 PASS。

## 可选本地模型与准入

`config/research_profile.json` 配置 Ollama endpoint 与模型。服务启动时只在模型确实存在时启用结构化生成；否则自动进入精确片段降级。下载模型不是运行公开检索与严格引用链路的前置条件。

Gate5 后可选的中文展示模型与 Claim 生成/验证完全隔离。展示模型必须同时通过
术语、数字、效应方向和外部引用约束；失败时回退至已核验英文原句。实际基准中
Qwen2.5-0.5B-Instruct 将 DOAC 错译为药名，因此被拒绝接入。此策略借鉴术语约束
机器翻译的做法，避免小模型输出“看起来流畅但医学错误”的中文文本。

- MarianMT: <https://github.com/huggingface/transformers/blob/main/docs/source/en/model_doc/marian.md>
- Terminology-constrained APE: <https://aclanthology.org/2020.wmt-1.141/>

## 验证

```powershell
pixi run test
pixi run demo
pixi run app
```

完整测试必须通过；`pixi run demo` 是版本化测试 fixture 回归，不是用户入口。普通页面默认使用 `research`。
