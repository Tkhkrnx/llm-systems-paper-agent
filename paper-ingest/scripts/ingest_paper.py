#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingest paper assets into Obsidian and prepare them for later analysis."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml


DEFAULT_VAULT = Path("C:/Users/peng/Documents/PHR/obsidian_phr")
DEFAULT_CONFIG = DEFAULT_VAULT / "99_System" / "Config" / "research_interests.yaml"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def safe_name(text: str, fallback: str = "paper") -> str:
    text = (text or fallback).strip()
    text = re.sub(r'[ /\\:*?"<>|]+', "_", text)
    text = re.sub(r"_+", "_", text).strip("._")
    return text[:180] or fallback


def slugify(text: str, fallback: str = "paper") -> str:
    value = safe_name(text, fallback=fallback).replace("_", "-").lower()
    value = re.sub(r"-+", "-", value).strip("-")
    return value or fallback


def tag_slug(text: str, fallback: str = "uncategorized") -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-").lower()
    return value or fallback


def normalize_title_key(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "", (text or "").lower())
    return value


def is_arxiv_id(value: str) -> bool:
    return bool(re.fullmatch(r"(arXiv:)?\d{4}\.\d{4,5}(v\d+)?", value.strip(), re.I))


def normalize_arxiv_id(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^arxiv:", "", value, flags=re.I)
    match = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", value)
    return match.group(1) if match else value


def read_yaml_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def fetch_arxiv_metadata(arxiv_id: str) -> dict:
    url = f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}"
    with urllib.request.urlopen(url, timeout=60) as resp:
        xml = resp.read().decode("utf-8")
    root = ET.fromstring(xml)
    entry = root.find("atom:entry", ARXIV_NS)
    if entry is None:
        return {}
    title = (entry.findtext("atom:title", default="", namespaces=ARXIV_NS) or "").strip()
    summary = (entry.findtext("atom:summary", default="", namespaces=ARXIV_NS) or "").strip()
    published = entry.findtext("atom:published", default="", namespaces=ARXIV_NS) or ""
    authors = []
    for author in entry.findall("atom:author", ARXIV_NS):
        name = author.findtext("atom:name", default="", namespaces=ARXIV_NS)
        if name:
            authors.append(name)
    categories = [c.get("term") for c in entry.findall("atom:category", ARXIV_NS) if c.get("term")]
    return {
        "paper_id": arxiv_id,
        "title": re.sub(r"\s+", " ", title),
        "authors": ", ".join(authors),
        "abstract": re.sub(r"\s+", " ", summary),
        "published": published[:10],
        "categories": categories,
        "source_url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
    }


def is_missing(value: Optional[str]) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in {"", "TBD", "Unknown", "None"}
    return False


def download_file(url: str, output: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "llm-systems-paper-agent/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        output.write_bytes(resp.read())


def resolve_input(input_value: str, title: Optional[str], authors: Optional[str]) -> Tuple[dict, Optional[Path], Optional[str]]:
    value = input_value.strip().strip('"')
    local = Path(value)
    if local.exists() and local.suffix.lower() == ".pdf":
        return {
            "paper_id": local.stem,
            "title": title or local.stem,
            "authors": authors or "TBD",
            "abstract": "TBD",
            "published": "TBD",
            "source_url": str(local),
            "pdf_url": str(local),
            "categories": [],
            "input_type": "local_pdf",
        }, local, None

    arxiv_match = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", value)
    if is_arxiv_id(value) or "arxiv.org" in value or arxiv_match:
        arxiv_id = normalize_arxiv_id(arxiv_match.group(1) if arxiv_match else value)
        metadata = fetch_arxiv_metadata(arxiv_id)
        if title:
            metadata["title"] = title
        if authors:
            metadata["authors"] = authors
        metadata["input_type"] = "arxiv"
        return metadata, None, metadata.get("pdf_url")

    if re.match(r"https?://", value):
        parsed = urllib.parse.urlparse(value)
        guessed = Path(parsed.path).stem or "paper"
        return {
            "paper_id": guessed,
            "title": title or guessed,
            "authors": authors or "TBD",
            "abstract": "TBD",
            "published": "TBD",
            "source_url": value,
            "pdf_url": value,
            "categories": [],
            "input_type": "pdf_url",
        }, None, value

    raise SystemExit(f"Unsupported input: {input_value}")


def guess_mineru_root(config: dict) -> Optional[Path]:
    configured = config.get("mineru_root")
    if configured:
        candidate = Path(str(configured)).expanduser()
        if candidate.exists():
            return candidate
    fallback = Path(__file__).resolve().parents[3] / "MinerU-mineru-3.1.5-released"
    return fallback if fallback.exists() else None


def run_command(cmd: List[str], cwd: Optional[Path], env: Dict[str, str]) -> Tuple[int, str]:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            capture_output=True,
            timeout=1800,
        )
        output = (result.stderr or "") + ("\n" if result.stderr and result.stdout else "") + (result.stdout or "")
        return result.returncode, output.strip()
    except Exception as exc:  # pragma: no cover - defensive path
        return 999, f"{type(exc).__name__}: {exc}"


def find_latest_markdown(mineru_output: Path) -> Optional[Path]:
    md_files = sorted(mineru_output.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return md_files[0] if md_files else None


def run_mineru(pdf_path: Path, mineru_output: Path, config: dict) -> Tuple[str, Optional[Path], List[dict]]:
    mineru_output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    attempts: List[dict] = []
    mineru_root = guess_mineru_root(config)

    commands: List[Tuple[List[str], Optional[Path], Dict[str, str], str]] = []
    if shutil.which("mineru"):
        commands.append((["mineru", "-p", str(pdf_path), "-o", str(mineru_output), "-b", "pipeline"], None, env.copy(), "cli"))

    if mineru_root:
        env_with_root = env.copy()
        env_with_root["PYTHONPATH"] = str(mineru_root) + os.pathsep + env_with_root.get("PYTHONPATH", "")
        commands.append((
            [sys.executable, "-m", "mineru.cli.client", "-p", str(pdf_path), "-o", str(mineru_output), "-b", "pipeline"],
            mineru_root,
            env_with_root,
            "module",
        ))

    if not commands:
        attempts.append({
            "kind": "setup",
            "command": "mineru",
            "cwd": None,
            "returncode": 127,
            "message": "Neither `mineru` CLI nor configured `mineru_root` is available.",
        })

    for cmd, cwd, cmd_env, kind in commands:
        returncode, output = run_command(cmd, cwd, cmd_env)
        attempts.append({
            "kind": kind,
            "command": cmd,
            "cwd": str(cwd) if cwd else None,
            "returncode": returncode,
            "message": output[-3000:],
        })
        raw_md = find_latest_markdown(mineru_output)
        if returncode == 0 and raw_md:
            return "success", raw_md, attempts

    raw_md = find_latest_markdown(mineru_output)
    if raw_md:
        attempts.append({
            "kind": "post-check",
            "command": ["find_latest_markdown"],
            "cwd": str(mineru_output),
            "returncode": 0,
            "message": f"Found Markdown after command failure: {raw_md}",
        })
        return "success", raw_md, attempts

    last = attempts[-1]["message"] if attempts else "unknown MinerU error"
    status = (
        "failed: no MinerU Markdown generated. "
        f"Checked output={mineru_output}. Last error={last}. "
        "Please verify `mineru` is installed or configure `mineru_root` in research_interests.yaml."
    )
    return status, None, attempts


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_abstract(text: str) -> Optional[str]:
    match = re.search(
        r"(?is)(?:^|\n)(?:abstract|摘要)\s*[-—:：]?\s*(.+?)(?:\n\s*\n|\n## |\n# |\nI\. |\n1\.)",
        text,
    )
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip(" -:：")
    return value[:3000] if value else None


def extract_title_authors_from_markdown(md_path: Optional[Path]) -> dict:
    if not md_path or not md_path.exists():
        return {}
    lines = [line.strip() for line in read_text(md_path).splitlines()[:30]]
    non_empty = [line for line in lines if line]
    if not non_empty:
        return {}

    title = non_empty[0]
    title = re.sub(r"^#\s*", "", title).strip()
    authors = None
    for line in non_empty[1:8]:
        lower = line.lower()
        if "abstract" in lower or line.startswith("##"):
            break
        if len(line.split()) <= 20 and not re.search(r"(introduction|摘要|abstract)", lower):
            authors = line.strip()
            break

    return {
        "title": title or None,
        "authors": authors or None,
        "abstract": extract_abstract(read_text(md_path)),
    }


def extract_figure_alias_map(md_text: str) -> Dict[str, str]:
    alias_map: Dict[str, str] = {}
    pattern = re.compile(r"!\[]\((images/[^\)]+)\)\s*\n?(?:\([a-z]\)\s*)?(?:\n)?Fig\.\s*(\d+[a-z]?)[:.]?\s*(.+)")
    for match in pattern.finditer(md_text):
        base = Path(match.group(1)).name
        fig_no = match.group(2).lower()
        caption = match.group(3).lower()
        keywords = []
        for keyword in ["workflow", "latency", "memory", "breakdown", "ablation", "architecture", "overview", "fit", "throughput", "accuracy"]:
            if keyword in caption:
                keywords.append(keyword)
        suffix = "-".join(keywords[:2])
        alias = f"fig{fig_no}"
        if suffix:
            alias = f"{alias}-{suffix}"
        alias_map[base] = f"{alias}.jpg"
    return alias_map


def infer_domain(metadata: dict, md_path: Optional[Path], config: dict) -> Tuple[str, str, List[str]]:
    requested = (metadata.get("requested_domain") or "").strip()
    if requested and requested not in {"TBD", "Uncategorized"}:
        return requested, "User explicitly provided domain.", []

    text_parts = [metadata.get("title", ""), metadata.get("abstract", "")]
    if md_path and md_path.exists():
        md_text = read_text(md_path)
        text_parts.append("\n".join(md_text.splitlines()[:120]))
    haystack = " ".join(text_parts).lower()

    best_domain = "Uncategorized"
    best_score = 0
    best_hits: List[str] = []
    for domain, info in (config.get("research_domains") or {}).items():
        keywords = info.get("keywords") or []
        hits = []
        score = 0
        for keyword in keywords:
            keyword_l = str(keyword).lower()
            if keyword_l and keyword_l in haystack:
                hits.append(keyword)
                score += 3 if len(keyword_l.split()) > 1 else 1
        if score > best_score:
            best_score = score
            best_domain = domain
            best_hits = hits[:8]

    if best_score == 0:
        return "Uncategorized", "No strong keyword signal from title/abstract/introduction.", []
    reason = f"Matched keywords from title/abstract/introduction: {', '.join(best_hits)}"
    return best_domain, reason, best_hits


def rename_images(image_dir: Path, alias_map: Optional[Dict[str, str]] = None) -> List[dict]:
    if not image_dir.exists():
        return []
    alias_map = alias_map or {}
    files = sorted([p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS])
    records = []
    counter = 1
    for path in files:
        stem = path.stem
        if re.fullmatch(r"fig\d+[a-z]?(?:-[a-z0-9-]+)?", stem, re.I):
            records.append({"original": path.name, "alias": path.name, "path": str(path)})
            continue
        alias = alias_map.get(path.name, f"fig{counter:02d}{path.suffix.lower()}")
        counter += 1
        target = path.with_name(alias)
        while target.exists():
            alias = f"fig{counter:02d}{path.suffix.lower()}"
            counter += 1
            target = path.with_name(alias)
        path.rename(target)
        records.append({"original": path.name, "alias": target.name, "path": str(target)})
    return records


def obsidian_link(path: Path, vault: Path, label: Optional[str] = None) -> str:
    rel = path.relative_to(vault).as_posix() if path.is_relative_to(vault) else path.as_posix()
    rel = re.sub(r"\.md$", "", rel)
    return f"[[{rel}|{label or path.stem}]]"


def vault_rel(path: Optional[Path], vault: Path) -> Optional[str]:
    if not path:
        return None
    return path.relative_to(vault).as_posix() if path.is_relative_to(vault) else path.as_posix()


def collect_image_dirs(asset_dir: Path) -> List[Path]:
    dirs = set()
    for path in asset_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            dirs.add(path.parent)
    return sorted(dirs)


def build_assets_index(
    metadata: dict,
    pdf_path: Path,
    raw_md: Optional[Path],
    vault: Path,
    mineru_status: str,
    note_path: Path,
    manifest_path: Path,
    asset_dir: Path,
    image_aliases: List[dict],
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    title = metadata.get("title") or "TBD"
    pdf_rel = pdf_path.relative_to(vault).as_posix()
    raw_link = obsidian_link(raw_md, vault, "MinerU Markdown") if raw_md else "TBD"
    source = metadata.get("source_url", "TBD")
    pdf_url = metadata.get("pdf_url", "TBD")
    categories = ", ".join(metadata.get("categories") or []) or "TBD"
    image_dirs = collect_image_dirs(asset_dir)
    image_lines = "\n".join(f"- {vault_rel(path, vault)}" for path in image_dirs) or "- TBD"
    alias_lines = "\n".join(
        f"- `{item['original']}` -> `{item['alias']}`"
        for item in image_aliases
        if item["original"] != item["alias"]
    ) or "- No image rename applied."
    secondary = metadata.get("secondary_domains") or []
    secondary_line = ", ".join(secondary) if secondary else "TBD"
    domain_tag = tag_slug(metadata.get("domain", "Uncategorized"))

    return f"""---
date: "{today}"
paper_id: "{metadata.get('paper_id', 'TBD')}"
title: "{title.replace('"', "'")}"
authors: "{(metadata.get('authors') or 'TBD').replace('"', "'")}"
year: "{(metadata.get('published') or 'TBD')[:4]}"
venue: "TBD"
domain: "{metadata.get('domain', 'Uncategorized')}"
tags:
  - paper-assets
  - mineru
  - {domain_tag}
status: assets-ingested
pdf_to_md_status: "{mineru_status.replace('"', "'")}"
created: "{today}"
updated: "{today}"
---

# Assets: {title}

## Source Assets
- PDF: [{pdf_path.name}]({pdf_rel})
- Source: {source}
- PDF URL: {pdf_url}
- MinerU Markdown: {raw_link}
- Asset directory: `{vault_rel(asset_dir, vault)}`
- Manifest: {obsidian_link(manifest_path, vault, "ingest manifest")}
- Suggested formal note: {obsidian_link(note_path, vault, title)}
- arXiv categories: {categories}
- MinerU status: `{mineru_status}`

## Paper Identity
Paper title: {title}
Authors: {metadata.get('authors') or 'TBD'}
Year: {(metadata.get('published') or 'TBD')[:4]}
Venue: TBD
Area: {metadata.get('domain', 'Uncategorized')}
Secondary tags: {secondary_line}

## Classification Rationale
- Primary domain: **{metadata.get('domain', 'Uncategorized')}**
- Reason: {metadata.get('classification_reason', 'TBD')}

## Image / Media Directories
{image_lines}

## Image Alias Map
{alias_lines}

## Next Step

Use `paper-analyze` to create or update the formal paper note at:

{obsidian_link(note_path, vault, title)}
"""


def write_manifest(manifest_path: Path, manifest: dict) -> None:
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def find_existing_note(title: str, vault: Path) -> Optional[Path]:
    papers_root = vault / "20_Research" / "Papers"
    if not papers_root.exists():
        return None
    target_name = f"{safe_name(title)}.md"
    target_key = normalize_title_key(title)
    for candidate in papers_root.rglob("*.md"):
        if "_assets" in candidate.parts:
            continue
        if candidate.name == target_name:
            return candidate
        try:
            head = candidate.read_text(encoding="utf-8", errors="ignore")[:2000]
        except OSError:
            continue
        frontmatter_title = None
        match = re.search(r'(?m)^title:\s*"?(.*?)"?\s*$', head)
        if match:
            frontmatter_title = match.group(1).strip()
        heading = None
        match = re.search(r'(?m)^#\s+(.+?)\s*$', head)
        if match:
            heading = match.group(1).strip()
        if normalize_title_key(frontmatter_title or "") == target_key:
            return candidate
        if normalize_title_key(heading or "") == target_key:
            return candidate
    return None


def choose_note_path(vault: Path, domain: str, title: str, existing_note: Optional[Path]) -> Path:
    if existing_note:
        return existing_note
    note_dir = vault / "20_Research" / "Papers" / domain
    note_dir.mkdir(parents=True, exist_ok=True)
    return note_dir / f"{safe_name(title)}.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest paper assets into Obsidian with MinerU conversion.")
    parser.add_argument("--input", required=True, help="arXiv ID, arXiv URL, PDF URL, or local PDF path")
    parser.add_argument("--title", default=None)
    parser.add_argument("--authors", default=None)
    parser.add_argument("--domain", default="Uncategorized")
    parser.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT_PATH") or str(DEFAULT_VAULT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--skip-mineru", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    config = read_yaml_config(Path(args.config))
    metadata, local_pdf, pdf_url = resolve_input(args.input, args.title, args.authors)
    metadata["requested_domain"] = args.domain
    title_seed = metadata.get("title") or metadata.get("paper_id") or "paper"
    asset_slug = slugify(title_seed, fallback="paper")
    asset_dir = vault / "20_Research" / "Papers" / "_assets" / asset_slug
    asset_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = asset_dir / f"{asset_slug}.pdf"
    if local_pdf:
        if local_pdf.resolve() != pdf_path.resolve():
            shutil.copy2(local_pdf, pdf_path)
    else:
        download_file(pdf_url, pdf_path)

    mineru_status = "skipped"
    raw_md: Optional[Path] = None
    mineru_attempts: List[dict] = []
    preexisting_md = find_latest_markdown(asset_dir / "mineru")
    if args.skip_mineru and preexisting_md:
        raw_md = preexisting_md
        mineru_status = "success"
        mineru_attempts = [{
            "kind": "reuse",
            "command": ["find_latest_markdown"],
            "cwd": str(asset_dir / "mineru"),
            "returncode": 0,
            "message": f"Reused existing MinerU Markdown: {preexisting_md}",
        }]
    elif not args.skip_mineru:
        mineru_status, raw_md, mineru_attempts = run_mineru(pdf_path, asset_dir / "mineru", config)
    elif preexisting_md:
        raw_md = preexisting_md
        mineru_status = "success"

    extracted = extract_title_authors_from_markdown(raw_md)
    if metadata.get("input_type") == "local_pdf":
        if extracted.get("title") and extracted["title"] != metadata.get("title"):
            metadata["title"] = extracted["title"]
        if extracted.get("authors") and is_missing(metadata.get("authors")):
            metadata["authors"] = extracted["authors"]
        if extracted.get("abstract") and is_missing(metadata.get("abstract")):
            metadata["abstract"] = extracted["abstract"]
    elif extracted.get("abstract") and is_missing(metadata.get("abstract")):
        metadata["abstract"] = extracted["abstract"]

    domain, classification_reason, matched_keywords = infer_domain(metadata, raw_md, config)
    metadata["domain"] = domain
    metadata["classification_reason"] = classification_reason
    metadata["matched_keywords"] = matched_keywords
    metadata["secondary_domains"] = []

    existing_note = find_existing_note(metadata.get("title") or asset_slug, vault)
    note_path = choose_note_path(vault, domain, metadata.get("title") or asset_slug, existing_note)
    alias_map = extract_figure_alias_map(read_text(raw_md)) if raw_md and raw_md.exists() else {}
    image_aliases: List[dict] = []
    for image_dir in collect_image_dirs(asset_dir):
        image_aliases.extend(rename_images(image_dir, alias_map))

    manifest_path = asset_dir / "ingest_manifest.json"
    assets_index = asset_dir / "assets.md"
    manifest = {
        "status": "assets-ingested",
        "paper_id": metadata.get("paper_id", "TBD"),
        "title": metadata.get("title") or "TBD",
        "authors": metadata.get("authors") or "TBD",
        "published": metadata.get("published") or "TBD",
        "year": (metadata.get("published") or "TBD")[:4],
        "domain": domain,
        "secondary_domains": metadata.get("secondary_domains") or [],
        "classification_reason": classification_reason,
        "matched_keywords": matched_keywords,
        "source_url": metadata.get("source_url", "TBD"),
        "pdf_url": metadata.get("pdf_url", "TBD"),
        "categories": metadata.get("categories") or [],
        "abstract": metadata.get("abstract") or "TBD",
        "vault": str(vault),
        "asset_dir": str(asset_dir),
        "pdf": str(pdf_path),
        "mineru_md": str(raw_md) if raw_md else None,
        "mineru_status": mineru_status,
        "mineru_attempts": mineru_attempts,
        "assets_index": str(assets_index),
        "suggested_note": str(note_path),
        "image_dirs": [str(path) for path in collect_image_dirs(asset_dir)],
        "image_aliases": image_aliases,
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "next_skill": "paper-analyze",
        "note_state": "analyzed" if existing_note else "needs_analysis",
    }
    write_manifest(manifest_path, manifest)
    assets_index.write_text(
        build_assets_index(metadata, pdf_path, raw_md, vault, mineru_status, note_path, manifest_path, asset_dir, image_aliases),
        encoding="utf-8",
    )

    status = "assets_ingested_note_exists" if existing_note else "assets_ingested_needs_analysis"
    print(json.dumps({
        "status": status,
        "suggested_next_skill": "paper-analyze",
        "note": str(note_path),
        "assets_index": str(assets_index),
        "manifest": str(manifest_path),
        "pdf": str(pdf_path),
        "mineru_md": str(raw_md) if raw_md else None,
        "mineru_status": mineru_status,
        "domain": domain,
        "classification_reason": classification_reason,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
