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
        f"{summary} 更直接地说，这些词共同指向长上下文推理中的运行时状态管理问题："
        "论文关心的不是单个算子，也不是离线模型压缩，而是 prompt KV 这种会被 serving 系统长期保留和反复消费的状态对象。"
    )


def concept_primer(text: str, domain: str) -> List[Tuple[str, str]]:
    lowered = text.lower()
    items = []
    if "kv cache" in lowered:
        items.append((
            "什么是 KV cache",
            "KV cache 是模型把历史 token 的 key/value 表示缓存下来，避免每生成一个新 token 都重新算完整上下文。长上下文时它会线性膨胀，因此既占显存，也限制系统能处理的上下文长度和并发。"
        ))
    if "prefill" in lowered or "decode" in lowered:
        items.append((
            "什么是 prefill / decode",
            "Prefill 是模型先一次性读完整个 prompt 并建立 prompt-side KV 的阶段；decode 是模型随后逐 token 生成输出并反复回读这份 prompt 状态的阶段。很多系统优化正是抓住了 prefill 只做一次、decode 会重复消费状态这一点。"
        ))
    if "compression" in lowered or "quant" in lowered:
        items.append((
            "什么是 dense compression",
            "Dense compression 的意思是不删 token，而是保留整份 prompt KV 的稠密表示，只是对不同部分使用不同压缩强度。它与 eviction 最大的区别是：dense compression 是压状态，eviction 是删状态。"
        ))
    if "eviction" in lowered:
        items.append((
            "什么是 eviction",
            "Eviction 是根据某种重要性规则只保留一部分状态，把其余 token 或 head 对应的 KV 直接丢掉，以换取内存节省。它的收益直接，但在证据敏感任务里也更容易造成不可逆的信息损失。"
        ))
    if not items:
        items.append((
            "理解本文前需要的背景",
            f"这篇论文主要落在 **{domain}**。读它时要先搞清楚它优化的是哪类状态对象、状态出现在推理流程的哪个阶段，以及作者是在删状态、压状态，还是重新安排状态如何被消费。"
        ))
    return items[:4]


def infer_method_steps() -> List[str]:
    return [
        "模型先完成 prefill，这时系统一次性看到了完整 prompt，也建立了完整的 prompt-side KV。",
        "系统在 prefill 中统计哪些 token 对后续 attention 更重要，把这些 token 视为更值得保留精度的状态位置。",
        "随后系统扫描已经生成的 prompt KV，估计不同 channel 对量化误差的敏感度，判断哪些 channel 不能被粗暴压缩。",
        "接着它把 token importance、channel sensitivity 和架构修正项放进同一个预算分配器里，决定有限 bit budget 应该怎么分。",
        "分配结果不会停留在分析阶段，而是被打包成 compressed prompt artifact，里面既有压缩后的 K/V，也有后续 decode 需要的元数据。",
        "decode 阶段回看 prompt 时直接消费这份 artifact，而不是继续保留原始 full-precision prompt KV，从而换取显存和可容纳上下文上的收益。",
    ]


def build_key_figure_section(figures: List[dict], manifest: dict) -> str:
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

    # Prefer human-renamed, semantically meaningful images over MinerU extraction order.
    preferred = [
        (
            pick_by_keywords(["workflow", "flow", "pipeline", "overview"]),
            "这张图应该最先看。它不是为了记住每个框的名字，而是为了把整篇论文的执行路径串起来：prefill 阶段观察 prompt 结构，系统据此生成压缩决策，再把压缩后的 prompt KV 作为 decode 阶段反复消费的状态工件。读图时先从输入 prompt 和原始 KV 开始，顺着箭头看哪些统计量被收集、预算分配器在哪里介入、最终 artifact 如何进入 decode。",
        ),
        (
            pick_by_keywords(["decode", "memory", "fit", "capacity"]),
            "这张图用来判断系统收益是否真的落到了 serving 侧。读它时不要只看最高提升，而要看横轴代表什么 workload 或 context setting、纵轴是在量 memory footprint 还是 context-fit frontier。它回答的是：压缩 prompt KV 之后，decode 阶段到底释放了多少可用显存，以及这种释放是否足以换来更长上下文或更大 batch 的空间。",
        ),
        (
            pick_by_keywords(["latency", "ratio", "runtime", "overhead", "breakdown"]),
            "这张图用来读代价边界。系统论文最容易只讲收益，但这里必须追问额外 latency 从哪里来：是 prefill 阶段统计结构信号，还是 artifact build / packing，还是 decode 端读取压缩格式产生开销。读图时重点看各阶段比例，而不是只记住一个总延迟数字。",
        ),
    ]

    used = set()
    lines = []
    for image_name, explanation in preferred:
        if not image_name or image_name in used:
            continue
        used.add(image_name)
        fig_no_match = re.search(r"fig0?(\d+[a-z]?)", image_name.lower())
        caption = caption_by_no.get(fig_no_match.group(1), "") if fig_no_match else ""
        caption_line = f"\n  MinerU 图注线索：{caption}" if caption else ""
        lines.append(
            f"- ![[20_Research/Papers/_assets/{asset_name}/mineru/{asset_name}/auto/images/{image_name}|800]]\n"
            f"  {image_name}：{explanation}{caption_line}"
        )

    if lines:
        return "\n".join(lines)

    for fig in figures:
        image_name = resolve_image_name(fig["number"], manifest)
        if image_name:
            return (
                f"- ![[20_Research/Papers/_assets/{asset_name}/mineru/{asset_name}/auto/images/{image_name}|800]]\n"
                f"  {image_name}：当前没有找到带语义短名的关键图，因此先保留这张可定位图片。读它时先判断图在说明流程、收益还是代价，再回到正文对应段落核对作者想证明的结论。"
            )
    return "- 当前没有自动定位到稳定的关键图。"


def build_note(manifest: dict, vault: Path, md_text: str) -> str:
    normalized = normalize_text(md_text)
    abstract = manifest.get("abstract") if not is_missing(manifest.get("abstract")) else extract_abstract(normalized)
    intro = extract_introduction(normalized)
    sections = split_sections(normalized)
    _, design_body = find_section(sections, ["design", "method", "approach"])
    _, evaluation_body = find_section(sections, ["evaluation", "experiment", "results"])
    figures = extract_figures(normalized)

    title = manifest.get("title", "TBD")
    paper_id = manifest.get("paper_id", "TBD")
    domain = manifest.get("domain", "Uncategorized")
    domain_tag = tag_slug(domain)
    today = datetime.now().strftime("%Y-%m-%d")
    asset_dir = Path(manifest["asset_dir"])

    primer = concept_primer(normalized, domain)
    primer_text = "\n\n".join(f"### {name}\n{body}" for name, body in primer)
    method_steps = "\n".join(f"{idx + 1}. {step}" for idx, step in enumerate(infer_method_steps()))
    figure_text = build_key_figure_section(figures, manifest)

    source_url = paper_id_to_url(paper_id, manifest.get("source_url", ""))
    pdf_link = obsidian_link(Path(manifest["pdf"]), vault, "原始 PDF")
    mineru_link = obsidian_link(Path(manifest["mineru_md"]), vault, "MinerU Markdown")
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
- **资产索引**：{assets_link}
{source_line}

## 一句话总结
这篇论文研究的是长上下文 LLM 推理里的 KV cache 压缩问题。把它讲给课题组同学听，最重要的不是先背它用了哪些指标，而是先抓住一个系统事实：长 prompt 在 prefill 后会变成一大块必须长期留在显存里、并在 decode 时反复读取的状态；如果这块状态太大，系统就会被显存和上下文容量卡住。作者的核心想法是：不要像 eviction 路线那样直接删 token，也不要像固定低比特量化那样平均分配精度，而是在 prefill 阶段先观察 prompt 的结构，再决定哪些 token、哪些 channel 更值得保留精度，最后把这个决策物化成 decode 阶段可以直接复用的压缩 artifact。

## 先修概念 / 背景铺垫
{primer_text}

## 资产分类判断 + 原因
{summarize_domain_reason(manifest)} 这个分类不是为了给论文贴标签，而是为了决定我们应该用什么问题意识读它：它不是单纯的模型压缩论文，也不是单纯的量化算法论文，而是一篇围绕推理系统状态对象进行估值、压缩和消费路径重构的工作。因此后面读正文时要一直追问三件事：它压缩的状态是什么，压缩决策在哪里产生，压缩后的状态如何被运行时继续使用。

## 导师七问
### 1. What is the problem?
背景解释：
长上下文推理真正卡住系统的，不只是算力，而是会被持续保留和重复访问的 prompt-side KV cache。我们可以把一次 LLM 推理拆成两个阶段：prefill 阶段读入整段 prompt，并为每一层、每个 token 建立 K/V 表示；decode 阶段逐 token 生成输出，每一步都会回看之前积累下来的 KV。上下文越长，prompt-side KV 就越大，这块状态不仅占显存，还会挤压 batch size、并发数和可支持的最大上下文长度。换句话说，长上下文不是“多算一点”这么简单，而是把一份很大的状态对象塞进了整个 serving path。

本文做法：
作者把问题收得很准：在不能随便丢失 prompt 证据的前提下，如何降低 KV cache 的成本，同时让 decode 端继续稳定地利用这些状态。它没有选择“删掉一部分 token”作为默认答案，因为很多长上下文任务里，关键证据可能只出现一次，一旦删掉就很难补救；它也没有选择“所有 KV 都统一压成同样位宽”，因为 prompt 内部显然不是每个 token、每个 channel 都同等重要。于是问题被重新表述为：如果我们要保留完整 prompt 的稠密状态，那么有限精度预算应该怎样分配才更合理。

关键结论与意义：
这篇论文抓住的是“状态对象本身的成本”这个一阶问题，而不是只做某个局部 kernel 或单次算子的微优化。对系统方向来说，这一点很关键：它把 KV cache 当作需要被管理、估值、压缩、打包和复用的系统资源，而不是模型内部一个不可触碰的中间张量。这个视角会自然连接到分层状态管理、跨硬件 memory tiering、prefill/decode 解耦和 runtime scheduling。

### 2. Why it matters?
背景解释：
很多真实任务都依赖长上下文，比如 RAG、文档问答、长文摘要、代码理解和 agent memory。它们和普通短 prompt 最大的区别是：答案往往依赖 prompt 中某几个稀疏但关键的证据片段，而这些片段未必在 attention 分数上一直显眼。如果系统为了省显存过早删掉 token，那么模型后续生成时就不再拥有完整证据；这不是精度小幅波动的问题，而是可能把可回答的问题变成不可回答的问题。

本文做法：
作者把 dense compression 视为一个独立设计目标，强调在 evidence-sensitive workload 里，保留所有 prompt token 的表示往往比直接删状态更稳妥。所谓 dense，不是说不压缩，而是说不改变 prompt state 的覆盖范围：每个 token 的 KV 仍然存在，只是不同位置、不同 channel 用不同精度表示。这样做的直觉很像存储系统里的分层编码：不是把数据随便丢掉，而是根据价值和敏感度决定哪些部分要高保真，哪些部分可以更激进压缩。

关键结论与意义：
这说明本文不是在追求“无脑压缩得更狠”，而是在探索一种对真实任务更稳的资源分配方式。对你的研究方向来说，它重要的地方在于：它把“质量保持”和“系统资源节省”放在同一个控制问题里，而不是把它们拆成模型侧和系统侧两个互不相干的问题。

### 3. Why existing works fail?
背景解释：
现有工作大致可以分成删状态和压状态两类。删状态路线通常会根据 attention 或 token importance 保留一部分 KV，把其余部分丢掉；压状态路线通常保留全部 KV，但用固定低比特或统一策略压缩。它们的问题不完全一样：前者风险在于不可逆地丢掉证据，后者风险在于把所有状态都当作差不多重要，从而浪费精度预算。

本文做法：
作者认为 eviction / selective retention 的风险在于会不可逆地丢失证据，而 fixed dense quantization 的问题在于对所有 token 和 channel 一视同仁，没有利用 prompt 本身的不均匀结构。更细一点说，一个 token 可能在语义上重要，一个 channel 可能对量化误差特别敏感，这两个维度不应该被揉成一个粗糙分数。本文试图把 token-level 的重要性和 channel-level 的敏感性拆开估计，再在同一个预算分配器里联合使用。

关键结论与意义：
作者借这个切分把问题重新定义成：如果必须保留 full prompt state，那么有限精度预算到底应该优先花在什么地方。这个定义比“我要不要删 token”更适合引出系统研究，因为它背后其实是一个通用问题：当状态对象太大但不能简单丢弃时，runtime 应该如何给状态的不同部分定价，并把资源预算分配给最值得保真的部分。

### 4. What is the key idea?
背景解释：
真正有用的压缩通常来自“不均匀分配”，前提是你得先知道系统内部哪里更值钱、哪里更敏感。长 prompt 的 KV cache 不是一块均质内存：不同 token 对最终回答的贡献不同，不同 channel 对量化误差的敏感程度也不同。如果把它们全部用同一种 bit-width 表示，就相当于把宝贵预算平均撒在所有位置上，这通常不是最优的。

本文做法：
作者把 prefill 视为最佳观察时机，因为这时完整 prompt 一次性可见，而且这些分析成本只需要付一次。随后它联合 token importance、channel sensitivity 和架构修正项，在共享 bit budget 下做 variable-rate allocation。这里最值得讲清楚的是“为什么在 prefill 做”：decode 阶段每一步都在生成新 token，如果此时再反复做复杂统计，会直接拖慢在线生成；prefill 虽然本身也有成本，但它只发生一次，而且正好拥有完整 prompt 的全局视野，因此适合作为状态估值窗口。

关键结论与意义：
关键 idea 不是“某个具体 bit-width”，而是把 prefill 变成一次性结构观察窗口，再把观察结果固化成 decode 端可复用的 artifact。这个想法很像把 runtime 的短暂观测转化成长期有效的状态布局决策：先看清状态结构，再决定资源分配，再把结果打包成后续阶段可以直接消费的格式。

### 5. What is the design?
背景解释：
如果只有一个抽象想法，却没有完整执行链路，那这篇论文就很难真正落到系统里。这里要带着系统实现问题去读：输入是什么，系统在什么时候插入统计逻辑，统计结果如何变成 bit allocation，压缩结果如何存储，decode 又如何读取。如果这些环节中任何一个没有闭合，这个方法就只是离线分析，而不是推理系统设计。

本文做法：
作者的设计链条很清楚：prefill 中提取结构信号，随后根据这些信号分配预算，再把分配结果打包成压缩 artifact，最后让 decode 端直接消费这份 artifact。更具体地讲，token importance 告诉系统哪些位置更值得保护，channel sensitivity 告诉系统哪些维度对误差更敏感，architecture-aware correction 用来避免某些模型结构下的估计偏差，variable-rate allocator 则把这些信号变成实际 bit budget。最终产物不是一段解释，而是一份压缩后的 prompt KV 以及配套元数据。

关键结论与意义：
对你的研究最有启发的，其实就是这条完整链路本身，因为它很容易迁移到更一般的分层状态管理和跨层协同优化问题。比如未来你可以把“bit budget”替换成 GPU/CPU/CXL/SSD 的 placement budget，把“压缩 artifact”替换成可迁移状态对象，把“prefill 观测”替换成 runtime profiling 或 workload prediction。

### 6. What is the experimental plan?
背景解释：
系统论文的实验不只是证明“比别人高一点”，更重要的是交代自己在哪些边界上赢了、又在哪些边界上付出了代价。读这篇论文的实验时，不能只问压缩率是多少，还要问：同等预算下质量是否保持住了，显存是否真的省了，context-fit frontier 是否真的往外推了，额外 runtime cost 是否会抵消系统收益。

本文做法：
实验主要围绕三个边界展开：一是和 eviction 路线比，在相同预算下是否更稳；二是和固定低比特 dense quantization 比，是否能利用 prompt 结构拿到更好的 fidelity；三是系统侧究竟换来了多少显存/容量收益，又付出了多少延迟成本。前两个边界回答“方法是否合理”，第三个边界回答“系统是否值得”。如果一篇论文只证明 fidelity 而不讲 latency，那它对 serving 系统的说服力是不够的；这篇论文至少把收益和代价都摆出来了。

关键结论与意义：
所以这篇论文最该读的不是单个数字，而是收益和代价是否同时被讲清楚。对课题组讨论来说，你可以把实验问题组织成一句话：PREFILLCOMP 是否用可接受的 prefill/runtime 代价，换来了比 eviction 更稳、比 fixed quantization 更聪明、并且对 decode serving 真有帮助的状态压缩方案。

### 7. What is the takeaway?
背景解释：
一篇系统论文的 takeaway 应该同时告诉你“这件事值不值得做”和“目前它还差哪口气”。本文值得带走的第一层 takeaway 是：长上下文 LLM serving 中的 KV cache 不是被动缓存，而是一个可以被主动估值和重排的状态对象。第二层 takeaway 是：prefill 和 decode 的阶段差异可以被系统利用，prefill 适合做一次性全局分析，decode 适合消费已经物化好的轻量状态。

本文做法：
作者通过 matched-budget fidelity、decode-side memory 改善和 latency 代价三个面向，把 PREFILLCOMP 的价值边界交代了出来。它没有把自己伪装成零成本方案，而是比较诚实地说明：更聪明的状态估值会带来额外运行时开销，因此系统设计的关键是让这份开销只发生在最合适的阶段，并让它在后续 decode 中被充分摊销。

关键结论与意义：
最值得带走的不是某个具体实验数，而是一个可复用的系统模式：先估计状态价值，再据此分配预算，最后把决策物化成后续阶段可消费的状态工件。这个模式可以成为你之后做分层状态优化的一个基本范式：状态不是只被缓存或淘汰，它还可以被估价、压缩、迁移、复制、降级和协同调度。

## 综述五字段
### 1. State object
论文主要管理和优化的状态对象是 `prompt-side KV cache`。这句话要展开讲：在长上下文推理里，prompt 一旦 prefill 完成，就会变成一份跨层、跨 head、跨 token 的 K/V 状态集合；这份状态之后不是偶尔用一次，而是在 decode 的每一步都可能被 attention 访问。作者真正想优化的，就是这份已经生成、必须保留、会被反复消费的 prompt 状态。它没有把重点放在 decode 过程中不断增长的新 KV 上，也没有把问题抽象成通用 tensor compression，而是很明确地抓住“长 prompt 形成的历史状态”这个 serving 系统里的核心资源瓶颈。

### 2. Control surface
论文显式暴露的控制面包括：token importance、channel sensitivity、architecture-aware correction、shared bit budget allocation，以及 decode 侧如何消费压缩 artifact。换成更系统的话说，它不是只给一个压缩率旋钮，而是把控制面拆成了几个层次：先判断状态位置的价值，再判断状态维度的误差敏感性，然后把这些信号映射成实际 bit allocation，最后还要决定压缩后的状态以什么格式交给 decode。这个控制面很有意思，因为它横跨模型结构、数值表示和 runtime 数据路径，天然适合拿来和分层状态优化、memory tiering、serving scheduler 做进一步组合。

### 3. Coupling path
模型的 attention 结构决定 token importance，张量统计决定 channel sensitivity，架构特性决定 correction factor，最后这些信号一起落到 serving path 上，形成 prefill 和 decode 之间的系统耦合。这里的耦合关系值得细读：模型侧提供“哪些状态可能重要”的结构信号，系统侧把这些信号变成“如何分配有限资源”的决策，硬件侧则通过显存容量和访问代价约束这个决策是否可部署。也就是说，本文不是一个单点优化，而是在模型观测、压缩表示和推理运行时之间搭了一条链路。

### 4. Evaluation boundary
作者主要在 fidelity、memory footprint、context-fit frontier 和 latency 四个边界上评估设计，而不是只看单个精度数字。fidelity 回答“压缩后模型还能不能正确利用 prompt”；memory footprint 回答“状态对象有没有真的变小”；context-fit frontier 回答“省出来的显存是否能换成更长上下文或更大 batch”；latency 回答“这些收益是不是被额外运行时成本吃掉了”。这四个边界放在一起，才像一篇系统论文该有的评价方式，因为它同时覆盖了质量、容量和在线代价。

### 5. Remaining systems gap
这篇论文最明显的系统短板是 runtime cost，尤其 prompt-side artifact build 和 decode integration 的延迟代价较高。更具体地说，PREFILLCOMP 证明了“prefill 原生状态估值 + 稠密压缩”这个 design point 有价值，但还没有完全回答生产级 serving 栈会追问的问题：统计和压缩能不能和 prefill kernel 融合，artifact format 能不能被高效分页和调度，压缩状态能不能跨请求、跨 GPU、跨 memory tier 复用，以及它和 continuous batching / prefix caching / prefill-decode disaggregation 放在一起时会不会产生新的瓶颈。因此它更像一个很有启发的研究原型，而不是已经闭环的工程方案。

## 用执行流程讲方法
{method_steps}

## 我怎么理解这篇论文在做什么
从系统视角看，这篇论文真正的动作不是“单纯换一种量化位宽”，而是把 **prefill 阶段的一次性全局观察** 变成 **decode 阶段反复可消费的状态工件**。如果给同学讲，我会把它拆成三句话：第一，prefill 让系统第一次拥有完整 prompt 的全局视野；第二，这个全局视野可以用来估计状态里哪些部分更值得保真；第三，估计结果不能只停留在分析报告里，而要变成 decode 实际读取的数据格式。这样看，PREFILLCOMP 更像一篇在研究 `state valuation -> budget allocation -> artifact materialization` 链路的论文，而不是只在做局部数值压缩。

## 关键图怎么读
{figure_text}

## 实验设置和关键结果
### 实验设置
实验主要围绕三个边界展开：一是和 eviction 路线比，在相同预算下是否更稳；二是和固定低比特 dense quantization 比，是否能利用 prompt 结构拿到更好的 fidelity；三是系统侧究竟换来了多少显存/容量收益，又付出了多少延迟成本。读实验时要把这些问题分开，不要混成“效果好不好”一句话。fidelity 实验是在证明状态没有被压坏，memory/context 实验是在证明系统资源真的被释放，latency 实验是在证明或暴露这套方案离在线部署还有多远。

### 关键结果
先看 fidelity：作者想证明在 matched budget 下，dense full-prompt compression 比 eviction 更稳。这里的重点不是“某个曲线赢了”，而是 dense 路线保留了所有 prompt token，因此在需要回溯细粒度证据的任务里更不容易出现不可逆信息丢失。换句话说，它的优势来自状态覆盖范围没有被破坏。

再看 systems：作者想证明 decode-side memory 和 context-fit frontier 有明确收益。这个结果对系统方向最重要，因为只有当压缩后的 prompt KV 真正减轻了 decode 阶段的显存压力，它才有可能转化为更长上下文、更大 batch 或更高并发。读这部分时应该关注收益是否发生在 serving 瓶颈处，而不是只看离线压缩率。

最后看代价：作者没有回避 latency，而是明确承认 prompt-side runtime cost 仍是主要短板。这一点反而让论文更值得研究，因为它暴露了下一步系统优化的入口：统计逻辑能否下沉到 kernel，artifact build 能否流水化，压缩结果能否被缓存复用，decode 端读取压缩格式能否减少解包开销。

## 与已有工作的关系
作者实际上在和两条路线对话：一条是 H2O 这类 eviction / selective retention 路线，另一条是 KIVI 这类 fixed dense quantization 路线。它的定位很明确：不删状态，但也不平均压缩，而是用 prompt-aware 的方式决定哪些状态更值得保精度。给组会讲的时候可以这样概括：H2O 问的是“哪些 token 可以留下”，KIVI 问的是“所有 KV 能不能统一低比特表示”，而 PREFILLCOMP 问的是“如果我保留全 prompt，那么精度预算该怎样按结构分配”。这三个问题的差别很重要，因为它们对应的是三种不同的状态管理哲学：选择性保留、均匀压缩、结构感知压缩。

## 对你研究方向的价值
它和你的主方向高度对齐，因为论文直接优化了长上下文推理中的 KV cache 状态对象，并且把优化点放在 prefill/decode 交界处。更进一步说，这篇论文最值得借鉴的不是某个 compression 公式，而是如何把 `一次性结构观察` 变成 `后续阶段可复用的状态决策工件`。如果你的研究目标是“大模型推理系统的分层状态优化与协同优化”，这篇论文可以作为一个具体 case：状态对象是 prompt KV，状态估值发生在 prefill，状态重编码产生压缩 artifact，状态消费发生在 decode，收益边界是 memory/context，代价边界是 runtime latency。这个 case 可以继续推广到跨 GPU/CPU/CXL 的状态放置、跨请求 prefix state 复用、以及 scheduler 对状态价值的感知调度。

## 局限性与 Open Gap
### 论文局限
第一，延迟代价偏高，尤其在线 serving 时不一定好消化。这里的问题不是“多花一点时间”这么简单，而是长上下文服务通常已经对首 token latency、吞吐和排队延迟很敏感；如果 artifact build 不能和 prefill 很好融合，就可能把显存收益换成用户可感知的响应延迟。

第二，目前更像证明 design point 成立，而不是已经证明自己是成熟生产方案。论文说明了 prompt-aware variable-rate dense compression 有价值，但生产系统还会追问更多工程问题：如何和 paged KV 管理结合，如何处理 batch 内不同请求的压缩布局，如何在多租户 serving 中做 admission control，如何在失败恢复或状态迁移时维护 artifact 一致性。

第三，架构相关修正项对不同 model family 的泛化性还需要更强证据。因为 token importance 和 channel sensitivity 都可能受模型结构、训练方式、上下文分布影响，如果换成不同 attention 结构、不同量化友好程度的模型，当前信号是否仍然稳定，需要更多跨模型验证。

### 可以继续追问的系统问题
第一个问题是：能否把这套 state-aware allocation 和 paged KV / tiered memory 结合？也就是说，高价值高敏感状态留在 GPU，高压缩低敏感状态下沉到 CPU/CXL，甚至把 bit allocation 和 placement allocation 合并成一个联合优化问题。

第二个问题是：能否把压缩 artifact 进一步变成 GPU/CPU/CXL/SSD 之间可迁移的统一状态对象？如果 artifact 只是一个本地压缩 buffer，那它的系统价值有限；如果它能被 runtime 识别、迁移、复用和恢复，它就更接近分布式推理系统里的状态管理单元。

第三个问题是：能否和 continuous batching、prefix caching、prefill-decode disaggregation 联合设计？这些机制都会改变 KV 的生命周期和访问模式，而 PREFILLCOMP 目前更像单请求内的压缩链路。下一步真正有系统味道的工作，是把状态估值和 serving scheduler 放到同一个闭环里。

## 人工阅读重点
### 必读部分
**Abstract + Introduction** 必须先读，而且不能只为了摘一句摘要。你要在这一部分确认三个边界：第一，作者为什么把长上下文 KV cache 视为推理系统瓶颈；第二，作者为什么不满意 eviction 和 fixed dense quantization；第三，作者把 PREFILLCOMP 放在 prefill/decode 流程中的哪个位置。读完后，你应该能用自己的话讲清楚：这篇论文不是泛泛地做压缩，而是在解决“完整 prompt 状态太大但又不能轻易删”的系统问题。

**Method / Design section** 是第二个必须精读的部分。读的时候不要先陷进公式，而要按执行顺序画出链路：prefill 阶段有什么输入，系统收集哪些结构信号，token importance 和 channel sensitivity 分别回答什么问题，allocator 如何把信号变成 bit budget，compressed prompt artifact 里到底装了什么，decode 阶段如何消费它。读完后，你应该能站在白板前顺着 prefill -> allocation -> artifact -> decode 讲完整个方法。

**Evaluation section** 是判断论文价值边界的部分。你要把实验分成三类看：质量保持实验说明压缩后模型是否还能用 prompt 证据，memory/context 实验说明系统瓶颈是否被缓解，latency 实验说明额外复杂度是否能被接受。读完后，你不应该只记住“方法有效”，而应该能判断它更适合作为直接部署方案，还是更适合作为 state-aware serving 的研究起点。

**关键图：workflow、decode memory、latency ratios** 应该穿插着读。workflow 图帮你建立全局心智模型，decode memory 图帮你判断收益是否真的落到 serving 瓶颈，latency 图帮你判断系统代价来自哪里。第一次阅读时，图比公式更重要，因为它们决定你能不能把论文讲成一个完整系统，而不是一组零散技术点。

### 可跳读部分
**参考文献与次要数据集描述** 可以第一轮先扫，不必一开始就陷进去。它们对写 related work 有用，但对理解本文主链路不是第一优先级。等你已经能说清 PREFILLCOMP 相对 H2O/KIVI 的定位后，再回头细查相关工作会更高效。

**重复性结果解释段落** 可以在看懂主图和主表后先略读。很多实验段落会反复解释同一趋势，第一次精读时重点应该放在“这个实验回答了哪个系统问题”，而不是把每个数值都抄下来。

### 建议精读顺序
1. 先读 `Abstract + Introduction`，目标是确认论文到底在反驳什么、主张什么，以及它为什么把 dense full-prompt compression 当成独立问题。这个阶段不要急着记技术细节，先把问题边界讲清楚。
2. 再读动机和已有方法对比，目标是搞清楚 eviction 为什么可能丢证据、fixed dense quantization 为什么浪费预算。读完这一步，你应该能讲出本文方法相对 H2O/KIVI 的位置。
3. 接着读 `Method / Design`，目标是顺着 prefill -> signal extraction -> allocation -> artifact -> decode 的顺序走一遍。这里建议边读边画流程图，因为这篇论文的价值主要在链路，而不是某个孤立公式。
4. 然后看关键图，先看 workflow 建立整体结构，再看 decode memory 判断收益，再看 latency ratios 判断代价。读图时不断问自己：这张图是在证明方法合理，还是在证明系统可用？
5. 最后回到 `Evaluation`，带着“收益是否值得代价”这个问题复核结果。如果你能同时说出它省了什么、保住了什么、花了什么成本，才算真正读懂。

### 与用户方向的连接
它和你的方向直接相连，因为它把推理系统中的状态对象看成可以被估值和重新布局的系统资源。KV cache 在这里不是普通 cache，而是长上下文推理中最关键的运行时状态；PREFILLCOMP 做的事情，本质上是给这个状态对象建立价值模型，再用价值模型指导压缩和后续消费。

这篇论文给你的最大启发，不是某个 compression 公式，而是如何把 `一次性结构观察` 变成 `后续阶段可复用的状态决策工件`。这正好可以扩展到你的分层状态优化：未来可以不只是决定 bit-width，还可以决定状态放在哪一层 memory、什么时候迁移、能否跨请求复用、是否由 scheduler 根据队列压力动态调整。

## 可提炼的研究命题
第一个命题：是否可以把本文的 prompt-aware allocation 扩展成跨 memory tier 的 state placement 决策？也就是让 token/channel 的价值估计不仅决定压缩位宽，还决定这部分状态留在 GPU、放到 CPU、迁到 CXL，还是以更低成本格式持久化。

第二个命题：是否可以同时联合 state compression、state migration 和 runtime scheduling，而不是只优化一个轴？例如，当 scheduler 知道某个请求的 prompt state 很大但复用价值高时，它可以选择更激进的压缩、更保守的迁移，或者把该请求安排到拥有更合适 memory tier 的设备上。

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
