---
name: paper-ingest
description: 论文资产入库：接收 arXiv ID、PDF URL 或本地 PDF，稳定下载 PDF，并调用 MinerU 生成标准 Markdown/图片资产；正式分析交给 paper-analyze。
allowed-tools: Read, Write, Bash, WebFetch
---

# 目标

把论文原始资产完整、稳定地放进 Obsidian，作为后续阅读、分析、翻译、审稿的证据底座。

`paper-ingest` 只负责资产入库，不负责正式分析笔记，不负责导师七问，不负责综述五字段，也不负责审稿意见。它要做好的事情只有几件：

- 尽量稳定地解析并下载论文 PDF
- 验证下载结果确实是可用 PDF，而不是跳转页或错误页
- 调用 MinerU 把 PDF 转成标准 Markdown 和图片
- 把产物整理成统一、可复用的目录结构
- 写出 `assets.md` 和 `ingest_manifest.json`
- 为 `paper-translate`、`paper-analyze`、`paper-review` 提供干净资产入口

# 必须产出

- 原始 PDF
- MinerU 转换得到的英文 Markdown
- MinerU 提取的图片/媒体资产
- 资产索引 `assets.md`
- 机器可读清单 `ingest_manifest.json`

# 关键原则

1. 下载成功与 MinerU 成功分开判断
   - PDF 成功落盘并通过校验，就算资产入库成功。
   - MinerU 失败不能伪装成“已经完整转好 Markdown”。

2. 优先做真实 PDF 校验
   - 不能只看 HTTP 200。
   - 至少检查：
     - 文件存在
     - 文件头是 `%PDF`
     - 文件大小足够

3. 多源回退下载
   - 优先顺序通常是：
     - arXiv PDF
     - OpenReview PDF
     - venue / DOI 页面解析出的 PDF
     - DBLP 或其他外链

4. 产物结构必须稳定
   - 标准目录形态应尽量保持为：
     - `20_Research/Papers/_assets/<paper-slug>/<paper-slug>.pdf`
     - `20_Research/Papers/_assets/<paper-slug>/mineru/<paper-id-or-stem>/auto/<paper-id-or-stem>.md`
     - `20_Research/Papers/_assets/<paper-slug>/mineru/<paper-id-or-stem>/auto/images/...`
   - 图片应尽量重命名为可读别名，例如：
     - `fig5-workflow.jpg`
     - `fig8-latency.jpg`
     - `fig9-memory-breakdown.jpg`

5. 不把历史补丁文件当作标准成功产物
   - `simple.pdf`
   - `simple.txt`
   - `fallback.md`
   这些如果只是在特殊事故里出现，最多作为历史残留记录，不能当成标准 ingest 产物去鼓励复用。

6. 所有关键状态都要写进 manifest
   - 后续必须能看出问题到底发生在：
     - 输入解析
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

# 工作流程

1. 先调用 `paper-search` 查重，确认是否已有 PDF、MinerU Markdown 或正式笔记。
2. 解析输入，识别 arXiv / DBLP / landing page / PDF URL / 本地 PDF。
3. 生成 PDF 候选源列表，并按优先级依次尝试。
4. 下载后做 PDF 校验。
5. 只有 PDF 校验通过时，才调用 MinerU：

```powershell
mineru -p <pdf> -o <output> -b pipeline
```

6. 保存 MinerU 输出的 Markdown、图片和相关资产，保持标准目录层级。
7. 对图片做可读别名重命名，并把原名到别名的映射写进 manifest 和 `assets.md`。
8. 写入 `assets.md` 和 `ingest_manifest.json`。
9. 返回下一步建议：
   - 先调用 `paper-translate` 生成中文版 Markdown
   - 再调用 `paper-analyze` 生成正式论文笔记

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
  --title "Paper Title" `
  --authors "Author A, Author B" `
  --domain "Hierarchical State Optimization"
```

# 输出要求

`assets.md` 至少应包含：

- 论文标题 / 作者 / 年份 / venue / 链接
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

# 规则

- 缺失证据写 `TBD`，不要编造。
- 保留 MinerU Markdown 作为原始证据。
- 不创建或覆盖正式论文分析笔记，除非用户明确要求。
- Obsidian 图片使用 `![[image.png|800]]`。
- Obsidian 链接使用 display alias。
- 如果 MinerU 没有产出标准 Markdown 结构，不要把半成品静默冒充成标准成功结果。

# 与其他 skill 的关系

- `paper-search`：先查重，再决定是否入库
- `paper-translate`：在入库完成后生成中文版 Markdown
- `paper-analyze`：基于英文原始证据生成正式分析笔记
- `paper-review`：基于原文、笔记和模板生成严格审稿意见
- `start-my-day` / `conf-papers`：会调用本 skill 完成批量资产入库

# Directory Rule

- If the paper directory already contains a PDF, ingest must use that PDF in place and treat that directory as the asset directory.
- If the caller explicitly points to a paper directory, PDF download, MinerU output, assets.md, and ingest_manifest.json must all stay in that same paper directory.
- Only when the target paper directory does not already have a PDF may ingest download one. Temporary short-path staging is allowed internally, but final assets must be written back to the original paper directory.

