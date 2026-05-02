---
name: conf-papers
description: CCF A 类会刊论文搜索：默认优先从全部 A 会中搜索，再补充系统相关 A 刊，以及其他对系统研究有启发的高水平 venue。
allowed-tools: Read, Write, Bash, WebFetch
---

# 目标

从 CCF A 类会议、系统相关 A 类期刊，以及其他对用户研究方向有启发的高水平 venue 中搜索相关论文，重点关注：

- LLM inference / LLM serving；
- KV cache、memory hierarchy、cache management；
- stateful systems、distributed state、stream processing；
- runtime scheduling、resource management、placement、routing；
- heterogeneous hardware、GPU、CXL、RDMA；
- RAG、continual learning、agent memory；
- 对大模型推理系统有启发的算法、系统、数据管理和检索工作。

# 默认范围

默认策略分三层：

1. **第一优先级**：CCF 全部 A 类会议，不论方向，都加入默认搜索范围。
2. **第二优先级**：系统相关 CCF A 类期刊，尤其是体系结构、并行与分布、存储、系统软件、数据库、网络等方向。
3. **第三优先级**：其他不一定属于 CCF 系统目录、但可能对系统研究有启发的高水平 venue，可按需保留或追加。

这样做的原因是：很多对大模型推理系统有启发的思路，不一定只出现在传统系统会议里，也可能出现在 AI/ML/NLP/IR/Data Mining/CV 等 A 会中；但默认排序仍应先看顶级 A 会，再看系统相关 A 刊和补充 venue。

# 默认 A 会范围

默认包含 CCF 全部 A 类会议。当前配置会尽量把这些会议作为首批搜索对象。

系统、体系结构、并行/分布、存储、软件、数据库、网络，以及 AI/ML/NLP/IR/CV 等方向的 A 会都应纳入。

# 默认 A 刊范围

默认加入系统相关的 CCF A 类期刊，至少包括体系结构、并行与分布、存储、系统软件、数据库、网络等方向中对大模型推理系统可能直接有启发的期刊。

# 补充高水平 venue

除 CCF A 会/A 刊外，可以继续保留一些对系统研究有启发的高水平 venue，例如 MLSys、SoCC、UAI、AISTATS、RecSys、MICCAI 等。它们未必都属于 CCF 系统目录，但对 LLM inference systems、state management、memory hierarchy、resource scheduling 等主题常有可迁移思路。

# 职责边界

`conf-papers` 是编排型 skill，只负责“从会议中发现和推荐候选论文”。它不应该自己完成 PDF 入库、图片提取或深度分析。

需要复用其他 skill：

- 查重和查已有论文：调用 `paper-search`。
- 有 arXiv ID、PDF URL 或本地 PDF 时：调用 `paper-ingest` 入库 PDF/MinerU/图片/manifest。
- 需要把英文 MinerU Markdown 转成中文学术材料时：调用 `paper-translate`。
- 需要正式论文笔记、深入阅读和系统分析时：调用 `paper-analyze`。
- 图片不完整时：调用 `extract-paper-images`。

# 工作流程

1. 使用本 skill 目录下的 `conf-papers.yaml` 读取关键词、排除词、默认年份、默认会议、默认期刊和 `top_n`。
2. 调用 `paper-search` 查找已有笔记和资产，避免重复推荐或重复入库。
3. 使用 `scripts/search_conf_papers.py` 搜索会刊论文。
4. 脚本通过 DBLP 获取会议/期刊论文列表，通过 Semantic Scholar 补充摘要、引用数和 arXiv ID。
5. 生成 Obsidian 推荐笔记；排序时默认保留“全 A 会纳入”的范围，但展示顺序优先系统相关 A 会，其次其他 A 会，再次系统相关 A 刊。
6. 对有 arXiv ID 或 PDF URL 的重点论文，调用 `paper-ingest`：
   - 保存 PDF；
   - 使用 MinerU 转 Markdown；
   - 保存图片；
   - 生成 `assets.md` 和 `ingest_manifest.json`。
7. 对重点论文，如果已经有 MinerU Markdown，调用 `paper-translate` 生成 `*.zh-CN.md` 中文版材料。
8. 对重点论文调用 `paper-analyze` 生成或更新正式论文笔记并做系统分析。
9. 如果 DBLP 或 Semantic Scholar 没检索到已知论文，直接使用 PDF URL 或本地 PDF 通过 `paper-ingest` 入库。

# 推荐命令

```powershell
python scripts/search_conf_papers.py `
  --config "conf-papers.yaml" `
  --output conf_papers_filtered.json `
  --year 2026 `
  --top-n 10
```

快速首轮筛查：

```powershell
python scripts/search_conf_papers.py `
  --config "conf-papers.yaml" `
  --output conf_papers_quick.json `
  --year 2026 `
  --top-n 15 `
  --quick
```

极快 smoke test：

```powershell
python scripts/search_conf_papers.py `
  --config "conf-papers.yaml" `
  --output conf_papers_very_quick.json `
  --year 2026 `
  --top-n 10 `
  --very-quick
```

# 注意事项

- DBLP 对不同会议、期刊和年份的收录格式不完全一致，脚本会尽量使用 toc 查询和 venue/year 查询。
- Semantic Scholar 可能限流，脚本会重试，但仍可能部分论文无法补全摘要或 arXiv ID。
- 在网络不稳定、DBLP 响应慢、或只是想先看第一批重点结果时，优先使用 `--quick` 或 `--very-quick`；它们会先聚焦系统优先会议并跳过 Semantic Scholar 补全。
- 如果目标年份过新，例如 2026，DBLP 可能尚未完整收录；这时应明确告诉用户“这是该年份当前可检索到的结果”，必要时同时用 2025/2024 做质量对照。
- 自动搜索不能保证覆盖所有论文；遇到遗漏时应使用 `paper-ingest` 直接入库。

# 调用示例

当用户说“搜索 2025 年 CCF A 会/A 刊论文”时，执行顺序应是：

1. `paper-search` 查已有笔记；
2. 本 skill 调 DBLP/Semantic Scholar 搜索会议论文；
3. 本 skill 生成会议推荐列表；
4. `paper-ingest` 入库重点论文资产；
5. `paper-translate` 为重点论文生成中文版 MinerU Markdown；
6. `paper-analyze` 对入库论文生成或补全正式分析笔记。
