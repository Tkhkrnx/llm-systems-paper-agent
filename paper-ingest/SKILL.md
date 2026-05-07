---
name: paper-ingest
description: 论文资产入库：稳定下载 PDF，优先开放来源，写入 manifest，并调用 MinerU 生成 Markdown/图片；正式分析交给 paper-analyze。
allowed-tools: Read, Write, Bash, WebFetch
---

# 目标

`paper-ingest` 只负责把论文原始资产稳定地放进 Obsidian，并把每一步状态记录清楚。

它的核心职责是：
- 尽量稳定地解析并下载论文 PDF
- 优先尝试开放获取来源，而不是一开始就落到 ACM / IEEE 等较慢或受限页面
- 验证下载结果确实是可用 PDF，而不是跳转页、错误页或登录页
- 调用 MinerU 生成英文 Markdown 和图片
- 生成 `assets.md` 与 `ingest_manifest.json`
- 为后续 `paper-translate`、`paper-analyze`、`paper-review` 提供干净的资产入口

它**不负责**生成正式分析笔记，也不负责审稿意见。

# 关键原则

1. **PDF 下载成功与 MinerU 成功分开判断**
   - PDF 已稳定落盘且校验通过，就算入库成功。
   - MinerU 失败不应混淆成“PDF 没下载下来”。

2. **必须做真 PDF 校验**
   - 不只看 HTTP 200。
   - 至少检查：
     - 文件是否存在
     - 文件头是否为 `%PDF`
     - 文件大小是否达到最小阈值

3. **开放来源优先，失败快速**
   - 默认优先顺序：
     - arXiv PDF
     - OpenReview PDF
     - USENIX / MLSys / 开放 proceedings PDF
     - 作者主页 / 高校主页 / 个人站公开 PDF
     - venue 页面可直接抽取出的 PDF
     - DOI / ACM / IEEE 等较慢或可能受限来源
   - 如果拿到的是 HTML 跳转页，优先从页面里抽取开放 PDF 候选链接，再继续尝试。
   - 如果下载内容不是有效 PDF，要尽快失败并切换下一个候选源。

4. **所有关键状态都写入 manifest**
   - 后续必须能看出失败究竟发生在：
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
- 资产目录：`20_Research/Papers/_assets/<paper-slug>/`
- 脚本：`scripts/ingest_paper.py`

# 工作流

1. 解析输入，识别 arXiv / DBLP / HTML 页面 / PDF URL / 本地 PDF。
2. 生成 PDF 候选源列表，并按开放来源优先级依次尝试。
3. 下载后做 PDF 校验。
4. 把下载轨迹写进 `ingest_manifest.json`，包括：
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
