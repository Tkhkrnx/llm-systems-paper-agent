# LLM Systems Paper Workflow

Customized for LLM inference systems, hierarchical state optimization, stateful/distributed systems, stream processing, runtime optimization, heterogeneous hardware, KV-cache management, RAG, and continual/agent-memory systems.

## Skills

- `start-my-day`: daily recommendation. Recommend 3 papers by default, then save PDF, convert PDF to Markdown with MinerU, save image/assets, and ask `paper-analyze` to create formal notes.
- `conf-papers`: search systems/architecture/HPC/parallel/database venues through DBLP plus Semantic Scholar enrichment.
- `paper-ingest`: ingest arXiv ID, PDF URL, or local PDF into Obsidian with PDF, MinerU Markdown, images, `assets.md`, and `ingest_manifest.json`.
- `paper-analyze`: create or deepen the formal paper note from ingested assets.
- `extract-paper-images`: extract paper figures when needed.
- `paper-search`: search existing notes in Obsidian.

## Priority Venues

Search broadly across A-level systems and AI venues because useful ideas for LLM inference/state optimization can appear in both.

Systems/architecture/HPC/parallel/data venues: MICRO, ASPLOS, SC, PPoPP, OSDI, SOSP, NSDI, EuroSys, USENIX ATC, FAST, HPCA, ISCA, ICS, VLDB, SIGMOD, SoCC, MLSys.

AI/ML/NLP/IR/web/data-mining venues: NeurIPS, ICML, ICLR, AAAI, IJCAI, ACL, EMNLP, NAACL, KDD, WWW, SIGIR, CIKM, RecSys, UAI, AISTATS, COLT, CVPR, ICCV, ECCV, MICCAI.

## Search Sources

Use sources together because no single API covers every known paper:

- arXiv API for preprints and recent papers;
- Semantic Scholar for enrichment, citations, and non-arXiv metadata;
- DBLP for conference proceedings;
- direct DOI/PDF/manual URL ingestion through `paper-ingest`;
- local PDF ingestion for papers found outside the APIs.

If a known paper is missing from automatic search, ingest it directly by PDF URL or local PDF path.

## Note Standard

Each paper note should include:

- exact paper identity and links;
- original PDF and MinerU Markdown links;
- ingested asset index and manifest links when available;
- advisor seven-question frame;
- survey five-field analytical frame:
  `State object`, `Control surface`, `Coupling path`, `Evaluation boundary`, `Remaining systems gap`;
- manual reading focus: must-read sections/figures/tables, skimmable parts, and suggested reading order;
- evidence-backed empirical claims;
- relation to nearby papers;
- confidence/readiness status.

Use `TBD` for missing evidence. Do not guess.
