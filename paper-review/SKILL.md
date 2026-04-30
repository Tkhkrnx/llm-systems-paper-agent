---
name: paper-review
description: 论文严格审稿：结合原文 PDF、MinerU Markdown、正式分析笔记与审稿模板，生成面向体系结构/系统顶会的严格专业审稿意见与分数。
allowed-tools: Read, Write, Bash, WebFetch
---

# 目标

基于已经入库的论文资产，生成一份符合顶会审稿视角的严格审稿意见。

`paper-review` 必须优先复用已有工作流，而不是重复实现：

1. 先用 `paper-search` 查找论文是否已经有 PDF、MinerU Markdown、正式分析笔记；
2. 若资产不完整，先调用 `paper-ingest`；
3. 若正式分析笔记不存在或过于陈旧，调用 `paper-analyze`；
4. 然后再由本 skill 生成审稿意见。

如果用户只给出论文标题、PDF 或 arXiv ID，本 skill 不应直接空写 review，而应先补齐资产链路。

# 输入

优先支持：

- `ingest_manifest.json`
- 正式论文笔记路径
- 本地 PDF 路径
- arXiv ID / 论文标题

如果用户显式给出审稿模板 PDF，也应读取模板内容并尽量贴合模板字段。当前默认模板参考：

- `C:/Users/peng/Documents/PHR/Intellistream/审稿模板.pdf`

# 核心原则

## 审稿立场

- 默认站在**严格的体系结构 / 系统顶会审稿专家**视角。
- 标准参考 `ASPLOS / MICRO / HPCA / ISCA / SC / PPoPP / OSDI / SOSP / NSDI / EuroSys / ATC / MLSys` 等 venue 的常见要求。
- 不能因为论文“方向热门”或“idea 看起来合理”就放松标准。
- 论文如果缺少关键证据、对比、消融、系统代价分析、部署合理性分析，必须明确指出。

## 证据要求

- 所有核心正反面判断都要尽量首先落在论文原文、MinerU Markdown中的事实证据上；正式分析笔记只作为辅助整理材料，而不是主裁决依据。
- 分数、Recommended Action、Technical Soundness 这类裁决性判断必须优先依据英文原文 / MinerU Markdown；分析笔记不能把缺失证据“补成已满足”。
- 不允许写“感觉不错”“似乎有意义”这种漂浮判断。
- 若证据不足，要明确写出“当前论文没有提供足够证据支持这一点”。
- 可以做合理推断，但必须让读者看得出哪些是原文事实，哪些是基于事实的审稿判断。

## 输出风格

- 全文用中文。
- 语气专业、严格、克制，不空泛恭维。
- 强项要讲清楚“强在哪里”，弱点要讲清楚“为什么这是决定性问题”。
- 默认优先从原文 claim、方法、图表、实验与局限展开审稿，而不是把正式笔记直接改写成 review。
- 避免明显 AI 话术和模板句式。不要使用“不是……而是……”“特别盯”“我最担心”“正式笔记里已经指出”“现有材料显示”“当前材料显示”等表达。
- 不要在审稿正文里提“分析笔记怎么说”。分析笔记只能帮助定位问题，review 里的判断必须直接指向论文、实验、图表、claim 或缺失证据。
- 不要写“这篇论文很有意思”“方向很重要所以值得关注”这类弱判断。若提强项，必须说明它怎样支撑接收；若提弱点，必须说明它怎样影响 soundness、generalizability 或 reproducibility。
- 每一条批评都应当是顶会审稿中可被作者回应、可被 PC 讨论、可影响最终决定的问题；避免泛泛评价和读书笔记式复述。
- 审稿意见要直指论文核心问题。每一段都应服务于接收判断、rebuttal 问题、技术 soundness、实验边界或可复现性，不写泛泛的过渡句。
- 不要把判断交还给读者。禁止写“审稿时仍需核对”“需要人工复核”“读者应该关注”“若要达到某会议标准应当覆盖”等指导性话术。review 必须直接下结论：当前证据支持什么、不支持什么、因此给什么分数和 action。
- 强项不能写成“原文触及了某维度”。必须说明该强项最多支撑 relevance、importance、originality 还是 soundness；如果不足以支撑接收，要直接说明不足以支撑接收。

## 严谨话术约束

- 使用直接、可验证的审稿语言，例如“该结论需要同预算强基线支撑”“该设置无法排除实现差异带来的收益”“端到端代价尚未与收益放在同一框架评估”。
- 少用修辞，多写判断条件、证据缺口和后果。
- 避免将弱点写成“建议作者补充”。如果该问题影响接收，应明确写出它为什么影响接收判断。
- 避免将 rebuttal 问题写成宽泛请求。每个 rebuttal 问题必须能决定分数是否上调或维持。
- 分数解释必须和正文缺陷一致。若正文指出 baseline 公平性、系统代价或 claim-over-evidence 存在关键缺口，`Technical Soundness` 不能高于 `3/5`，`Recommended Action` 默认不能高于 `Borderline`。

## 细化审稿检查项

生成 review 时，必须显式检查并尽量在正文中回应以下问题：

- 方法结构是否合理：问题定义、核心假设、方法组件、执行路径和最终 claim 是否闭合；
- 方法组件是否必要：每个组件是否有清楚作用、消融或替代设计对比，是否存在堆组件但贡献不清的问题；
- baseline 是否足够强，且是否真正公平；
- budget / 精度 / 资源约束是否对齐；
- 实验设计是否全面：质量、容量、延迟、吞吐、可扩展性、失败区间、跨模型/任务/上下文长度是否覆盖；
- claim 是否超过了证据本身能支撑的范围；
- 系统代价是否被完整披露，而不是只讲收益；
- deployment realism 是否充分，例如在线路径、批处理、多租户、尾延迟、工程集成约束；
- artifact / reproducibility 风险是否单独交代；
- 是否存在“方向重要，但稿件成熟度还不够”的情况。

# 默认输出结构

生成的审稿意见应尽量贴合模板，默认包含以下部分：

1. `## Summary and High Level Discussion`
2. `## Strengths`
3. `## Weaknesses`
4. `## Comments for Rebuttal`
5. `## Detailed Comments for Authors`
6. `## Scored Review Questions`
7. `## Reproducibility`
8. `## Confidential Comments to the Program Committee`

其中必须额外包含 `## Multi-Angle Technical Assessment`，从以下角度逐项给出结论：

- 方法结构合理性；
- 核心技术假设；
- 组件必要性与消融；
- 实验合理性；
- baseline 与预算公平性；
- 系统代价和部署真实性；
- claim 与证据是否匹配；
- artifact / reproducibility。

每一项都要直接下判断：支持、部分支持或不支持，并说明影响接收判断的原因。

## Strengths / Weaknesses 要求

- `Strengths` 只写真正能支撑接收判断的优点。
- `Weaknesses` 优先写决定性弱点，而不是零碎小建议。
- `Weaknesses` 必须同时覆盖两层：一层是 baseline 公平性、实验设计、系统代价、artifact/reproducibility 等全面检查；另一层是能决定接收判断的系统性核心局限，例如 runtime cost 如何破坏 serving claim、方法产生的状态对象是否能进入生产 runtime 管理闭环、关键模型/架构假设是否具备跨模型泛化证据。
- 不要把核心局限写成 checklist 标签。每条决定性 weakness 都要写成因果链：原文证据或图表信号 -> 方法/系统机制原因 -> 对 deployment、soundness、generalization 或 reproducibility 的后果 -> 对接收判断的影响。
- 每条 weakness 尽量包含：
  - 问题是什么；
  - 为什么这是关键问题；
  - 论文目前缺了什么证据；
  - 这如何影响接收判断。

## Comments for Rebuttal 要求

这里要明确写出作者 rebuttal 最该回答的 1-2 个关键问题。  
这些问题必须是明确、可操作、且足以影响最终决定的。

## Scored Review Questions 要求

默认至少给出以下字段，并附 1-2 句话解释分数理由：

- `Relevance`
- `Technical Soundness`
- `Technical Importance`
- `Originality`
- `Quality of Presentation`
- `Recommended Action`
- `Confidence`
- `Expertise`
- `Best Paper Award`

分数与文字必须一致。  
如果正文已经指出核心技术证据不足、baseline 不充分、claim 站不住，那 `Technical Soundness` 和 `Recommended Action` 不能还给高分。

## Recommended Action 标尺

- `Strong Reject`
- `Reject`
- `Weak Reject`
- `Borderline`
- `Weak Accept`
- `Accept`
- `Strong Accept`

默认偏严格；除非论文在问题重要性、设计完整性和证据力度上都明显过关，否则不要轻易给 `Weak Accept` 以上。

# 工作流程

1. 用 `paper-search` 查找已有论文资产与正式笔记。
2. 若没有完整资产，调用 `paper-ingest`。
3. 若没有正式分析笔记，调用 `paper-analyze`。
4. 读取：
   - PDF 路径
   - MinerU Markdown
   - 正式分析笔记
   - `assets.md`
   - `ingest_manifest.json`
5. 若用户给了模板 PDF，则按模板字段组织输出；否则使用默认模板结构。
6. 生成一份审稿 Markdown。
7. 将审稿结果保存到 Obsidian，默认放在正式笔记旁边，命名为 `<paper-note-stem>.review.md`。

# 规则

- 不得只根据中文翻译版做审稿，必须以英文原文和正式分析笔记为主。
- 不覆盖用户已有手写 review，除非用户明确要求覆盖。
- 缺证据时要明说，不要脑补。
- 默认不因为“论文方向跟用户研究方向相关”而放松标准。

# 与其他 skill 的关系

- 依赖 `paper-search` 做资产定位；
- 必要时调用 `paper-ingest` 补全原始资产；
- 依赖 `paper-analyze` 提供结构化分析笔记；
- 不依赖 `paper-translate` 作为主证据，但可把中文版 Markdown 作为人工辅助阅读材料。
