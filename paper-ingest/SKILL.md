---
name: paper-ingest
description: 论文资产入库：稳定下载 PDF，写入 manifest，并调用 MinerU 生成 Markdown/图片；正式分析交给 paper-analyze。
allowed-tools: Read, Write, Bash, WebFetch
---

# 目标

`paper-ingest` 只负责把论文原始资产稳定地放进 Obsidian，并把每一步状态记录清楚。

它的核心职责是：

- 尽量稳定地解析并下载论文 PDF
- 验证下载结果确实是可用 PDF，而不是跳转页或错误页
- 调用 MinerU 生成英文 Markdown 和图片
- 生成 `assets.md` 与 `ingest_manifest.json`
- 为后续 `paper-translate`、`paper-analyze`、`paper-review` 提供干净的资产入口

它**不负责**生成正式分析笔记，也不负责审稿意见。

# 关键原则

1. **下载成功与 MinerU 成功分开判断**
   - PDF 只要已经稳定落盘且校验通过，就算入库成功。
   - MinerU 失败不应被混淆成“PDF 没下载下来”。

2. **优先做真实 PDF 校验**
   - 不只看 HTTP 200。
   - 至少检查：
     - 文件是否存在
     - 文件头是否为 `%PDF`
     - 文件大小是否足够

3. **多源回退**
   - 优先顺序通常是：
     - arXiv PDF
     - OpenReview PDF
     - venue / DOI 页面解析出的 PDF
     - DBLP / 其他外链

4. **所有关键状态写入 manifest**
   - 后续要能看出失败究竟发生在：
     - PDF 解析
     - PDF 下载
     - PDF 校验
     - MinerU 转换

# 支持输入

- arXiv ID，例如 `2402.12345`
- arXiv URL
- DBLP 论文记录页
- 直接 PDF URL
- 论文 landing page URL
- 本地 PDF 路径

# 默认路径

- Obsidian vault：`C:/Users/peng/Documents/PHR/obsidian_phr`
- 配置文件：`C:/Users/peng/Documents/PHR/obsidian_phr/99_System/Config/research_interests.yaml`
- 资产目录：`20_Research/Papers/_assets/<paper-slug>/`
- 脚本：`scripts/ingest_paper.py`

# 工作流

1. 解析输入，识别 arXiv / DBLP / HTML 页面 / PDF URL / 本地 PDF。
2. 生成 PDF 候选源列表，并按优先级依次尝试。
3. 下载后做 PDF 校验。
4. 把下载轨迹写进 `ingest_manifest.json`：
   - `pdf_download_status`
   - `pdf_download_record`
   - `pdf_download_attempts`
   - `pdf_validation`
5. 仅在 PDF 有效时再调用 MinerU。
6. 生成：
   - 原始 PDF
   - MinerU Markdown
   - 图片目录
   - `assets.md`
   - `ingest_manifest.json`
7. 后续如需中文 Markdown，调用 `paper-translate`。
8. 后续如需正式笔记，调用 `paper-analyze`。

# 推荐命令

```powershell
python scripts/ingest_paper.py `
  --input "2402.12345" `
  --vault "C:/Users/peng/Documents/PHR/obsidian_phr" `
  --domain "LLM Inference Systems"
```

```powershell
python scripts/ingest_paper.py `
  --input "https://dblp.org/rec/conf/asplos/xxxx" `
  --vault "C:/Users/peng/Documents/PHR/obsidian_phr"
```

```powershell
python scripts/ingest_paper.py `
  --input "C:/path/to/paper.pdf" `
  --domain "Hierarchical State Optimization"
```

# 输出要求

`assets.md` 至少应包含：

- PDF 链接
- 来源链接
- MinerU Markdown 链接
- 资产目录
- manifest 链接
- 推荐正式笔记路径
- 分类结果与原因
- 图片目录与图片别名映射
- MinerU 状态

`ingest_manifest.json` 至少应包含：

- 论文元数据
- PDF 下载状态与尝试记录
- PDF 校验信息
- MinerU 状态与尝试记录
- 资产路径
- 推荐正式笔记路径

# 与其他 skill 的关系

- `paper-search`：先查重，再决定是否入库
- `paper-translate`：在入库完成后生成中文版 Markdown
- `paper-analyze`：基于英文原始证据生成正式分析笔记
- `paper-review`：基于原文、笔记和模板生成严格审稿意见
- `start-my-day` / `conf-papers`：会调用本 skill 完成批量资产入库
