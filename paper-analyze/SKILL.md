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
- 方法整体机制总结：必须说明作者通过哪些具体组件实现方法，每个阶段具体做什么、输入/输出是什么、为什么可以这样做、好处是什么、组件之间如何闭合成系统路径。不能只写“提取信号、分配预算、生成 artifact”这类大框架套话；例如论文若有 Phase 1/2/3/4/5，就要逐阶段讲清因果注意力如何用于 token importance、channel sensitivity 如何计算、allocator 如何联合分配、artifact 如何构建、decode 如何消费；
- 系统架构或执行路径；
- 分析框架图：只保留方法框架 / workflow / overview 图，并说明图中的阶段和数据流如何对应正文机制；
- 实验设置和关键结果：必须覆盖原文主要图表和实验，不要只挑部分图解释。每个图/实验都要说明它验证的问题、指标含义、关键数据、证明的结论和结论边界；
- 与已有工作的关系；
- 对用户研究方向的价值；
- 局限和 open gap；

默认禁止生成“当前可信度 / 是否可进入正文 / 是否可进入 matrix / BibTeX 或正文”这类小节。只有当用户明确要求做综述证据筛选或 BibTeX/matrix 整理时，才额外生成对应内容。

`## 论文基本信息` 必须由 `ingest_manifest.json` 确定性生成，不能交给模型自由发挥，格式固定为：

```markdown
## 论文基本信息
- **论文 ID**：...
- **作者**：...
- **年份**：...
- **会议/期刊**：...
- **PDF**：[[...|原始 PDF]]
- **MinerU Markdown**：[[...|MinerU Markdown]]
- **中文版 Markdown**：[[...|中文版 Markdown]]
- **资产索引**：[[...|assets]]
```

如果 manifest 中存在来源链接，可以在最后追加 `- **来源**：<...>`。不要写“论文标题：”“固定链接：”这类自由格式，也不要让一篇论文的作者、年份或资产路径污染到另一篇论文。

frontmatter 也必须由 manifest 确定性生成，至少包含 `paper_id`、`title`、`authors`、`year`、`venue`、`domain`、`tags`、`status`、`created`、`updated`。模型生成的 frontmatter 必须被脚本替换掉。

# 输出风格硬约束

整篇笔记都必须写成“讲给课题组同学听”的教学式长段解释，而不只是导师七问如此。默认读者是具备科研训练、了解大模型基础概念、但记得不牢且理解不深入的研究生；因此解释必须把大模型基础知识、系统背景知识和论文机制连起来，不能默认读者已经能把 attention、KV cache、量化、GPU kernel、访存瓶颈这些概念自动串通。

这套笔记的目标风格以现有高质量笔记 `Prefill-Native_Dense_KV_Cache_Compression_for_Long-Context_Large_Language_Model_Inference.md` 为参照，但要抽取的是“表达层次”和“信息组织方式”，不是照抄该论文内容。生成新笔记时，应尽量继承下面这些特征：

- `## 一句话总结` 不是泛泛摘要，而是三件事一起交代：论文在处理什么系统对象、方法链条的核心动作是什么、关键证据和代价边界分别是什么。
- `## 资产分类判断 + 原因` 要先把论文放回正确研究语境，再告诉读者为什么这个分类能帮助理解主线。不要只贴标签。
- `## 导师七问` 的每一问都采用固定三段结构：背景解释、本文做法、关键结论与意义。重点不是把七问答满，而是让每一问都能单独成立。
- `## 综述五字段` 必须回到五个固定字段本身，每个字段用一段到两段密实解释，把对象、控制面、耦合路径、评估边界和剩余系统缺口讲清楚。
- `## 方法整体机制总结` 要像 PREFILLCOMP 那样沿着完整执行链条顺下来，能让读者回答“系统到底看到了什么、在什么时候做了什么决策、这些决策如何变成后续可消费的状态或执行路径”。
- `## 实验设置和关键结果` 不是摘几张图说结论，而是先交代实验设置，再逐图说明每张图在整篇论文中的职责、支持的结论、以及结论边界。
- `## 局限性与 Open Gap` 最好分成两层：先写“论文局限”，再写“可以继续追问的系统问题”。前者贴着现有证据，后者面向后续研究。
- `## 人工阅读重点` 要指出读完笔记后还值得回原文核对的少数关键位置，不要把全篇重新推荐一遍。

- 不要把 MinerU 原文大段粘进笔记；笔记应该是中文解释、系统化转述和研究视角分析。
- 不要写成短句提纲。除论文基本信息外，核心小节里的每个要点都应至少用一段话讲清背景、本文做法、为什么这样设计、结果意味着什么。
- 导师七问的七个标题必须固定保留英文原题，不要翻成中文，也不要中英文混写成别的标题。
- `## 综述五字段` 也必须严格保留这五个字段本身，不要改写成“研究问题 / 核心假设 / 方法路线 / 关键证据 / 结论边界”这类别的总结卡片。那类高密度总结如果需要，应该放在别的总括段里，不能占用综述五字段的位置。
- 避免用“不是……而是……”“直觉很像……”“原因很清楚”“换句话说”“其实”“更具体地说”“可以概括成”这类转折套话代替解释。需要从底层逻辑逐层讲：问题为什么出现、原文具体机制是什么、该机制解决了哪一步、论文用什么实验或数字支撑、读者应该怎样理解这个结果。
- 内容密度优先于篇幅。先把最重要的机制、证据、边界和代价讲明白，再组织叙述，不要为了写成长段落而堆空话。
- 不要单独再加一个“基础名词解释”或“先修概念”小节。基础知识、背景知识和术语解释必须直接织进各个正文 section，让读者在读问题、方法、实验、局限时顺手完成理解，而不是先看一份词典再看正文。
- 如果出现 KV cache、prefill、decode、dense compression、eviction、paged KV、prefix caching、memory tiering 等概念，必须在第一次真正用到它们的正文位置，当场解释它们在本文中扮演的角色。
- 方法机制解释必须按“这一阶段要解决什么问题 -> 原文具体怎么做 -> 为什么能这样做 -> 工程收益和代价是什么”的层次展开。不能只说“利用 attention 提取 importance”“扫描 KV 得到 sensitivity”“allocator 分配 bit”，必须讲清 attention 矩阵为什么能反映 token 被后续位置使用、为什么列求和对应 token importance、为什么扫描已生成 KV cache 不需要额外 forward、为什么二分/水位线能满足全局 bit budget、为什么 artifact 需要 payload/metadata/index、为什么 decode 要用底层 kernel 按需解包。
- 对运行时、调度、执行路径重构、状态管理这类系统论文，不能只停留在“提出了某个机制”这一层。必须把设计链条讲完整：输入是什么，系统先收集或观测了哪些信息，哪些约束限定了搜索空间或控制空间，控制决策分几步做出，每一步依赖哪些中间量，运行时如何把这些决策落到 kernel、调度、状态迁移或存储层上，以及最终的工程收益和工程代价分别出现在哪里。
- 方法名、缩写、workload 类型和实验指标都必须解释清楚。比如 evidence-sensitive workload、TTFT、decode latency、end-to-end latency、BPT、matched budget、artifact、throughput、p99 latency、context-fit frontier 等，不能假设读者已经知道；解释时要说明“这个术语在本文里衡量什么、为什么会影响系统结论、读对应图表时应该怎么理解”。
- 导师七问、综述五字段、方法整体机制总结、分析框架图、实验、局限、人工阅读重点、研究命题都要保持这种讲解口吻，不能只列关键词。
- 但凡属于“判断性内容”而不是“说明性内容”，例如局限性、open gap、与已有工作的边界、实验是否真正支持 claim、对你研究方向的可借鉴之处，都必须采用接近严格审稿的证据标准来写：判断应尽量锚定论文原文、图表、实验设置与正式结果，避免轻飘的启发式评价。
- 这不意味着整篇笔记要写成审稿意见；而是意味着笔记中的判断句必须更严谨、更克制、更有证据边界。
- 如果论文没有提供足够证据支持某个强判断，就应明确写出“现有原文证据还不足以把结论说到这一步”，而不是顺手替作者补完论证。
- 缺失信息不要输出生硬的 `TBD` 断句。无法确认的会议、年份、作者等元数据可写“待确认”；正文分析中如果证据不足，要说明“当前 MinerU 文本未提供足够证据”，并给出需要人工核对的位置。
- 图片只引用真实存在的短文件名。优先选择带语义的关键图，例如 workflow、memory、latency、breakdown、fit、overview，而不是按 MinerU 提取顺序随便选择。
- 分析框架图不应重复“执行流程讲方法”，而应把方法图中的阶段和数据流映射到正文机制。实验部分负责逐图逐实验解释指标含义、数据支撑的结论、以及该图对方法合理性、系统收益或系统代价的作用。
- 实验部分不插入任何图片。它只用文字解释 Figure / Table / RQ 的作用、指标口径、实验结论和结论边界。
- 整篇笔记最多只允许在 `## 分析框架图` 中插入一张方法框架、workflow、overview 或执行流水图。生成后必须做确定性清理：删除所有实验图片、删除所有坏路径图片、删除分析框架图以外的图片。

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
- 缺失元数据可写“待确认”。正文分析里不要写 `TBD` 断句，要用完整中文说明当前证据边界。
- 不覆盖用户手写笔记，除非用户明确要求。
- 图片使用 `![[figure.png|800]]`，且只允许使用真实存在的短文件名或发布到 `20_Research/Papers/_img` 的图片。
- 论文链接使用 display alias。

# 和其他 skill 的关系

- 被 `start-my-day` 和 `conf-papers` 调用，用于补全重点论文。
- 调用 `paper-search` 找已有材料。
- 必要时调用 `paper-ingest` 入库论文。
- 用户需要中文版论文材料时，可先调用 `paper-translate`。
- 必要时调用 `extract-paper-images` 补图。
