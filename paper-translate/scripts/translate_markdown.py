#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Translate MinerU Markdown into rigorous Chinese academic Markdown."""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import tomllib


DEFAULT_VAULT = Path("C:/Users/peng/Documents/PHR/obsidian_phr")
DEFAULT_CODEX_CONFIG = Path("C:/Users/peng/.codex/config.toml")
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_BASE_URL = "https://api.openai.com/v1"

SYSTEM_PROMPT = """你是一名严谨的学术论文翻译助手。

你的任务是把英文论文 Markdown 直译为中文学术 Markdown，要求如下：
1. 以忠实原文为第一原则，不改变原意，不擅自扩写，不擅自删减，不补充原文没有的信息。
2. 翻译风格以“准确、克制、学术、自然”为准，优先直译；只有当直译会造成明显中文病句时，才做最小幅度润色。
3. 保留原始 Markdown 结构，包括标题、段落、列表、表格、公式、图片引用、脚注、参考文献。
4. 模型名、方法名、系统名、数据集名、库名、框架名、缩写默认不翻译；必要时首次出现可写成“中文（英文）”。
5. 专业术语使用计算机系统、大模型、体系结构领域常见译法，避免生硬硬译。
6. 不要把 technical artifact 机械翻译成奇怪词语。例如：
   - artifact 在本文语境下通常译为“产物”或“表示”，不要随意译成“制品”
   - heavy hitter 通常保留为 heavy hitter，或译为“高频/高贡献项”，不要译成奇怪词
   - time-between-output-token 可译为“输出 token 间隔时间”，必要时保留英文缩写 TBOT
7. 如果原文存在 OCR 断裂、病句、乱码或格式残缺，优先忠实保留语义，并做最小必要整理，使中文可读；不要编造缺失内容。
8. 只输出翻译后的 Markdown 正文，不要输出说明、注释、免责声明或额外总结。
"""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
        raise SystemExit(
            "Missing API key. Set OPENAI_API_KEY (or API_KEY). "
            "The script already supports Codex-compatible base_url/model from ~/.codex/config.toml."
        )
    return api_key, base_url, model


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
    text = text.replace("鈥�", "—")
    text = text.replace("鈥?", "–")
    text = text.replace("锟?", "")
    text = text.replace("timebetween-output-token", "time-between-output-token")
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
        hard_boundary = is_heading(line) or is_image(line) or is_reference_line(line) or (not line.strip())
        if current and current_len + line_len > max_chars and hard_boundary:
            flush()
        current.append(line)
        current_len += line_len
        if hard_boundary and current_len >= max_chars * 0.75:
            flush()

    flush()
    return [block for block in blocks if block.strip()]


def build_user_prompt(block: str) -> str:
    return f"""请把下面这段英文论文 Markdown 翻译成中文。

翻译要求：
- 以直译为主，忠实保留原意，不改写作者观点。
- 让中文读起来自然、严谨、学术，但不要为了“润色”而偏离原文。
- 保留所有 Markdown 结构、公式、图片链接、表格和引用。
- 对系统术语采用本领域常见译法；若直译生硬，可做最小限度调整。
- 不要输出任何解释，只输出译文。

原文如下：

{block}"""


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


def build_image_alias_map(manifest: dict) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for item in manifest.get("image_aliases", []) or []:
        original = str(item.get("original") or "").strip()
        alias = str(item.get("alias") or "").strip()
        if original and alias:
            mapping[original] = alias
    return mapping


def rewrite_image_references(text: str, image_alias_map: Dict[str, str]) -> str:
    if not image_alias_map:
        return text

    def replace(match: re.Match[str]) -> str:
        alt = match.group(1)
        target = match.group(2)
        prefix = match.group(3)
        filename = Path(target).name
        alias = image_alias_map.get(filename)
        if not alias:
            return match.group(0)
        new_target = f"{prefix}{alias}"
        return f"![{alt}]({new_target})"

    pattern = re.compile(r"!\[([^\]]*)\]\(((images/)?[^)\s]+)\)")
    return pattern.sub(replace, text)


def cleanup_translated_text(text: str) -> str:
    replacements = {
        "制品": "产物",
        "重击者": "heavy hitter",
        "时间between-output-token": "输出 token 间隔时间",
        "time-between-output-token（TBOT）": "输出 token 间隔时间（TBOT）",
        "更加 closer": "更接近",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"(?<=\S)TBD 这里。?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def translate_markdown(text: str, api_key: str, model: str, base_url: str, image_alias_map: Dict[str, str]) -> str:
    frontmatter, body = split_frontmatter(text)
    body = normalize_text(body)
    body = rewrite_image_references(body, image_alias_map)
    blocks = split_markdown_blocks(body)
    translated_blocks = [translate_block(block, api_key, model, base_url) for block in blocks]
    translated_body = "\n\n".join(block.strip() for block in translated_blocks if block.strip()).strip()
    translated_body = cleanup_translated_text(translated_body)
    if frontmatter:
        return frontmatter + translated_body
    return translated_body


def repair_source_markdown(md_path: Path, image_alias_map: Dict[str, str]) -> bool:
    original = read_text(md_path)
    repaired = rewrite_image_references(normalize_text(original), image_alias_map)
    if repaired != normalize_text(original):
        write_text(md_path, repaired + "\n")
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate MinerU Markdown into Chinese academic Markdown.")
    parser.add_argument("--manifest", help="Path to ingest_manifest.json")
    parser.add_argument("--md", help="Path to the source Markdown file")
    parser.add_argument("--output", help="Optional explicit output Markdown path")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()

    api_key, base_url, model = resolve_api_settings(args.model, args.base_url)

    manifest_path, md_path = resolve_paths(
        Path(args.manifest).resolve() if args.manifest else None,
        Path(args.md).resolve() if args.md else None,
    )
    manifest = load_manifest(manifest_path) if manifest_path else {}
    image_alias_map = build_image_alias_map(manifest)

    source_repaired = repair_source_markdown(md_path, image_alias_map)
    source_text = read_text(md_path)
    output_path = Path(args.output).resolve() if args.output else make_output_path(md_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    translated_text = translate_markdown(source_text, api_key, model, base_url, image_alias_map)
    write_text(output_path, translated_text)

    result = {
        "status": "translated",
        "source_md": str(md_path),
        "translated_md": str(output_path),
        "model": model,
        "base_url": base_url,
        "source_repaired": source_repaired,
        "image_aliases_applied": len(image_alias_map),
    }

    if manifest_path:
        manifest["translated_md"] = str(output_path)
        manifest["translation_status"] = "success"
        manifest["translation_updated"] = datetime.now().strftime("%Y-%m-%d")
        manifest["translation_model"] = model
        manifest["source_md_repaired"] = source_repaired
        write_manifest(manifest_path, manifest)
        result["manifest"] = str(manifest_path)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
