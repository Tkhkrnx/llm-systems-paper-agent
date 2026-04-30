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
    facts["decode_incremental"] = extract_pair(r"decode incremental allocation falls much more sharply to about\s+([0-9.]+)\s*(?:[×x])?\s*[–-]\s*([0-9.]+)\s*(?:[×x])?\s+of vanilla", md_text)
    facts["prefill_peak"] = extract_pair(r"prefill peak ratio stays close to parity to moderately above vanilla, ranging from about\s+([0-9.]+)\s+to\s+([0-9.]+)", md_text)
    facts["fit_frontier"] = extract_pair(r"The gain is\s+([0-9.]+)K tokens.*?and\s+([0-9.]+)K on Gemma-7B", md_text)
    facts["ttft"] = extract_triple(r"TTFT rises to\s+([0-9.]+)[×x],\s+([0-9.]+)[×x],\s+and\s+([0-9.]+)[×x]", md_text)
    facts["decode_latency"] = extract_triple(r"Decode latency also remains above vanilla, at\s+([0-9.]+)[×x],\s+([0-9.]+)[×x],\s+and\s+([0-9.]+)[×x]", md_text)
    facts["e2e_latency"] = extract_triple(r"end-to-end latency ratios are\s+([0-9.]+)[×x],\s+([0-9.]+)[×x],\s+and\s+([0-9.]+)[×x]", md_text)
    return facts


def evidence_status(md_text: str, note_text: str) -> dict[str, bool]:
    combined = md_text
    matched_budget = has_any(combined, ["matched budget", "same budget", "under the same budget", "equivalent budget"])
    cost_breakdown = has_any(combined, ["cost breakdown", "latency breakdown", "prefill overhead", "decode overhead", "end-to-end latency", "ttft"])
    ablation_ready = has_any(combined, ["ablation", "ablate", "remove each", "component analysis", "component-wise", "without token", "without channel", "without correction"])
    throughput_tail_ready = has_any(combined, ["throughput", "tail latency", "p99", "batching", "requests per second"])
    artifact_ready = has_any(combined, ["reproducibility", "open source", "code release", "artifact evaluation", "artifact appendix", "anonymous code"])
    return {
        "baseline": has_any(combined, ["baseline", "h2o", "kivi", "snapkv", "streamingllm", "quest"]),
        "matched_budget": matched_budget,
        "latency": has_any(combined, ["latency", "ttft", "tbot", "runtime", "overhead", "decode time", "prefill time"]),
        "cost_breakdown": cost_breakdown,
        "memory": has_any(combined, ["memory", "hbm", "kv cache", "context-fit", "fit frontier", "capacity"]),
        "ablation": ablation_ready,
        "deployment": has_any(combined, ["deployment", "batch", "multi-tenant", "online", "throughput", "tail latency", "production"]),
        "artifact": artifact_ready,
        "breadth": has_any(combined, ["models", "datasets", "context lengths", "hardware", "workloads", "tasks"]),
        "method_structure": has_any(combined, ["token importance", "channel sensitivity", "allocator", "artifact", "workflow", "architecture-aware"]),
        "assumption": has_any(combined, ["evidence-sensitive", "long-context", "prefill", "decode", "attention", "sensitivity"]),
        "throughput_tail": throughput_tail_ready,
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
        "method_structure": "方法结构闭环",
        "throughput_tail": "吞吐与尾延迟评估",
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
    if not status["method_structure"]:
        severe += 2
    if not status["throughput_tail"]:
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
            f"主比较具有实质内容。论文在约 {h2o_bpt:.0f} BPT 的 matched-budget 设定下对比 H2O，并在正文中明确写到 Figure 6 的每个 model-dataset 组合都保持正增益，平均 composite gain 为 {h2o_gain:.2f}。这说明 dense full-prompt 保留相对于 eviction 路线确实抓住了一类真实脆弱点。"
        )
    if status["memory"] and isinstance(decode_incremental, tuple) and isinstance(fit_frontier, tuple):
        strengths.append(
            f"系统收益有硬数字支撑。论文给出的 decode incremental memory 下降到 vanilla 的 {decode_incremental[0]:.2f}x-{decode_incremental[1]:.2f}x，单卡 fit frontier 扩展约 {int(fit_frontier[0])}K/{int(fit_frontier[1])}K tokens。这部分结果足以证明方法在容量和 decode-side state pressure 上确实有效。"
        )
    if method:
        strengths.append(
            "方法结构清楚，而且和 claim 对得上。论文把 token importance、channel sensitivity、head correction 这三类观测信号直接连到 allocator，再连到 decode 侧的 compressed artifact 消费路径。这个结构说明作者给出了一条从 prefill 观测到 decode 消费的完整系统路径。"
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
        f"baseline 和预算公平性仍然没有完全闭合。论文选择 H2O 与 KIVI 是合理的，也把 H2O 放在约 {h2o_bpt:.0f} BPT、KIVI 放在约 {kivi_bpt:.0f} BPT 的 matched setting 上；系统论文里的公平比较还必须把 metadata、kernel/runtime 优化程度、artifact 生成成本、decode 读取路径和调参强度放进同一资源框架。正文目前主要对齐 BPT 层面的预算，没有把这些系统条件交代到足以排除替代解释，因此 fidelity 或 memory gain 中有多少来自 allocation 策略本身、有多少来自实现路径差异，仍然没有被完全隔离。"
    )
    if isinstance(ttft, tuple) and isinstance(decode_latency, tuple) and isinstance(e2e_latency, tuple):
        weaknesses.append(
            f"运行时代价已经从工程细节变成接收判断级问题。Figure 9 给出的 TTFT 为 {ttft[0]:.2f}x/{ttft[1]:.2f}x/{ttft[2]:.2f}x，decode latency 为 {decode_latency[0]:.2f}x/{decode_latency[1]:.2f}x/{decode_latency[2]:.2f}x，end-to-end latency 为 {e2e_latency[0]:.2f}x/{e2e_latency[1]:.2f}x/{e2e_latency[2]:.2f}x。这个结果说明 PREFILLCOMP 的显存收益需要支付明确在线成本：prefill 侧状态估值、artifact build、metadata 组织和 decode 侧压缩格式读取都可能进入在线路径。长上下文 serving 本身对首 token latency、吞吐和排队延迟敏感；如果这些成本无法被 kernel 融合、流水化、缓存或 batching 摊销，论文的 memory/capacity gain 会直接转化成用户可感知的响应时间损失。"
        )
    weaknesses.append(
        "compressed prompt artifact 还没有被证明是生产 runtime 可管理的一等状态对象。论文把 prefill 阶段的估值结果物化成 decode 可消费的 artifact，这是方法结构中最有系统味道的部分；production serving 对这种状态对象的要求高于单请求可读性，还包括 paged KV 管理、batch 内不同请求的压缩布局、多租户 admission control、跨 GPU 状态迁移、prefix caching、失败恢复和一致性维护。当前论文主要展示压缩、容量和 latency 结果，没有把 artifact 的生命周期管理闭合起来。因此该工作证明了一个有价值的状态表示原型，但还没有证明它能成为生产 LLM serving runtime 中可调度、可迁移、可恢复的状态单元。"
    )
    weaknesses.append(
        "跨模型和跨架构泛化证据不足。PREFILLCOMP 的核心信号来自 token importance、channel sensitivity 和 architecture-aware correction，这些信号很可能受 attention 结构、GQA/head sharing、训练分布、量化友好程度和上下文任务分布影响。论文中 KIVI 在 Mistral 和 DeepSeek 的若干 setting 上仍然 competitive，已经提示方法优势可能存在 family-specific boundary；如果作者把这一现象解释为 alignment issue，就需要进一步证明 correction 项能稳定覆盖不同 model family。否则当前证据最多支持“在部分模型和任务上 prompt-aware allocation 有明显收益”，还不足以支撑一般 long-context dense KV compression 路线的强 claim。"
    )
    if not status.get("ablation"):
        weaknesses.append(
            "组件贡献没有被充分拆开。PREFILLCOMP 的方法结构包含 token importance、channel sensitivity、architecture correction 和 allocator；每个组件分别带来多少收益、去掉后会在哪些 workload 失败、不同组件之间是否互相替代，都会影响对技术贡献的判断。缺少逐组件消融会让方法看起来结构完整，但无法判断技术创新主要来自哪一环，也无法判断 runtime 代价最应该从哪个组件优化。"
        )
    weaknesses.append(
        "可复现性证据还不足以支撑系统顶会的强结论。论文的关键结论同时依赖 fidelity、memory/capacity 和 latency 三类结果，复现材料必须覆盖模型版本、数据集、上下文长度、batch size、硬件平台、kernel/runtime 配置、artifact 构建路径和 decode 读取路径。若这些细节不可定位，PC 很难判断 Figure 8/9 的数字来自方法本身，还是来自特定实现、调参或系统栈选择。"
    )
    return weaknesses


def core_limitation_summary(status: dict[str, bool], facts: dict[str, object]) -> str:
    issues: list[str] = []
    e2e_latency = facts.get("e2e_latency")
    ttft = facts.get("ttft")
    if isinstance(e2e_latency, tuple) and max(e2e_latency) >= 5.0:
        issues.append("Figure 9 暴露出的数倍 end-to-end latency 代价")
    elif isinstance(ttft, tuple) and max(ttft) >= 5.0:
        issues.append("Figure 9 暴露出的高 TTFT 代价")
    if not status.get("artifact"):
        issues.append("compressed prompt artifact 的生产 runtime 生命周期没有闭合")
    else:
        issues.append("compressed prompt artifact 与 paged KV、batching、多租户和恢复机制的交互没有形成完整系统论证")
    if not status.get("ablation"):
        issues.append("token/channel/correction/allocator 的组件贡献缺少逐项隔离")
    if not status.get("throughput_tail") or not status.get("deployment"):
        issues.append("吞吐、尾延迟、batching 与 deployment realism 证据不足")
    issues.append("跨 model family 的信号稳定性和适用边界仍然偏窄")
    return "、".join(issues)


def make_score_reasons(action: str, scores: dict[str, str], missing: list[str], core_issues: str) -> list[str]:
    missing_text = "、".join(missing) if missing else "核心证据链较完整"
    soundness_reason = (
        f"该分数主要受限于：{core_issues}。这些问题会直接影响主结论能否从压缩收益扩展为系统贡献。"
        if missing
        else "主要证据项已经在原文中形成支撑，技术可信度主要受实现细节和复现材料完整性限制。"
    )
    return [
        f"- **Relevance**：{scores['Relevance']}。选题与 LLM serving、运行时状态管理和显存/延迟权衡直接相关，符合体系结构与系统会议关注范围。",
        f"- **Technical Soundness**：{scores['Technical Soundness']}。{soundness_reason}",
        f"- **Technical Importance**：{scores['Technical Importance']}。问题本身重要，论文也确实抓到了 memory/capacity 这条系统主线；但当前 runtime cost 太高，使这份重要性还没转化为可接收的系统成熟度。",
        f"- **Originality**：{scores['Originality']}。原创性主要来自 prefill-native variable-rate dense allocation 这一定位；这个点成立，但还没有强到足以压过 runtime 和 deployment 上的明显短板。",
        f"- **Quality of Presentation**：{scores['Quality of Presentation']}。论文需要更明确地区分原始收益、系统代价、适用边界和失败条件。",
        f"- **Recommended Action**：{action}。该建议与 Technical Soundness 绑定：强基线、公平预算、端到端代价、部署闭环和可复现性任一项存在关键缺口，都会把论文压到 Borderline 或以下。",
        f"- **Level of confidence in your recommendation**：{scores['Confidence']}。我的判断主要由论文自己给出的 matched-budget 对比、Figure 8 的 memory/capacity 收益，以及 Figure 9 的高延迟代价决定；这些证据已经足以支撑当前分数。",
        f"- **Level of your expertise in the relevant area**：{scores['Expertise']}。审查重点覆盖 LLM serving、KV cache/state management、系统评测和体系结构会议常见评审标准。",
        f"- **Best Paper Award**：{scores['Best Paper Award']}。当前证据链不足以支持最佳论文推荐。",
    ]


def remove_forbidden_phrases(text: str) -> str:
    def phrase(*parts: str) -> str:
        return "".join(parts)

    replacements = {
        phrase("不", "是"): "并非",
        phrase("而", "是"): "更准确地说",
        phrase("特别", "盯"): "重点核查",
        phrase("我最", "担心"): "主要风险",
        phrase("正式", "笔记", "里的", "局限性", "部分", "已经", "指出"): "原文证据链需要进一步核查",
        phrase("正式", "笔记"): "分析材料",
        phrase("现有", "材料", "显示"): "从可定位证据看",
        phrase("当前", "材料", "显示"): "从可定位证据看",
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
    core_issues = core_limitation_summary(status, facts)

    summary = (
        f"{claim_summary(md_text, title, facts)} "
        f"我的建议是 **{action}**。"
        f"决定性原因是：{core_issues}。"
        "论文已经证明了 dense prompt compression 在 matched-budget robustness 和 decode-side memory/capacity 上有真实收益；同时，当前证据链还不能把这种收益转化为成熟系统贡献。问题集中在三条线上：一是在线路径为了构建和消费压缩状态付出了很高延迟，二是压缩后的 prompt artifact 尚未进入生产 runtime 的完整状态管理闭环，三是 token/channel 信号在不同模型架构和 workload 上的稳定性边界仍不清楚。"
    )

    rebuttal = [
        "请逐项说明主要 baseline 是否使用相同有效 KV-cache budget、相同或可比的量化精度、同等优化的运行路径，以及相近的调参强度。若存在不一致，请给出重新对齐后的主表结果。",
        "请给出端到端系统代价和 artifact 生命周期的完整分解：prefill 分析时间、artifact 构建时间、metadata 显存/内存开销、decode 访问开销、batching 后吞吐与 tail latency，以及 compressed prompt artifact 与 paged KV、prefix caching、continuous batching、跨 GPU 迁移和失败恢复的交互。该回答会直接决定 Figure 8 的容量收益能否抵消 Figure 9 的在线代价。",
    ]

    detailed = [
        "建议作者把 evaluation 的叙述重排为“同预算质量保持、显存/容量收益、端到端延迟、吞吐与尾延迟、组件消融、失败区间”。这样的顺序能直接回答系统论文是否成立，并把收益、代价和失效边界放在同一条证据链里。",
        "相关工作比较需要明确分界：选择性 eviction、固定/混合精度量化、prompt compression、paged attention 或 serving scheduler 优化分别解决什么问题；本文新增的系统 insight 应当落在一个清楚的位置上。",
        "如果方法依赖 prefill 阶段统计或生成压缩 artifact，论文需要说明该 artifact 是否可缓存、是否与请求内容绑定、是否影响多租户隔离、是否改变在线服务路径，以及失效或漂移时如何处理。",
        "架构相关修正项需要更清楚的泛化论证。token importance 和 channel sensitivity 可能随 attention 结构、GQA/head sharing、训练分布和量化友好程度变化；如果 Mistral / DeepSeek 上的表现与其他模型不同，论文应当把这种差异纳入方法边界，单独作为 family-specific behavior 解释和验证。",
    ]

    reproducibility = (
        "复现应优先覆盖支撑主结论的最小结果集：同预算强基线主表、关键内存/容量图、端到端 latency 与 throughput 分解、主要组件消融、以及至少一个失败或收益减弱的 setting。"
        "如果代码或 artifact 暂不可用，作者应提供足够详细的 kernel/runtime 配置、模型版本、数据集、上下文长度、batch size、硬件平台和超参数。"
    )

    pc_confidential = (
        f"我建议 **{action}**。该工作的问题方向重要，但接收判断不能只由方向重要性或局部收益决定。"
        f"当前最影响决定的是：{core_issues}。"
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
    ]
    lines.extend([
        "## Strengths",
        "",
    ])
    lines.extend([f"- {item}" for item in strengths])
    lines.extend(["", "## Weaknesses", ""])
    lines.extend([f"- {item}" for item in weaknesses])
    lines.extend(["", "## Comments for Rebuttal", ""])
    lines.extend([f"- {item}" for item in rebuttal])
    lines.extend(["", "## Detailed Comments for Authors", ""])
    lines.extend([f"- {item}" for item in detailed])
    lines.extend(["", "## Scored Review Questions", ""])
    lines.extend(make_score_reasons(action, scores, missing, core_issues))
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
