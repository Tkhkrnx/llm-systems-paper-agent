---
name: extract-paper-images
description: 论文图片提取：优先复用 MinerU 输出，其次 arXiv 源码图片，最后从 PDF 中提取图片。
allowed-tools: Read, Write, Bash
---

# 目标

为 Obsidian 论文笔记收集有用图片，尤其是：

- 系统架构图；
- 方法流程图；
- runtime / scheduler / memory hierarchy 图；
- 实验结果图；
- 消融实验图；
- 对理解论文机制有帮助的表格或图。

`extract-paper-images` 是图片处理型 skill，只负责补齐和整理图片。它不负责下载论文、生成完整笔记或做深度分析；这些分别交给 `paper-ingest` 和 `paper-analyze`。

# 图片来源优先级

1. `paper-ingest` 生成的 MinerU 输出；
2. arXiv source package 中的原始图片；
3. PDF 中直接提取或裁剪的图片。

# 工作流程

1. 调用或复用 `paper-search` 的结果，确认论文资产目录在哪里。
2. 如果论文已经用 `paper-ingest` 入库，优先检查：

   `20_Research/Papers/_assets/<paper>/mineru/`

3. 复用 MinerU 生成的图片和 Markdown 引用。
4. 如果 MinerU 资产不够，再运行 `scripts/extract_images.py`。
5. 将最终图片保存到论文 `_assets` 目录或对应 `images` 目录。
6. 在笔记中使用 Obsidian 图片嵌入：

   `![[figure.png|800]]`

# 推荐命令

```powershell
python scripts/extract_images.py `
  "2402.12345" `
  "C:/Users/peng/Documents/PHR/obsidian_phr/20_Research/Papers/_assets/Paper_Title/images" `
  "C:/Users/peng/Documents/PHR/obsidian_phr/20_Research/Papers/_assets/Paper_Title/images/index.md"
```

# 规则

- 优先保留论文核心图，过滤 logo、页眉页脚、无意义装饰图。
- 图片文件名应稳定、可读。
- `index.md` 中记录图片来源。
- 不覆盖用户手动整理过的图片，除非用户明确要求。

# 和其他 skill 的关系

- 被 `paper-ingest` 的后续流程或 `paper-analyze` 调用，用于补图。
- 优先复用 `paper-ingest` 生成的 MinerU 图片。
- 不单独创建论文分析笔记。
