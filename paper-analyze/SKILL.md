---
name: paper-analyze
description: 论文深度分析：基于 PDF/MinerU Markdown 证据，为大模型推理系统与状态优化方向生成详细 Obsidian 笔记。
allowed-tools: Read, Write, Bash, WebFetch
---

# 目标

对单篇论文做系统层面的深度分析，生成或完善 Obsidian 论文笔记。

如果论文还没有入库，优先使用 `paper-ingest`：

- 保存 PDF；
- 使用 MinerU 转 Markdown；
- 保存图片；
- 生成 `assets.md` 和 `ingest_manifest.json`。

之后由本 skill 生成或更新正式结构化论文笔记。

`paper-analyze` 是唯一负责生成正式论文分析笔记的 skill，不负责每日推荐，也不负责会议搜索。它应该消费 `paper-ingest` 生成的 PDF、MinerU Markdown、图片资产和 manifest。

# 分析重点

每篇论文都要尽量回答以下系统问题：

- State object：论文管理、缓存、迁移、复制、更新或恢复的状态对象是什么？
- Control surface：论文暴露了哪些控制面，例如 scheduling、placement、batching、eviction、routing、replication、memory tiering、admission control？
- Coupling path：模型、runtime、系统、硬件之间如何耦合？
- Evaluation boundary：优化边界是什么，例如 throughput、p99 latency、memory footprint、recovery time、cost、quality、freshness、scalability？
- Remaining systems gap：论文仍然没有解决什么系统问题？

# 必须使用的分析框架

导师七问：

1. What is the problem?
2. Why it matters?
3. Why existing works fail?
4. What is the key idea?
5. What is the design?
6. What is the experimental plan?
7. What is the takeaway?

综述五字段：

1. State object
2. Control surface
3. Coupling path
4. Evaluation boundary
5. Remaining systems gap

# 输出要求

分析笔记应包含：

- 论文基本信息；
- PDF 和 MinerU Markdown 链接；
- 人工阅读重点：明确标注读者应优先阅读论文的哪些 section、figure、table、algorithm 或 appendix，并说明每一部分为什么值得读、预计阅读目的是什么；
- 核心问题与动机；
- 方法设计；
- 系统架构或执行路径；
- 实验设置和关键结果；
- 与已有工作的关系；
- 对用户研究方向的价值；
- 局限和 open gap；

默认不要生成“当前可信度 / 是否可进入正文”一节，除非用户明确要求做综述证据筛选。

# 输出风格硬约束

整篇笔记都必须写成“讲给课题组同学听”的教学式长段解释，而不只是导师七问如此。默认读者是具备科研训练、但不熟悉本文具体方向的研究生。

- 不要把 MinerU 原文大段粘进笔记；笔记应该是中文解释、系统化转述和研究视角分析。
- 不要写成短句提纲。除论文基本信息外，核心小节里的每个要点都应至少用一段话讲清背景、本文做法、为什么这样设计、结果意味着什么。
- 如果出现 KV cache、prefill、decode、dense compression、eviction、paged KV、prefix caching、memory tiering 等概念，必须先用研究生能听懂的方式解释它们在本文中扮演的角色。
- 导师七问、综述五字段、方法流程、关键图、实验、局限、人工阅读重点、研究命题都要保持这种讲解口吻，不能只列关键词。
- 缺失信息不要输出生硬的 `TBD` 断句。无法确认的会议、年份、作者等元数据可写“待确认”；正文分析中如果证据不足，要说明“当前 MinerU 文本未提供足够证据”，并给出需要人工核对的位置。
- 图片只引用真实存在的短文件名。优先选择带语义的关键图，例如 workflow、memory、latency、breakdown、fit、overview，而不是按 MinerU 提取顺序随便选择。
- 每张关键图都要说明“先看哪里、图在回答什么问题、它对系统结论有什么帮助”，不能只插图。

# 工作流程

1. 调用 `paper-search` 查找目标论文是否已有正式笔记和 MinerU 资产。
2. 如果没有 PDF 或 MinerU Markdown，先调用 `paper-ingest`。
3. 读取已有正式笔记（如果存在）、PDF 链接、MinerU Markdown、图片资产、`assets.md` 和 `ingest_manifest.json`。
4. 如果正式笔记不存在，创建它；如果已存在，基于证据补全导师七问、综述五字段和人工阅读重点。
5. 如果图片缺失，调用 `extract-paper-images`。
6. 将分析结果写回结构化笔记，保留用户已有手写内容。

# 人工阅读重点要求

论文分析完成后，必须额外输出 `## 人工阅读重点` 小节，帮助用户在后续人工精读时节省时间。该小节至少包含：

- `必读部分`：列出最应该读的 section / subsection / figure / table / algorithm / appendix。
- `阅读目的`：说明读这一部分是为了理解问题定义、系统设计、关键算法、实验设置、对比结果、局限性，还是寻找可借鉴 idea。
- `可跳读部分`：列出可以快速浏览或暂时跳过的部分，并解释原因。
- `精读顺序`：给出 3-6 步的建议阅读路线。
- `与用户方向的连接`：说明这些部分和 LLM 推理系统、分层状态优化、协同优化之间的关系。

# 规则

- 优先引用 PDF 或 MinerU Markdown 中的证据。
- 抽象总结必须和论文证据分开。
- 缺失证据写 `TBD`。
- 不覆盖用户手写笔记，除非用户明确要求。
- 图片使用 `![[figure.png|800]]`。
- 论文链接使用 display alias。

# 和其他 skill 的关系

- 被 `start-my-day` 和 `conf-papers` 调用，用于补全重点论文。
- 调用 `paper-search` 找已有材料。
- 必要时调用 `paper-ingest` 入库论文。
- 必要时调用 `extract-paper-images` 补图。
