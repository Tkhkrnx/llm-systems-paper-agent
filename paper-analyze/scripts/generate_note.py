#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a readable Chinese formal paper note from MinerU assets."""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import yaml


DEFAULT_VAULT = Path("C:/Users/peng/Documents/PHR/obsidian_phr")
DEFAULT_CONFIG = DEFAULT_VAULT / "99_System" / "Config" / "research_interests.yaml"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def is_missing(value: Optional[str]) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in {"", "TBD", "Unknown", "None"}
    return False


def clip_text(text: str, max_len: int = 320) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= max_len:
        return cleaned
    window = cleaned[:max_len]
    cut = max(window.rfind("。"), window.rfind("."), window.rfind("；"), window.rfind(";"))
    if cut > int(max_len * 0.55):
        return window[: cut + 1].strip()
    cut = window.rfind(" ")
    if cut > int(max_len * 0.75):
        return window[:cut].strip()
    return window.strip()


def obsidian_link(path: Path, vault: Path, label: Optional[str] = None) -> str:
    rel = path.relative_to(vault).as_posix() if path.is_relative_to(vault) else path.as_posix()
    rel = re.sub(r"\.md$", "", rel)
    return f"[[{rel}|{label or path.stem}]]"


def paper_id_to_url(paper_id: str, fallback: str) -> str:
    if re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", paper_id or ""):
        return f"https://arxiv.org/abs/{paper_id}"
    if fallback and re.match(r"^[a-zA-Z]:[\\/]", fallback):
        return ""
    return fallback or "TBD"


def clean_meta(value: Optional[str], fallback: str = "待确认") -> str:
    if is_missing(value):
        return fallback
    return str(value).strip()


def tag_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value or "").strip("-").lower()
    return slug or "uncategorized"


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_abstract(text: str) -> str:
    match = re.search(r"(?is)(?:^|\n)(?:abstract|摘要)\s*[-—:：]?\s*(.+?)(?:\n## |\n# |\nI\. |\n1\. |\Z)", text)
    if match:
        return clip_text(match.group(1), 600)
    return "TBD"


def extract_introduction(text: str) -> str:
    match = re.search(r"(?is)##\s+I\.\s+INTRODUCTION\s*(.+?)(?:\n##\s+II\.|\Z)", text)
    if match:
        return normalize_text(match.group(1))
    return ""


def split_sections(text: str) -> List[Tuple[str, str]]:
    pattern = re.compile(r"(?m)^##\s+([^\n]+)\n")
    matches = list(pattern.finditer(text))
    sections = []
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((title, body))
    return sections


def find_section(sections: List[Tuple[str, str]], keywords: List[str]) -> Tuple[str, str]:
    for title, body in sections:
        title_lower = title.lower()
        if any(keyword in title_lower for keyword in keywords):
            return title, normalize_text(body)
    return "TBD", ""


def extract_float(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return float(match.group(1).rstrip("."))


def extract_pair(pattern: str, text: str) -> Optional[Tuple[float, float]]:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def extract_triple(pattern: str, text: str) -> Optional[Tuple[float, float, float]]:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2)), float(match.group(3))


def collect_paper_facts(text: str) -> dict:
    facts = {
        "h2o_bpt": extract_float(r"matched budget of about\s+([0-9.]+)\s*BPT", text),
        "h2o_gain": extract_float(r"mean composite gain of\s+([0-9.]+)", text),
        "kivi_bpt": extract_float(r"matched dense operating point at around\s+([0-9.]+)\s*BPT", text),
        "decode_incremental": extract_pair(r"decode incremental allocation falls much more sharply to about\s+([0-9.]+)\s*(?:[×x])?\s*[–-]\s*([0-9.]+)\s*(?:[×x])?\s+of vanilla", text),
        "prefill_peak": extract_pair(r"prefill peak ratio stays close to parity to moderately above vanilla, ranging from about\s+([0-9.]+)\s+to\s+([0-9.]+)", text),
        "fit_frontier": extract_pair(r"The gain is\s+([0-9.]+)K tokens.*?and\s+([0-9.]+)K on Gemma-7B", text),
        "ttft": extract_triple(r"TTFT rises to\s+([0-9.]+)[×x],\s+([0-9.]+)[×x],\s+and\s+([0-9.]+)[×x]", text),
        "decode_latency": extract_triple(r"Decode latency also remains above vanilla, at\s+([0-9.]+)[×x],\s+([0-9.]+)[×x],\s+and\s+([0-9.]+)[×x]", text),
        "e2e_latency": extract_triple(r"end-to-end latency ratios are\s+([0-9.]+)[×x],\s+([0-9.]+)[×x],\s+and\s+([0-9.]+)[×x]", text),
    }
    return facts


def fmt_fact(value: object, fallback: str = "待确认") -> str:
    if value is None:
        return fallback
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, tuple):
        return "/".join(f"{item:g}" for item in value)
    return str(value)


def extract_figures(text: str) -> List[dict]:
    figures = []
    pattern = re.compile(r"!\[]\((images/[^\)]+)\)\s*\n?(?:\([a-z]\)\s*)?(?:\n)?Fig\.\s*(\d+[a-z]?)[:.]?\s*(.+)")
    for match in pattern.finditer(text):
        figures.append({
            "number": match.group(2).lower(),
            "caption": clip_text(match.group(3), 220),
        })
    return figures


def resolve_image_name(fig_no: str, manifest: dict) -> Optional[str]:
    image_dirs = manifest.get("image_dirs") or []
    candidates: List[str] = []
    for image_dir in image_dirs:
        folder = Path(image_dir)
        if not folder.exists():
            continue
        for item in folder.iterdir():
            if item.is_file() and item.name.lower().startswith(f"fig{fig_no}"):
                candidates.append(item.name)
    if not candidates:
        return None
    preferred = sorted(candidates, key=lambda name: ("-" not in name, len(name), name))
    return preferred[0]


def summarize_domain_reason(manifest: dict) -> str:
    domain = manifest.get("domain", "Uncategorized")
    domain_tag = tag_slug(domain)
    keywords = manifest.get("matched_keywords") or []
    if keywords:
        summary = f"主分类是 **{domain}**，因为标题、摘要和引言里反复出现了 `{', '.join(keywords[:8])}` 这些信号。"
    else:
        summary = f"主分类是 **{domain}**，这个判断主要依据论文标题、摘要和问题设置的整体语义。"
    return (
        f"{summary} 这些信号共同指向一个具体系统问题：长 prompt 在 prefill 后会变成 prompt-side KV cache，"
        "这份状态会占用显存，并在 decode 阶段被反复读取。本文要解释的是这份长期存在的运行时状态怎样被估值、怎样被压缩成可消费的 artifact，以及这种处理怎样影响后续 decode 的显存和延迟。"
    )


def concept_primer(text: str, domain: str) -> List[Tuple[str, str]]:
    lowered = text.lower()
    items = []

    def add_when(condition: bool, name: str, body: str) -> None:
        if condition and name not in {item[0] for item in items}:
            items.append((name, body))

    if "kv cache" in lowered:
        add_when(True,
            "什么是 KV cache",
            "KV cache 是模型把历史 token 的 key/value 表示缓存下来，避免每生成一个新 token 都重新算完整上下文。长上下文时它会线性膨胀，因此既占显存，也限制系统能处理的上下文长度和并发。"
        )
    if "prefill" in lowered or "decode" in lowered:
        add_when(True,
            "什么是 prefill / decode",
            "Prefill 是模型先一次性读完整个 prompt 并建立 prompt-side KV 的阶段；decode 是模型随后逐 token 生成输出并反复回读这份 prompt 状态的阶段。很多系统优化正是抓住了 prefill 只做一次、decode 会重复消费状态这一点。"
        )
    if "compression" in lowered or "quant" in lowered:
        add_when(True,
            "什么是 dense compression",
            "Dense compression 在本文里的含义是：prompt 里的每个 token 仍然有对应的 KV 表示，系统不把某些 token 的状态直接删除；压缩发生在表示精度上，也就是不同 token、不同 channel 可以用不同 bit budget 表示。这样读会更清楚：eviction 改变的是“哪些状态还存在”，dense compression 改变的是“这些状态用多高精度保存”。"
        )
    if "eviction" in lowered:
        add_when(True,
            "什么是 eviction",
            "Eviction 是根据某种重要性规则只保留一部分状态，把其余 token 或 head 对应的 KV 直接丢掉，以换取内存节省。它的收益直接，但在证据敏感任务里也更容易造成不可逆的信息损失。"
        )

    add_when("evidence-sensitive" in lowered or "evidence sensitive" in lowered,
        "什么是 evidence-sensitive workload",
        "Evidence-sensitive workload 指答案依赖上下文里具体证据片段的任务，例如长文档问答、RAG、代码定位、法律或医学材料问答。理解这类 workload 时要抓住证据 token 的稀疏性和不可替代性：它们可能只出现一次、位置很散、attention 分数未必一直最高，却可能是回答问题必须引用的依据。对这类任务来说，直接 eviction 某些 token 的风险更高，因为被删掉的证据在 decode 阶段无法再被模型读取；PREFILLCOMP 强调 full-prompt dense compression，正是为了降低这种不可逆证据丢失风险。"
    )
    add_when("prefillcomp" in lowered,
        "PREFILLCOMP 这个名字在说什么",
        "PREFILLCOMP 可以拆成 Prefill + Compression 来理解。它把压缩决策前移到 prefill 阶段，利用完整 prompt 的全局视野一次性估计 token importance 和 channel sensitivity，再把决策打包成 compressed prompt artifact。这个名字提醒读者：本文的核心是把 prefill 阶段的结构观察转成 decode 阶段可复用的运行时状态表示，因此它更接近推理系统里的状态重编码，和普通离线量化的关注点不同。"
    )
    add_when("bpt" in lowered or "bit per token" in lowered or "bits per token" in lowered,
        "什么是 BPT / matched budget",
        "BPT 在这里可以理解为每个 token 的 KV 状态平均分到多少 bit budget。论文用 matched budget 做对比，是为了避免一种不公平比较：某个方法看起来质量更好，只是因为它用了更多内存。matched-budget 对比要求不同方法在相近内存预算下比较 fidelity 或 composite gain，这样才能更清楚地判断预算分配策略本身是否更有效。"
    )
    add_when("ttft" in lowered or "time to first token" in lowered or "decode latency" in lowered or "end-to-end latency" in lowered,
        "TTFT、decode latency 和 end-to-end latency 分别是什么",
        "TTFT 是 Time To First Token，也就是从请求开始到模型吐出第一个输出 token 的时间，主要反映 prefill、调度、artifact 构建等首 token 前路径的开销。Decode latency 更关注后续逐 token 生成阶段每一步或整体 decode 的速度，反映压缩格式读取、解包和 attention 访问是否拖慢在线生成。End-to-end latency 是用户看到的总耗时，把 prefill、TTFT 前后的准备、decode 以及系统额外开销都算进去。读 PREFILLCOMP 的 Figure 9 时要把这三个指标分开：TTFT 高说明首 token 前成本重，decode latency 高说明生成阶段仍有持续开销，end-to-end latency 高说明最终用户体验受到整体影响。"
    )
    add_when("artifact" in lowered,
        "什么是 compressed prompt artifact",
        "Compressed prompt artifact 是 prefill 后物化出来的一份压缩状态包。它不只是压缩后的 K/V 数值，还包含 decode 阶段需要按正确格式读取这些状态的元数据。这个概念很重要，因为它把算法决策变成了 runtime 可以消费的数据对象：如果没有 artifact，token importance 和 bit allocation 只停留在分析层；有了 artifact，decode path 才能真正带着压缩后的 prompt state 运行。"
    )
    if not items:
        items.append((
            "理解本文前需要的背景",
            f"这篇论文主要落在 **{domain}**。读它时要先搞清楚它优化的是哪类状态对象、状态出现在推理流程的哪个阶段，以及作者是在删状态、压状态，还是重新安排状态如何被消费。"
        ))
    return items[:8]


def build_method_summary() -> str:
    return (
        "PREFILLCOMP 的方法本质上是一条从 prefill 观测到 decode 消费的完整状态处理链路，单独看某个压缩公式无法解释它的系统作用。"
        "更适合的讲法是把它当作一个在线推理系统改造：作者没有重新训练模型，也没有离线做一张固定量化表；他们在推理时抓住 prefill 已经产生的中间变量和 KV 张量，顺手提取两类状态价值信号，再把信号变成位宽分配，最后把原始 FP16 prompt KV 换成 decode 能读取的压缩状态对象。"
        "这条链路可以按原文的五个 phase 来讲，每一阶段都要看清楚它要解决的问题、具体改了什么、为什么能这样改，以及它带来的工程收益和代价。\n\n"
        "第一阶段是 **Prefill-Time Prompt Importance Extraction**。它的输入是 prefill 过程中已经计算出来的 causal attention 权重。"
        "这里先把基础概念说透：prefill 时模型会一次性处理整个 prompt，每一层每个 head 都会算一个因果注意力矩阵；矩阵第 `t` 行表示第 `t` 个位置作为 query 时看前面哪些 token，第 `i` 列表示第 `i` 个 prompt token 被后续多少位置看见。"
        "因此，如果把第 `i` 列从 `t=i` 到 prompt 末尾的 attention mass 加起来，再跨 layer 和 KV head 累加，就得到“这个 prompt token 被后续上下文反复使用的总量”。"
        "原文公式 2 做的就是这件事：把所有指向 prompt position `i` 的 causal attention-column mass 累加，然后用 `Z_I` 归一化，让所有 token 的 importance 加起来等于 1。"
        "工程实现上，作者 patch 了 HuggingFace 的 eager attention path，在 chunked prefill 的 attention forward 里顺手累加列和。"
        "这一步的关键收益是没有新增模型 forward pass：模型本来就要算 attention probabilities，作者只是在概率产生后额外做轻量累加。"
        "这一阶段的输出是一条 prompt-specific token importance vector `I`，它告诉 allocator：哪些 prompt 位置在当前 prompt、当前模型、当前 attention 行为下更值得保留高精度。"
        "它的代价主要是 attention path 里多了统计逻辑和缓存/累加开销；如果实现不够融合，这些开销会反映到 TTFT 上。\n\n"
        "第二阶段是 **Channel Sensitivity Characterization**。第一阶段只回答“哪个 token 重要”，但每个 token 的 K/V 表示内部还有很多 channel；同一个 token 的不同 channel 对量化误差的容忍度并不一样。"
        "可以把 prompt KV cache 想成一个已经躺在显存里的高维张量，维度大致包括 batch、prompt length、layer、KV head、head dimension，以及 K/V 类型。"
        "如果某个 channel 在 prompt 维度上的取值范围很大，那么用少量 bit 表示时更容易产生较大误差；取值范围较小的 channel 往往能用更低精度保存。"
        "所以作者在 prefill 完成后，直接对已经物化的 FP16 prompt K/V 张量沿 prompt length 维度做 reduction，计算每个 layer、KV head、channel 的 min 和 dynamic range，并在 head 内归一化 range。"
        "这一步为什么便宜：系统不用重新跑模型，不用重新算 attention，只是在现成 KV cache 上做类似 max/min 的张量归约；这类操作非常适合 GPU 并行执行。"
        "这一阶段的输出是 K/V channel-level sensitivity profile，也就是告诉 allocator 哪些表示维度更怕量化误差。"
        "它和第一阶段互补：第一阶段在 token 维度上判断“哪一列 prompt state 值得保护”，第二阶段在 channel 维度上判断“同一列里的哪些数值维度更难压”。\n\n"
        "第三阶段是 **Joint Budgeted Allocation**。这一阶段把前两阶段的信号真正变成 bit 分配。"
        "此时系统手里有 token importance `I`，有 channel range/sensitivity `R`，还要考虑 GQA/head sharing 带来的 architecture-aware correction `S`。"
        "原文对每个 layer、KV head、prompt position、channel 和 K/V 类型构造联合权重：`token importance × normalized channel range × architecture-aware correction`。"
        "这里的 architecture-aware correction 主要处理 supported GQA 模型：在 grouped-query attention 里，一个 KV head 会被多个 query head 共享，所以同一个 KV head 的误差会影响更多 downstream attention path。"
        "原文用 query-head sharing factor `G` 和 head dimension 归一化项来修正这种敏感度；标准 MHA 下 correction 默认是 1。"
        "得到联合权重 `W` 后，问题就变成带全局约束的预算分配：平均 bit budget 可能是 3 BPT 或 5 BPT，系统要决定每个位置用 2-bit、4-bit、8-bit 或其他支持档位，同时总预算不能超。"
        "原文采用 water-filling-style Lagrangian allocation，可以把它理解成找一个全局“水位线”参数：水位线给定后，每个元素根据自己的权重算出应得 bit；如果总 bit 超预算，就把水位线调得更严格；如果总 bit 低于预算，就放宽水位线。"
        "这个全局参数用 binary search 找，GPU 上可以并行评估所有元素在某个水位线下需要多少 bit。"
        "为避免临时权重张量过大导致 OOM，作者还实现了 chunked exact GPU solver，把 prompt/token block 分块处理，同时保持整体 bit budget 准确。"
        "这一阶段的输出已经落到具体的 per-token/per-channel/per-KV-type bit allocation；这一步之后，系统不再只知道“哪里重要”，而是知道每个位置应该用多少 bit 保存。\n\n"
        "第四阶段是 **Compressed Prompt Artifact Construction**。第三阶段只决定“哪里用多少 bit”，第四阶段把这个决策变成 decode 真的能读取的数据对象。"
        "这里先补一个量化背景：FP16 数值不能直接塞进 2-bit 或 4-bit 里，必须先用每个 channel 的 min/range 做 affine quantization，把连续浮点数映射到有限整数区间；例如 4-bit 只能表示 0 到 15，2-bit 只能表示 0 到 3。"
        "PREFILLCOMP 根据 Phase 3 的 bit allocation 对 prompt K/V 做量化，再用 variable-bit packing 把 2-bit、4-bit、8-bit 等不同宽度的小整数紧密塞进 byte stream。"
        "artifact 里至少有三类内容。第一是 **payloads**，也就是压缩打包后的 prompt K/V 字节流；第二是 **metadata**，包括 bit-width、min/range 等反量化所需信息，相当于解压说明书；第三是 **index**，记录不同 prompt tile 或 token block 在字节流里的位置，让 decode 不必从头扫描整段压缩数据。"
        "这一步很关键，因为没有 artifact，前面的 importance、sensitivity 和 allocator 仍然只是分析结果；有了 artifact，它们才变成 runtime 可以保存、传递、读取的 prompt-side state。"
        "建好 artifact 之后，原始 FP16 prompt KV 理论上可以释放，decode 阶段长期保留的是更小的 packed compressed representation。"
        "代价也在这里出现：packing、metadata 组织和 index 构建会增加首 token 前路径的工作量，Figure 9 里 Phase 4-5 的 TTFT 占比正是在暴露这一点。\n\n"
        "第五阶段是 **Decode-Time Integration**。decode 仍然按自回归方式生成新 token，新生成 token 的 KV 也正常增长；变化发生在模型回看 prompt-side state 时。"
        "基础路径是这样的：每生成一个新 token，模型会拿当前 query 去和 prompt K 做点积得到 attention score，再用 score 加权 prompt V 得到上下文表示。"
        "现在 prompt K/V 已经变成压缩 byte stream，标准 attention kernel 无法直接读取，所以作者 patch decode attention path，并用 Triton kernel 做 tiled fast path。"
        "当 query 需要访问某一块 prompt K/V 时，kernel 根据 artifact 的 index 找到对应压缩 payload，把这块数据读到 GPU 更靠近计算单元的缓存/片上存储中，再用 metadata 里的 min/range 和 bit-width 做 on-demand unpacking / dequantization，恢复近似 K/V，然后立即参与 attention 点积和加权计算。"
        "用完之后，这些临时恢复的 K/V 不写回主显存。"
        "这个设计背后的系统逻辑是用更多局部计算换更少 HBM 读取：decode 阶段通常受显存带宽和 KV 读取压力限制，压缩 payload 减少了从 HBM 搬运的字节数；额外解包计算如果能被 kernel 融合并留在片上完成，就有机会用计算换访存。"
        "PREFILLCOMP 的收益来自 decode 阶段持续读取更小的 prompt state；代价来自 prefill 侧统计、artifact build、metadata 组织和 decode 侧按需解包。"
        "Figure 8 说明 memory/capacity 收益确实存在，Figure 9 说明当前实现的 latency 代价还没有被完全消化。"
    )


def build_framework_figure_section(figures: List[dict], manifest: dict) -> str:
    asset_name = Path(manifest["asset_dir"]).name
    caption_by_no = {str(fig.get("number", "")).lower(): fig.get("caption", "") for fig in figures}
    image_files: List[str] = []
    for image_dir in manifest.get("image_dirs") or []:
        folder = Path(image_dir)
        if folder.exists():
            image_files.extend(item.name for item in folder.iterdir() if item.is_file())

    def pick_by_keywords(keywords: List[str]) -> Optional[str]:
        scored = []
        for name in image_files:
            lower = name.lower()
            if any(keyword in lower for keyword in keywords):
                score = sum(1 for keyword in keywords if keyword in lower)
                scored.append((-score, len(name), name))
        return sorted(scored)[0][2] if scored else None

    image_name = pick_by_keywords(["workflow", "flow", "pipeline", "overview"]) or resolve_image_name("5", manifest)
    if image_name:
        fig_no_match = re.search(r"fig0?(\d+[a-z]?)", image_name.lower())
        caption = caption_by_no.get(fig_no_match.group(1), "") if fig_no_match else ""
        caption_line = f"\n\nMinerU 图注线索：{caption}" if caption else ""
        return (
            f"![[20_Research/Papers/_assets/{asset_name}/mineru/{asset_name}/auto/images/{image_name}|800]]\n\n"
            "这张框架图只用来帮助建立方法的整体地图，不再承担实验结论解释。顺着图读，PREFILLCOMP 的数据流是："
            "prefill 先生成完整 prompt KV，同时收集 prompt-token importance；随后系统扫描已经物化的 KV cache，得到 channel-level sensitivity；"
            "allocator 把 token、channel 和 architecture-aware correction 三类信号合并，在 shared bit budget 下决定不同位置和维度的 bit-width；"
            "接着 Phase 4 把分配结果打包成 compressed prompt artifact；最后 decode 阶段在回看 prompt 时消费这份 artifact，完整 FP16 prompt cache 不再是主要 prompt-side 读取对象。"
            "这张图最重要的作用是把“观察发生在 prefill、状态物化成 artifact、收益发生在 decode”这三件事连起来。"
            "它说明方法是一条插进 serving path 的状态生命周期：生成状态、估值状态、重编码状态、再消费状态；离线量化表无法表达这条运行时链路。"
            f"{caption_line}"
        )

    for fig in figures:
        image_name = resolve_image_name(fig["number"], manifest)
        if image_name:
            return (
                f"![[20_Research/Papers/_assets/{asset_name}/mineru/{asset_name}/auto/images/{image_name}|800]]\n\n"
                "当前没有找到带 workflow/overview 语义短名的框架图，因此保留这张可定位图片。人工核对时应优先确认它是否对应方法 workflow；如果不对应，应回到 MinerU 图片目录选择真正的框架图。"
            )
    return "当前没有自动定位到稳定的方法框架图。"


def build_experiment_results(facts: dict) -> str:
    h2o_bpt = fmt_fact(facts.get("h2o_bpt"))
    h2o_gain = fmt_fact(facts.get("h2o_gain"))
    kivi_bpt = fmt_fact(facts.get("kivi_bpt"))
    decode_incremental = fmt_fact(facts.get("decode_incremental"))
    prefill_peak = fmt_fact(facts.get("prefill_peak"))
    fit_frontier = fmt_fact(facts.get("fit_frontier"))
    ttft = fmt_fact(facts.get("ttft"))
    decode_latency = fmt_fact(facts.get("decode_latency"))
    e2e_latency = fmt_fact(facts.get("e2e_latency"))
    return f"""### 实验设置
原文实验在单张 NVIDIA A100-40GB 上完成，使用 PyTorch、Transformers 和 Triton 组成的实现路径。这个设置要注意两点：第一，quality-oriented comparison 使用 integrated prompt-compression path；第二，systems-oriented result 使用 packed artifact path，并把 metadata accounting 纳入统计。论文把压缩后的 prompt artifact 放进实际 serving 路径里评估，评价对象不止是名义上的低比特模拟。模型覆盖 LLaMA-2-7B、Mistral-7B-v0.3、Gemma-7B-it、LLaMA-3.1-8B 和 DeepSeek-7B-Base，数据集覆盖 TriviaQA、2WikiMQA、GovReport，并额外用 NIAH 做系统容量压力测试。baseline 选择也围绕本文 claim 展开：H2O 代表 selective-retention / eviction 路线，KIVI 代表 fixed dense quantization 路线。

### Figure 1：dense full-prompt compression 为什么值得做
Figure 1 是 motivation 实验，主要负责支撑设计目标，完整方法的主结果还要看后面的 RQ 实验。它在约 {h2o_bpt} BPT 的 matched budget 下，用 TriviaQA 比较 PREFILLCOMP 和 H2O，并用 oracle-aligned BERTScore 衡量输出与 vanilla FP16 输出的接近程度。BPT 是平均每个 prompt token 使用多少 bit 来存储压缩后的 prompt state；matched budget 的意义是避免“谁用更多显存谁更好”的不公平比较。这个图证明的是：在 evidence-sensitive QA 中，保留 full prompt coverage 再降低精度，确实可能比直接 eviction 更稳。它给后文的方法设计提供动机，但还不能单独证明完整方法成立，因为这里主要是设计目标验证。

### Figure 2：为什么需要 token importance
Figure 2 验证 prompt-token influence 是否高度集中。图里的核心含义是：少量 prompt positions 承担了不成比例的 aggregate importance。这个观察支撑 Phase 1 的 causal-attention importance extraction：如果每个 token 对后续生成的影响差不多，那么按 token 分配不同 bit 没有必要；但如果影响高度偏斜，把更多精度给高影响 token 就有系统意义。这里的指标本质上是在问“哪些 prompt 位置被后续 causal attention 反复使用”。它证明 token 维度存在非均匀性。

### Figure 3：为什么还需要 channel sensitivity
Figure 3 验证 KV channel 维度也有明显非均匀性。原文计算每个 KV head 内不同 channel 的 dynamic range ratio，并在固定相对误差目标 epsilon = 5% 下估计可节省的 bit。dynamic range ratio 越大，说明同一个 head 内的 channel 分布差异越明显；在量化时，range 大的 channel 往往更需要精度保护，range 小的 channel 可以更激进压缩。这个图证明 Phase 2 有独立作用：只知道哪个 token 重要还不够，因为同一个 token 的不同 channel 对量化误差的敏感度也不同。

### Figure 4：为什么需要 architecture-aware correction
Figure 4 处理的是 GQA/head sharing 带来的结构性误差放大。GQA 中一个 KV head 会服务多个 query heads，所以压缩同一个 KV head 可能影响更多 downstream attention path。Figure 4(a) 看 normalized sensitivity 是否落在 acceptance band 内，Figure 4(b) 展示 raw amplification 和 correction 后的 normalized ratio。原文结果说明 LLaMA-3.1 和 Mistral 这类 supported GQA cases 上，head sharing 造成的 sensitivity shift 强且可预测；DeepSeek 和 Gemma 不完全符合该 correction。这个图支撑 Phase 3 的 architecture-aware term，同时也给出方法边界：correction 的证据主要落在 supported GQA family 上，不能直接外推成所有架构上的普适规律。

### Figure 5：方法框架图
Figure 5 是方法 workflow 图，它把 Phase 1 到 Phase 5 连成完整路径：prefill 提取 token importance，post-prefill 扫描 KV 得到 channel sensitivity，allocator 联合分配 bit，artifact construction 打包 prompt K/V 和 metadata，decode integration 按需消费压缩 artifact。这个图证明的是系统链路闭合，不证明性能收益。性能收益要看 Figure 6 到 Figure 9。

### Figure 6：与 H2O 的 matched-budget 对比
Figure 6 是回答 RQ1 的主图。实验问题是：在相同或相近存储预算下，保留所有 prompt token 并降低精度，是否比 eviction 更稳。Figure 6(a) 把 ROUGE-L、BLEU、cosine similarity 和 BERTScore 都作为与 vanilla FP16 oracle output 的接近程度来评估；Figure 6(b) 把结果汇总到 model-dataset combination 层面。原文给出的平均增益包括 +0.343 ROUGE-L、+0.296 BLEU、+0.347 cosine similarity、+0.107 BERTScore，composite gain 平均为 {h2o_gain}，且展示的组合都为正。这个结果支撑本文最核心的质量 claim：在证据敏感 workload 下，dense preservation 比 eviction 更不容易破坏输出行为。

### Figure 7：与 KIVI 的 dense-to-dense 对比
Figure 7 回答 RQ2：当两种方法都保留 full prompt context 时，prompt-aware variable-rate allocation 是否比 fixed low-bit quantization 更会花预算。原文把 KIVI-4bit 和 PREFILLCOMP 放在约 {kivi_bpt} effective BPT 的操作点比较，因为 KIVI 的 metadata 会让名义 4-bit 接近 5 BPT。图中 BLEU 和 ROUGE-L 显示 LLaMA-2、LLaMA-3.1 等 setting 上 PREFILLCOMP 有大幅提升，例如 L2-TQA 上 BLEU 从 0.123 到 0.760，ROUGE-L 从 0.317 到 0.843。这个图证明 variable-rate allocation 在部分 model family 上确实比固定 dense policy 更有效；同时 Mistral 和 DeepSeek 上 KIVI 仍有 competitive cases，这说明 prompt-aware signal 和 allocator 的有效性存在 family-specific boundary。

### Figure 8：系统内存和容量收益
Figure 8 回答 RQ3：PREFILLCOMP 给 serving 系统带来什么 memory behavior 和 fit capacity 收益。Figure 8(a) 区分 prefill peak、decode peak 和 decode incremental allocation。prefill peak ratio 大约为 {prefill_peak}，说明 prefill 侧因为统计和 artifact 构建并没有明显省内存；decode incremental memory 降到 vanilla 的 {decode_incremental}，说明真正收益出现在反复消费 prompt state 的 decode 阶段。Figure 8(b) 看 context-fit frontier，原文报告 LLaMA-2、LLaMA-3.1、Mistral、DeepSeek 提升约 5K tokens，Gemma-7B 提升约 4K tokens，把 frontier 从约 7-8K 推到 12K。这个结果支撑系统收益 claim：压缩 prompt artifact 能降低 decode-side state pressure，并把显存收益转化为更长可服务上下文。

### Figure 9：运行时代价和瓶颈来源
Figure 9 回答 RQ4：当前 runtime cost 从哪里来。Figure 9(a) 给出 latency ratios：TTFT 为 {ttft}x，decode latency 为 {decode_latency}x，end-to-end latency 为 {e2e_latency}x。TTFT 高说明首 token 前路径很重，通常来自 prefill 分析、artifact build 和 metadata 组织；decode latency 高说明按需读取和解包压缩格式也拖慢了生成阶段；end-to-end latency 高说明这些代价最终没有被系统完全摊掉。Figure 9(b) 进一步显示 Phase 4-5 work 占 method TTFT 的约 0.77/0.76/0.75，说明主要瓶颈集中在 artifact build 和 decode integration path，代价并非均匀散落在整个系统里。这个图是本文最重要的负面证据：方法确实换来了 memory/capacity 收益，但当前实现还没有达到低延迟 serving 所需的成熟度。
"""


def build_note(manifest: dict, vault: Path, md_text: str) -> str:
    normalized = normalize_text(md_text)
    abstract = manifest.get("abstract") if not is_missing(manifest.get("abstract")) else extract_abstract(normalized)
    intro = extract_introduction(normalized)
    sections = split_sections(normalized)
    _, design_body = find_section(sections, ["design", "method", "approach"])
    _, evaluation_body = find_section(sections, ["evaluation", "experiment", "results"])
    figures = extract_figures(normalized)
    facts = collect_paper_facts(normalized)
    h2o_bpt = fmt_fact(facts.get("h2o_bpt"))
    h2o_gain = fmt_fact(facts.get("h2o_gain"))
    kivi_bpt = fmt_fact(facts.get("kivi_bpt"))
    decode_incremental = fmt_fact(facts.get("decode_incremental"))
    prefill_peak = fmt_fact(facts.get("prefill_peak"))
    fit_frontier = fmt_fact(facts.get("fit_frontier"))
    ttft = fmt_fact(facts.get("ttft"))
    decode_latency = fmt_fact(facts.get("decode_latency"))
    e2e_latency = fmt_fact(facts.get("e2e_latency"))

    title = manifest.get("title", "TBD")
    paper_id = manifest.get("paper_id", "TBD")
    domain = manifest.get("domain", "Uncategorized")
    domain_tag = tag_slug(domain)
    today = datetime.now().strftime("%Y-%m-%d")
    asset_dir = Path(manifest["asset_dir"])

    primer = concept_primer(normalized, domain)
    primer_text = "\n\n".join(f"### {name}\n{body}" for name, body in primer)
    method_summary = build_method_summary()
    framework_figure_text = build_framework_figure_section(figures, manifest)
    experiment_results = build_experiment_results(facts)

    source_url = paper_id_to_url(paper_id, manifest.get("source_url", ""))
    pdf_link = obsidian_link(Path(manifest["pdf"]), vault, "原始 PDF")
    mineru_link = obsidian_link(Path(manifest["mineru_md"]), vault, "MinerU Markdown")
    translated_md = manifest.get("translated_md")
    translated_link = (
        obsidian_link(Path(translated_md), vault, "中文版 Markdown")
        if translated_md and Path(translated_md).exists()
        else ""
    )
    assets_link = obsidian_link(Path(manifest["assets_index"]), vault, "assets")
    authors = clean_meta(manifest.get("authors"))
    year = clean_meta(manifest.get("year"))
    source_line = f"- **来源链接**：{source_url}\n" if source_url else ""

    note = f"""---
date: "{today}"
paper_id: "{paper_id}"
title: "{title.replace('"', "'")}"
authors: "{authors.replace('"', "'")}"
year: "{year}"
venue: "待确认"
domain: "{domain}"
tags:
  - paper-note
  - {domain_tag}
  - llm-systems
status: analyzed
created: "{today}"
updated: "{today}"
---

# {title}

## 论文基本信息
- **论文 ID**：{paper_id}
- **作者**：{authors}
- **年份**：{year}
- **会议/期刊**：待确认
- **PDF**：{pdf_link}
- **MinerU Markdown**：{mineru_link}
- **中文版 Markdown**：{translated_link or '待生成'}
- **资产索引**：{assets_link}
{source_line}

## 一句话总结
这篇论文研究的是长上下文 LLM 推理里的 KV cache 压缩问题。讲清楚它要先抓住一个系统事实：prompt 在 prefill 后会变成跨层、跨 head、跨 token 的 K/V 状态集合，这份状态会留在显存里，并在 decode 的每一步被反复读取。PREFILLCOMP 这个名字可以理解成 prefill-native compression：它先在 prefill 阶段观察完整 prompt 形成的结构信号，再把有限 bit budget 分给更重要或更敏感的 token/channel，最后生成 decode 阶段可以直接消费的 compressed prompt artifact。原文的核心证据也围绕这条链路展开：约 {h2o_bpt} BPT 下对比 H2O，约 {kivi_bpt} BPT 下对比 KIVI，decode incremental memory 降到 vanilla 的 {decode_incremental}，但 TTFT 和 end-to-end latency 也分别升到 {ttft} 和 {e2e_latency}。这里的 TTFT 是首 token 前路径的时间，end-to-end latency 是用户请求的总耗时，所以这些数字说明方法有显存收益，也有在线服务必须继续消化的时间成本。

## 先修概念 / 背景铺垫
{primer_text}

## 资产分类判断 + 原因
{summarize_domain_reason(manifest)} 按这个分类读它时，重点要放在三件事上：第一，状态对象是 prefill 后生成并在 decode 中反复读取的 prompt KV；第二，压缩决策发生在 prefill 这个拥有完整 prompt 视野的阶段；第三，压缩结果会被打包成 artifact，并进入 decode 的实际数据路径。这样读，后面的公式和图就不会散掉。

## 导师七问
### 1. What is the problem?
背景解释：
长上下文推理的瓶颈来自一份会长期存在的状态。prefill 阶段读完整段 prompt 后，每一层都会为每个 prompt token 生成 K/V；decode 阶段每生成一个新 token，都要回看这些 K/V。prompt 变长时，这份 prompt-side KV 按 token 数线性增长，占用显存，也挤压 batch size、并发数和最大上下文长度。原文在 motivation 里把这个问题说得很直接：KV cache 在长上下文 serving 中已经是一阶系统瓶颈。

本文做法：
作者把问题具体化成一个状态预算分配问题：完整 prompt 的 KV 要继续保留，但不同 token 和 channel 不必用同样精度保存。原文先说明 evidence-sensitive workload 中删 token 会有不可逆风险；这里的 evidence-sensitive workload 指答案依赖具体上下文证据的任务，一旦相关 token 被删，后续 decode 就无法再读取这条证据。随后作者指出固定低比特量化会把预算平均撒给所有状态。PREFILLCOMP 因此把问题改写为：在保留完整 prompt 覆盖范围的条件下，哪些位置和维度应该拿到更高 bit budget，哪些部分可以更激进压缩。

关键结论与意义：
这篇论文的意义在于把 KV cache 从“模型内部中间张量”讲成了“推理系统里的状态资源”。一旦这样看，系统可以围绕它做估值、压缩、打包、迁移和复用。这个视角自然连接到分层状态管理、跨硬件 memory tiering、prefill/decode 解耦和 runtime scheduling。

### 2. Why it matters?
背景解释：
很多真实任务都依赖长上下文，比如 RAG、文档问答、长文摘要、代码理解和 agent memory。它们和普通短 prompt 最大的区别是：答案往往依赖 prompt 中某几个稀疏但关键的证据片段，而这些片段未必在 attention 分数上一直显眼。如果系统为了省显存过早删掉 token，那么模型后续生成时就不再拥有完整证据；在证据敏感任务里，这种信息缺失可能直接把可回答的问题变成不可回答的问题。

本文做法：
作者把 dense compression 作为独立目标来做，是因为它保留了 prompt state 的覆盖范围。每个 prompt token 仍然有 KV 表示，变化发生在表示精度上：重要 token、敏感 channel 得到更多 bit，影响小或误差容忍度高的部分得到更少 bit。原文用 H2O matched-budget 对比来支撑这个动机：在约 {h2o_bpt} BPT 下，PREFILLCOMP 在所有展示的 model-dataset 组合上相对 H2O 保持正增益，平均 composite gain 是 {h2o_gain}。

关键结论与意义：
这部分要讲给同学听，重点是“覆盖范围”和“精度分配”这两个层次要分开。覆盖范围决定模型还能不能看到每个 prompt token 的状态，精度分配决定有限显存预算花在状态的哪些部分。PREFILLCOMP 的系统价值就在于把质量保持和显存节省放进同一个控制问题里。

### 3. Why existing works fail?
背景解释：
现有工作大致可以分成删状态和压状态两类。删状态路线通常会根据 attention 或 token importance 保留一部分 KV，把其余部分丢掉；压状态路线通常保留全部 KV，但用固定低比特或统一策略压缩。它们的问题不完全一样：前者风险在于不可逆地丢掉证据，后者风险在于把所有状态都当作差不多重要，从而浪费精度预算。

本文做法：
作者认为 eviction / selective retention 的风险在于会不可逆地丢失证据，而 fixed dense quantization 的问题在于对所有 token 和 channel 一视同仁，没有利用 prompt 本身的不均匀结构。更细一点说，一个 token 可能在语义上重要，一个 channel 可能对量化误差特别敏感，这两个维度不应该被揉成一个粗糙分数。本文试图把 token-level 的重要性和 channel-level 的敏感性拆开估计，再在同一个预算分配器里联合使用。

关键结论与意义：
作者借这个切分把问题重新定义成：如果必须保留 full prompt state，那么有限精度预算到底应该优先花在什么地方。这个定义比“我要不要删 token”更适合引出系统研究，因为它背后其实是一个通用问题：当状态对象太大但不能简单丢弃时，runtime 应该如何给状态的不同部分定价，并把资源预算分配给最值得保真的部分。

### 4. What is the key idea?
背景解释：
真正有用的压缩来自两个判断：哪些状态更影响输出，哪些状态更怕误差。长 prompt 的 KV cache 由不同 token 位置和不同 channel 维度组成，它们对生成结果的贡献并不均匀。某些 token 可能承载答案证据，某些 channel 可能对量化误差更敏感；如果所有 token 和 channel 都用同样 bit-width，就会把预算花在低价值位置上，同时让高价值位置保护不足。

本文做法：
作者把 prefill 视为最佳观察时机，因为这时完整 prompt 一次性可见，而且这些分析成本只需要付一次。随后它联合 token importance、channel sensitivity 和架构修正项，在共享 bit budget 下做 variable-rate allocation。这里最值得讲清楚的是“为什么在 prefill 做”：decode 阶段每一步都在生成新 token，如果此时再反复做复杂统计，会直接拖慢在线生成；prefill 虽然本身也有成本，但它只发生一次，而且正好拥有完整 prompt 的全局视野，因此适合作为状态估值窗口。

关键结论与意义：
关键 idea 可以按三步讲：第一，prefill 看到完整 prompt，所以它适合估计状态价值；第二，估计结果进入 shared bit budget allocator，实际改变每部分 KV 的表示精度；第三，allocator 的输出被打包成 compressed prompt artifact，让 decode 阶段消费一个已经重编码的状态对象。这三步连起来，才是本文方法的核心。

### 5. What is the design?
背景解释：
一个压缩想法要落到推理系统里，必须闭合完整执行链路。这里要带着系统实现问题去读：输入是什么，系统在什么时候插入统计逻辑，统计结果如何变成 bit allocation，压缩结果如何存储，decode 又如何读取。如果这些环节中任何一个没有闭合，方法就停留在离线分析层面，不能真正改变 serving path。

本文做法：
作者的设计链条可以顺着数据流讲。输入是 prefill 后已经生成的 prompt KV 和 attention 行为；第一步从 causal attention 中估计 token importance，回答“后续 decode 更可能依赖哪些 prompt 位置”；第二步从 KV channel 的动态范围和误差敏感度估计 channel sensitivity，回答“哪些维度被低比特表示后更容易伤害输出”；第三步加入 GQA/head sharing 相关的 architecture-aware correction，避免共享 KV head 的结构放大误差；第四步由 variable-rate allocator 在 shared bit budget 下给不同 token/channel 分配精度；最后输出 compressed prompt artifact，decode 阶段直接读取这份 artifact。

关键结论与意义：
对你的研究最有启发的，其实就是这条完整链路本身，因为它很容易迁移到更一般的分层状态管理和跨层协同优化问题。比如未来你可以把“bit budget”替换成 GPU/CPU/CXL/SSD 的 placement budget，把“压缩 artifact”替换成可迁移状态对象，把“prefill 观测”替换成 runtime profiling 或 workload prediction。

### 6. What is the experimental plan?
背景解释：
系统论文的实验需要把收益和代价拆开看。对这篇论文来说，压缩率本身只能说明状态变小了，还不能说明模型是否仍能利用 prompt 证据，也不能说明在线推理是否真的能服务更长上下文。更合理的读法是按三条证据线来读：质量线看同等预算下 fidelity 是否保持，容量线看 decode 阶段显存是否释放，代价线看 TTFT、decode latency 和 end-to-end latency 增加到什么程度。

本文做法：
实验主要围绕三个边界展开。第一条边界是和 H2O 这类 eviction 路线做 matched-budget 对比，matched budget 的意思是在相近内存预算下比较方法，避免某个方法只是因为用更多 bit 才显得效果好；这条边界用来说明保留 full prompt state 后再做 variable-rate compression 是否更稳。第二条边界是和 KIVI 这类固定 dense quantization 对比，用来说明 prompt-aware 的 bit allocation 是否真的比统一低比特更会花预算。第三条边界是系统资源边界，论文用 prefill peak、decode incremental allocation、context-fit frontier 和 latency ratios 来说明收益出现在哪个阶段、代价又集中在哪个阶段。

关键结论与意义：
把这些实验连起来看，PREFILLCOMP 的结论是有层次的：它在质量保持上证明了 full prompt dense compression 的动机，在 decode memory 上证明了压缩 artifact 对 serving 状态占用有帮助，同时也通过 Figure 9 暴露了当前实现的在线延迟压力。组会里讲实验时，不要把它讲成“效果更好”四个字，而要讲成：这套方法把显存问题往 decode 阶段推进了一步，但 prefill 侧统计、artifact 构建和压缩格式读取仍然是后续系统优化必须处理的成本来源。

### 7. What is the takeaway?
背景解释：
这篇论文最值得带走的是它对推理状态生命周期的拆解。长上下文 LLM serving 里的 KV cache 会经历生成、保存、压缩、再消费几个阶段；不同阶段看到的信息不同，能承受的开销也不同。prefill 拥有完整 prompt 的全局视野，适合做一次性的状态估值；decode 对延迟更敏感，适合消费已经物化好的轻量状态表示。这个阶段差异，是本文整个设计成立的基础。

本文做法：
作者通过 matched-budget fidelity、decode-side memory 改善和 latency 代价三个面向，把 PREFILLCOMP 的价值边界交代了出来。这里的 fidelity 可以理解成“压缩以后模型还能不能利用 prompt 证据完成任务”，decode-side memory 指逐 token 生成阶段需要持续占用的 prompt 状态显存，latency 则要拆成 TTFT、decode latency 和 end-to-end latency 分别看。原文的数字说明这条路确实能降低 decode 侧状态占用，但 Figure 9 的 latency ratios 也说明当前实现还没有把额外计算和数据格式开销完全压下去。换句话说，PREFILLCOMP 更像是在给出一个清晰的 design point：先在 prefill 做状态估值，再把估值结果固化成 decode 可消费的压缩状态。

关键结论与意义：
这篇论文可以抽象成一个可复用的系统模式：先估计状态价值，再据此分配预算，最后把决策物化成后续阶段可消费的状态工件。这个模式可以成为你之后做分层状态优化的基本范式：同一份状态在不同生命周期阶段可以有不同表示、不同放置位置和不同调度策略；runtime 的任务就是在质量、容量和延迟之间做有证据支撑的分配。

## 综述五字段
### 1. State object
论文主要管理和优化的状态对象是 `prompt-side KV cache`。这句话要展开讲：在长上下文推理里，prompt 一旦 prefill 完成，就会变成一份跨层、跨 head、跨 token 的 K/V 状态集合；这份状态之后会在 decode 的每一步被 attention 访问。作者关注的资源瓶颈，就是这份已经生成、需要保留、会被反复消费的 prompt 状态。把对象限定在 prompt-side KV 上很重要，因为它解释了为什么论文选择 prefill 作为观察窗口，也解释了为什么收益主要体现在 decode 阶段的状态读取和显存占用上。

### 2. Control surface
论文显式暴露的控制面包括：token importance、channel sensitivity、architecture-aware correction、shared bit budget allocation，以及 decode 侧如何消费压缩 artifact。可以把它理解成四层控制：先判断哪些 token 位置更值得保真，再判断哪些 channel 对量化误差更敏感，然后把这些信号映射成实际 bit allocation，最后把压缩后的状态组织成 decode 可以读取的数据格式。这个控制面横跨模型结构、数值表示和 runtime 数据路径，所以它很适合继续接到分层状态优化、memory tiering 和 serving scheduler 上。

### 3. Coupling path
模型的 attention 结构决定 token importance，张量统计决定 channel sensitivity，架构特性决定 correction factor，最后这些信号一起落到 serving path 上，形成 prefill 和 decode 之间的系统耦合。这里的耦合关系值得细读：模型侧提供“哪些状态可能重要”的结构信号，系统侧把这些信号变成“如何分配有限资源”的决策，硬件侧再通过显存容量和访问代价限制这个决策能否高效部署。本文的系统味道就在这条链路里：模型观测、压缩表示和推理运行时围绕同一份 prompt 状态形成闭环。

### 4. Evaluation boundary
作者主要在 fidelity、memory footprint、context-fit frontier 和 latency 四个边界上评估设计。fidelity 回答“压缩后模型还能不能正确利用 prompt”；memory footprint 回答“状态对象有没有真的变小”；context-fit frontier 回答“省出来的显存是否能换成更长上下文或更大 batch”；latency 回答“这些收益会带来多大的在线代价”。这四个边界放在一起，才能完整解释 PREFILLCOMP 的价值：它既有质量和容量收益，也有必须继续优化的 runtime cost。

### 5. Remaining systems gap
这篇论文最明显的系统短板是 runtime cost，尤其 prompt-side artifact build 和 decode integration 的延迟代价较高。更具体地说，PREFILLCOMP 证明了“prefill 原生状态估值 + 稠密压缩”这个 design point 有价值，但生产级 serving 栈还需要回答更多工程问题：统计和压缩能否和 prefill kernel 融合，artifact format 能否被高效分页和调度，压缩状态能否跨请求、跨 GPU、跨 memory tier 复用，以及它和 continuous batching / prefix caching / prefill-decode disaggregation 放在一起时会不会产生新的瓶颈。因此这篇论文适合作为 state-aware serving 的研究起点，后续工作需要把状态表示和 runtime 管理真正接起来。

## 方法整体机制总结
{method_summary}

## 分析框架图
{framework_figure_text}

## 实验设置和关键结果
{experiment_results}

## 与已有工作的关系
作者实际上在和两条路线对话：一条是 H2O 这类 eviction / selective retention 路线，另一条是 KIVI 这类 fixed dense quantization 路线。H2O 的核心问题是“在预算有限时哪些 token 应该留下”，所以它改变的是状态覆盖范围；KIVI 的核心问题是“整份 KV 能否用统一低比特表示”，所以它主要改变的是整体表示精度；PREFILLCOMP 的问题设定介于二者之间，它保留 full prompt coverage，然后在 token 和 channel 两个维度上分配不同精度。这个定位很关键，因为它把状态管理从二选一的“保留/删除”扩展成更细粒度的“保留范围 + 表示精度 + 后续消费格式”联合设计。

## 对你研究方向的价值
它和你的主方向高度对齐，因为论文直接优化了长上下文推理中的 KV cache 状态对象，并且把优化点放在 prefill/decode 交界处。对“分层状态优化与协同优化”来说，这篇论文提供了一个非常具体的 case：状态对象是 prompt KV，状态估值发生在 prefill，状态重编码产生压缩 artifact，状态消费发生在 decode，收益边界是 memory/context，代价边界是 runtime latency。这个 case 可以自然推广：bit-width 是一种资源预算，GPU/CPU/CXL placement 也是资源预算；compressed artifact 是一种状态表示，跨请求 prefix cache、跨 GPU 迁移状态、失败恢复 checkpoint 也都需要状态表示。读这篇论文时可以重点思考：如果 runtime 已经知道某些状态更重要、更敏感、更可能被复用，它还能不能进一步决定这些状态放在哪里、什么时候迁移、由哪个请求共享、由 scheduler 如何调度。

## 局限性与 Open Gap
### 论文局限
第一，延迟代价偏高，尤其在线 serving 时不容易直接消化。Figure 9 给出的 TTFT、decode latency 和 end-to-end latency ratios 说明，当前实现为了获得 prompt-aware allocation 付出了明显 runtime cost。这个问题会直接影响长上下文服务的首 token latency、吞吐和排队延迟；如果 artifact build 不能和 prefill kernel 融合，或者压缩格式读取不能在 decode 端高效执行，显存收益就会伴随用户可感知的响应延迟增加。

第二，论文已经证明 prompt-aware variable-rate dense compression 有价值，但生产系统需要的状态管理闭环还没有完全展开。具体来说，论文主要展示单篇工作中的压缩、容量和延迟结果；真正放进 serving runtime 后，还要处理 paged KV 管理、batch 内不同请求的压缩布局、多租户 admission control、跨 GPU 状态迁移，以及失败恢复时 artifact 一致性等问题。这些问题会决定 compressed prompt artifact 能否从论文原型变成 runtime 可管理的一等状态对象。

第三，架构相关修正项对不同 model family 的泛化性还需要更强证据。因为 token importance 和 channel sensitivity 都可能受模型结构、训练方式、上下文分布影响，如果换成不同 attention 结构、不同量化友好程度的模型，当前信号是否仍然稳定，需要更多跨模型验证。

### 可以继续追问的系统问题
第一个问题是：能否把这套 state-aware allocation 和 paged KV / tiered memory 结合？也就是说，高价值高敏感状态留在 GPU，高压缩低敏感状态下沉到 CPU/CXL，甚至把 bit allocation 和 placement allocation 合并成一个联合优化问题。

第二个问题是：能否把压缩 artifact 进一步变成 GPU/CPU/CXL/SSD 之间可迁移的统一状态对象？如果 artifact 只是一个本地压缩 buffer，那它的系统价值有限；如果它能被 runtime 识别、迁移、复用和恢复，它就更接近分布式推理系统里的状态管理单元。

第三个问题是：能否和 continuous batching、prefix caching、prefill-decode disaggregation 联合设计？这些机制都会改变 KV 的生命周期和访问模式，而 PREFILLCOMP 目前更像单请求内的压缩链路。下一步真正有系统味道的工作，是把状态估值和 serving scheduler 放到同一个闭环里。

## 人工阅读重点：读完笔记后回原文查漏补缺
读完这份笔记后，不需要从头把论文再顺读一遍。更高效的方式是带着缺口回原文核对：笔记已经帮你建立了问题、方法、图表和局限的主线，原文精读应该用来确认笔记里最容易遗漏或误解的技术细节。

### 必须回原文核对的部分
**Method / Design 中关于 token importance、channel sensitivity、architecture-aware correction 和 allocator 的段落** 需要回原文核对。笔记已经说明了这四个组件的作用，但原文里的公式、归一化方式、预算约束和实现细节会决定这个方法到底是启发式规则、可优化目标，还是一个可复用的 runtime policy。读这部分时只需要回答一个问题：作者到底如何把观测信号变成 bit allocation。

**方法框架图和对应正文说明** 需要回原文核对。这里的目的是确认 workflow 图中的每个箭头是否在正文里有实现解释：prefill 统计在哪里插入，artifact 什么时候生成，metadata 包含什么，decode 如何消费压缩状态。图很清楚但正文缺少实现细节时，你要把它视为系统设计证据不足，而不能只按图理解。

**实验图中所有核心指标的定义和统计口径** 需要回原文核对，尤其是 BPT、matched budget、decode incremental memory、context-fit frontier、TTFT、decode latency 和 end-to-end latency。笔记里已经解释了这些指标的含义，但原文会告诉你它们是按哪个模型、哪个数据集、哪个上下文长度、哪个 batch 或硬件配置统计出来的。这个口径决定实验结论能不能推广。

**Figure 8 / Figure 9 附近的实验设置和结果讨论** 需要回原文核对。Figure 8 主要支撑 memory/context 收益，Figure 9 主要暴露 latency 代价；你回原文看这两处，是为了确认作者有没有把收益和代价放在同一个 serving 场景里比较。如果收益来自一种 setting，代价来自另一种 setting，结论力度就会变弱。

### 可以暂时不细读的部分
参考文献列表、次要数据集介绍和重复解释趋势的结果段落可以先跳过。它们对写 related work 和补充背景有用，但在你已经读完这份笔记之后，最需要补的是方法公式、系统路径和实验口径，背景信息可以放到后面再查。

### 查漏补缺后的判断标准
回原文核对后，你应该能补上三件事：第一，PREFILLCOMP 的四个组件各自输入什么、输出什么；第二，关键实验图里的每个指标如何定义，数据证明的是质量、容量还是代价；第三，论文当前没有解决的系统问题到底是实现优化问题，还是方法本身泛化性不足。只有这三件事都能回答，才说明你已经越过故事线，真正读到了这篇论文的技术边界。

## 可提炼的研究命题
第一个命题：是否可以把本文的 prompt-aware allocation 扩展成跨 memory tier 的 state placement 决策？也就是让 token/channel 的价值估计不仅决定压缩位宽，还决定这部分状态留在 GPU、放到 CPU、迁到 CXL，还是以更低成本格式持久化。

第二个命题：是否可以同时联合 state compression、state migration 和 runtime scheduling？例如，当 scheduler 知道某个请求的 prompt state 很大但复用价值高时，它可以选择更激进的压缩、更保守的迁移，或者把该请求安排到拥有更合适 memory tier 的设备上。这里的关键问题是把状态价值、迁移成本和排队延迟放进同一个 runtime 决策模型。

第三个命题：是否可以把 artifact 从“压缩 prompt KV”扩展成“统一的层次化状态表示”？如果 artifact 能包含压缩格式、放置位置、复用范围、恢复策略和生命周期元数据，它就可能成为 LLM serving runtime 里的基本状态管理单元。
"""
    return note


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a formal paper note from MinerU assets.")
    parser.add_argument("--manifest", required=True, help="Path to ingest_manifest.json")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    _config = read_yaml(Path(args.config))
    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)
    if not manifest.get("mineru_md"):
        raise SystemExit("Manifest does not contain mineru_md. Run paper-ingest successfully first.")

    md_path = Path(manifest["mineru_md"])
    md_text = read_text(md_path)
    extracted_abstract = extract_abstract(md_text)
    if is_missing(manifest.get("abstract")) and not is_missing(extracted_abstract):
        manifest["abstract"] = extracted_abstract

    note_path = Path(manifest["suggested_note"])
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_text = build_note(manifest, vault, md_text)
    note_path.write_text(note_text, encoding="utf-8")

    manifest["note_state"] = "analyzed"
    manifest["updated"] = datetime.now().strftime("%Y-%m-%d")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "status": "analyzed",
        "note": str(note_path),
        "manifest": str(manifest_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
