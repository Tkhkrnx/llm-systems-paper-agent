# LLM Systems Paper Agent

这是一套面向大模型系统论文工作流的 Obsidian Agent 工具集。

它的目标是：
- 高质量检索系统 / 体系结构 / AI / ML 论文
- 稳定下载 PDF 并入库
- 使用 MinerU 生成 Markdown 与图片
- 生成正式论文笔记和审稿意见
- 与 Obsidian 资产结构稳定协同

## 主要 skills

1. `paper-search`：在现有论文笔记、_assets 和历史记录中查重。
2. `paper-ingest`：入库 PDF、MinerU Markdown、图片和 manifest。
3. `paper-translate`：把 MinerU 英文 Markdown 翻译成中文版本。
4. `paper-analyze`：基于 PDF 与 MinerU 证据生成正式分析笔记。
5. `paper-review`：生成面向系统 / 体系结构顶会风格的中文审稿意见。
6. `conf-papers` / `start-my-day`：做批量检索、推荐与入库。

## `paper-ingest` 当前的重点优化

当前版本的 `paper-ingest` 已经优化为“开放来源优先、失败快速、状态可追踪”的下载流程：

- 优先尝试作者主页 / arXiv / OpenReview / USENIX / MLSys 等开放 PDF 来源
- 对 OpenReview、arXiv、ACM、IEEE、MLSys 等链接做 URL 规范化和 PDF 快路径推断
- 如果 landing page 返回 HTML，会从页面中抽取 PDF 候选链接
- 下载后会检查 `%PDF` 头和最小文件大小
- 不再把普通 DOI / URL 误判为 arXiv ID
- manifest 会记录 `pdf_download_status`、`pdf_download_attempts`、`pdf_validation` 等关键字段

## 工作目录

- 仓库源码：`C:/Users/peng/Documents/PHR/Intellistream/projects/llm-systems-paper-agent`
- 默认 Obsidian vault：`C:/Users/peng/Documents/PHR/obsidian_phr`
- Codex skills：`C:/Users/peng/.codex/skills`
- Vault 内 Codex skills：`C:/Users/peng/Documents/PHR/obsidian_phr/.codex/skills`
- Vault 内 Claudian skills：`C:/Users/peng/Documents/PHR/obsidian_phr/.claude/skills`

## 使用建议

- 批量检索论文时，先用 `conf-papers` 或 `paper-search` 查重
- 需要入库时，使用 `paper-ingest` 保存 PDF 与 MinerU 资产
- 需要中文阅读材料时，使用 `paper-translate`
- 需要正式研究笔记时，使用 `paper-analyze`
- 需要严格审稿意见时，使用 `paper-review`

## 说明

README 的职责是描述工作流、skills 关系和仓库定位。
具体入库规则、PDF 下载策略、manifest 字段约定以 `paper-ingest/SKILL.md` 为准。
