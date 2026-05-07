#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingest paper assets into Obsidian and prepare them for later analysis."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import yaml


DEFAULT_VAULT = Path("C:/Users/peng/Documents/PHR/obsidian_phr")
DEFAULT_CONFIG = DEFAULT_VAULT / "99_System" / "Config" / "research_interests.yaml"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
PDF_MAGIC = b"%PDF"
MIN_PDF_BYTES = 100 * 1024
REQUEST_TIMEOUT = 120
DOWNLOAD_RETRIES = 3


def urlopen_no_proxy(request_or_url, timeout=60):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(request_or_url, timeout=timeout)


def requests_session_no_proxy() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    return session


def windows_long_path(path: Path) -> str:
    raw = str(path.resolve())
    if os.name != "nt":
        return raw
    if raw.startswith("\\\\?\\"):
        return raw
    if raw.startswith("\\\\"):
        return "\\\\?\\UNC\\" + raw.lstrip("\\")
    return "\\\\?\\" + raw


def path_exists_safe(path: Path) -> bool:
    try:
        return os.path.exists(windows_long_path(path))
    except Exception:
        return path.exists()


def open_binary_safe(path: Path, mode: str):
    return open(windows_long_path(path), mode)


def copy_file_safe(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(windows_long_path(src), windows_long_path(dst))


def copy_tree_safe(src: Path, dst: Path) -> None:
    for item in src.rglob("*"):
        relative = item.relative_to(src)
        target = dst / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(windows_long_path(item), windows_long_path(target))


def looks_like_pdf_url(url: str) -> bool:
    lower = (url or "").lower()
    return (
        lower.endswith(".pdf")
        or "/pdf/" in lower
        or "pdf?id=" in lower
        or "download=true" in lower
        or "download=1" in lower
        or "viewcontent.cgi" in lower
        or "stamp/stamp.jsp" in lower
    )


def candidate_source_rank(url: str) -> int:
    lower = (url or "").lower()
    if "arxiv.org/pdf/" in lower:
        return 0
    if "openreview.net/pdf" in lower:
        return 1
    if "usenix.org" in lower and looks_like_pdf_url(lower):
        return 2
    if "proceedings.mlsys.org" in lower and looks_like_pdf_url(lower):
        return 3
    if any(host in lower for host in [
        "cs.", ".edu/", "people.", "faculty.", "sites.google.com/",
        "github.io/", "personal.", "homepages.", "~"
    ]) and looks_like_pdf_url(lower):
        return 4
    if looks_like_pdf_url(lower):
        return 5
    if "usenix.org" in lower:
        return 6
    if "arxiv.org/abs/" in lower:
        return 7
    if "openreview.net/forum" in lower:
        return 8
    if "proceedings.mlsys.org" in lower:
        return 9
    if "doi.org/" in lower:
        return 20
    if "dl.acm.org" in lower:
        return 21
    if "ieeexplore.ieee.org" in lower:
        return 22
    return 10


def normalize_candidate_pdf_url(url: str) -> str:
    if not url:
        return url
    parsed = urllib.parse.urlparse(url)
    lower = url.lower()

    if "arxiv.org/abs/" in lower:
        arxiv_id = normalize_arxiv_id(parsed.path.rsplit("/abs/", 1)[-1])
        return f"{parsed.scheme}://{parsed.netloc}/pdf/{arxiv_id}.pdf"

    if "openreview.net" in lower:
        qs = urllib.parse.parse_qs(parsed.query)
        if ("/forum" in parsed.path or "/pdf" in parsed.path) and qs.get("id"):
            paper_id = qs["id"][0]
            return f"{parsed.scheme}://{parsed.netloc}/pdf?id={urllib.parse.quote(paper_id)}"

    if "ieeexplore.ieee.org/document/" in lower:
        m = re.search(r"/document/(\d+)", parsed.path)
        if m:
            arnumber = m.group(1)
            return f"{parsed.scheme}://{parsed.netloc}/stamp/stamp.jsp?tp=&arnumber={arnumber}"

    if "dl.acm.org/doi/" in lower and "/doi/pdf/" not in lower:
        doi_path = parsed.path.split("/doi/", 1)[-1].lstrip("/")
        return f"{parsed.scheme}://{parsed.netloc}/doi/pdf/{doi_path}"

    if "proceedings.mlsys.org/paper_files/" in lower and "abstract-conference.html" in lower:
        return url.replace("-Abstract-Conference.html", "-Paper.pdf")

    return url


def expand_candidate_pdf_urls(url: str) -> List[str]:
    candidates: List[str] = []
    if not url:
        return candidates

    def add(value: Optional[str]) -> None:
        if value and value not in candidates:
            candidates.append(value)

    normalized = normalize_candidate_pdf_url(url)
    add(url)
    add(normalized)

    lower = normalized.lower()
    if "proceedings.mlsys.org/paper_files/" in lower and "-paper.pdf" in lower:
        add(normalized.replace("-Paper.pdf", "-Paper-Conference.pdf"))
    if "proceedings.mlsys.org/paper_files/" in lower and "-paper-conference.pdf" in lower:
        add(normalized.replace("-Paper-Conference.pdf", "-Paper.pdf"))
    if "usenix.org/conference/" in lower and not looks_like_pdf_url(lower):
        add(normalized.rstrip("/") + ".pdf")
    return sorted(candidates, key=lambda item: (candidate_source_rank(item), len(item)))


def prioritize_candidate_urls(urls: List[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for url in urls:
        for candidate in expand_candidate_pdf_urls(url):
            if candidate not in seen:
                seen.add(candidate)
                deduped.append(candidate)
    return sorted(deduped, key=lambda item: (candidate_source_rank(item), len(item)))


def safe_name(text: str, fallback: str = "paper") -> str:
    text = (text or fallback).strip()
    text = re.sub(r'[ /\\:*?"<>|]+', "_", text)
    text = re.sub(r"_+", "_", text).strip("._")
    return text[:80] or fallback


def slugify(text: str, fallback: str = "paper") -> str:
    value = safe_name(text, fallback=fallback).replace("_", "-").lower()
    value = re.sub(r"-+", "-", value).strip("-")
    value = value[:60].strip("-")
    return value or fallback


def compact_slug(text: str, fallback: str = "paper", max_len: int = 48) -> str:
    value = slugify(text, fallback=fallback)
    if len(value) <= max_len:
        return value
    compact = re.sub(r"\b(with|for|and|the|of|to|a|an)\b", "-", value)
    compact = re.sub(r"-+", "-", compact).strip("-")
    if len(compact) <= max_len:
        return compact
    parts = [part for part in compact.split("-") if part]
    shortened: List[str] = []
    for part in parts:
        keep = 4 if len(part) > 8 else min(len(part), 6)
        shortened.append(part[:keep])
    merged = "-".join(shortened)
    merged = re.sub(r"-+", "-", merged).strip("-")
    return merged[:max_len].rstrip("-") or fallback


def preferred_mineru_stem(metadata: dict, pdf_path: Optional[Path] = None) -> str:
    """Pick a short, stable stem for MinerU outputs from the start."""
    candidates = [
        str(metadata.get("paper_id") or "").strip(),
        str(metadata.get("arxiv_id") or "").strip(),
        str(metadata.get("title") or "").strip(),
        pdf_path.stem if pdf_path else "",
    ]
    for candidate in candidates:
        if not candidate or candidate in {"TBD", "Unknown", "None"}:
            continue
        if re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", candidate):
            return candidate.replace(".", "-")
        return compact_slug(candidate, fallback="paper", max_len=40)
    return "paper"


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
    try:
        with urlopen_no_proxy(url, timeout=60) as resp:
            xml = resp.read().decode("utf-8")
        root = ET.fromstring(xml)
        entry = root.find("atom:entry", ARXIV_NS)
        if entry is None:
            raise ValueError("Empty arXiv metadata entry")
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
    except Exception as exc:
        return {
            "paper_id": arxiv_id,
            "title": arxiv_id,
            "authors": "TBD",
            "abstract": "TBD",
            "published": "TBD",
            "categories": [],
            "source_url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            "_fetch_error": f"{type(exc).__name__}: {exc}",
        }


def fetch_dblp_metadata(dblp_url: str) -> dict:
    """Fetch metadata from a DBLP record page via its XML endpoint."""
    parsed = urllib.parse.urlparse(dblp_url.strip())
    rec_path = parsed.path.rstrip("/")
    xml_url = urllib.parse.urlunparse(parsed._replace(path=rec_path + ".xml", query="", fragment=""))
    xml = None
    try:
        with urlopen_no_proxy(urllib.request.Request(xml_url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as resp:
            xml = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        xml = None
    if not xml:
        try:
            with urlopen_no_proxy(urllib.request.Request(dblp_url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            m_title = re.search(r"<title>dblp:\s*(.+?)</title>", html, re.I | re.S)
            title = clean_html_text(m_title.group(1)) if m_title else rec_path.rsplit("/", 1)[-1]
            return {
                "paper_id": rec_path.rsplit("/", 1)[-1],
                "title": title.rstrip("."),
                "authors": "TBD",
                "abstract": "TBD",
                "published": "TBD",
                "categories": [],
                "venue": "TBD",
                "source_url": dblp_url,
                "pdf_url": discover_pdf_from_dblp_html(dblp_url) or dblp_url,
                "dblp_xml_url": xml_url,
                "ee_links": [],
            }
        except Exception:
            return {}
    root = ET.fromstring(xml)
    entry = None
    for child in root:
        if child.tag.endswith("inproceedings") or child.tag.endswith("article") or child.tag.endswith("incollection"):
            entry = child
            break
    if entry is None:
        return {}
    title = (entry.findtext("title") or "").strip().rstrip(".")
    authors = [a.text.strip() for a in entry.findall("author") if a.text and a.text.strip()]
    year = (entry.findtext("year") or "").strip()
    venue = (entry.findtext("booktitle") or entry.findtext("journal") or "").strip()
    paper_id = entry.get("key") or rec_path.rsplit("/", 1)[-1]
    ee_links = []
    for ee in entry.findall("ee"):
        link = (ee.text or "").strip()
        if link:
            ee_links.append(link)
    source_url = dblp_url
    pdf_url = resolve_pdf_url_from_links(ee_links) or discover_pdf_from_dblp_html(dblp_url)
    return {
        "paper_id": paper_id.split("/")[-1],
        "title": title,
        "authors": ", ".join(authors),
        "abstract": "TBD",
        "published": f"{year}-01-01" if year else "TBD",
        "categories": [],
        "venue": venue or "TBD",
        "source_url": source_url,
        "pdf_url": pdf_url or source_url,
        "dblp_xml_url": xml_url,
        "ee_links": ee_links,
    }


def clean_html_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = html_unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def html_unescape(text: str) -> str:
    import html
    return html.unescape(text)


def extract_open_candidate_links(html: str, base_url: str) -> List[str]:
    candidates: List[str] = []

    def add(value: Optional[str]) -> None:
        if not value:
            return
        resolved = urllib.parse.urljoin(base_url, value)
        if resolved not in candidates:
            candidates.append(resolved)

    for pattern in [
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
        r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']',
        r'href=["\']([^"\']*openreview\.net/forum\?id=[^"\']+)["\']',
        r'href=["\']([^"\']*openreview\.net/pdf\?id=[^"\']+)["\']',
        r'href=["\']([^"\']*arxiv\.org/abs/[^"\']+)["\']',
        r'href=["\']([^"\']*arxiv\.org/pdf/[^"\']+)["\']',
        r'href=["\']([^"\']*usenix\.org/[^"\']+)["\']',
        r'href=["\']([^"\']*proceedings\.mlsys\.org/[^"\']+)["\']',
        r'href=["\']([^"\']*(?:cs\.|people\.|faculty\.|sites\.google\.com|github\.io|personal\.|homepages\.|~)[^"\']*\.pdf(?:\?[^"\']*)?)["\']',
        r'href=["\']([^"\']*doi\.org/[^"\']+)["\']',
        r'href=["\']([^"\']*dl\.acm\.org/[^"\']+)["\']',
        r'href=["\']([^"\']*ieeexplore\.ieee\.org/[^"\']+)["\']',
    ]:
        for match in re.finditer(pattern, html, re.I):
            add(match.group(1))

    return prioritize_candidate_urls(candidates)


def resolve_pdf_url_from_links(links: List[str]) -> Optional[str]:
    prioritized = prioritize_candidate_urls(links)
    for link in prioritized:
        lower = link.lower()
        if looks_like_pdf_url(lower):
            return normalize_candidate_pdf_url(link)
        if "doi.org/" in lower or "usenix.org" in lower or "proceedings.mlsys.org" in lower:
            pdf = discover_pdf_from_page(link)
            if pdf:
                return pdf
    for link in prioritized:
        lower = link.lower()
        if lower.startswith("https://") or lower.startswith("http://"):
            try:
                req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen_no_proxy(req, timeout=30) as resp:
                    ctype = (resp.headers.get("Content-Type") or "").lower()
                    if "pdf" in ctype:
                        return normalize_candidate_pdf_url(link)
                    html = resp.read().decode("utf-8", errors="ignore")
                    candidates = extract_open_candidate_links(html, link)
                    if candidates:
                        return candidates[0]
            except Exception:
                continue
    return None


def extract_pdf_from_html(html: str, base_url: str) -> Optional[str]:
    if not html:
        return None
    patterns = [
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+\.pdf[^"\']*)["\']',
        r'citation_pdf_url["\']\s+content=["\']([^"\']+\.pdf[^"\']*)["\']',
        r'href=[\"\']([^\"\']+\.pdf(?:\?[^\"\']*)?)[\"\']',
        r'contentUrl["\']\s*:\s*["\']([^"\']+\.pdf[^"\']*)["\']',
        r'(?:/)?pdf\?id=([^\"\']+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.I)
        if m:
            hit = m.group(1)
            if pattern.endswith(r'(?:/)?pdf\?id=([^\"\']+)'):
                return urllib.parse.urljoin(base_url, f"/pdf?id={hit}")
            return urllib.parse.urljoin(base_url, hit)
    return None


def discover_pdf_from_page(url: str) -> Optional[str]:
    normalized = normalize_candidate_pdf_url(url)
    if looks_like_pdf_url(normalized):
        return normalized
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen_no_proxy(req, timeout=45) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return normalized if looks_like_pdf_url(normalized) else None
    pdf = extract_pdf_from_html(html, url)
    if pdf:
        return normalize_candidate_pdf_url(pdf)
    candidates = extract_open_candidate_links(html, url)
    if candidates:
        return candidates[0]
    return normalized if looks_like_pdf_url(normalized) else None


def discover_pdf_from_dblp_html(dblp_url: str) -> Optional[str]:
    try:
        req = urllib.request.Request(dblp_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen_no_proxy(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None
    pdf = extract_pdf_from_html(html, dblp_url)
    if pdf:
        return pdf
    pdf_candidates = re.findall(r'href=[\"\']([^\"\']+\.pdf(?:\?[^\"\']*)?)[\"\']', html, re.I)
    for candidate in pdf_candidates:
        return urllib.parse.urljoin(dblp_url, candidate)
    for pattern in [
        r'href=[\"\']([^\"\']*openreview\.net/forum\?id=[^\"\']+)[\"\']',
        r'href=[\"\']([^\"\']*openreview\.net[^\"\']+)[\"\']',
        r'href=[\"\']([^\"\']*doi\.org/[^\"\']+)[\"\']',
        r'href=[\"\']([^\"\']*arxiv\.org/abs/[^\"\']+)[\"\']',
        r'href=[\"\']([^\"\']*proceedings\.mlsys\.org/[^\"\']+)[\"\']',
        r'href=[\"\']([^\"\']*usenix\.org/[^\"\']+)[\"\']',
    ]:
        m = re.search(pattern, html, re.I)
        if m:
            ext = m.group(1)
            if "openreview.net/forum?id=" in ext:
                q = urllib.parse.parse_qs(urllib.parse.urlparse(ext).query).get("id", [""])[0]
                if q:
                    return f"https://openreview.net/pdf?id={urllib.parse.quote(q)}"
            return discover_pdf_from_page(ext) or ext
    return None


def is_missing(value: Optional[str]) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in {"", "TBD", "Unknown", "None"}
    return False


def parse_content_disposition_filename(header_value: Optional[str]) -> Optional[str]:
    if not header_value:
        return None
    match = re.search(r"filename\*?=(?:UTF-8''|\"?)([^\";]+)", header_value, re.I)
    if not match:
        return None
    return urllib.parse.unquote(match.group(1).strip().strip('"'))


def inspect_pdf_file(path: Path) -> dict:
    result = {
        "exists": path_exists_safe(path),
        "size_bytes": os.path.getsize(windows_long_path(path)) if path_exists_safe(path) else 0,
        "header_ok": False,
        "size_ok": False,
        "is_valid_pdf": False,
    }
    if not path_exists_safe(path):
        return result
    with open_binary_safe(path, "rb") as fh:
        header = fh.read(8)
    result["header_ok"] = header.startswith(PDF_MAGIC)
    result["size_ok"] = result["size_bytes"] >= MIN_PDF_BYTES
    result["is_valid_pdf"] = result["header_ok"] and result["size_ok"]
    return result


def extract_pdf_candidate_from_response(resp: requests.Response) -> Optional[str]:
    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "pdf" in content_type:
        return None
    try:
        html = resp.text
    except Exception:
        return None
    return extract_pdf_from_html(html, resp.url)


def build_pdf_candidates(metadata: dict, original_input: str) -> List[str]:
    candidates: List[str] = []

    def add(url: Optional[str]) -> None:
        if not url:
            return
        candidates.append(str(url).strip())

    add(metadata.get("pdf_url"))
    add(metadata.get("source_url"))
    for link in metadata.get("ee_links") or []:
        add(link)

    source_url = str(metadata.get("source_url") or "")
    if "arxiv.org/abs/" in source_url:
        add(source_url.replace("/abs/", "/pdf/") + ("" if source_url.endswith(".pdf") else ".pdf"))
    if "openreview.net/forum?id=" in source_url:
        forum_id = urllib.parse.parse_qs(urllib.parse.urlparse(source_url).query).get("id", [""])[0]
        if forum_id:
            add(f"https://openreview.net/pdf?id={urllib.parse.quote(forum_id)}")

    if re.match(r"https?://", original_input.strip()):
        add(original_input.strip())
    return prioritize_candidate_urls(candidates)


def try_download_candidate(url: str, output: Path) -> Tuple[dict, Optional[str]]:
    attempt = {
        "url": url,
        "status": "failed",
        "http_status": None,
        "content_type": None,
        "resolved_url": None,
        "size_bytes": 0,
        "pdf_header_ok": False,
        "pdf_size_ok": False,
        "message": "",
    }
    temp_dir = Path(tempfile.mkdtemp(prefix="paper_pdf_dl_"))
    tmp_path = temp_dir / "paper.pdf"

    try:
        for candidate in expand_candidate_pdf_urls(url):
            for retry in range(1, DOWNLOAD_RETRIES + 1):
                try:
                    session = requests_session_no_proxy()
                    session.headers.update({
                        "Accept": "application/pdf,text/html,application/xhtml+xml",
                        "Referer": urllib.parse.urlunparse(
                            urllib.parse.urlparse(candidate)._replace(path="", params="", query="", fragment="")
                        ) or candidate,
                    })
                    with session.get(candidate, stream=True, timeout=REQUEST_TIMEOUT, allow_redirects=True) as resp:
                        attempt["url"] = candidate
                        attempt["http_status"] = resp.status_code
                        attempt["content_type"] = resp.headers.get("Content-Type")
                        attempt["resolved_url"] = resp.url
                        resp.raise_for_status()

                        discovered = extract_pdf_candidate_from_response(resp)
                        if discovered and discovered != candidate:
                            attempt["status"] = "redirected-to-html"
                            attempt["message"] = f"Resolved HTML landing page; extracted PDF candidate {discovered}"
                            return attempt, discovered

                        output.parent.mkdir(parents=True, exist_ok=True)
                        with tmp_path.open("wb") as fh:
                            for chunk in resp.iter_content(chunk_size=1024 * 64):
                                if chunk:
                                    fh.write(chunk)

                    report = inspect_pdf_file(tmp_path)
                    attempt["size_bytes"] = report["size_bytes"]
                    attempt["pdf_header_ok"] = report["header_ok"]
                    attempt["pdf_size_ok"] = report["size_ok"]
                    if report["is_valid_pdf"]:
                        shutil.copy2(tmp_path, windows_long_path(output))
                        verify = inspect_pdf_file(output)
                        if not verify["is_valid_pdf"]:
                            raise FileNotFoundError(f"Downloaded PDF could not be verified at destination: {output}")
                        attempt["status"] = "success"
                        attempt["message"] = "Downloaded and validated as PDF."
                        return attempt, None

                    tmp_path.unlink(missing_ok=True)
                    attempt["status"] = "invalid-pdf"
                    attempt["message"] = (
                        f"Downloaded file failed validation: header_ok={report['header_ok']}, "
                        f"size_bytes={report['size_bytes']}."
                    )
                except Exception as exc:
                    tmp_path.unlink(missing_ok=True)
                    attempt["status"] = "exception"
                    attempt["message"] = f"{type(exc).__name__}: {exc}"

                if retry < DOWNLOAD_RETRIES:
                    time.sleep(1.2 ** retry)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return attempt, None


def copy_local_pdf(local_pdf: Path, output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    if local_pdf.resolve() != output.resolve():
        copy_file_safe(local_pdf, output)
    report = inspect_pdf_file(output)
    if not report["is_valid_pdf"]:
        raise SystemExit(
            f"Local PDF validation failed for {local_pdf}: "
            f"header_ok={report['header_ok']}, size_bytes={report['size_bytes']}"
        )
    return {
        "mode": "local_copy",
        "status": "success",
        "source_path": str(local_pdf),
        "resolved_url": str(local_pdf),
        "size_bytes": report["size_bytes"],
        "pdf_header_ok": report["header_ok"],
        "pdf_size_ok": report["size_ok"],
    }


def ensure_pdf_asset(metadata: dict, original_input: str, local_pdf: Optional[Path], pdf_path: Path) -> Tuple[dict, List[dict]]:
    if local_pdf:
        record = copy_local_pdf(local_pdf, pdf_path)
        return record, [record]

    candidates = build_pdf_candidates(metadata, original_input)
    attempts: List[dict] = []
    queue = list(candidates)
    seen = set()
    while queue:
        candidate = queue.pop(0)
        if candidate in seen:
            continue
        seen.add(candidate)
        attempt, discovered = try_download_candidate(candidate, pdf_path)
        attempts.append(attempt)
        if attempt["status"] == "success":
            metadata["pdf_url"] = attempt.get("resolved_url") or candidate
            return attempt, attempts
        if discovered and discovered not in seen:
            queue.insert(0, discovered)

    existing = inspect_pdf_file(pdf_path)
    if existing["is_valid_pdf"]:
        record = {
            "mode": "reuse_existing",
            "status": "success",
            "source_path": str(pdf_path),
            "resolved_url": str(pdf_path),
            "size_bytes": existing["size_bytes"],
            "pdf_header_ok": existing["header_ok"],
            "pdf_size_ok": existing["size_ok"],
        }
        attempts.append(record)
        return record, attempts

    detail = attempts[-1]["message"] if attempts else "No PDF candidate was resolved."
    raise SystemExit(f"PDF download failed for {original_input}. Last error: {detail}")


def resolve_input(input_value: str, title: Optional[str], authors: Optional[str]) -> Tuple[dict, Optional[Path], Optional[str]]:
    value = input_value.strip().strip('"')
    local = Path(value)
    if local.suffix.lower() == ".pdf" and path_exists_safe(local):
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
    if is_arxiv_id(value) or "arxiv.org" in value:
        arxiv_id = normalize_arxiv_id(arxiv_match.group(1) if arxiv_match else value)
        metadata = fetch_arxiv_metadata(arxiv_id)
        if title:
            metadata["title"] = title
        if authors:
            metadata["authors"] = authors
        metadata["input_type"] = "arxiv"
        return metadata, None, metadata.get("pdf_url")

    if "dblp.org/rec/" in value:
        metadata = fetch_dblp_metadata(value)
        if title:
            metadata["title"] = title
        if authors:
            metadata["authors"] = authors
        metadata["input_type"] = "dblp"
        metadata["pdf_url"] = metadata.get("pdf_url") or discover_pdf_from_dblp_html(value) or discover_pdf_from_page(value) or value
        return metadata, None, metadata.get("pdf_url")

    if re.match(r"https?://", value):
        parsed = urllib.parse.urlparse(value)
        guessed = Path(parsed.path).stem or "paper"
        fast_pdf_guess = normalize_candidate_pdf_url(value)
        if looks_like_pdf_url(fast_pdf_guess):
            return {
                "paper_id": guessed,
                "title": title or guessed,
                "authors": authors or "TBD",
                "abstract": "TBD",
                "published": "TBD",
                "source_url": value,
                "pdf_url": fast_pdf_guess,
                "categories": [],
                "input_type": "pdf_url",
            }, None, fast_pdf_guess
        pdf_guess = discover_pdf_from_page(value) or discover_pdf_from_dblp_html(value) or fast_pdf_guess
        if not isinstance(pdf_guess, str) or not pdf_guess.strip():
            pdf_guess = value
        return {
            "paper_id": guessed,
            "title": title or guessed,
            "authors": authors or "TBD",
            "abstract": "TBD",
            "published": "TBD",
            "source_url": value,
            "pdf_url": pdf_guess,
            "categories": [],
            "input_type": "html_url",
        }, None, pdf_guess

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


def create_junction(link_path: Path, target_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.exists():
        remove_junction(link_path)
    command = f'cmd /c mklink /J "{link_path}" "{target_path}"'
    result = subprocess.run(command, text=True, capture_output=True, shell=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "mklink failed").strip())


def remove_junction(link_path: Path) -> None:
    if not link_path.exists():
        return
    command = f'cmd /c rmdir "{link_path}"'
    subprocess.run(command, text=True, capture_output=True, shell=True, timeout=30)


def standardize_mineru_markdown(raw_md: Optional[Path]) -> Optional[Path]:
    if not raw_md or not raw_md.exists():
        return raw_md
    parent = raw_md.parent
    target_stem = raw_md.parent.parent.name if raw_md.parent.name == "auto" else raw_md.stem
    target = parent / f"{target_stem}.md"
    if raw_md.name == target.name:
        return raw_md
    if target.exists():
        return target
    raw_md.rename(target)
    return target


def standardize_mineru_tree(mineru_output: Path, paper_stem: str) -> Optional[Path]:
    if not mineru_output.exists():
        return None
    md_files = sorted(mineru_output.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not md_files:
        return None
    raw_md = md_files[0]
    auto_dir = raw_md.parent
    paper_dir = auto_dir.parent
    normalized_stem = compact_slug(paper_stem, fallback="paper", max_len=40)
    target_dir = mineru_output / normalized_stem
    if paper_dir.name != normalized_stem:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.move(str(paper_dir), str(target_dir))
        paper_dir = target_dir
        auto_dir = paper_dir / "auto"
        raw_md = auto_dir / raw_md.name
    target_md = auto_dir / f"{normalized_stem}.md"
    if raw_md.exists() and raw_md.name != target_md.name:
        if target_md.exists():
            target_md.unlink()
        raw_md.rename(target_md)
        raw_md = target_md
    for suffix in [
        "_content_list.json",
        "_content_list_v2.json",
        "_layout.pdf",
        "_middle.json",
        "_model.json",
        "_origin.pdf",
        "_span.pdf",
    ]:
        new = auto_dir / f"{normalized_stem}{suffix}"
        matching = sorted(
            [path for path in auto_dir.iterdir() if path.is_file() and path.name.endswith(suffix)],
            key=lambda path: (path.name != new.name, len(path.name)),
        )
        if not matching:
            continue
        primary = matching[0]
        if primary.name != new.name:
            if new.exists():
                new.unlink()
            primary.rename(new)
        for stale in matching[1:]:
            if stale.exists():
                stale.unlink()
    for child in mineru_output.iterdir():
        if child.is_dir() and child.name != normalized_stem:
            shutil.rmtree(child, ignore_errors=True)
    return raw_md if raw_md.exists() else None


def run_mineru(pdf_path: Path, mineru_output: Path, config: dict, paper_stem: str) -> Tuple[str, Optional[Path], List[dict]]:
    mineru_output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    attempts: List[dict] = []
    mineru_root = guess_mineru_root(config)
    temp_root = Path(tempfile.mkdtemp(prefix="paper_ingest_link_"))
    staged_pdf = temp_root / "paper.pdf"
    output_for_run = temp_root / "mineru_out"
    output_for_run.mkdir(parents=True, exist_ok=True)
    copy_file_safe(pdf_path, staged_pdf)

    def collect_from_temp_output() -> Optional[Path]:
        raw_md_temp = standardize_mineru_tree(output_for_run, paper_stem) or find_latest_markdown(output_for_run)
        if not raw_md_temp or not raw_md_temp.exists():
            return None
        alias_map = extract_figure_alias_map(read_text(raw_md_temp))
        image_aliases_for_md = consolidate_mineru_images(raw_md_temp, output_for_run, alias_map)
        rewrite_markdown_image_refs(raw_md_temp, image_aliases_for_md)
        raw_md_temp = standardize_mineru_tree(output_for_run, paper_stem) or raw_md_temp
        cleanup_stale_mineru_dirs(output_for_run, raw_md_temp.parent.parent.name)
        reset_mineru_output(mineru_output)
        copy_tree_safe(output_for_run, mineru_output)
        raw_md_final = standardize_mineru_tree(mineru_output, paper_stem) or find_latest_markdown(mineru_output)
        if raw_md_final and raw_md_final.exists():
            cleanup_stale_mineru_dirs(mineru_output, raw_md_final.parent.parent.name)
        return raw_md_final

    commands: List[Tuple[List[str], Optional[Path], Dict[str, str], str]] = []
    if shutil.which("mineru"):
        commands.append((["mineru", "-p", str(staged_pdf), "-o", str(output_for_run), "-b", "pipeline"], None, env.copy(), "cli"))

    if mineru_root:
        env_with_root = env.copy()
        env_with_root["PYTHONPATH"] = str(mineru_root) + os.pathsep + env_with_root.get("PYTHONPATH", "")
        commands.append((
            [sys.executable, "-m", "mineru.cli.client", "-p", str(staged_pdf), "-o", str(output_for_run), "-b", "pipeline"],
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

    try:
        for cmd, cwd, cmd_env, kind in commands:
            returncode, output = run_command(cmd, cwd, cmd_env)
            attempts.append({
                "kind": kind,
                "command": cmd,
                "cwd": str(cwd) if cwd else None,
                "returncode": returncode,
                "message": output[-3000:],
            })
            raw_md = collect_from_temp_output()
            if returncode == 0 and raw_md:
                return "success", raw_md, attempts

        raw_md = collect_from_temp_output()
        if raw_md:
            attempts.append({
                "kind": "post-check",
                "command": ["find_latest_markdown"],
                "cwd": str(output_for_run),
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
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


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
    md_text = read_text(md_path)
    lines = [line.strip() for line in md_text.splitlines()[:80]]
    non_empty = [line for line in lines if line]
    if not non_empty:
        return {}

    def should_skip(line: str) -> bool:
        lower = line.lower()
        return (
            line.startswith("![](")
            or line.startswith("##")
            or bool(re.fullmatch(r"https?://\S+", line))
            or lower.startswith("figure ")
            or lower.startswith("fig.")
            or "proceedings of" in lower
            or "open access to the proceedings" in lower
            or "sponsored by" in lower
        )

    title = None
    authors = None
    for idx, line in enumerate(non_empty[:24]):
        candidate = re.sub(r"^#\s*", "", line).strip()
        if not candidate or should_skip(candidate):
            continue
        if len(candidate.split()) < 4:
            continue
        title = candidate
        for probe in non_empty[idx + 1: idx + 10]:
            probe = re.sub(r"^#\s*", "", probe).strip()
            lower = probe.lower()
            if not probe or should_skip(probe):
                continue
            if "abstract" in lower:
                break
            if len(probe.split()) <= 40 and not re.search(r"(introduction|abstract)", lower):
                authors = re.sub(r"\s+", " ", probe).strip()
                break
        break

    if title is None:
        title = re.sub(r"^#\s*", "", non_empty[0]).strip()

    return {
        "title": title or None,
        "authors": authors or None,
        "abstract": extract_abstract(md_text),
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
        semantic_alias = alias_map.get(path.name)
        base_alias = f"fig{counter:02d}{path.suffix.lower()}"
        alias = base_alias
        counter += 1
        target = path.with_name(alias)
        while target.exists():
            base_alias = f"fig{counter:02d}{path.suffix.lower()}"
            alias = base_alias
            counter += 1
            target = path.with_name(alias)
        path.rename(target)
        records.append({"original": path.name, "alias": target.name, "path": str(target)})
        if semantic_alias and semantic_alias != target.name:
            semantic_target = target.with_name(semantic_alias)
            if not semantic_target.exists():
                shutil.copy2(target, semantic_target)
                records.append({"original": target.name, "alias": semantic_target.name, "path": str(semantic_target)})
    return records


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def next_fig_alias(counter: int, suffix: str) -> str:
    return f"fig{counter:02d}{suffix.lower()}"


def consolidate_mineru_images(raw_md: Optional[Path], mineru_output: Path, alias_map: Optional[Dict[str, str]] = None) -> List[dict]:
    if not raw_md or not raw_md.exists():
        return []
    alias_map = alias_map or {}
    canonical_image_dir = raw_md.parent / "images"
    canonical_image_dir.mkdir(parents=True, exist_ok=True)

    image_files = sorted(
        [path for path in mineru_output.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTS],
        key=lambda path: (path.parent != canonical_image_dir, path.name),
    )
    if not image_files:
        return []

    counter = 1
    digest_to_canonical: Dict[str, Path] = {}
    records: List[dict] = []

    for path in image_files:
        digest = file_sha256(path)
        canonical = digest_to_canonical.get(digest)

        if canonical is None:
            if path.parent == canonical_image_dir and re.fullmatch(r"fig\d+[a-z]?(?:-[a-z0-9-]+)?", path.stem, re.I):
                canonical = path
            else:
                alias = next_fig_alias(counter, path.suffix)
                counter += 1
                canonical = canonical_image_dir / alias
                while canonical.exists():
                    alias = next_fig_alias(counter, path.suffix)
                    counter += 1
                    canonical = canonical_image_dir / alias
                if path.resolve() != canonical.resolve():
                    shutil.move(str(path), str(canonical))
            digest_to_canonical[digest] = canonical
        elif path.resolve() != canonical.resolve():
            path.unlink(missing_ok=True)

        records.append({"original": path.name, "alias": canonical.name, "path": str(canonical)})

    for original_name, semantic_alias in alias_map.items():
        semantic_alias = str(semantic_alias or "").strip()
        if not semantic_alias:
            continue
        base_record = next((item for item in records if item["original"] == original_name), None)
        if not base_record:
            continue
        canonical = Path(str(base_record["path"]))
        semantic_target = canonical.with_name(semantic_alias)
        if semantic_target.name == canonical.name:
            continue
        if not semantic_target.exists():
            shutil.copy2(canonical, semantic_target)
        records.append({"original": canonical.name, "alias": semantic_target.name, "path": str(semantic_target)})

    return records


def rewrite_markdown_image_refs(md_path: Optional[Path], image_aliases: List[dict]) -> None:
    if not md_path or not md_path.exists() or not image_aliases:
        return
    text = read_text(md_path)
    updated = text
    seen_originals = set()
    for item in image_aliases:
        original = str(item.get("original") or "").strip()
        alias = str(item.get("alias") or "").strip()
        if not original or not alias or original == alias:
            continue
        if original in seen_originals:
            continue
        seen_originals.add(original)
        updated = updated.replace(f"images/{original}", f"images/{alias}")
    if updated != text:
        md_path.write_text(updated, encoding="utf-8")


def cleanup_stale_mineru_dirs(mineru_output: Path, keep_dir_name: str) -> None:
    if not mineru_output.exists():
        return
    for child in mineru_output.iterdir():
        if child.is_dir() and child.name != keep_dir_name:
            try:
                shutil.rmtree(windows_long_path(child), ignore_errors=False)
            except Exception:
                shutil.rmtree(child, ignore_errors=True)


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


def reset_mineru_output(mineru_output: Path) -> None:
    """Ensure each ingest run starts from a clean MinerU output tree."""
    if mineru_output.exists():
        shutil.rmtree(mineru_output, ignore_errors=True)
    mineru_output.mkdir(parents=True, exist_ok=True)


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


def find_existing_asset_dir(vault: Path, asset_slug: str, title: str, source_hints: Optional[List[str]] = None) -> Optional[Path]:
    assets_root = vault / "20_Research" / "Papers" / "_assets"
    if not assets_root.exists():
        return None

    direct = assets_root / asset_slug
    if direct.exists():
        return direct

    target_key = normalize_title_key(title or asset_slug)
    hint_keys = set()
    for hint in source_hints or []:
        if not hint:
            continue
        if re.match(r"https?://", hint):
            hint_value = Path(urllib.parse.urlparse(hint).path).stem
        else:
            hint_value = Path(hint).stem
        hint_keys.add(normalize_title_key(hint_value))

    for candidate in assets_root.rglob("*"):
        if not candidate.is_dir():
            continue

        manifest_path = candidate / "ingest_manifest.json"
        pdf_match = candidate / f"{candidate.name}.pdf"
        mineru_dir = candidate / "mineru"
        if not (manifest_path.exists() or pdf_match.exists() or mineru_dir.exists()):
            continue

        candidate_keys = {normalize_title_key(candidate.name)}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
            for field in ("title", "paper_id", "source_url", "pdf_url"):
                value = manifest.get(field)
                if not isinstance(value, str) or not value.strip():
                    continue
                if field.endswith("_url"):
                    if re.match(r"https?://", value):
                        value = Path(urllib.parse.urlparse(value).path).stem
                    else:
                        value = Path(value).stem
                candidate_keys.add(normalize_title_key(value))

        if asset_slug == candidate.name or target_key in candidate_keys or candidate_keys.intersection(hint_keys):
            return candidate
    return None


def choose_asset_pdf_path(asset_dir: Path, asset_slug: str) -> Path:
    existing_pdfs = sorted(asset_dir.glob("*.pdf"))
    if existing_pdfs:
        return existing_pdfs[0]
    return asset_dir / f"{asset_slug}.pdf"


def find_existing_paper_dir(vault: Path, asset_slug: str) -> Optional[Path]:
    assets_root = vault / "20_Research" / "Papers" / "_assets"
    if not assets_root.exists():
        return None
    for candidate in assets_root.rglob(asset_slug):
        if not candidate.is_dir():
            continue
        if any((candidate / name).exists() for name in ("ingest_manifest.json", "mineru")) or list(candidate.glob("*.pdf")):
            return candidate
    return None


def find_existing_pdf_asset(vault: Path, title: str, source_hints: Optional[List[str]] = None) -> Optional[Path]:
    assets_root = vault / "20_Research" / "Papers" / "_assets"
    if not assets_root.exists():
        return None

    title_key = normalize_title_key(title) if title else ""
    hint_keys = set()
    for hint in source_hints or []:
        if not hint:
            continue
        if re.match(r"https?://", hint):
            hint_keys.add(normalize_title_key(Path(urllib.parse.urlparse(hint).path).stem))
        else:
            hint_keys.add(normalize_title_key(Path(hint).stem))

    best = None
    best_score = -1
    for pdf in assets_root.rglob("*.pdf"):
        score = 0
        name_key = normalize_title_key(pdf.stem)
        parent_key = normalize_title_key(pdf.parent.name)
        if title_key:
            if name_key == title_key:
                score += 12
            if parent_key == title_key:
                score += 12
        if name_key in hint_keys:
            score += 2
        if parent_key in hint_keys:
            score += 2

        manifest_path = pdf.parent / "ingest_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
            manifest_title = manifest.get("title")
            if isinstance(manifest_title, str) and normalize_title_key(manifest_title) == title_key:
                score += 10
            manifest_paper_id = manifest.get("paper_id")
            if isinstance(manifest_paper_id, str) and normalize_title_key(manifest_paper_id) in hint_keys:
                score += 2
            for field in ("source_url", "pdf_url"):
                value = manifest.get(field)
                if not isinstance(value, str) or not value.strip():
                    continue
                if re.match(r"https?://", value):
                    value = Path(urllib.parse.urlparse(value).path).stem
                else:
                    value = Path(value).stem
                value_key = normalize_title_key(value)
                if value_key == title_key:
                    score += 4
                elif value_key in hint_keys:
                    score += 1

        if score > best_score:
            best = pdf
            best_score = score

    return best if best_score > 0 else None


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
    parser.add_argument("--asset-dir", default=None, help="Explicit asset directory to reuse/write into")
    parser.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT_PATH") or str(DEFAULT_VAULT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--skip-mineru", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    config = read_yaml_config(Path(args.config))
    metadata, local_pdf, pdf_url = resolve_input(args.input, args.title, args.authors)
    pdf_url = pdf_url or metadata.get("pdf_url") or metadata.get("source_url")
    metadata["requested_domain"] = args.domain
    title_seed = metadata.get("title")
    if is_missing(title_seed):
        title_seed = metadata.get("paper_id") or "paper"
    asset_slug = slugify(title_seed, fallback="paper")
    if local_pdf:
        pdf_path = local_pdf.resolve()
        asset_dir = pdf_path.parent
    else:
        if args.asset_dir:
            asset_dir = Path(args.asset_dir).resolve()
        else:
            existing_dir = find_existing_paper_dir(vault, asset_slug)
            if existing_dir is not None:
                asset_dir = existing_dir
            else:
                asset_dir = vault / "20_Research" / "Papers" / "_assets" / asset_slug
        asset_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = choose_asset_pdf_path(asset_dir, asset_slug)

    asset_dir.mkdir(parents=True, exist_ok=True)
    mineru_stem = preferred_mineru_stem(metadata, pdf_path)
    if pdf_url:
        metadata["pdf_url"] = pdf_url
    pdf_download, pdf_attempts = ensure_pdf_asset(metadata, args.input, local_pdf, pdf_path)
    pdf_validation = inspect_pdf_file(pdf_path)

    mineru_status = "skipped"
    raw_md: Optional[Path] = None
    mineru_attempts: List[dict] = []
    mineru_output_dir = asset_dir / "mineru"
    preexisting_md = find_latest_markdown(mineru_output_dir)
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
        reset_mineru_output(mineru_output_dir)
        mineru_status, raw_md, mineru_attempts = run_mineru(pdf_path, mineru_output_dir, config, mineru_stem)
    elif preexisting_md:
        raw_md = preexisting_md
        mineru_status = "success"

    raw_md = standardize_mineru_markdown(raw_md)

    extracted = extract_title_authors_from_markdown(raw_md)
    if extracted.get("title") and (is_missing(metadata.get("title")) or metadata.get("title") == metadata.get("paper_id")):
        metadata["title"] = extracted["title"]
    if metadata.get("input_type") == "local_pdf":
        if extracted.get("title") and extracted["title"] != metadata.get("title"):
            metadata["title"] = extracted["title"]
        if extracted.get("authors") and is_missing(metadata.get("authors")):
            metadata["authors"] = extracted["authors"]
        if extracted.get("abstract") and is_missing(metadata.get("abstract")):
            metadata["abstract"] = extracted["abstract"]
    else:
        if extracted.get("authors") and is_missing(metadata.get("authors")):
            metadata["authors"] = extracted["authors"]
        if extracted.get("abstract") and is_missing(metadata.get("abstract")):
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
    if raw_md and raw_md.exists():
        image_aliases = consolidate_mineru_images(raw_md, asset_dir / "mineru", alias_map)
        rewrite_markdown_image_refs(raw_md, image_aliases)
        cleanup_stale_mineru_dirs(asset_dir / "mineru", raw_md.parent.parent.name)

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
        "pdf_download_status": pdf_download.get("status", "unknown"),
        "pdf_download_record": pdf_download,
        "pdf_download_attempts": pdf_attempts,
        "pdf_validation": pdf_validation,
        "mineru_md": str(raw_md) if raw_md else None,
        "mineru_status": mineru_status,
        "mineru_attempts": mineru_attempts,
        "assets_index": str(assets_index),
        "suggested_note": str(note_path),
        "image_dirs": [str(path) for path in collect_image_dirs(asset_dir)],
        "image_aliases": image_aliases,
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "next_skill": "paper-translate" if raw_md else "paper-analyze",
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
        "suggested_next_skill": manifest["next_skill"],
        "note": str(note_path),
        "assets_index": str(assets_index),
        "manifest": str(manifest_path),
        "pdf": str(pdf_path),
        "pdf_download_status": pdf_download.get("status", "unknown"),
        "mineru_md": str(raw_md) if raw_md else None,
        "mineru_status": mineru_status,
        "domain": domain,
        "classification_reason": classification_reason,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
