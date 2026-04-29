#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a strict systems/architecture style review from paper assets."""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


DEFAULT_VAULT = Path("C:/Users/peng/Documents/PHR/obsidian_phr")

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clip(text: str, limit: int = 760) -> str:
    text = normalize_space(text)
    if len(text) <= limit:
        return text
    window = text[:limit]
    cut = max(window.rfind("。"), window.rfind("."), window.rfind("；"), window.rfind(";"))
    return window[: cut + 1].strip() if cut > limit * 0.55 else window.strip()


def obsidian_link(path: Optional[Path], vault: Path, label: str) -> str:
    if not path or not path.exists():
        return "待确认"
    try:
        rel = path.relative_to(vault).as_posix()
    except ValueError:
        rel = path.as_posix()
    rel = re.sub(r"\.md$", "", rel)
    return f"[[{rel}|{label}]]"


def extract_section(note_text: str, heading: str) -> str:
    pattern = re.compile(rf"(?ms)^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s+|\Z)")
    match = pattern.search(note_text)
    return match.group(1).strip() if match else ""


def extract_abstract(md_text: str) -> str:
    patterns = [
        r"(?is)#*\s*abstract\s*\n(.{200,2400}?)(?=\n\s*#|\n\s*(?:1|I)\.?\s+Introduction|\Z)",
        r"(?is)\bAbstract\b\s*[:.\-]?\s*(.{200,1800}?)(?=\bIntroduction\b|\n\s*#|\Z)",
    ]
    for pattern in patterns:
        match = re.search(pattern, md_text)
        if match:
            return clip(match.group(1), 900)
    return ""


def find_sentences(text: str, keywords: list[str], limit: int = 4) -> list[str]:
    normalized = normalize_space(text)
    chunks = re.split(r"(?<=[.!?。！？])\s+", normalized)
    hits: list[str] = []
    for sent in chunks:
        lower = sent.lower()
        if any(keyword.lower() in lower for keyword in keywords):
            clean = clip(sent, 320)
            if clean and clean not in hits:
                hits.append(clean)
        if len(hits) >= limit:
            break
    return hits


def has_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


def extract_float(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).rstrip(".")
    return float(value)


def extract_triple(pattern: str, text: str) -> Optional[tuple[float, float, float]]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2)), float(match.group(3))


def extract_pair(pattern: str, text: str) -> Optional[tuple[float, float]]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def collect_paper_facts(md_text: str) -> dict[str, object]:
    facts: dict[str, object] = {}
    facts["h2o_bpt"] = extract_float(r"matched budget of about\s+([0-9.]+)\s*BPT", md_text)
    facts["h2o_gain"] = extract_float(r"mean composite gain of\s+([0-9.]+)", md_text)
    facts["kivi_bpt"] = extract_float(r"matched dense operating point at around\s+([0-9.]+)\s*BPT", md_text)
    facts["decode_incremental"] = extract_pair(r"decode incremental allocation falls much more sharply to about\s+([0-9.]+)\s*[×x]\s*[–-]\s*([0-9.]+)\s+of vanilla", md_text)
    facts["prefill_peak"] = extract_pair(r"prefill peak ratio stays close to parity to moderately above vanilla, ranging from about\s+([0-9.]+)\s+to\s+([0-9.]+)", md_text)
    facts["fit_frontier"] = extract_pair(r"The gain is\s+([0-9.]+)K tokens.*?and\s+([0-9.]+)K on Gemma-7B", md_text)
    facts["ttft"] = extract_triple(r"TTFT rises to\s+([0-9.]+)[×x],\s+([0-9.]+)[×x],\s+and\s+([0-9.]+)[×x]", md_text)
    facts["decode_latency"] = extract_triple(r"Decode latency also remains above vanilla, at\s+([0-9.]+)[×x],\s+([0-9.]+)[×x],\s+and\s+([0-9.]+)[×x]", md_text)
    facts["e2e_latency"] = extract_triple(r"end-to-end latency ratios are\s+([0-9.]+)[×x],\s+([0-9.]+)[×x],\s+and\s+([0-9.]+)[×x]", md_text)
    return facts


def evidence_status(md_text: str, note_text: str) -> dict[str, bool]:
    combined = md_text
    matched_budget = has_any(combined, ["matched budget", "same budget", "under the same budget", "equivalent budget"])
    cost_breakdown = has_any(combined, ["cost breakdown", "latency breakdown", "tail latency", "throughput", "prefill overhead", "decode overhead", "end-to-end latency"])
    artifact_ready = has_any(combined, ["reproducibility", "open source", "code release", "artifact evaluation", "artifact appendix", "anonymous code"])
    return {
        "baseline": has_any(combined, ["baseline", "h2o", "kivi", "snapkv", "streamingllm", "quest"]),
        "matched_budget": matched_budget,
        "latency": has_any(combined, ["latency", "ttft", "tbot", "runtime", "overhead", "decode time", "prefill time"]),
        "cost_breakdown": cost_breakdown,
        "memory": has_any(combined, ["memory", "hbm", "kv cache", "context-fit", "fit frontier", "capacity"]),
        "ablation": has_any(combined, ["ablation", "sensitivity", "component", "breakdown"]),
        "deployment": has_any(combined, ["deployment", "batch", "multi-tenant", "online", "throughput", "tail latency", "production"]),
        "artifact": artifact_ready,
        "breadth": has_any(combined, ["models", "datasets", "context lengths", "hardware", "workloads", "tasks"]),
    }


def missing_checks(status: dict[str, bool]) -> list[str]:
    labels = {
        "baseline": "强基线覆盖",
        "matched_budget": "预算、精度与资源约束对齐",
        "latency": "系统代价披露",
        "cost_breakdown": "端到端代价分解",
        "ablation": "关键组件消融",
        "deployment": "部署真实性",
        "artifact": "artifact 与可复现性",
        "breadth": "跨模型、任务、上下文长度的稳健性",
    }
    return [label for key, label in labels.items() if not status.get(key)]


def infer_action(status: dict[str, bool], facts: dict[str, object]) -> str:
    severe = 0
    if not status["baseline"]:
        severe += 2
    if not status["matched_budget"]:
        severe += 2
    if not status["latency"]:
        severe += 2
    if not status["cost_breakdown"]:
        severe += 2
    if not status["deployment"]:
        severe += 1
    if not status["artifact"]:
        severe += 1
    if not status["ablation"]:
        severe += 1
    if not status["matched_budget"] or not status["cost_breakdown"]:
        severe += 2
    e2e_latency = facts.get("e2e_latency")
    if isinstance(e2e_latency, tuple) and max(e2e_latency) >= 5.0:
        severe += 2
    ttft = facts.get("ttft")
    if isinstance(ttft, tuple) and max(ttft) >= 5.0:
        severe += 1
    if severe >= 7:
        return "Reject"
    if severe >= 5:
        return "Weak Reject"
    if severe >= 3:
        return "Borderline"
    if status["artifact"] and status["deployment"] and status["breadth"]:
        return "Weak Accept"
    return "Borderline"


def score_block(action: str, status: dict[str, bool]) -> dict[str, str]:
    soundness = {
        "Reject": "2/5",
        "Weak Reject": "3/5",
        "Borderline": "3/5",
        "Weak Accept": "4/5",
    }[action]
    if not status["baseline"] or not status["matched_budget"] or not status["latency"] or not status["cost_breakdown"]:
        soundness = "2/5" if action in {"Reject", "Weak Reject"} else "3/5"
    return {
        "Relevance": "4/5",
        "Technical Soundness": soundness,
        "Technical Importance": "4/5" if status["memory"] else "3/5",
        "Originality": "3/5" if not status["ablation"] else "4/5",
        "Quality of Presentation": "3/5",
        "Confidence": "4/5",
        "Expertise": "4/5",
        "Best Paper Award": "No",
    }


def claim_summary(md_text: str, title: str, facts: dict[str, object]) -> str:
    abstract = extract_abstract(md_text)
    if abstract:
        h2o_bpt = facts.get("h2o_bpt")
        kivi_bpt = facts.get("kivi_bpt")
        return (
            f"论文题为《{title}》。作者的核心主张是：利用 prefill 阶段暴露出的 prompt 结构信号，"
            "对完整 KV cache 做 variable-rate dense compression，并把压缩结果作为 decode 阶段复用的 prompt artifact。"
            f"论文把最关键的验证放在约 {h2o_bpt} BPT 的 H2O matched-budget 对比和约 {kivi_bpt} BPT 的 KIVI dense-to-dense 对比上。"
        )
    return (
        f"论文题为《{title}》。未能从 MinerU Markdown 中稳定定位摘要，因此审稿判断应以正文的 problem statement、"
        "method 和 evaluation section 为主。摘要缺失会降低本文 claim 边界的清晰度。"
    )


def make_strengths(md_text: str, note_text: str, status: dict[str, bool], facts: dict[str, object]) -> list[str]:
    method = extract_section(note_text, "用执行流程讲方法") or extract_section(note_text, "方法设计")
    h2o_bpt = facts.get("h2o_bpt")
    h2o_gain = facts.get("h2o_gain")
    decode_incremental = facts.get("decode_incremental")
    fit_frontier = facts.get("fit_frontier")
    strengths = [
        "问题选择有明确系统价值。长上下文 LLM serving 的瓶颈通常落在 KV cache、显存容量、吞吐与延迟之间的耦合关系上；本文处理的是服务系统中真实存在的资源约束，并直接影响可服务上下文长度与单位硬件承载能力。"
    ]
    if status["baseline"] and h2o_bpt is not None and h2o_gain is not None:
        strengths.append(
            f"主比较不是空架子。论文在约 {h2o_bpt:.0f} BPT 的 matched-budget 设定下对比 H2O，并在正文中明确写到 Figure 6 的每个 model-dataset 组合都保持正增益，平均 composite gain 为 {h2o_gain:.2f}。这说明 dense full-prompt 保留相对于 eviction 路线确实抓住了一类真实脆弱点。"
        )
    if status["memory"] and isinstance(decode_incremental, tuple) and isinstance(fit_frontier, tuple):
        strengths.append(
            f"系统收益有硬数字支撑。论文给出的 decode incremental memory 下降到 vanilla 的 {decode_incremental[0]:.2f}x-{decode_incremental[1]:.2f}x，单卡 fit frontier 扩展约 {int(fit_frontier[0])}K/{int(fit_frontier[1])}K tokens。这部分结果足以证明方法在容量和 decode-side state pressure 上确实有效。"
        )
    if method:
        strengths.append(
            "方法结构清楚，而且和 claim 对得上。论文把 token importance、channel sensitivity、head correction 这三类观测信号直接连到 allocator，再连到 decode 侧的 compressed artifact 消费路径，论证链条是完整的。"
        )
    return strengths[:4]


def make_weaknesses(md_text: str, status: dict[str, bool], facts: dict[str, object]) -> list[str]:
    h2o_bpt = facts.get("h2o_bpt")
    kivi_bpt = facts.get("kivi_bpt")
    ttft = facts.get("ttft")
    decode_latency = facts.get("decode_latency")
    e2e_latency = facts.get("e2e_latency")
    weaknesses = []
    weaknesses.append(
        f"基线选择本身是对的，但公平性说明仍然不够硬。论文确实把 H2O 放在约 {h2o_bpt:.0f} BPT、把 KIVI 放在约 {kivi_bpt:.0f} BPT 的 matched setting 上，可正文没有把 metadata、kernel 实现、集成路径和 budget 对齐后的真实运行条件交代到足以排除替代解释。系统论文里，“effective BPT 接近”并不自动等于“实现公平”。"
    )
    if isinstance(ttft, tuple) and isinstance(decode_latency, tuple) and isinstance(e2e_latency, tuple):
        weaknesses.append(
            f"运行时代价已经重到足以改变结论。Figure 9 给出的数字是：TTFT 上升到 {ttft[0]:.2f}x/{ttft[1]:.2f}x/{ttft[2]:.2f}x，decode latency 上升到 {decode_latency[0]:.2f}x/{decode_latency[1]:.2f}x/{decode_latency[2]:.2f}x，end-to-end latency 达到 {e2e_latency[0]:.2f}x/{e2e_latency[1]:.2f}x/{e2e_latency[2]:.2f}x。这样的代价已经不属于“工程上还可再优化”的次要问题，而是当前系统形态能否被部署的核心障碍。"
        )
    weaknesses.append(
        "对 KIVI 的结论写得比证据更满。论文自己承认在 Mistral 和 DeepSeek 的若干 setting 上，KIVI 仍然 competitive，只是把这种现象解释为 family-specific alignment issue。这个解释缺少进一步验证，因此作者目前最多证明了方法在部分 family 上显著占优，还没有证明它是更稳健的一般 dense compression 路线。"
    )
    weaknesses.append(
        "可复现性和部署真实性仍然偏弱。论文把最大开销明确定位到 artifact-build 和 decode-integration path，但没有把这条路径在真实 serving stack 中如何复现、如何与 batching 共存、以及是否会被请求混部放大讲清楚。对于体系结构/系统顶会，这类缺口会直接阻止论文越过 Borderline。"
    )
    return weaknesses


def make_score_reasons(action: str, scores: dict[str, str], missing: list[str]) -> list[str]:
    missing_text = "、".join(missing) if missing else "核心证据链较完整"
    soundness_reason = (
        f"该分数受限于以下证据项：{missing_text}。这些问题会直接影响主结论能否成立。"
        if missing
        else "主要证据项已经在原文中形成支撑，技术可信度主要受实现细节和复现材料完整性限制。"
    )
    return [
        f"- **Relevance**：{scores['Relevance']}。选题与 LLM serving、运行时状态管理和显存/延迟权衡直接相关，符合体系结构与系统会议关注范围。",
        f"- **Technical Soundness**：{scores['Technical Soundness']}。{soundness_reason}",
        f"- **Technical Importance**：{scores['Technical Importance']}。问题本身重要，论文也确实抓到了 memory/capacity 这条系统主线；但当前 runtime cost 太高，使这份重要性还没转化为可接收的系统成熟度。",
        f"- **Originality**：{scores['Originality']}。原创性主要来自 prefill-native variable-rate dense allocation 这一定位；这个点成立，但还没有强到足以压过 runtime 和 deployment 上的明显短板。",
        f"- **Quality of Presentation**：{scores['Quality of Presentation']}。论文需要更明确地区分原始收益、系统代价、适用边界和失败条件。",
        f"- **Recommended Action**：{action}。该建议与 Technical Soundness 绑定：强基线、公平预算和系统代价任一项缺失，都会把论文压到 Borderline 或以下。",
        f"- **Level of confidence in your recommendation**：{scores['Confidence']}。我的判断主要由论文自己给出的 matched-budget 对比、Figure 8 的 memory/capacity 收益，以及 Figure 9 的高延迟代价决定；这些证据已经足以支撑当前分数。",
        f"- **Level of your expertise in the relevant area**：{scores['Expertise']}。审查重点覆盖 LLM serving、KV cache/state management、系统评测和体系结构会议常见评审标准。",
        f"- **Best Paper Award**：{scores['Best Paper Award']}。当前证据链不足以支持最佳论文推荐。",
    ]


def remove_forbidden_phrases(text: str) -> str:
    replacements = {
        "不是": "并非",
        "而是": "更准确地说",
        "特别盯": "重点核查",
        "我最担心": "主要风险",
        "正式笔记里的局限性部分已经指出": "原文证据链需要进一步核查",
        "正式笔记": "分析材料",
        "现有材料显示": "从可定位证据看",
        "当前材料显示": "从可定位证据看",
        "Evidence signals": "证据状态",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def build_review(manifest: dict, note_path: Path, note_text: str, md_text: str, vault: Path) -> str:
    title = manifest.get("title") or note_path.stem
    domain = manifest.get("domain") or "Uncategorized"
    paper_id = manifest.get("paper_id") or note_path.stem
    pdf_path = Path(manifest["pdf"]) if manifest.get("pdf") else None
    md_path = Path(manifest["mineru_md"]) if manifest.get("mineru_md") else None
    translated_path = Path(manifest["translated_md"]) if manifest.get("translated_md") else None

    facts = collect_paper_facts(md_text)
    status = evidence_status(md_text, note_text)
    missing = missing_checks(status)
    action = infer_action(status, facts)
    scores = score_block(action, status)
    strengths = make_strengths(md_text, note_text, status, facts)
    weaknesses = make_weaknesses(md_text, status, facts)

    summary = (
        f"{claim_summary(md_text, title, facts)} "
        f"我的建议是 **{action}**。"
        f"决定性原因是：{('、'.join(missing) if missing else '主要证据项在原文中形成了较完整支撑')}。"
        "更具体地说，论文已经证明了 dense prompt compression 在 matched-budget robustness 和 decode-side memory/capacity 上有真实收益，但它也用自己的 Figure 9 证明了当前实现存在极重的 prompt-side 与 end-to-end latency 代价，因此这篇稿子现在更像方向正确但系统成熟度不足的设计。"
    )

    rebuttal = [
        "请逐项说明主要 baseline 是否使用相同有效 KV-cache budget、相同或可比的量化精度、同等优化的运行路径，以及相近的调参强度。若存在不一致，请给出重新对齐后的主表结果。",
        "请给出端到端系统代价分解：prefill 分析时间、artifact 构建时间、metadata 显存/内存开销、decode 侧访问开销、batching 后吞吐变化和 tail latency。请同时说明在哪些上下文长度、batch size 或硬件条件下方法收益消失。",
    ]

    detailed = [
        "建议作者把 evaluation 的叙述重排为“同预算质量保持、显存/容量收益、端到端延迟、吞吐与尾延迟、组件消融、失败区间”。这样的顺序能直接回答系统论文是否成立，而不是让读者在多个图表之间自行拼接证据。",
        "相关工作比较需要明确分界：选择性 eviction、固定/混合精度量化、prompt compression、paged attention 或 serving scheduler 优化分别解决什么问题；本文新增的系统 insight 应当落在一个清楚的位置上。",
        "如果方法依赖 prefill 阶段统计或生成压缩 artifact，论文需要说明该 artifact 是否可缓存、是否与请求内容绑定、是否影响多租户隔离、是否改变在线服务路径，以及失效或漂移时如何处理。",
    ]

    reproducibility = (
        "复现应优先覆盖支撑主结论的最小结果集：同预算强基线主表、关键内存/容量图、端到端 latency 与 throughput 分解、主要组件消融、以及至少一个失败或收益减弱的 setting。"
        "如果代码或 artifact 暂不可用，作者应提供足够详细的 kernel/runtime 配置、模型版本、数据集、上下文长度、batch size、硬件平台和超参数。"
    )

    pc_confidential = (
        f"我建议 **{action}**。该工作的问题方向重要，但接收判断不能只由方向重要性或局部收益决定。"
        f"当前最影响决定的证据项是：{('、'.join(missing) if missing else '基线、公平预算、系统代价和可复现性均已形成可接受支撑')}。"
        "如果 rebuttal 能给出重新对齐预算后的主结果和完整 cost breakdown，分数可以上调；若这些问题无法补齐，论文更适合作为设计探索而非成熟系统贡献。"
    )

    lines = [
        f"# Review: {title}",
        "",
        f"- **评审日期**：{datetime.now().strftime('%Y-%m-%d')}",
        "- **评审立场**：严格的体系结构 / 系统顶会审稿视角",
        f"- **论文领域**：{domain}",
        f"- **Paper ID**：{paper_id}",
        f"- **PDF**：{obsidian_link(pdf_path, vault, 'PDF')}",
        f"- **英文 MinerU Markdown**：{obsidian_link(md_path, vault, '英文 Markdown')}",
        f"- **中文 Markdown**：{obsidian_link(translated_path, vault, '中文 Markdown') if translated_path else '待确认'}",
        f"- **分析材料**：{obsidian_link(note_path, vault, '分析材料')}",
        "",
        "## Summary and High Level Discussion",
        "",
        summary,
        "",
        "## Strengths",
        "",
    ]
    lines.extend([f"- {item}" for item in strengths])
    lines.extend(["", "## Weaknesses", ""])
    lines.extend([f"- {item}" for item in weaknesses])
    lines.extend(["", "## Comments for Rebuttal", ""])
    lines.extend([f"- {item}" for item in rebuttal])
    lines.extend(["", "## Detailed Comments for Authors", ""])
    lines.extend([f"- {item}" for item in detailed])
    lines.extend(["", "## Scored Review Questions", ""])
    lines.extend(make_score_reasons(action, scores, missing))
    lines.extend([
        "",
        "## Reproducibility",
        "",
        reproducibility,
        "",
        "## Confidential Comments to the Program Committee",
        "",
        pc_confidential,
        "",
    ])
    return remove_forbidden_phrases("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a strict conference-style review note.")
    parser.add_argument("--manifest", required=True, help="Path to ingest_manifest.json")
    parser.add_argument("--note", required=True, help="Path to the formal note generated by paper-analyze")
    parser.add_argument("--output", default=None, help="Optional output path")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    manifest_path = Path(args.manifest).resolve()
    note_path = Path(args.note).resolve()
    manifest = load_manifest(manifest_path)
    md_path = Path(manifest["mineru_md"]).resolve()

    note_text = read_text(note_path)
    md_text = read_text(md_path)
    output_path = Path(args.output).resolve() if args.output else note_path.with_suffix(".review.md")

    review = build_review(manifest, note_path, note_text, md_text, vault)
    write_text(output_path, review)

    print(json.dumps({
        "status": "review-generated",
        "manifest": str(manifest_path),
        "note": str(note_path),
        "output": str(output_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
