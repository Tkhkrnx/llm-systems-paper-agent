# LLM Systems Paper Agent

An Obsidian-centered paper workflow for LLM inference systems, hierarchical state optimization, and cross-layer co-optimization.

This repository is a personalized adaptation of
[`@juliye2025/evil-read-arxiv`](https://github.com/juliye2025/evil-read-arxiv).
The upstream project provided the original paper recommendation, reading, and
Obsidian workflow foundation. This repository customizes that idea for:

- LLM inference and serving;
- KV-cache and long-context serving;
- stateful and distributed systems;
- runtime/resource co-optimization;
- heterogeneous hardware and memory hierarchy;
- RAG, continual learning, and agent memory.

See [README.md](README.md) for the maintained Chinese documentation.
See [NOTICE.md](NOTICE.md) for attribution details.

## paper-ingest updates

- Better DBLP / DOI / OpenReview / arXiv source resolution
- Safer blocked-source fallback handling
- Download retry support for unstable fetches
- Shorter generated asset slugs to reduce Windows path-length failures
- Improved support for large-batch ingest workflows
