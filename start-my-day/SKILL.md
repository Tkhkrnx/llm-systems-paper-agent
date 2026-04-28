---
name: start-my-day
description: 每日论文推荐：面向大模型推理系统、分层状态优化与协同优化，每天推荐3篇论文并准备 Obsidian 笔记和资产。
allowed-tools: Read, Write, Bash, WebFetch
---

# 目标

为用户每天推荐值得阅读的论文，研究方向聚焦：

- 大模型推理系统与 LLM serving；
- 分层状态优化、状态放置、状态迁移、状态恢复；
- stateful systems、distributed systems、stream processing；
- runtime optimization、cross-layer co-optimization；
- heterogeneous hardware、GPU、CXL、RDMA、memory hierarchy；
- KV cache、prefix/prompt/context cache、long-context serving；
- RAG、continual learning、agent memory。

# 默认配置

优先读取：

`C:/Users/peng/Documents/PHR/obsidian_phr/99_System/Config/research_interests.yaml`

如果环境变量 `$OBSIDIAN_VAULT_PATH` 不存在，默认使用：

`C:/Users/peng/Documents/PHR/obsidian_phr`

# 搜索范围

运行 `scripts/search_arxiv.py`，默认使用系统方向相关 arXiv 分类：

`cs.DC,cs.OS,cs.PF,cs.AR,cs.DB,cs.NI,cs.ET,cs.PL,cs.IR,cs.LG,cs.CL,cs.AI`

脚本会同时搜索：

- 最近 arXiv 论文；
- Semantic Scholar 中近一年高影响论文；
- 然后根据相关性、新近性、热度和质量评分排序。

# 职责边界

`start-my-day` 是编排型 skill，只负责“每日发现与推荐”。它不应该重新实现搜索已有笔记、PDF 入库、图片提取或深度分析。

需要复用其他 skill：

- 查重和检索已有笔记：调用 `paper-search`。
- PDF 下载、MinerU Markdown、图片和资产 manifest 入库：调用 `paper-ingest`。
- 将 MinerU 英文 Markdown 转成中文学术版 Markdown：调用 `paper-translate`。
- 正式论文笔记生成、深度分析和系统框架补全：调用 `paper-analyze`。
- 单独补图或整理图片：调用 `extract-paper-images`。

# 必须执行的流程

1. 调用 `paper-search` 扫描已有 Obsidian 论文笔记和 MinerU 原始 Markdown，避免重复。
2. 使用 `scripts/search_arxiv.py --top-n 10` 搜索候选论文。
3. 在 `10_Daily/` 下生成每日推荐笔记。
4. 默认推荐 3 篇最值得深读的论文，除非用户明确要求更多或更少。
5. 对前 3 篇论文，如果尚未入库且有 arXiv ID 或 PDF URL，调用 `paper-ingest`：
   - 保存 PDF；
   - 使用 MinerU 转 Markdown；
   - 保存图片和原始解析资产；
   - 生成 `assets.md` 和 `ingest_manifest.json`。
6. 对前 3 篇论文，无论是新入库还是已有资产，只要存在 MinerU Markdown，都调用 `paper-translate` 生成 `*.zh-CN.md` 中文版材料。
7. 对前 3 篇论文，再调用 `paper-analyze` 生成或补全正式论文笔记、导师七问、综述五字段和人工阅读重点。
8. 如果图片缺失或 MinerU 图片不够清晰，调用 `extract-paper-images`。
9. 缺失证据一律写 `TBD`，不要猜测。

# 推荐命令

```powershell
python scripts/search_arxiv.py `
  --config "C:/Users/peng/Documents/PHR/obsidian_phr/99_System/Config/research_interests.yaml" `
  --output arxiv_filtered.json `
  --max-results 200 `
  --top-n 10 `
  --categories "cs.DC,cs.OS,cs.PF,cs.AR,cs.DB,cs.NI,cs.ET,cs.PL,cs.IR,cs.LG,cs.CL,cs.AI"
```

# 输出要求

每日推荐笔记应包含：

- 今日推荐概览；
- 3 篇重点论文；
- 每篇论文的标题、作者、来源、链接、推荐理由；
- 是否已生成 PDF/MinerU Markdown/中文版 Markdown/详细笔记；
- 后续阅读建议。

# 调用示例

当用户说“start my day”时，执行顺序应是：

1. `paper-search` 查重；
2. 本 skill 搜索和排序新论文；
3. `paper-ingest` 入库前 3 篇新论文的 PDF/MinerU/图片/manifest；
4. `paper-translate` 为前 3 篇生成中文版 MinerU Markdown；
5. `paper-analyze` 对前 3 篇生成或补全正式详细分析笔记；
6. `extract-paper-images` 只在图片缺失时补图；
7. 回到本 skill 汇总今日推荐笔记。
