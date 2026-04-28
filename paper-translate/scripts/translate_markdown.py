#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Translate MinerU Markdown into rigorous Chinese academic Markdown."""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import requests


DEFAULT_VAULT = Path("C:/Users/peng/Documents/PHR/obsidian_phr")
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1")
DEFAULT_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

SYSTEM_PROMPT = """你是一名严谨的学术论文翻译助手。

任务是把英文论文 Markdown 翻译成中文学术 Markdown，要求：
1. 准确、克制、严谨，不擅自扩写，不擅自删减。
2. 保留原 Markdown 结构，包括标题、列表、表格、公式、图片引用、参考文献。
3. 模型名、方法名、系统名、数据集名、库名、框架名、缩写默认不翻译。
4. 术语采用计算机系统与大模型方向常见译法。必要时首次出现可写成“中文（英文）”。
5. 不要输出解释、注释、免责声明、前言或总结，只输出翻译后的 Markdown。
6. 如果原文存在 OCR 断裂、病句或明显错误，优先忠实保留语义并做最小限度整理，不编造原文没有的信息。
"""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def split_frontmatter(text: str) -> Tuple[str, str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[: end + 5], text[end + 5 :]
    return "", text


def is_heading(line: str) -> bool:
    return bool(re.match(r"^\s{0,3}#{1,6}\s+", line))


def is_image(line: str) -> bool:
    return bool(re.match(r"^\s*!\[.*\]\(.*\)\s*$", line))


def is_reference_line(line: str) -> bool:
    return bool(re.match(r"^\[\d+\]\s+", line.strip()))


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_markdown_blocks(text: str, max_chars: int = 5000) -> List[str]:
    lines = text.splitlines()
    blocks: List[str] = []
    current: List[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            blocks.append("\n".join(current).strip())
        current = []
        current_len = 0

    for line in lines:
        line_len = len(line) + 1
        hard_boundary = (
            is_heading(line)
            or is_image(line)
            or is_reference_line(line)
            or (not line.strip())
        )
        if current and current_len + line_len > max_chars and hard_boundary:
            flush()
        current.append(line)
        current_len += line_len
        if hard_boundary and current_len >= max_chars * 0.75:
            flush()

    flush()
    return [block for block in blocks if block.strip()]


def build_user_prompt(block: str) -> str:
    return (
        "请将下面这段英文论文 Markdown 准确翻译成中文学术 Markdown。\n"
        "要求保留原始 Markdown 结构和信息边界，不要添加解释。\n\n"
        f"{block}"
    )


def translate_block(block: str, api_key: str, model: str, base_url: str, timeout: int = 180) -> str:
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": build_user_prompt(block)}]},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(f"{base_url}/responses", headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    output_texts: List[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                output_texts.append(text)
    translated = "\n".join(output_texts).strip()
    if not translated:
        raise RuntimeError("Translation API returned empty output.")
    return translated


def resolve_paths(manifest_path: Optional[Path], md_path: Optional[Path]) -> Tuple[Optional[Path], Path]:
    if manifest_path:
        manifest = load_manifest(manifest_path)
        mineru_md = manifest.get("mineru_md")
        if not mineru_md:
            raise SystemExit("Manifest does not contain `mineru_md`.")
        return manifest_path, Path(mineru_md)
    if md_path:
        return None, md_path
    raise SystemExit("Either --manifest or --md must be provided.")


def make_output_path(md_path: Path) -> Path:
    if md_path.suffix.lower() != ".md":
        return md_path.with_name(f"{md_path.name}.zh-CN.md")
    return md_path.with_name(f"{md_path.stem}.zh-CN.md")


def translate_markdown(text: str, api_key: str, model: str, base_url: str) -> str:
    frontmatter, body = split_frontmatter(text)
    body = normalize_text(body)
    blocks = split_markdown_blocks(body)
    translated_blocks = [translate_block(block, api_key, model, base_url) for block in blocks]
    translated_body = "\n\n".join(block.strip() for block in translated_blocks if block.strip()).strip() + "\n"
    if frontmatter:
        return frontmatter + translated_body
    return translated_body


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate MinerU Markdown into Chinese academic Markdown.")
    parser.add_argument("--manifest", help="Path to ingest_manifest.json")
    parser.add_argument("--md", help="Path to the source Markdown file")
    parser.add_argument("--output", help="Optional explicit output Markdown path")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Missing OPENAI_API_KEY. Configure your OpenAI-compatible API credentials first.")

    manifest_path, md_path = resolve_paths(
        Path(args.manifest).resolve() if args.manifest else None,
        Path(args.md).resolve() if args.md else None,
    )
    source_text = read_text(md_path)
    output_path = Path(args.output).resolve() if args.output else make_output_path(md_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    translated_text = translate_markdown(source_text, api_key, args.model, args.base_url)
    output_path.write_text(translated_text, encoding="utf-8")

    result = {
        "status": "translated",
        "source_md": str(md_path),
        "translated_md": str(output_path),
        "model": args.model,
    }

    if manifest_path:
        manifest = load_manifest(manifest_path)
        manifest["translated_md"] = str(output_path)
        manifest["translation_status"] = "success"
        manifest["translation_updated"] = datetime.now().strftime("%Y-%m-%d")
        write_manifest(manifest_path, manifest)
        result["manifest"] = str(manifest_path)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
