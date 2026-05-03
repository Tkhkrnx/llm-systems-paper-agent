# LLM Systems Paper Agent

面向大模型推理系统、分层状态优化与协同优化的论文搜索、入库、翻译、分析、审稿与 Obsidian 工作流。

本仓库是在 [@juliye2025/evil-read-arxiv](https://github.com/juliye2025/evil-read-arxiv) 的基础上进行的个性化改进与研究方向适配，重点服务于以下方向：

- LLM inference / LLM serving
- KV cache / prompt cache / context state management
- stateful systems / distributed state / runtime optimization
- heterogeneous hardware / memory hierarchy / GPU serving
- RAG / continual systems / retrieval state
- 跨模型、跨运行时、跨硬件的协同优化

更详细的来源说明见 [NOTICE.md](NOTICE.md)。

## 这套 Agent 现在做什么

这套 skill 不是单纯“推荐论文”，而是把论文工作流拆成几个明确步骤：

1. 搜索与查重：`paper-search`
2. 稳定下载 PDF 并入库：`paper-ingest`
3. 生成中文版 MinerU Markdown：`paper-translate`
4. 生成正式分析笔记：`paper-analyze`
5. 生成严格审稿意见：`paper-review`
6. 每日推荐与批量会刊搜索：`start-my-day`、`conf-papers`

## 目录结构

默认 Obsidian vault：

`C:/Users/peng/Documents/PHR/obsidian_phr`

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
    Guides/
```

`99_System` 用来放配置、说明文档和工作流指南，不放正式论文正文笔记。

## Skills

### `paper-search`

搜索与查重。先检查：

- 正式论文笔记
- `_assets` 下的 PDF / MinerU Markdown / assets 索引
- 每日推荐笔记

### `paper-ingest`

论文资产入库。负责：

- 稳定解析 PDF 来源
- 多源回退下载 PDF
- 校验下载结果是不是“真 PDF”
- 调用 MinerU 生成 Markdown 和图片
- 生成 `assets.md`
- 生成 `ingest_manifest.json`

### `paper-translate`

把英文 MinerU Markdown 翻译成严谨、学术化、偏直译但流畅的中文版 Markdown。

注意：分析和审稿仍以英文原始 Markdown 为主证据；中文 Markdown 是辅助阅读材料。

### `paper-analyze`

基于 PDF、MinerU Markdown、图片、assets 索引和 manifest 生成正式 Obsidian 笔记。

当前版本的重点不是“摘录”，而是把论文讲清楚，尤其适合“知道大模型基础概念、但理解还不牢”的读者。

### `paper-review`

基于原文 PDF、英文 MinerU Markdown、正式分析笔记和审稿模板，生成偏体系结构 / 系统顶会风格的严格中文审稿意见。

### `start-my-day`

每日推荐 3 篇论文，并串联：

- `paper-search`
- `paper-ingest`
- `paper-translate`
- `paper-analyze`
- 必要时 `paper-review`

### `conf-papers`

面向 CCF A 类及高水平系统 / AI / ML / NLP / IR / 数据库 / 并行 / 体系结构 venue 做会议论文检索，再串联入库与分析。

## `paper-ingest` 这次重点优化了什么

这次最核心的改动，是把“PDF 下载”从“MinerU 后处理”里拆出来，避免用户把所有失败都感知成“论文下不来”。

### 新的 ingest 原则

1. PDF 下载成功与 MinerU 成功分开记录  
2. 下载后必须做 PDF 校验，不只看 HTTP 200  
3. 支持多源回退：arXiv / OpenReview / venue / DOI / DBLP 派生链接  
4. 每次尝试都写进 manifest，方便判断失败到底发生在哪一环  

### Manifest 里新增的关键字段

- `pdf_download_status`
- `pdf_download_record`
- `pdf_download_attempts`
- `pdf_validation`
- `mineru_status`
- `mineru_attempts`

这样后面看到失败时，可以明确区分：

- 没解析到 PDF
- PDF 下载失败
- 下载到的不是 PDF
- PDF 正常，但 MinerU 失败

## 会议范围

系统、体系结构、高性能、并行、数据库：

`MICRO, ASPLOS, SC, PPoPP, OSDI, SOSP, NSDI, EuroSys, USENIX ATC, FAST, HPCA, ISCA, ICS, VLDB, SIGMOD, SoCC, MLSys`

AI / ML / NLP / IR / Web / Data Mining / CV：

`NeurIPS, ICML, ICLR, AAAI, IJCAI, ACL, EMNLP, NAACL, KDD, WWW, SIGIR, CIKM, RecSys, UAI, AISTATS, COLT, CVPR, ICCV, ECCV, MICCAI`

## MinerU

当前工作流优先使用本机已安装的 `mineru` 命令；如有需要，也支持通过配置文件里的 `mineru_root` 回退到本地源码目录。

核心命令：

```powershell
mineru -p <pdf> -o <output> -b pipeline
```

## 快速使用

```text
使用 start-my-day，今天给我推荐 3 篇和 LLM serving、KV cache、state management 相关的论文，并保存 PDF、MinerU Markdown、中文 Markdown 和正式分析笔记。
```

```text
使用 conf-papers，搜索 2024 到 2026 年 MICRO、ASPLOS、OSDI、SOSP、NeurIPS、ICML 里和 LLM inference systems 相关的论文，并把最值得读的几篇入库分析。
```

```text
使用 paper-ingest，把 arXiv:2402.12345 保存到 Obsidian。
```

```text
使用 paper-analyze，按现在的高质量笔记标准分析这篇论文，重点把方法机制和实验结论讲清楚。
```

```text
使用 paper-review，基于原文和笔记生成严格的系统顶会风格中文审稿意见。
```

## 安装位置

仓库源码：

`C:/Users/peng/Documents/PHR/Intellistream/projects/llm-systems-paper-agent`

Claude / Claudian skills：

`C:/Users/peng/Documents/PHR/obsidian_phr/.claude/skills`

Codex skills：

`C:/Users/peng/.codex/skills`

修改 skill 时，优先改仓库源码，再同步到 Claude 和 Codex 的 skill 安装目录。
