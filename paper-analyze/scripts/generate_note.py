#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a high-quality Chinese paper note from MinerU assets."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import requests
import tomllib


DEFAULT_VAULT = Path("C:/Users/peng/Documents/PHR/obsidian_phr")
DEFAULT_CODEX_CONFIG = Path("C:/Users/peng/.codex/config.toml")
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


SYSTEM_PROMPT = """????????????????????????

?????????????????????????????????????????????????????

????
1. ???????????????????? Transformer ? LLM ????????????????????
2. ?????????????????????????????????
3. ??????????????????? bullet list ??????
4. ????????????????????????????
5. `What is the design?` ? `????????` ???????????????????????????????????????????
6. `?????????` ?????????????????????????????????????????????????
7. ???? `## ?????` ?????????????????
8. ?????????????????????????????? `TBD`?
9. ????open gap?????????????????????????????????????????
10. ?????????????????????????????????
11. ?????????????????????????????????????????????
12. ???? KV cache?prefill?decode?tensor parallelism?GQA?TTFT?throughput?context-fit frontier?artifact?pipeline bubble ??????????????????????????
13. ????????????????????????????????????????????????????????????
"""


REFINE_SYSTEM_PROMPT = """????????????????????????

???
1. ?? Markdown ????????????? section ???
2. ????????????????????????????????? AI ???
3. ??????????????????????
4. ???????????????????????????????????
5. ??????????????????????????????????????
6. ?????????????????????
7. ???????????????????????
8. ????????? Markdown???????????
"""

# Alignment contract with `paper-analyze/SKILL.md`.
# When style or structure requirements change, update both places together.
NOTE_READER_MODEL = """
默认读者是具备科研训练、了解大模型基础概念、但记得不牢且理解不深入的研究生。
因此解释不能假设读者已经自动把 attention、KV cache、prefill、decode、GQA、张量并行、GPU kernel、访存瓶颈这些概念串起来。
每次真正用到术语时，都要顺手解释它在本文中的角色，以及它为什么会影响系统设计或实验结论。
""".strip()

NOTE_STYLE_CONTRACT = """
整篇笔记都要写成讲给课题组同学听的教学式长段解释，而不是提纲式摘要。
每个核心段落默认遵循“场景和对象 -> 论文具体做法 -> 为什么这样做能成立 -> 工程收益和工程代价”的顺序。
要主动补因果桥，说明读者为什么应该关心这一点、这一机制解决了什么困惑或瓶颈、以及它与前后内容如何连起来。
避免术语堆叠、空泛套话和只对熟手友好的压缩表达。
""".strip()

NOTE_STRUCTURE_CONTRACT = """
必须稳定保留这些核心 section：一句话总结、资产分类判断 + 原因、导师七问、综述五字段、方法整体机制总结、分析框架图、实验设置和关键结果、与已有工作的关系、对你研究方向的价值、局限性与 Open Gap、人工阅读重点、可提炼的研究命题。
导师七问默认采用“背景解释 / 本文做法 / 关键结论与意义”的三段结构。
综述五字段必须回到固定字段本身，不能退化成关键词卡片。
人工阅读重点必须包含：必须回原文核对的部分、核对目的、可以暂时不细读的部分、查漏补缺后的判断标准。
""".strip()

SYSTEM_PROMPT = f"""你是一名严格、克制、擅长系统论文讲解的研究助理。

你的任务不是写摘要，也不是拼接提纲，而是把论文整理成一份真正能给课题组同学阅读、讨论和复述的中文分析笔记。

读者模型：
{NOTE_READER_MODEL}

风格契约：
{NOTE_STYLE_CONTRACT}

结构契约：
{NOTE_STRUCTURE_CONTRACT}

其他硬约束：
1. 对局限、open gap、与已有工作的边界、实验是否真正支持 claim、对研究方向的价值这类判断性内容，要采用接近严格审稿的证据标准。
2. 如果证据不足，必须明确说明边界，不能替作者补完论证，更不能写 `TBD`。
3. 禁止大量复述原文英文句子；应以中文解释、系统化转述和证据约束为主。
4. 避免使用“不是……而是……”“换句话说”“其实”“更具体地说”“可以概括成”这类空转套话。
5. 只允许在 `## 分析框架图` 中插入一张方法图；实验部分不插图。
"""

REFINE_SYSTEM_PROMPT = f"""你负责对已经生成的论文笔记做严格润色和结构校正。

请始终以这份对齐契约为准：

读者模型：
{NOTE_READER_MODEL}

风格契约：
{NOTE_STYLE_CONTRACT}

结构契约：
{NOTE_STRUCTURE_CONTRACT}

额外要求：
1. 保持 Markdown 标题结构稳定，不要改动既定 section 层级。
2. 删除空泛口头连接词和 AI 套话，但不要把段落压短成提纲。
3. 如果某段已经有信息但还像写给熟手看的压缩说明，请主动补场景、对象和因果桥。
4. 分析框架图最多保留一张；实验部分不能插图。
5. 所有判断句都应尽量收紧到原文证据支持的边界内。
6. 输出仍然必须是完整 Markdown，不能附加解释性前言。
"""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_manifest(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_line(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_text(text).replace("\n", " ")).strip()


def clip_text(text: str, max_len: int = 420) -> str:
    cleaned = clean_line(text)
    if len(cleaned) <= max_len:
        return cleaned
    window = cleaned[:max_len]
    cut_candidates = [window.rfind(x) for x in [".", "。", ";", "；", "!", "！", "?", "？"]]
    cut = max(cut_candidates)
    if cut > int(max_len * 0.6):
        return window[: cut + 1].strip()
    cut = window.rfind(" ")
    if cut > int(max_len * 0.75):
        return window[:cut].strip()
    return window.strip()


def split_sections(text: str) -> List[Tuple[str, str]]:
    pattern = re.compile(r"(?m)^##\s+([^\n]+)\n")
    matches = list(pattern.finditer(text))
    sections: List[Tuple[str, str]] = []
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = normalize_text(text[start:end])
        sections.append((title, body))
    return sections


def first_paragraph(text: str) -> str:
    for part in re.split(r"\n\s*\n", text or ""):
        line = clean_line(part)
        if len(line) >= 40:
            return line
    return clean_line(text)


def first_sentences(text: str, limit: int = 3) -> str:
    source = clean_line(text)
    parts = re.split(r"(?<=[.!?])\s+|(?<=[。！？])", source)
    items = [item.strip() for item in parts if len(item.strip()) >= 18]
    return " ".join(items[:limit])


def find_section(sections: Sequence[Tuple[str, str]], keywords: Sequence[str]) -> Tuple[str, str]:
    keys = [item.lower() for item in keywords]
    for title, body in sections:
        lower = title.lower()
        if any(keyword in lower for keyword in keys):
            return title, body
    return "", ""


def collect_sections(sections: Sequence[Tuple[str, str]], keywords: Sequence[str], max_items: int = 8) -> List[dict]:
    keys = [item.lower() for item in keywords]
    items: List[dict] = []
    for title, body in sections:
        lower = title.lower()
        if any(keyword in lower for keyword in keys):
            items.append(
                {
                    "title": title,
                    "summary": first_sentences(body, 5),
                    "paragraph": clip_text(first_paragraph(body), 700),
                }
            )
        if len(items) >= max_items:
            break
    return items


def parse_figure_entries(md_text: str) -> List[dict]:
    image_pattern = re.compile(r"!\[[^\]]*\]\((images/[^\)]+)\)")
    caption_pattern = re.compile(r"Figure\s+(\d+[a-z]?)[:.]?\s*(.+?)(?=\n\s*(?:Figure\s+\d+[a-z]?[:.]?|!\[|## )|\Z)", re.IGNORECASE | re.DOTALL)
    figures = []
    for match in caption_pattern.finditer(md_text):
        previous_images = list(image_pattern.finditer(md_text, 0, match.start()))
        image_ref = ""
        if previous_images:
            previous = previous_images[-1]
            if match.start() - previous.end() <= 1800:
                image_ref = previous.group(1).strip()
        figures.append(
            {
                "number": match.group(1).lower(),
                "image_ref": image_ref,
                "caption": clip_text(match.group(2), 260),
            }
        )
    return figures


def mineru_content_list_path(mineru_md: Path) -> Optional[Path]:
    stem = mineru_md.stem
    candidates = [
        mineru_md.with_name(f"{stem}_content_list.json"),
        mineru_md.with_name(f"{stem}_content_list_v2.json"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def first_caption_text(value: object) -> str:
    if isinstance(value, list):
        for item in value:
            text = clean_line(str(item or ""))
            if text:
                return text
        return ""
    return clean_line(str(value or ""))


def parse_figure_entries_from_content_list(manifest: dict) -> List[dict]:
    mineru_md = Path(str(manifest.get("mineru_md") or ""))
    if not mineru_md.exists():
        return []

    content_list = mineru_content_list_path(mineru_md)
    if not content_list:
        return []

    try:
        payload = json.loads(content_list.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("content") or []
    else:
        items = payload

    figure_pattern = re.compile(r"Figure\s+(\d+[a-z]?)[:.]?\s*(.+)", re.IGNORECASE | re.DOTALL)
    figures: List[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").lower()
        if item_type not in {"image", "table", "chart"}:
            continue

        caption = ""
        for key in ("image_caption", "table_caption", "chart_caption", "caption"):
            caption = first_caption_text(item.get(key))
            if caption:
                break
        if not caption:
            continue

        match = figure_pattern.match(caption)
        if not match:
            continue

        image_ref = clean_line(str(item.get("img_path") or ""))
        figures.append(
            {
                "number": match.group(1).lower(),
                "image_ref": image_ref,
                "caption": clip_text(match.group(2), 260),
                "source_type": item_type,
            }
        )
    return figures


def merge_figure_entries(manifest: dict, md_text: str) -> List[dict]:
    merged: Dict[str, dict] = {}

    for item in parse_figure_entries(md_text):
        key = str(item.get("number") or "").lower()
        if key:
            merged[key] = item

    for item in parse_figure_entries_from_content_list(manifest):
        key = str(item.get("number") or "").lower()
        if not key:
            continue
        existing = merged.get(key, {})
        chosen = dict(existing) if existing else {}
        chosen["number"] = key
        chosen["caption"] = item.get("caption") or existing.get("caption") or ""
        chosen["image_ref"] = item.get("image_ref") or existing.get("image_ref") or ""
        chosen["source_type"] = item.get("source_type") or existing.get("source_type") or ""
        merged[key] = chosen

    return [merged[key] for key in sorted(merged.keys(), key=lambda value: (int(re.match(r"\d+", value).group(0)), value))]


def resolve_image_alias(manifest: dict, image_ref: str) -> Optional[str]:
    filename = Path(image_ref).name
    for item in manifest.get("image_aliases", []) or []:
        original = str(item.get("original") or "").strip()
        alias = str(item.get("alias") or "").strip()
        if filename == alias:
            return alias
        if filename == original and alias:
            return alias
    return None


def obsidian_link(path: Path, vault: Path, label: Optional[str] = None) -> str:
    rel = path.relative_to(vault).as_posix() if path.is_relative_to(vault) else path.as_posix()
    rel = re.sub(r"\.md$", "", rel)
    return f"[[{rel}|{label or path.stem}]]"


def yaml_quote(value: object) -> str:
    text = str(value or "待确认").replace('"', '\\"')
    return f'"{text}"'


def slug_tag(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "paper"


def note_title_from_manifest(manifest: dict) -> str:
    title = clean_line(str(manifest.get("title") or manifest.get("paper_id") or "Untitled Paper"))
    if not title:
        title = str(manifest.get("paper_id") or "Untitled Paper")
    return title


def build_frontmatter(manifest: dict) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    domain = manifest.get("domain") or "Uncategorized"
    tags = ["paper-note", slug_tag(domain), "llm-systems"]
    unique_tags = []
    for tag in tags:
        if tag not in unique_tags:
            unique_tags.append(tag)
    tag_lines = "\n".join(f"  - {tag}" for tag in unique_tags)
    return "\n".join(
        [
            "---",
            f"date: {yaml_quote(manifest.get('updated') or today)}",
            f"paper_id: {yaml_quote(manifest.get('paper_id'))}",
            f"title: {yaml_quote(note_title_from_manifest(manifest))}",
            f"authors: {yaml_quote(manifest.get('authors'))}",
            f"year: {yaml_quote(manifest.get('year'))}",
            f"venue: {yaml_quote(manifest.get('venue') or '待确认')}",
            f"domain: {yaml_quote(domain)}",
            "tags:",
            tag_lines,
            "status: analyzed",
            f"created: {yaml_quote(manifest.get('created') or manifest.get('updated') or today)}",
            f"updated: {yaml_quote(today)}",
            "---",
        ]
    )


def build_basic_info(manifest: dict, vault: Path) -> str:
    translated_md = manifest.get("translated_md")
    translated_link = "待生成"
    if translated_md and Path(translated_md).exists():
        translated_link = obsidian_link(Path(translated_md), vault, "中文版 Markdown")
    lines = [
        "## 论文基本信息",
        f"- **论文 ID**：{manifest.get('paper_id') or '待确认'}",
        f"- **作者**：{manifest.get('authors') or '待确认'}",
        f"- **年份**：{manifest.get('year') or '待确认'}",
        f"- **会议/期刊**：{manifest.get('venue') or '待确认'}",
        f"- **PDF**：{obsidian_link(Path(manifest['pdf']), vault, '原始 PDF')}",
        f"- **MinerU Markdown**：{obsidian_link(Path(manifest['mineru_md']), vault, 'MinerU Markdown')}",
        f"- **中文版 Markdown**：{translated_link}",
        f"- **资产索引**：{obsidian_link(Path(manifest['assets_index']), vault, 'assets')}",
    ]
    source_url = manifest.get("source_url")
    if source_url:
        lines.append(f"- **来源**：<{source_url}>")
    return "\n".join(lines)


def replace_frontmatter_and_basic_info(note_text: str, manifest: dict, vault: Path) -> str:
    text = note_text.strip()
    text = re.sub(r"(?s)^---\n.*?\n---\n*", "", text, count=1).strip()
    text = re.sub(r"(?m)^#\s+.+", f"# {note_title_from_manifest(manifest)}", text, count=1)
    if not re.search(r"(?m)^#\s+", text):
        text = f"# {note_title_from_manifest(manifest)}\n\n{text}"

    basic = build_basic_info(manifest, vault)
    pattern = re.compile(r"(?ms)^##\s*论文基本信息\s*\n.*?(?=^##\s+|\Z)")
    if pattern.search(text):
        text = pattern.sub(basic + "\n\n", text, count=1)
    else:
        title_match = re.search(r"(?m)^#\s+.+\n", text)
        insert_at = title_match.end() if title_match else 0
        text = text[:insert_at].rstrip() + "\n\n" + basic + "\n\n" + text[insert_at:].lstrip()

    return build_frontmatter(manifest) + "\n\n" + text.strip() + "\n"


def read_codex_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return data if isinstance(data, dict) else {}


def resolve_api_settings(cli_model: Optional[str], cli_base_url: Optional[str]) -> Tuple[str, str, str]:
    codex_config = read_codex_config(DEFAULT_CODEX_CONFIG)
    provider_name = str(codex_config.get("model_provider") or "").strip()
    providers = codex_config.get("model_providers") or {}
    provider = providers.get(provider_name) if isinstance(providers, dict) else None
    codex_base_url = ""
    if isinstance(provider, dict):
        codex_base_url = str(provider.get("base_url") or "").strip()

    api_key = (
        os.environ.get("OPENAI_API_KEY", "").strip()
        or os.environ.get("OPENAI_APIKEY", "").strip()
        or os.environ.get("API_KEY", "").strip()
    )
    env_base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
    env_model = os.environ.get("OPENAI_MODEL", "").strip()

    base_url = (cli_base_url or env_base_url or codex_base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    model = (cli_model or env_model or DEFAULT_MODEL).strip()
    if not api_key:
        raise SystemExit("Missing API key. Set OPENAI_API_KEY or API_KEY.")
    return api_key, base_url, model


def post_responses(api_key: str, base_url: str, model: str, system_prompt: str, user_prompt: str, timeout: int = 240) -> str:
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    session = requests.Session()
    session.trust_env = False
    last_error: Optional[Exception] = None
    for _ in range(3):
        try:
            response = session.post(f"{base_url}/responses", headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            chunks: List[str] = []
            for item in data.get("output", []):
                for content in item.get("content", []):
                    text = content.get("text")
                    if text:
                        chunks.append(text)
            result = "\n".join(chunks).strip()
            if not result:
                raise RuntimeError("Model returned empty content.")
            return result
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Failed to generate content via model API after retries: {last_error}")


def build_evidence_json(manifest: dict, sections: Sequence[Tuple[str, str]], figures: Sequence[dict]) -> dict:
    abstract_title, abstract_body = find_section(sections, ["abstract"])
    intro_title, intro = find_section(sections, ["introduction"])
    background_title, background = find_section(sections, ["background"])
    analysis_title, analysis = find_section(sections, ["analysis"])
    design_title, design = find_section(sections, ["design"])
    runtime_title, runtime = find_section(sections, ["runtime"])
    implementation_title, implementation = find_section(sections, ["implementation"])
    setup_title, setup = find_section(sections, ["experiment setup"])
    throughput_title, throughput = find_section(sections, ["throughput"])
    latency_title, latency = find_section(sections, ["latency"])
    ablation_title, ablation = find_section(sections, ["ablation"])
    resource_title, resource = find_section(sections, ["resource usage"])
    generalization_title, generalization = find_section(sections, ["performance on other llms"])
    related_title, related = find_section(sections, ["related work"])
    conclusion_title, conclusion = find_section(sections, ["conclusion"])
    method_details = collect_sections(
        sections,
        [
            "operation characteristics",
            "intra-device parallelism",
            "automated pipeline search",
            "kernel profiling",
            "interference modeling",
            "pipeline structure search",
            "refining the pipeline",
            "example pipelines",
            "nanoflow runtime",
            "request scheduling",
            "kv-cache management",
            "implementation",
        ],
        max_items=12,
    )
    experiment_details = collect_sections(
        sections,
        [
            "experiment setup",
            "throughput",
            "latency",
            "ablation",
            "resource usage",
            "performance on other llms",
        ],
        max_items=10,
    )

    figure_items: List[dict] = []
    for figure in figures:
        figure_items.append(
            {
                "number": figure["number"],
                "caption_summary": figure["caption"],
                "image_alias": resolve_image_alias(manifest, figure["image_ref"]),
            }
        )

    analysis_figure = None
    for item in figure_items:
        caption = (item.get("caption_summary") or "").lower()
        if any(key in caption for key in ["automatically generated by nanoflow", "workflow", "overall framework"]):
            analysis_figure = item
            break
    if analysis_figure is None:
        for item in figure_items:
            caption = (item.get("caption_summary") or "").lower()
            if "execution pipeline" in caption and "existing systems" not in caption:
                analysis_figure = item
                break

    return {
        "paper_meta": {
            "paper_id": manifest.get("paper_id"),
            "title": manifest.get("title"),
            "authors": manifest.get("authors"),
            "year": manifest.get("year"),
            "venue": manifest.get("venue") or "待确认",
            "domain": manifest.get("domain"),
            "classification_reason": manifest.get("classification_reason"),
            "source_url": manifest.get("source_url"),
            "abstract": clip_text(manifest.get("abstract") or "", 520),
        },
        "abstract": {
            "title": abstract_title,
            "summary": first_sentences(abstract_body, 4),
            "paragraph": clip_text(first_paragraph(abstract_body), 320),
        },
        "sections": {
            "introduction": {"title": intro_title, "summary": first_sentences(intro, 4), "paragraph": clip_text(first_paragraph(intro), 380)},
            "background": {"title": background_title, "summary": first_sentences(background, 4), "paragraph": clip_text(first_paragraph(background), 380)},
            "analysis": {"title": analysis_title, "summary": first_sentences(analysis, 4), "paragraph": clip_text(first_paragraph(analysis), 380)},
            "design": {"title": design_title, "summary": first_sentences(design, 4), "paragraph": clip_text(first_paragraph(design), 380)},
            "runtime": {"title": runtime_title, "summary": first_sentences(runtime, 4), "paragraph": clip_text(first_paragraph(runtime), 380)},
            "implementation": {"title": implementation_title, "summary": first_sentences(implementation, 4), "paragraph": clip_text(first_paragraph(implementation), 320)},
            "experiment_setup": {"title": setup_title, "summary": first_sentences(setup, 4), "paragraph": clip_text(first_paragraph(setup), 320)},
            "throughput": {"title": throughput_title, "summary": first_sentences(throughput, 4), "paragraph": clip_text(first_paragraph(throughput), 380)},
            "latency": {"title": latency_title, "summary": first_sentences(latency, 4), "paragraph": clip_text(first_paragraph(latency), 380)},
            "ablation": {"title": ablation_title, "summary": first_sentences(ablation, 4), "paragraph": clip_text(first_paragraph(ablation), 380)},
            "resource_usage": {"title": resource_title, "summary": first_sentences(resource, 4), "paragraph": clip_text(first_paragraph(resource), 340)},
            "generalization": {"title": generalization_title, "summary": first_sentences(generalization, 4), "paragraph": clip_text(first_paragraph(generalization), 340)},
            "related_work": {"title": related_title, "summary": first_sentences(related, 4), "paragraph": clip_text(first_paragraph(related), 340)},
            "conclusion": {"title": conclusion_title, "summary": first_sentences(conclusion, 4), "paragraph": clip_text(first_paragraph(conclusion), 340)},
        },
        "method_details": method_details,
        "experiment_details": experiment_details,
        "figures": figure_items,
        "analysis_figure": analysis_figure,
    }


def publish_analysis_figure(manifest: dict, vault: Path, evidence: dict) -> None:
    analysis_figure = evidence.get("analysis_figure") or {}
    alias = str(analysis_figure.get("image_alias") or "").strip()
    if not alias:
        return

    source_path = None
    for item in manifest.get("image_aliases", []) or []:
        if str(item.get("alias") or "").strip() == alias:
            source_path = str(item.get("path") or "").strip()
            break
    if not source_path:
        return

    source = Path(source_path)
    if not source.exists():
        return

    target_dir = vault / "20_Research" / "Papers" / "_img"
    target_dir.mkdir(parents=True, exist_ok=True)
    published_name = f"{str(manifest.get('paper_id') or 'paper').replace('.', '-')}-{alias}"
    target = target_dir / published_name
    if not target.exists():
        shutil.copy2(source, target)
    evidence["analysis_figure"]["published_name"] = published_name


def has_published_analysis_figure(evidence: dict) -> bool:
    return bool((evidence.get("analysis_figure") or {}).get("published_name"))


def build_prompt(manifest: dict, vault: Path, evidence: dict) -> str:
    pdf_link = obsidian_link(Path(manifest["pdf"]), vault, "原始 PDF")
    mineru_link = obsidian_link(Path(manifest["mineru_md"]), vault, "MinerU Markdown")
    translated_link = "待生成"
    translated_md = manifest.get("translated_md")
    if translated_md and Path(translated_md).exists():
        translated_link = obsidian_link(Path(translated_md), vault, "中文版 Markdown")
    assets_link = obsidian_link(Path(manifest["assets_index"]), vault, "assets")

    return f"""
请基于下面的结构化证据，写一篇高质量的 Obsidian 中文论文笔记。

这次最重要的要求不是“写得短”，而是“写得清楚、写得像我真的在给组里同学讲”。请优先保证段落密度、解释深度和结构稳定性。目标不是生成一份模板化分析，而是生成一份真正能拿来读、能拿来讲、能帮助理解方法和实验的笔记。

默认读者画像请固定成这样：读者是做系统或大模型方向的研究生，知道 Transformer、attention、KV cache、prefill、decode、张量并行这些词，但概念之间经常串不起来，也不一定能立刻把“模型结构细节”和“系统瓶颈”连成因果链。你写的时候要主动补这层桥，不能把读者当成已经完全懂的人。

输出格式必须严格遵守：
1. 直接输出完整 Markdown。
2. 先输出 frontmatter。
3. frontmatter 后紧接着输出一级标题。
4. 二级结构必须严格按下面顺序输出：
- ## 论文基本信息
- ## 一句话总结
- ## 资产分类判断 + 原因
- ## 导师七问
- ## 综述五字段
- ## 方法整体机制总结
- ## 分析框架图
- ## 实验设置和关键结果
- ## 与已有工作的关系
- ## 对你研究方向的价值
- ## 局限性与 Open Gap
- ## 人工阅读重点
- ## 可提炼的研究命题

导师七问下面的三级标题也必须严格按下面顺序输出，标题文字必须一字不差：
- ### 1. What is the problem?
- ### 2. Why it matters?
- ### 3. Why existing works fail?
- ### 4. What is the key idea?
- ### 5. What is the design?
- ### 6. What is the experimental plan?
- ### 7. What is the takeaway?

`## 综述五字段` 下面也必须严格按下面五个三级标题输出，标题文字必须一字不差：
- ### 1. State object
- ### 2. Control surface
- ### 3. Coupling path
- ### 4. Evaluation boundary
- ### 5. Remaining systems gap

5. “论文基本信息”部分必须使用这些固定链接：
- PDF：{pdf_link}
- MinerU Markdown：{mineru_link}
- 中文版 Markdown：{translated_link}
- 资产索引：{assets_link}

6. 图片规则：
- 整篇笔记里，只有 `## 分析框架图` 允许插入一张方法/流程/执行流水图。
- `## 实验设置和关键结果` 不允许插图，只能写 `### Figure X` 的中文解释。
- 如果 `analysis_figure` 中存在 `published_name`，`分析框架图` 才允许使用短文件名引用：`![[<published_name>|800]]`。
- 如果 `analysis_figure` 没有 `published_name`，说明当前 MinerU 没有可安全引用的相邻图片；这时只用文字解释框架图，不要自行编造图片链接。

7. “### 5. What is the design?” 的强制要求：
- 必须把方法拆成清晰的阶段或组件顺序来讲。
- 至少覆盖：每一阶段要解决什么、输入是什么、输出是什么、作者在这一阶段具体做了什么、为什么这一步可以成立、这一步的工程收益和工程代价是什么。
- 必须优先使用 evidence.method_details 中的子节证据，而不是只根据摘要或 `## 4 Design` 的开头概括。
- 如果 evidence.method_details 中出现分阶段搜索、kernel profiling、interference modeling、request scheduling、runtime event/dependency、状态分层、host-device 数据搬运等细节，要逐一讲清它们在系统路径中的位置。

8. “## 方法整体机制总结” 的强制要求：
- 用更顺的方式把全文最核心的方法链条再讲一遍。
- 从系统执行路径出发，把关键组件之间的先后关系、依赖关系、数据如何流动、控制决策如何落地讲清楚。
- 这部分必须像给同学讲系统设计一样细：先讲系统看到了什么输入和约束，再讲这些输入如何进入分析、搜索、规划或控制阶段，再讲运行时如何执行这些决策，最后讲收益和代价分别落在哪个阶段。

9. “## 实验设置和关键结果” 的强制要求：
- 先单独写 `### 实验设置`，交代硬件、模型、数据、baseline 和指标口径。
- 尽可能覆盖 evidence 中出现的主要图，不要只挑一两张。
- 每张图都要交代它在整篇论文中的职责：是在论证问题动机、验证方法假设、证明系统收益、揭示运行时代价，还是展示泛化边界。
- 解释结果时必须把指标放回系统语境。
- 不要插实验图。

10. 全文禁止出现英文原句、禁止出现“原文写明”“论文写道”等说法。
11. 禁止出现“不是……而是……”这种空转句式及其近似变体。
12. 尽量避免“原因很清楚”“纠正了一个……直觉”“换句话说”“其实”“更具体地说”“可以概括成”这类空洞口头连接词。需要推进论证时，直接讲对象、机制、证据和结论。
13. 证据不足时，用完整中文句子说明边界，不要写“TBD”式断句。
14. 如果需要写“研究问题 / 核心假设 / 方法路线 / 关键证据 / 结论边界”这类高密度总括内容，不要放进 `## 综述五字段`，否则会破坏该 section 的固定结构。
15. 目标风格请以高质量的 PREFILLCOMP 笔记为参照：总括段短而硬，机制段按链条展开，实验段按图组织，局限段先写现有限制再写后续可追问问题。
16. 除 `## 论文基本信息` 外，默认不要使用 bullet list 作为正文主体。`导师七问`、`综述五字段`、`方法整体机制总结`、`与已有工作的关系`、`对你研究方向的价值`、`局限性与 Open Gap`、`人工阅读重点` 都应以密实段落为主。
17. `## 导师七问` 下的每一个问题，默认都按三段展开：`背景解释：`、`本文做法：`、`关键结论与意义：`。每一问都要能单独拿出来给人讲清楚，不能只写 2-3 句摘要。
18. `## 综述五字段` 不能写成条目堆砌。每个字段至少写一段完整解释，把对象、控制面、耦合关系或边界放回系统上下文。
19. `## 人工阅读重点` 必须至少包含四个三级标题：`### 必须回原文核对的部分`、`### 核对目的`、`### 可以暂时不细读的部分`、`### 查漏补缺后的判断标准`。
20. `## 资产分类判断 + 原因` 不能只说“这是一篇 LLM Inference Systems 论文”。必须进一步解释：为什么它属于这个语境、这种分类如何帮助读者建立阅读主线、它和看起来相近但实际不同的论文类型如何区分。
21. `## 与已有工作的关系` 不能只列类别。要明确本文到底改变了状态对象、执行路径、控制面还是资源编排中的哪一层，并说明这样比较的意义。
22. `## 对你研究方向的价值` 不能停留在“有启发”。要抽象出可迁移的系统模式、可复用的控制结构，以及不能直接迁移的边界。
23. `## 局限性与 Open Gap` 先写贴着证据的“现有限制”，再写面向后续研究的“Open Gap”，两层都要用完整段落说明。
24. 每当正文第一次真正需要用到术语时，要顺手解释“它在本文里扮演什么角色”。例如，不要只说 `prefill`，而要说它为什么是一次性处理完整 prompt 的阶段、它为什么会影响 batch 形成或状态初始化；不要只说 `KV cache`，而要说它为什么会在 decode 里被反复读取、因此会变成系统资源压力。
25. 每个核心段落默认要补一层“为什么读者会关心这个”。也就是不要只说作者做了什么，还要说明这一步是在解决哪一种困惑、哪一种资源浪费、哪一种系统瓶颈。
26. 解释方法时，优先使用“先交代场景和对象 -> 再说论文具体怎么做 -> 再说为什么这样做能成立 -> 最后说它带来的收益和代价”这一节奏。不要从公式或组件名直接开讲。
27. 如果一段话里同时出现多个术语或缩写，默认认为读者不能自动把它们串起来。需要显式说清它们之间的关系，例如“因为……所以……”“这一步之后系统才能……”“这会进一步导致……”。不要只做术语堆叠。
28. 你的目标不是让段落看起来学术，而是让一个基础不错但没完全吃透这篇论文的人，顺着段落就能把问题背景、方法链条和实验意义讲给别人听。

下面是结构化证据 JSON：
{json.dumps(evidence, ensure_ascii=False, indent=2)}
"""


def refine_note_with_model(draft: str, evidence: dict, api_key: str, base_url: str, model: str) -> str:
    user_prompt = (
        "请润色并纠正下面这份论文笔记草稿。\n\n"
        "特别任务：\n"
        "1. 去掉空泛和 AI 套话，尤其是“不是……而是……”句式，以及“原因很清楚”“换句话说”“其实”“更具体地说”“可以概括成”这类口头填充词。\n"
        "2. 保持原有标题结构不变，导师七问的七个标题必须固定为英文原题，综述五字段的五个标题必须固定为 State object / Control surface / Coupling path / Evaluation boundary / Remaining systems gap。\n"
        "3. 实验部分不要插图；分析框架图只允许保留一张方法/流程/执行流水图。\n"
        "4. 保持整篇是中文讲解稿口吻，优先保留真正有信息量的机制、证据和边界解释。\n"
        "5. 你要主动把读者当成“懂基础词汇但概念链条不够稳的课题组同学”。若某段只是把术语堆在一起、缺少桥接解释，请补上为什么这个术语在本文中重要、它与前后机制有什么关系。\n"
        "6. 若某段直接从组件名、公式名、缩写名开始，而没有先交代对象、场景或系统困惑，请改写成更容易讲给同学听的顺序。\n\n"
        f"Figure 证据：\n{json.dumps(evidence.get('figures', []), ensure_ascii=False, indent=2)}\n\n"
        f"推荐的分析框架图：\n{json.dumps(evidence.get('analysis_figure'), ensure_ascii=False, indent=2)}\n\n"
        f"草稿如下：\n{draft}"
    )
    return post_responses(api_key, base_url, model, REFINE_SYSTEM_PROMPT, user_prompt)


def enforce_visual_policy(note_text: str, evidence: dict) -> str:
    lines = note_text.splitlines()
    new_lines: List[str] = []
    inside_analysis = False
    inside_experiment = False
    analysis_inserted = False
    published_name = ""
    if evidence.get("analysis_figure") and evidence["analysis_figure"].get("published_name"):
        published_name = str(evidence["analysis_figure"]["published_name"])

    for line in lines:
        stripped = line.strip()
        if stripped == "## 分析框架图":
            inside_analysis = True
            inside_experiment = False
            analysis_inserted = False
            new_lines.append(line)
            continue
        if stripped == "## 实验设置和关键结果":
            inside_analysis = False
            inside_experiment = True
            new_lines.append(line)
            continue
        if stripped.startswith("## ") and stripped not in {"## 分析框架图", "## 实验设置和关键结果"}:
            inside_analysis = False
            inside_experiment = False

        if inside_experiment and (stripped.startswith("![[") or re.match(r"!\[[^\]]*\]\([^)]+\)", stripped)):
            continue

        if inside_analysis and (stripped.startswith("![[") or re.match(r"!\[[^\]]*\]\([^)]+\)", stripped)):
            continue

        new_lines.append(line)

        if inside_analysis and published_name and not analysis_inserted and stripped:
            new_lines.append("")
            new_lines.append(f"![[{published_name}|800]]")
            analysis_inserted = True

    return "\n".join(new_lines).strip() + "\n"


def remove_broken_and_experiment_images(note_text: str) -> str:
    lines = note_text.splitlines()
    cleaned: List[str] = []
    inside_experiment = False
    inside_analysis = False
    analysis_image_seen = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## 分析框架图":
            inside_analysis = True
            inside_experiment = False
            analysis_image_seen = False
            cleaned.append(line)
            continue
        if stripped == "## 实验设置和关键结果":
            inside_analysis = False
            inside_experiment = True
            cleaned.append(line)
            continue
        if stripped.startswith("## ") and stripped not in {"## 分析框架图", "## 实验设置和关键结果"}:
            inside_analysis = False
            inside_experiment = False

        is_image = stripped.startswith("![[") or bool(re.match(r"!\[[^\]]*\]\([^)]+\)", stripped))
        if inside_experiment and is_image:
            continue
        if is_image and not inside_analysis:
            continue
        if inside_analysis and is_image:
            if analysis_image_seen:
                continue
            analysis_image_seen = True
        cleaned.append(line)
    return "\n".join(cleaned).strip() + "\n"


def enforce_question_headings(note_text: str) -> str:
    if "## 导师七问" not in note_text:
        return note_text
    section_pattern = re.compile(r"(?ms)(^##\s*导师七问\s*\n)(.*?)(?=^##\s+|\Z)")
    match = section_pattern.search(note_text)
    if not match:
        return note_text
    body = match.group(2)
    replacements = [
        (r"(?m)^###\s*1\.\s*.+$", "### 1. What is the problem?"),
        (r"(?m)^###\s*2\.\s*.+$", "### 2. Why it matters?"),
        (r"(?m)^###\s*3\.\s*.+$", "### 3. Why existing works fail?"),
        (r"(?m)^###\s*4\.\s*.+$", "### 4. What is the key idea?"),
        (r"(?m)^###\s*5\.\s*.+$", "### 5. What is the design?"),
        (r"(?m)^###\s*6\.\s*.+$", "### 6. What is the experimental plan?"),
        (r"(?m)^###\s*7\.\s*.+$", "### 7. What is the takeaway?"),
    ]
    for pattern, target in replacements:
        body = re.sub(pattern, target, body, count=1)
    return note_text[: match.start()] + match.group(1) + body + note_text[match.end() :]


def enforce_review_fields_headings(note_text: str) -> str:
    if "## 综述五字段" not in note_text:
        return note_text
    section_pattern = re.compile(r"(?ms)(^##\s*综述五字段\s*\n)(.*?)(?=^##\s+|\Z)")
    match = section_pattern.search(note_text)
    if not match:
        return note_text
    body = match.group(2)
    replacements = [
        (r"(?m)^###\s*1\.\s*.+$", "### 1. State object"),
        (r"(?m)^###\s*2\.\s*.+$", "### 2. Control surface"),
        (r"(?m)^###\s*3\.\s*.+$", "### 3. Coupling path"),
        (r"(?m)^###\s*4\.\s*.+$", "### 4. Evaluation boundary"),
        (r"(?m)^###\s*5\.\s*.+$", "### 5. Remaining systems gap"),
    ]
    for pattern, target in replacements:
        body = re.sub(pattern, target, body, count=1)
    return note_text[: match.start()] + match.group(1) + body + note_text[match.end() :]


def strip_filler_phrases(text: str) -> str:
    replacements = [
        ("原因很清楚：", ""),
        ("更具体地说，", ""),
        ("换句话说，", ""),
        ("换句话说", ""),
        ("其实，", ""),
        ("其实", ""),
        ("可以概括成一句话：", ""),
        ("可以概括成：", ""),
        ("纠正了一个常见直觉：", ""),
        ("纠正了一个常见判断：", ""),
        ("纠正了一个很有影响力的工程直觉。", ""),
        ("从方法组成看，这篇文章也很完整。", ""),
        ("这几层观察合起来，基本就是", "这几层观察合在一起，构成了"),
        ("它的代价也很直接：", "对应的代价也很直接："),
        ("整体上看，", ""),
        ("从图意来看，", ""),
        ("这个工作最值得抓住的是：", ""),
        ("最值得注意的是：", ""),
        ("可以先记成一句更简单的话：", ""),
    ]
    result = text
    for old, new in replacements:
        result = result.replace(old, new)
    result = re.sub(r"(?m)^[ \t]*直觉上[，,:：]", "", result)
    result = re.sub(r"(?m)^[ \t]*更重要的是[，,:：]", "", result)
    result = re.sub(r"(?m)^[ \t]*需要先抓住的一点是[，,:：]", "", result)
    result = re.sub(r"\b原因很清楚\b", "", result)
    result = re.sub(r"\b更具体地说\b", "", result)
    result = re.sub(r"\b可以概括成\b", "", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def strip_banned_phrases(note_text: str) -> str:
    replacements = [
        ("不是单纯一个 runtime，而是一套", "它是一套"),
        ("不是简单把所有东西并起来，而是", "关键不在于把所有东西盲目并起来，而在于"),
        ("不是拍脑袋重叠", "这不是随意决定哪些操作重叠"),
        ("不是自动带来收益", "并不会自动带来收益"),
        ("不是某个单独算子", "重点并不落在某个单独算子上"),
        ("不是模板改写", "要写成真正的讲解稿"),
    ]
    text = note_text
    for old, new in replacements:
        text = text.replace(old, new)
    text = re.sub(r"(?m)^[ \t]*这说明它不是在[^\n]*$", "", text)
    text = re.sub(r"(?m)^[ \t]*这一点本身就很重要[。．]?$", "", text)
    text = re.sub(r"(?m)^[ \t]*这里先把基础概念说透[，,:：]", "", text)
    return strip_filler_phrases(text)


def strengthen_teaching_tone(note_text: str) -> str:
    text = note_text
    replacements = [
        ("资源特征更偏显存带宽", "这一步更容易被显存带宽限制，因为系统需要从缓存中把每个请求各自的 K/V 读出来"),
        ("更偏网络带宽", "这一步主要受跨卡通信带宽限制，因为不同 GPU 上的分片结果需要同步"),
        ("资源占用模式不同", "对计算单元、显存带宽和网络链路的占用方式不同"),
        ("顺序执行会导致任一时刻通常只有一类资源处于高利用，其他资源闲置", "顺序执行的直接后果是：某一小段时间里可能只有计算单元在忙，而显存和网络基本闲着；下一小段时间又变成显存在忙，计算单元闲下来"),
        ("把批处理从单一维度扩展为“批切分 + 操作重排 + 资源配额”的联合问题", "把原来只关心 batch 大小的问题，改写成同时决定怎么切 batch、怎么排操作顺序、以及每一步给多少设备资源的问题"),
        ("提供明确目标函数", "让后面的搜索器知道自己到底在优化什么"),
        ("更接近真实执行情况", "不只在纸面上好看，而是在真实 GPU 并发时也更可能成立"),
        ("稳定落地成高利用运行时", "变成运行时真的能按事件和依赖一步步执行出来的流水"),
        ("系统收益", "系统层面的直接收益"),
        ("适用边界", "结论能成立到什么范围为止"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    text = re.sub(r"(?m)^([^\n]*术语.*)$", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def rewrite_asset_classification_section(note_text: str) -> str:
    matches = list(re.finditer(r"(?m)^##\s+([^\n]+)\n", note_text))
    if len(matches) < 4:
        return note_text
    match = matches[2]
    body_start = match.end()
    body_end = matches[3].start()
    body = note_text[body_start:body_end].strip()

    lines = [line.strip() for line in body.splitlines() if line.strip()]
    bullet_lines = [line.lstrip("-").strip() for line in lines if line.startswith("-")]
    bullet_lines = [re.sub(r"^\*\*?资产分类判断[:：]?\**\s*", "", line) for line in bullet_lines]
    bullet_lines = [re.sub(r"^\*\*?原因[:：]?\**\s*", "", line) for line in bullet_lines]
    bullet_lines = [line.strip() for line in bullet_lines if line.strip()]

    if bullet_lines:
        main_object = bullet_lines[0]
        rationale = " ".join(bullet_lines[1:4]).strip()
    else:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        main_object = paragraphs[0] if paragraphs else ""
        rationale = paragraphs[1] if len(paragraphs) > 1 else ""

    main_object = re.sub(r"\s+", " ", main_object).strip()
    rationale = re.sub(r"\s+", " ", rationale).strip()
    main_object = main_object.replace("**", "").strip()
    rationale = rationale.replace("**", "").strip()

    if main_object and "主分类" not in main_object and "归到" not in main_object and "视作" not in main_object:
        main_object = f"主分类是 **LLM Inference Systems**。{main_object}"

    rebuilt = main_object
    if rationale:
        rebuilt += "\n\n" + rationale
    rebuilt = rebuilt.strip() + "\n"
    return note_text[:body_start] + rebuilt + note_text[body_end:]


def rewrite_reading_focus_section(note_text: str) -> str:
    matches = list(re.finditer(r"(?m)^##\s+([^\n]+)\n", note_text))
    if len(matches) < 2:
        return note_text
    match = matches[-2]
    body_start = match.end()
    body_end = matches[-1].start()
    body = note_text[body_start:body_end].strip()

    sections = {}
    current_title = None
    current_lines: List[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            if current_title:
                sections[current_title] = "\n".join(current_lines).strip()
            current_title = stripped
            current_lines = []
        else:
            current_lines.append(line.rstrip())
    if current_title:
        sections[current_title] = "\n".join(current_lines).strip()

    intro = "读完这份笔记后，不需要回原文从头顺读一遍。更高效的做法是只回去核对那些真正决定方法边界、实验口径和系统结论强度的位置。"
    required_titles = [
        "### 必须回原文核对的部分",
        "### 核对目的",
        "### 可以暂时不细读的部分",
        "### 查漏补缺后的判断标准",
    ]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    fallback = {
        "### 必须回原文核对的部分": paragraphs[0] if len(paragraphs) > 0 else "应优先核对成本模型、两阶段搜索、干扰建模和主结果图附近的正文与图注，确认笔记中涉及的机制和口径是否与原文一致。",
        "### 核对目的": paragraphs[1] if len(paragraphs) > 1 else "核对的重点是确认公式假设、依赖关系、搜索变量、指标定义以及系统收益与代价是否来自同一实验设置。",
        "### 可以暂时不细读的部分": paragraphs[2] if len(paragraphs) > 2 else "读完笔记后，可以暂时跳过重复介绍背景的数据集描述、次要 related work 展开和不影响主结论的辅助段落。",
        "### 查漏补缺后的判断标准": paragraphs[3] if len(paragraphs) > 3 else "补完原文后，应能够说清：系统的执行单位是什么、两阶段搜索各自固定和优化什么、主结果图分别支撑哪条结论、现有证据的结论边界在哪里。",
    }

    rebuilt_parts = [intro]
    for title in required_titles:
        content = sections.get(title, "").strip() or fallback[title]
        content = re.sub(r"(?m)^[-*]\s*", "", content).strip()
        rebuilt_parts.append(title)
        rebuilt_parts.append(content)

    rebuilt = "\n\n".join(part for part in rebuilt_parts if part.strip()).strip() + "\n"
    return note_text[:body_start] + rebuilt + note_text[body_end:]


def enforce_quality_policy(note_text: str) -> str:
    text = enforce_question_headings(note_text)
    text = enforce_review_fields_headings(text)
    text = strip_banned_phrases(text)
    text = strengthen_teaching_tone(text)
    text = rewrite_asset_classification_section(text)
    text = rewrite_reading_focus_section(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def build_note_with_model(manifest: dict, vault: Path, md_text: str, api_key: str, base_url: str, model: str) -> str:
    sections = split_sections(md_text)
    figures = merge_figure_entries(manifest, md_text)
    evidence = build_evidence_json(manifest, sections, figures)
    publish_analysis_figure(manifest, vault, evidence)
    prompt = build_prompt(manifest, vault, evidence)
    draft = post_responses(api_key, base_url, model, SYSTEM_PROMPT, prompt).strip()
    refined = refine_note_with_model(draft, evidence, api_key, base_url, model).strip()
    refined = enforce_quality_policy(refined)
    refined = enforce_visual_policy(refined, evidence)
    refined = enforce_quality_policy(refined)
    refined = remove_broken_and_experiment_images(refined)
    refined = replace_frontmatter_and_basic_info(refined, manifest, vault)
    return refined.strip() + "\n"


def repair_existing_note(note_path: Path, manifest: dict, vault: Path) -> str:
    text = read_text(note_path)
    md_text = normalize_text(read_text(Path(manifest["mineru_md"])))
    sections = split_sections(md_text)
    figures = merge_figure_entries(manifest, md_text)
    evidence = build_evidence_json(manifest, sections, figures)
    publish_analysis_figure(manifest, vault, evidence)
    text = enforce_quality_policy(text)
    text = enforce_visual_policy(text, evidence)
    text = remove_broken_and_experiment_images(text)
    text = replace_frontmatter_and_basic_info(text, manifest, vault)
    write_text(note_path, text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a high-quality Chinese paper note.")
    parser.add_argument("--manifest", required=True, help="Path to ingest_manifest.json")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    manifest_path = Path(args.manifest).resolve()
    manifest = load_manifest(manifest_path)
    mineru_md = manifest.get("mineru_md")
    if not mineru_md:
        raise SystemExit("Manifest does not contain mineru_md.")

    api_key, base_url, model = resolve_api_settings(args.model, args.base_url)
    md_text = normalize_text(read_text(Path(mineru_md)))
    note_path = Path(manifest["suggested_note"])
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_text = build_note_with_model(manifest, vault, md_text, api_key, base_url, model)
    write_text(note_path, note_text)

    manifest["note_state"] = "analyzed"
    manifest["updated"] = datetime.now().strftime("%Y-%m-%d")
    manifest["analysis_model"] = model
    dump_manifest(manifest_path, manifest)

    print(
        json.dumps(
            {
                "status": "analyzed",
                "note": str(note_path),
                "manifest": str(manifest_path),
                "model": model,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
