---
name: conf-papers
description: 顶会论文搜索：从系统、体系结构、HPC、并行、数据库、AI/ML/NLP/IR 等 A 会中搜索相关论文。
allowed-tools: Read, Write, Bash, WebFetch
---

# 目标

从顶级会议中搜索与用户研究方向相关的论文，重点关注：

- LLM inference / LLM serving；
- KV cache、memory hierarchy、cache management；
- stateful systems、distributed state、stream processing；
- runtime scheduling、resource management、placement、routing；
- heterogeneous hardware、GPU、CXL、RDMA；
- RAG、continual learning、agent memory；
- 对大模型推理系统有启发的算法、系统、数据管理和检索工作。

# 默认会议范围

搜索范围不只限系统会议。因为大模型推理系统、状态优化和协同优化的思路也可能出现在 AI/ML/NLP/IR/Data Mining 等会议中。

系统、体系结构、HPC、并行、数据库方向：

`MICRO, ASPLOS, SC, PPoPP, OSDI, SOSP, NSDI, EuroSys, USENIX ATC, FAST, HPCA, ISCA, ICS, VLDB, SIGMOD, SoCC, MLSys`

AI/ML/NLP/IR/Web/Data Mining/CV 方向：

`NeurIPS, ICML, ICLR, AAAI, IJCAI, ACL, EMNLP, NAACL, KDD, WWW, SIGIR, CIKM, RecSys, UAI, AISTATS, COLT, CVPR, ICCV, ECCV, MICCAI`

# 职责边界

`conf-papers` 是编排型 skill，只负责“从会议中发现和推荐候选论文”。它不应该自己完成 PDF 入库、图片提取或深度分析。

需要复用其他 skill：

- 查重和查已有论文：调用 `paper-search`。
- 有 arXiv ID、PDF URL 或本地 PDF 时：调用 `paper-ingest` 入库 PDF/MinerU/图片/manifest。
- 需要正式论文笔记、深入阅读和系统分析时：调用 `paper-analyze`。
- 图片不完整时：调用 `extract-paper-images`。

# 工作流程

1. 使用本 skill 目录下的 `conf-papers.yaml` 读取关键词、排除词、默认年份、默认会议和 `top_n`。
2. 调用 `paper-search` 查找已有笔记和资产，避免重复推荐或重复入库。
3. 使用 `scripts/search_conf_papers.py` 搜索会议论文。
4. 脚本通过 DBLP 获取会议论文列表，通过 Semantic Scholar 补充摘要、引用数和 arXiv ID。
5. 生成 Obsidian 会议推荐笔记。
6. 对有 arXiv ID 或 PDF URL 的重点论文，调用 `paper-ingest`：
   - 保存 PDF；
   - 使用 MinerU 转 Markdown；
   - 保存图片；
   - 生成 `assets.md` 和 `ingest_manifest.json`。
7. 对重点论文调用 `paper-analyze` 生成或更新正式论文笔记并做系统分析。
8. 如果 DBLP 或 Semantic Scholar 没检索到已知论文，直接使用 PDF URL 或本地 PDF 通过 `paper-ingest` 入库。

# 推荐命令

```powershell
python scripts/search_conf_papers.py `
  --config "conf-papers.yaml" `
  --output conf_papers_filtered.json `
  --year 2026 `
  --top-n 10
```

# 注意事项

- DBLP 对不同会议和年份的收录格式不完全一致，脚本会尽量使用 toc 查询和 venue/year 查询。
- Semantic Scholar 可能限流，脚本会重试，但仍可能部分论文无法补全摘要或 arXiv ID。
- 自动搜索不能保证覆盖所有论文；遇到遗漏时应使用 `paper-ingest` 直接入库。

# 调用示例

当用户说“搜索 2025 年顶会论文”时，执行顺序应是：

1. `paper-search` 查已有笔记；
2. 本 skill 调 DBLP/Semantic Scholar 搜索会议论文；
3. 本 skill 生成会议推荐列表；
4. `paper-ingest` 入库重点论文资产；
5. `paper-analyze` 对入库论文生成或补全正式分析笔记。
