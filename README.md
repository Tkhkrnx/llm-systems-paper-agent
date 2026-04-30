# LLM Systems Paper Agent

面向大模型推理系统、分层状态优化与协同优化的论文搜索、入库、分析和 Obsidian 笔记工作流。

本仓库是在 [@juliye2025/evil-read-arxiv](https://github.com/juliye2025/evil-read-arxiv) 的基础上进行的个人研究方向适配与二次改造。原项目提供了论文推荐、阅读和 Obsidian 整理工作流的基础思路；本仓库当前目标不再是通用论文推荐，而是围绕以下研究方向组织论文。详细来源说明见 [NOTICE.md](NOTICE.md)。

- LLM inference / LLM serving；
- KV cache、prefix/prompt/context cache、long-context serving；
- stateful systems、distributed state、state placement、state migration；
- stream processing、distributed systems、runtime optimization；
- heterogeneous hardware、GPU、CXL、RDMA、memory hierarchy；
- RAG、continual learning、agent memory；
- 跨模型、runtime、系统、硬件层的协同优化。

## Skill 组成

### `paper-search`

基础查询/查重 skill。其他 skill 在创建新笔记或下载论文前应先调用它。

搜索范围包括：

- `20_Research/Papers/**/*.md`
- `20_Research/Papers/_assets/**/*.md`
- MinerU 原始 Markdown；
- PDF 资产；
- 每日推荐笔记。

### `paper-ingest`

论文资产入库 skill。输入 arXiv ID、PDF URL 或本地 PDF，产出：

- PDF；
- MinerU Markdown；
- 图片/媒体资产；
- `assets.md`；
- `ingest_manifest.json`。

它不生成正式论文分析笔记；正式笔记统一由 `paper-analyze` 生成或更新。

### `paper-analyze`

论文深度分析 skill。读取 `paper-ingest` 产出的 PDF、MinerU Markdown、图片、`assets.md` 和 `ingest_manifest.json`，生成或补全正式论文笔记：

- 导师七问；
- 综述五字段；
- 方法整体机制总结；
- 分析框架图；
- 实验设置和关键结果；
- 人工阅读重点；
- 与已有工作的关系；
- 对用户研究方向的价值；
- 局限性和 open gap。

当前 `paper-analyze` 的默认写法已经不是“摘要式摘录”，而是面向“了解大模型基础概念、但记得不牢且系统联系不够紧的研究生”来讲清楚。它有几个明确约束：

- 不再单独生成“先修概念 / 背景铺垫”词典式小节；
- 基础知识、背景知识和术语解释会直接织进问题、方法、实验、局限等正文部分；
- 方法部分会按“要解决什么问题 -> 原文具体怎么做 -> 为什么这样做可行 -> 工程收益和代价是什么”的层次展开；
- 实验部分会覆盖主要图表，而不是只挑几张图解释；
- 局限、open gap、与已有工作的边界会尽量按接近严格审稿的证据标准来写，但整篇笔记仍保持教学式讲解口吻。

### `paper-review`

严格审稿 skill。读取 `paper-ingest` 与 `paper-analyze` 的产物，结合原文 PDF、MinerU Markdown、正式分析笔记与审稿模板，生成一份偏体系结构 / 系统顶会风格的中文审稿意见，包括：

- Summary and High Level Discussion
- Strengths
- Weaknesses
- Comments for Rebuttal
- Detailed Comments for Authors
- Scored Review Questions
- Reproducibility
- Confidential Comments to the Program Committee

当前 `paper-review` 已经移除了单独的 `Multi-Angle Technical Assessment` checklist section。方法结构、baseline 公平性、系统代价、artifact 生命周期、deployment realism、claim-over-evidence、reproducibility 等判断会直接融入原有 review 结构里。

### `paper-translate`

论文 Markdown 翻译 skill。读取 `paper-ingest` 生成的 MinerU 英文 Markdown，生成一份严谨、准确、学术化的中文版 Markdown，并把翻译结果路径写回 `ingest_manifest.json`。

### `extract-paper-images`

图片补全 skill。优先复用 MinerU 图片，其次 arXiv 源码图，最后从 PDF 提取。

### `start-my-day`

每日推荐编排 skill。它不重复实现入库和分析，而是按顺序调用：

1. `paper-search`
2. arXiv/Semantic Scholar 搜索脚本
3. `paper-ingest`
4. `paper-translate`
5. `paper-analyze`
6. `paper-review`
7. 必要时 `extract-paper-images`

默认每日推荐 3 篇重点论文。

### `conf-papers`

顶会论文搜索编排 skill。它负责会议论文发现与推荐，后续入库和分析交给：

- `paper-search`
- `paper-ingest`
- `paper-translate`
- `paper-analyze`
- `paper-review`
- `extract-paper-images`

## 会议范围

系统、体系结构、HPC、并行、数据库：

`MICRO, ASPLOS, SC, PPoPP, OSDI, SOSP, NSDI, EuroSys, USENIX ATC, FAST, HPCA, ISCA, ICS, VLDB, SIGMOD, SoCC, MLSys`

AI/ML/NLP/IR/Web/Data Mining/CV：

`NeurIPS, ICML, ICLR, AAAI, IJCAI, ACL, EMNLP, NAACL, KDD, WWW, SIGIR, CIKM, RecSys, UAI, AISTATS, COLT, CVPR, ICCV, ECCV, MICCAI`

## 数据源

自动搜索会综合使用：

- arXiv API；
- Semantic Scholar API；
- DBLP；
- 用户给定 PDF URL；
- 用户给定本地 PDF。

没有任何单一数据源能保证覆盖所有已发表和预印本论文，因此发现遗漏时应直接使用 `paper-ingest` 通过 PDF URL 或本地 PDF 入库。

## Obsidian 目录约定

默认 vault：

`C:/Users/peng/Documents/PHR/obsidian_phr`

目录结构：

```text
obsidian_phr/
  10_Daily/
  20_Research/
    Papers/
      _assets/
      LLM Inference Systems/
      Hierarchical State Optimization/
      Cross-layer Runtime Co-optimization/
      RAG Memory and Continual Systems/
  99_System/
    Config/
      research_interests.yaml
```

`99_System` 用来放 agent 和脚本配置，不是论文正文目录。

## MinerU

本工作流依赖 MinerU 将 PDF 转成 Markdown 和图片。

当前本机已按源码 editable 方式安装 MinerU：

```powershell
python -m pip install -e ".[all]" -i https://mirrors.aliyun.com/pypi/simple
mineru --version
```

PDF 转 Markdown 的核心命令：

```powershell
mineru -p <pdf> -o <output> -b pipeline
```

`paper-ingest` 会自动调用 MinerU。

## 快速使用

在 Obsidian 的 Claudian/Claude Code 对话里使用自然语言：

```text
使用 start-my-day，今天给我推荐3篇 LLM serving 和状态优化方向的论文，并保存 PDF、MinerU Markdown、图片，然后生成正式分析笔记。
```

```text
使用 conf-papers，搜索 2025 年 MICRO、ASPLOS、SC、PPoPP、NeurIPS、ICML、ICLR 中与 KV cache 和 LLM serving 相关的论文。
```

```text
使用 paper-ingest，导入 arXiv:2402.12345，领域设为 LLM Inference Systems。
```

```text
使用 paper-translate，把这篇论文的 MinerU Markdown 转成中文学术版 Markdown。
```

```text
使用 paper-analyze，分析这篇论文。整篇笔记都按“了解大模型基础但理解不牢的同学”来讲清楚，方法部分要讲清 Phase 1 到 Phase 5 的具体机制，实验部分按图逐项解释。
```

```text
使用 paper-review，基于原文 PDF、MinerU Markdown 和正式分析笔记生成体系结构/系统顶会风格的严格中文审稿意见。
```

## 配置文件

主配置文件：

`config.yaml`

安装到 Obsidian 后的位置：

`C:/Users/peng/Documents/PHR/obsidian_phr/99_System/Config/research_interests.yaml`

会议搜索配置：

`conf-papers/conf-papers.yaml`

## 验证

```powershell
python -m py_compile `
  "start-my-day/scripts/search_arxiv.py" `
  "conf-papers/scripts/search_conf_papers.py" `
  "paper-ingest/scripts/ingest_paper.py"
```
