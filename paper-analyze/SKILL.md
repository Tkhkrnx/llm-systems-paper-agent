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

如果用户希望先获得中文版论文材料，可以在 `paper-ingest` 之后先调用 `paper-translate`。但 `paper-analyze` 必须始终以英文原始 MinerU Markdown 作为主证据；中文版 Markdown 只用于人工阅读，不参与正式证据判断。

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
- 方法整体机制总结：必须说明作者通过哪些具体组件实现方法，每个组件输入/输出是什么，组件之间如何闭合成系统路径；
- 系统架构或执行路径；
- 实验设置和关键结果；
- 图表证据链：方法框架图和实验图分别在论文论证中承担什么角色、图中指标代表什么、数据证明了什么结论；
- 与已有工作的关系；
- 对用户研究方向的价值；
- 局限和 open gap；

默认禁止生成“当前可信度 / 是否可进入正文 / 是否可进入 matrix / BibTeX 或正文”这类小节。只有当用户明确要求做综述证据筛选或 BibTeX/matrix 整理时，才额外生成对应内容。

# 输出风格硬约束

整篇笔记都必须写成“讲给课题组同学听”的教学式长段解释，而不只是导师七问如此。默认读者是具备科研训练、但不熟悉本文具体方向的研究生。

- 不要把 MinerU 原文大段粘进笔记；笔记应该是中文解释、系统化转述和研究视角分析。
- 不要写成短句提纲。除论文基本信息外，核心小节里的每个要点都应至少用一段话讲清背景、本文做法、为什么这样设计、结果意味着什么。
- 避免用“不是……而是……”“直觉很像……”这类转折套话代替解释。需要从底层逻辑逐层讲：问题为什么出现、原文具体机制是什么、该机制解决了哪一步、论文用什么实验或数字支撑、读者应该怎样理解这个结果。
- 如果出现 KV cache、prefill、decode、dense compression、eviction、paged KV、prefix caching、memory tiering 等概念，必须先用研究生能听懂的方式解释它们在本文中扮演的角色。
- 方法名、缩写、workload 类型和实验指标都必须解释清楚。比如 evidence-sensitive workload、TTFT、decode latency、end-to-end latency、BPT、matched budget、artifact、throughput、p99 latency、context-fit frontier 等，不能假设读者已经知道；解释时要说明“这个术语在本文里衡量什么、为什么会影响系统结论、读对应图表时应该怎么理解”。
- 导师七问、综述五字段、方法流程、方法整体机制总结、图表证据链、实验、局限、人工阅读重点、研究命题都要保持这种讲解口吻，不能只列关键词。
- 但凡属于“判断性内容”而不是“说明性内容”，例如局限性、open gap、与已有工作的边界、实验是否真正支持 claim、对你研究方向的可借鉴之处，都必须采用接近严格审稿的证据标准来写：判断应尽量锚定论文原文、图表、实验设置与正式结果，避免轻飘的启发式评价。
- 这不意味着整篇笔记要写成审稿意见；而是意味着笔记中的判断句必须更严谨、更克制、更有证据边界。
- 如果论文没有提供足够证据支持某个强判断，就应明确写出“现有原文证据还不足以把结论说到这一步”，而不是顺手替作者补完论证。
- 缺失信息不要输出生硬的 `TBD` 断句。无法确认的会议、年份、作者等元数据可写“待确认”；正文分析中如果证据不足，要说明“当前 MinerU 文本未提供足够证据”，并给出需要人工核对的位置。
- 图片只引用真实存在的短文件名。优先选择带语义的关键图，例如 workflow、memory、latency、breakdown、fit、overview，而不是按 MinerU 提取顺序随便选择。
- 图表部分不应写成“怎么看图”的泛泛说明，而要写成“这张方法框架图或实验图在论文论证链中证明什么”。必须解释图中指标含义、数据支撑的结论、以及该图对方法合理性、系统收益或系统代价的作用。

# 工作流程

1. 调用 `paper-search` 查找目标论文是否已有正式笔记和 MinerU 资产。
2. 如果没有 PDF 或 MinerU Markdown，先调用 `paper-ingest`。
3. 读取已有正式笔记（如果存在）、PDF 链接、MinerU Markdown、图片资产、`assets.md` 和 `ingest_manifest.json`。
4. 如果正式笔记不存在，创建它；如果已存在，基于证据补全导师七问、综述五字段和人工阅读重点。
5. 如果图片缺失，调用 `extract-paper-images`。
6. 将分析结果写回结构化笔记，保留用户已有手写内容。

# 人工阅读重点要求

论文分析完成后，必须额外输出 `## 人工阅读重点` 小节，帮助用户在读完笔记后回原文查漏补缺。该小节不是重新推荐读者从头通读全文，而是指出笔记无法完全替代原文核对的关键位置。至少包含：

- `必须回原文核对的部分`：只列出读完笔记后仍需要核对的 section / figure / table / algorithm / appendix。
- `核对目的`：说明核对这一部分是为了确认公式、实现路径、指标口径、实验设置、失败边界还是可复现细节。
- `可以暂时不细读的部分`：列出读完笔记后可暂时跳过的部分，避免浪费时间重头读。
- `查漏补缺后的判断标准`：说明读者补完原文后应该能回答哪些问题。

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
- 用户需要中文版论文材料时，可先调用 `paper-translate`。
- 必要时调用 `extract-paper-images` 补图。
