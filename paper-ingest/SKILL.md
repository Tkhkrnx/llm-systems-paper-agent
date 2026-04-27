---
name: paper-ingest
description: 论文资产入库：接收 arXiv ID、PDF URL 或本地 PDF，保存 PDF，并用 MinerU 转 Markdown/图片；正式论文笔记交给 paper-analyze 生成。
allowed-tools: Read, Write, Bash, WebFetch
---

# 目标

把一篇论文的原始资产完整放入 Obsidian，作为后续阅读、分析、综述写作的证据材料。

`paper-ingest` 是资产入库型 skill，只负责“把 PDF、MinerU Markdown、图片和资产索引保存下来”。它不生成正式论文分析笔记，也不维护导师七问、综述五字段或人工阅读重点；这些统一交给 `paper-analyze`。

必须产出：

- 原始 PDF；
- MinerU 转换得到的 Markdown；
- MinerU 或 PDF 中提取的图片/媒体资产；
- 资产索引 `assets.md`；
- 机器可读清单 `ingest_manifest.json`；
- 下一步 `paper-analyze` 所需的 PDF、MinerU Markdown、图片目录和元数据路径。

# 支持输入

可以输入：

- arXiv ID，例如 `2402.12345`；
- arXiv URL；
- 直接 PDF URL；
- 本地 `.pdf` 路径。

# 默认路径

- Obsidian vault：`C:/Users/peng/Documents/PHR/obsidian_phr`
- MinerU 源码目录：`C:/Users/peng/Documents/PHR/Intellistream/projects/MinerU-mineru-3.1.5-released`
- 脚本：`scripts/ingest_paper.py`
- PDF 和 MinerU 资产目录：`20_Research/Papers/_assets/<论文安全文件名>/`
- 正式论文笔记目录：`20_Research/Papers/<domain>/<论文安全文件名>.md`，由 `paper-analyze` 生成或更新。

# 工作流程

1. 先调用 `paper-search` 查重，确认是否已有结构化笔记、PDF 或 MinerU Markdown。
2. 如果已有完整笔记，不重复生成笔记；只补齐缺失 PDF/MinerU/图片资产，并返回已有笔记路径。
3. 解析输入，判断是 arXiv ID、URL 还是本地 PDF。
4. 下载或复制 PDF 到 Obsidian 的 `_assets` 目录。
5. 调用 MinerU：

   ```powershell
   mineru -p <pdf> -o <output> -b pipeline
   ```

6. 保存 MinerU 输出的 Markdown、图片和相关资产。
7. 写入 `assets.md` 和 `ingest_manifest.json`，记录 PDF、MinerU Markdown、图片目录、来源链接和元数据。
8. 返回下一步建议：立即调用 `paper-analyze` 生成或更新正式论文笔记。
9. `paper-analyze` 生成的正式笔记应链接：
   - PDF；
   - MinerU Markdown；
   - 图片资产；
   - 论文来源链接。

# 推荐命令

arXiv 论文：

```powershell
python scripts/ingest_paper.py `
  --input "2402.12345" `
  --vault "C:/Users/peng/Documents/PHR/obsidian_phr" `
  --domain "LLM Inference Systems"
```

本地 PDF：

```powershell
python scripts/ingest_paper.py `
  --input "C:/path/to/paper.pdf" `
  --title "Paper Title" `
  --authors "Author A, Author B" `
  --domain "Hierarchical State Optimization"
```

# 资产索引要求

`assets.md` 必须包含：

- Paper title / Authors / Year / Venue / Links；
- PDF 路径；
- MinerU Markdown 路径；
- 图片/媒体目录；
- arXiv categories 或来源信息；
- MinerU 状态；
- 建议的正式笔记路径；
- 下一步：调用 `paper-analyze`。

# 规则

- 缺失证据写 `TBD`，不要编造。
- 保留 MinerU Markdown 作为原始证据。
- 不创建或覆盖正式论文分析笔记，除非用户明确要求只生成占位文件。
- Obsidian 图片使用 `![[image.png|800]]`。
- Obsidian 链接使用 display alias，例如 `[[path/to/note|Paper Title]]`。

# 和其他 skill 的关系

- 被 `start-my-day` 和 `conf-papers` 调用，用于把推荐论文资产保存到 Obsidian。
- 调用 `paper-search` 做查重。
- 产出的 PDF、MinerU Markdown、图片和 manifest 会被 `paper-analyze` 作为证据使用。
- 入库完成后，通常应立即调用 `paper-analyze` 生成正式论文笔记。
- 图片不足时再调用 `extract-paper-images`。
