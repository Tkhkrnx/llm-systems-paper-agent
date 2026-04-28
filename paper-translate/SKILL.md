---
name: paper-translate
description: 论文 Markdown 学术翻译：将 MinerU 英文 Markdown 转为严谨、准确、学术化的中文版 Markdown，并保存到 Obsidian 资产目录。
allowed-tools: Read, Write, Bash, WebFetch
---

# 目标

把已经通过 `paper-ingest` 生成好的英文论文 Markdown，进一步转换为适合中文阅读的学术化 Markdown。

`paper-translate` 不替代原始 MinerU Markdown，也不替代 `paper-analyze`。它只是额外生成一份中文版阅读材料。它的职责是：

- 保留英文原始 Markdown 作为原始证据；
- 生成并保存一份结构尽量一致的中文版 Markdown；
- 把翻译产物路径写回 `ingest_manifest.json`；
- 让用户后续人工阅读时能直接看中文版材料。

# 输入

优先支持两种输入：

- `ingest_manifest.json` 路径；
- 已存在的 MinerU Markdown 路径。

如果只给论文标题或 PDF，请先使用 `paper-search` / `paper-ingest`。

# 输出

默认输出到原始 MinerU Markdown 同目录，文件名约定为：

- 原文：`paper.md`
- 中文版：`paper.zh-CN.md`

同时更新 `ingest_manifest.json`，写入：

- `translated_md`
- `translation_status`
- `translation_updated`

# 翻译标准

- 准确优先，不擅自扩写、不擅自删减。
- 用语学术化、严谨、自然，适合研究生和论文阅读场景。
- 保留标题层级、段落、列表、公式、图片引用、表格和参考文献结构。
- 专业术语优先采用领域内常见译法；必要时第一次出现可保留英文原词，例如 `key-value (KV) cache`。
- 对模型名、方法名、数据集名、系统名、框架名、库名、缩写默认不翻译。
- 不把不确定内容翻死。如果原文本身 OCR 有误或句子明显破碎，要尽量保守处理，不编造。
- 不输出“机翻说明”“免责声明”之类的额外废话。

# 工作流程

1. 如果用户给的是 manifest，读取其中的 `mineru_md`。
2. 如果用户给的是 Markdown 路径，直接读取该文件。
3. 分块翻译正文，避免一次性整篇长文本导致质量下降。
4. 保留 Markdown 结构，生成 `*.zh-CN.md`。
5. 如果存在 manifest，则更新其中的翻译产物路径和状态。
6. 返回中文 Markdown 路径。后续人工阅读时可优先看中文版；`paper-analyze` 仍然只应以英文原始 Markdown 为主证据。

# 模型与环境

脚本默认通过 OpenAI 兼容接口调用翻译模型。需要以下环境变量之一：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`（可选，若使用兼容网关）
- `OPENAI_MODEL`（可选，默认 `gpt-5.4`）

如果环境变量未配置，脚本应直接报错，而不是输出低质量占位翻译。

# 和其他 skill 的关系

- 通常在 `paper-ingest` 之后调用。
- 可以被 `paper-analyze` 之前手动调用，用于先生成中文版材料。
- 中文版 Markdown 不参与搜索、分类、评分或正式分析证据判断。
- 不负责论文分析、不负责会议搜索、不负责每日推荐。
