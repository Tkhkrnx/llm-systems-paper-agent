---
name: paper-search
description: 论文笔记搜索：在 Obsidian 已有论文笔记、MinerU Markdown、PDF 资产和每日推荐中搜索相关论文。
allowed-tools: Read, Grep, Glob, Bash
---

# 目标

在推荐、入库或分析论文前，先搜索 Obsidian 中是否已有相关材料，避免重复整理。

`paper-search` 是基础查询型 skill。其他 skill 在创建新内容之前都应该先调用它。

# 搜索范围

需要搜索：

- `20_Research/Papers/**/*.md`
- `20_Research/Papers/_assets/**/*.md`
- `_assets/*/mineru/` 下的 MinerU 原始 Markdown；
- `_assets/` 下的 PDF 文件名；
- `10_Daily/` 下的每日推荐笔记。

# 工作流程

1. 解析用户查询，判断是标题、作者、关键词、会议、年份、领域还是系统概念。
2. 搜索结构化论文笔记的 frontmatter 和正文。
3. 搜索 MinerU 原始 Markdown，找证据级匹配。
4. 搜索 PDF 文件名和资产目录。
5. 返回排序后的结果。

# 被谁调用

- `start-my-day`：每日推荐前查重，避免重复推荐或重复入库。
- `conf-papers`：会议论文推荐前查重。
- `paper-ingest`：入库前确认是否已有 PDF、MinerU Markdown 或结构化笔记。
- `paper-analyze`：分析前查找已有笔记和证据材料。
- `extract-paper-images`：补图前定位论文资产目录。

# 返回格式

每个结果应包含：

- 笔记路径；
- 论文标题；
- 匹配位置或证据片段；
- 是否存在 PDF；
- 是否存在 MinerU Markdown；
- 建议下一步操作，例如：
  - 已有完整笔记，可以直接阅读；
  - 只有 PDF/MinerU Markdown，建议调用 `paper-analyze`；
  - 没有入库，建议调用 `paper-ingest`。

# 推荐命令

```powershell
Get-ChildItem -Path "C:/Users/peng/Documents/PHR/obsidian_phr/20_Research/Papers" -Recurse -Include *.md |
  Select-String -Pattern "KV cache|LLM serving|state placement" -CaseSensitive:$false
```

# 排序规则

- 标题/frontmatter 精确匹配优先；
- MinerU 原文证据匹配其次；
- 正文提及再次；
- PDF/资产文件名匹配最后；
- 已有 PDF + MinerU Markdown + 结构化笔记的结果优先展示。

# 规则

- 优先复用已有笔记，避免重复创建。
- Obsidian 链接使用 display alias。
- 如果只找到原始 Markdown 或 PDF，建议继续用 `paper-analyze` 规范化。
