#!/usr/bin/env python3
"""
CCF A 类会议 / 期刊论文搜索脚本
使用 DBLP API 获取论文列表 + Semantic Scholar API 补充引用数和摘要
默认优先覆盖 CCF A 类会议，并支持补充系统相关 A 类期刊。
"""

import json
import os
import re
import sys
import time
import logging
import argparse
from typing import List, Dict, Optional, Tuple
import urllib.request
import urllib.parse

logger = logging.getLogger(__name__)


def emit_json_output(payload: Dict) -> None:
    """Print JSON safely across terminals with limited default encodings."""
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    try:
        sys.stdout.write(text + "\n")
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def title_to_note_filename(title: str) -> str:
    """将论文标题转换为 Obsidian 笔记文件名（与 generate_note.py 保持一致）。

    使用与 paper-analyze/scripts/generate_note.py 完全相同的规则，
    确保 conf-papers 生成的 wikilink 路径能正确指向 paper-analyze 创建的文件。
    """
    filename = re.sub(r'[ /\\:*?"<>|]+', '_', title).strip('_')
    return filename

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests library not found, using urllib")

# ---------------------------------------------------------------------------
# 复用 search_arxiv.py 的评分函数
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_START_MY_DAY_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(_SCRIPT_DIR)), 'start-my-day', 'scripts')
if _START_MY_DAY_SCRIPTS not in sys.path:
    sys.path.insert(0, _START_MY_DAY_SCRIPTS)

from search_arxiv import (
    calculate_relevance_score,
    calculate_quality_score,
    SCORE_MAX,
    RELEVANCE_TITLE_KEYWORD_BOOST,
    RELEVANCE_SUMMARY_KEYWORD_BOOST,
    RELEVANCE_CATEGORY_MATCH_BOOST,
    S2_RATE_LIMIT_WAIT,
)

# ---------------------------------------------------------------------------
# Venue 配置
# ---------------------------------------------------------------------------
# 会议：DBLP toc key 映射：用于 toc:db/conf/... 查询格式
# 对于无法用 toc 查询的会议，使用 venue+year 备选查询
DBLP_CONFERENCES = {
    # Systems / architecture / HPC / parallel / data systems
    "MICRO": {"toc": "conf/micro", "toc_name": "micro{year}", "venue_query": "MICRO"},
    "ASPLOS": {"toc": "conf/asplos", "toc_name": "asplos{year}", "venue_query": "ASPLOS"},
    "SC": {"toc": "conf/sc", "toc_name": "sc{year}", "venue_query": "SC"},
    "PPoPP": {"toc": "conf/ppopp", "toc_name": "ppopp{year}", "venue_query": "PPoPP"},
    "OSDI": {"toc": "conf/osdi", "toc_name": "osdi{year}", "venue_query": "OSDI"},
    "SOSP": {"toc": "conf/sosp", "toc_name": "sosp{year}", "venue_query": "SOSP"},
    "NSDI": {"toc": "conf/nsdi", "toc_name": "nsdi{year}", "venue_query": "NSDI"},
    "EuroSys": {"toc": "conf/eurosys", "toc_name": "eurosys{year}", "venue_query": "EuroSys"},
    "ATC": {"toc": "conf/usenix", "toc_name": "usenix{year}", "venue_query": "USENIX Annual Technical Conference"},
    "FAST": {"toc": "conf/fast", "toc_name": "fast{year}", "venue_query": "FAST"},
    "HPCA": {"toc": "conf/hpca", "toc_name": "hpca{year}", "venue_query": "HPCA"},
    "ISCA": {"toc": "conf/isca", "toc_name": "isca{year}", "venue_query": "ISCA"},
    "ICS": {"toc": "conf/ics", "toc_name": "ics{year}", "venue_query": "ICS"},
    "VLDB": {"toc": "conf/vldb", "toc_name": "vldb{year}", "venue_query": "VLDB"},
    "SIGMOD": {"toc": "conf/sigmod", "toc_name": "sigmod{year}", "venue_query": "SIGMOD"},
    "SoCC": {"toc": "conf/cloud", "toc_name": "socc{year}", "venue_query": "SoCC"},
    "MLSys": {"toc": "conf/mlsys", "toc_name": "mlsys{year}", "venue_query": "MLSys"},

    # AI / ML / NLP / IR / web / data mining / vision
    "NeurIPS": {"toc": "conf/nips", "toc_name": "neurips{year}", "venue_query": "NeurIPS"},
    "ICML": {"toc": "conf/icml", "toc_name": "icml{year}", "venue_query": "ICML"},
    "ICLR": {"toc": "conf/iclr", "toc_name": "iclr{year}", "venue_query": "ICLR"},
    "AAAI": {"toc": "conf/aaai", "toc_name": "aaai{year}", "venue_query": "AAAI"},
    "IJCAI": {"toc": "conf/ijcai", "toc_name": "ijcai{year}", "venue_query": "IJCAI"},
    "ACL": {"toc": "conf/acl", "toc_name": "acl{year}", "venue_query": "ACL"},
    "EMNLP": {"toc": "conf/emnlp", "toc_name": None, "venue_query": "EMNLP"},
    "NAACL": {"toc": "conf/naacl", "toc_name": None, "venue_query": "NAACL"},
    "KDD": {"toc": "conf/kdd", "toc_name": "kdd{year}", "venue_query": "KDD"},
    "WWW": {"toc": "conf/www", "toc_name": "www{year}", "venue_query": "WWW"},
    "SIGIR": {"toc": "conf/sigir", "toc_name": "sigir{year}", "venue_query": "SIGIR"},
    "CIKM": {"toc": "conf/cikm", "toc_name": "cikm{year}", "venue_query": "CIKM"},
    "RecSys": {"toc": "conf/recsys", "toc_name": "recsys{year}", "venue_query": "RecSys"},
    "UAI": {"toc": "conf/uai", "toc_name": "uai{year}", "venue_query": "UAI"},
    "AISTATS": {"toc": "conf/aistats", "toc_name": "aistats{year}", "venue_query": "AISTATS"},
    "COLT": {"toc": "conf/colt", "toc_name": "colt{year}", "venue_query": "COLT"},
    "CVPR": {"toc": "conf/cvpr", "toc_name": "cvpr{year}", "venue_query": "CVPR"},
    "ICCV": {"toc": "conf/iccv", "toc_name": "iccv{year}", "venue_query": "ICCV"},
    "ECCV": {"toc": "conf/eccv", "toc_name": None, "venue_query": "ECCV"},
    "MICCAI": {"toc": "conf/miccai", "toc_name": None, "venue_query": "MICCAI"},
}

# 期刊：优先使用 venue + year 查询
DBLP_JOURNALS = {
    # System-related CCF A journals
    "TOCS": {"venue_query": "ACM Transactions on Computer Systems"},
    "TOS": {"venue_query": "ACM Transactions on Storage"},
    "TACO": {"venue_query": "ACM Transactions on Architecture and Code Optimization"},
    "TOPLAS": {"venue_query": "ACM Transactions on Programming Languages and Systems"},
    "TOSEM": {"venue_query": "ACM Transactions on Software Engineering and Methodology"},
    "TSE": {"venue_query": "IEEE Transactions on Software Engineering"},
    "TC": {"venue_query": "IEEE Transactions on Computers"},
    "TPDS": {"venue_query": "IEEE Transactions on Parallel and Distributed Systems"},
    "TKDE": {"venue_query": "IEEE Transactions on Knowledge and Data Engineering"},
    "TODS": {"venue_query": "ACM Transactions on Database Systems"},
    "VLDBJ": {"venue_query": "The VLDB Journal"},
    "JSAC": {"venue_query": "IEEE Journal on Selected Areas in Communications"},
    "TON": {"venue_query": "IEEE/ACM Transactions on Networking"},
}

VENUE_TO_CATEGORIES = {
    "MICRO": ["cs.AR", "cs.PF"],
    "ASPLOS": ["cs.AR", "cs.OS", "cs.PF"],
    "SC": ["cs.DC", "cs.PF", "cs.AR"],
    "PPoPP": ["cs.DC", "cs.PF", "cs.PL"],
    "OSDI": ["cs.OS", "cs.DC"],
    "SOSP": ["cs.OS", "cs.DC"],
    "NSDI": ["cs.NI", "cs.DC"],
    "EuroSys": ["cs.OS", "cs.DC"],
    "ATC": ["cs.OS", "cs.DC"],
    "FAST": ["cs.OS", "cs.DB"],
    "HPCA": ["cs.AR", "cs.PF"],
    "ISCA": ["cs.AR", "cs.PF"],
    "ICS": ["cs.PF", "cs.DC"],
    "VLDB": ["cs.DB", "cs.DC"],
    "SIGMOD": ["cs.DB"],
    "SoCC": ["cs.DC", "cs.OS"],
    "MLSys": ["cs.LG", "cs.DC", "cs.PF"],
    "NeurIPS": ["cs.LG", "cs.AI", "cs.CL", "cs.DC"],
    "ICML": ["cs.LG", "cs.AI"],
    "ICLR": ["cs.LG", "cs.AI", "cs.CL"],
    "AAAI": ["cs.AI"],
    "IJCAI": ["cs.AI"],
    "ACL": ["cs.CL"],
    "EMNLP": ["cs.CL"],
    "NAACL": ["cs.CL"],
    "KDD": ["cs.DB", "cs.LG", "cs.AI"],
    "WWW": ["cs.IR", "cs.DB", "cs.AI"],
    "SIGIR": ["cs.IR"],
    "CIKM": ["cs.IR", "cs.DB"],
    "RecSys": ["cs.IR", "cs.LG"],
    "UAI": ["cs.LG", "cs.AI"],
    "AISTATS": ["cs.LG"],
    "COLT": ["cs.LG"],
    "CVPR": ["cs.CV"],
    "ICCV": ["cs.CV"],
    "ECCV": ["cs.CV"],
    "MICCAI": ["cs.CV", "eess.IV"],
    "TOCS": ["cs.OS", "cs.DC"],
    "TOS": ["cs.OS", "cs.AR"],
    "TACO": ["cs.AR", "cs.PF", "cs.PL"],
    "TOPLAS": ["cs.PL"],
    "TOSEM": ["cs.SE"],
    "TSE": ["cs.SE"],
    "TC": ["cs.AR", "cs.PF"],
    "TPDS": ["cs.DC", "cs.PF"],
    "TKDE": ["cs.DB", "cs.LG"],
    "TODS": ["cs.DB"],
    "VLDBJ": ["cs.DB"],
    "JSAC": ["cs.NI"],
    "TON": ["cs.NI"],
}

WEIGHTS_CONF = {
    'relevance': 0.40,
    'popularity': 0.40,
    'quality': 0.20,
}

SYSTEM_A_CONFERENCES = {
    "MICRO", "ASPLOS", "SC", "PPoPP", "OSDI", "SOSP", "NSDI", "EuroSys",
    "ATC", "FAST", "HPCA", "ISCA", "ICS", "VLDB", "SIGMOD", "SoCC", "MLSys",
}

QUICK_PRIORITY_CONFERENCES = [
    "ASPLOS", "OSDI", "SOSP", "NSDI", "EuroSys", "ATC", "FAST", "HPCA",
    "ISCA", "MICRO", "SC", "PPoPP", "VLDB", "SIGMOD", "SoCC", "MLSys", "ICS",
]

SYSTEM_A_JOURNALS = {
    "TOCS", "TOS", "TACO", "TOPLAS", "TOSEM", "TSE", "TC", "TPDS",
    "TKDE", "TODS", "VLDBJ", "JSAC", "TON",
}

VENUE_PRIORITY_SCORE = {
    "system_a_conference": 3.0,
    "other_a_conference": 2.0,
    "system_a_journal": 1.0,
    "other": 0.0,
}

# 热门度：高影响力引用满分基准
POPULARITY_INFLUENTIAL_CITATION_FULL_SCORE = 100

# Semantic Scholar 配置
S2_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper"
S2_FIELDS = "title,abstract,citationCount,influentialCitationCount,externalIds,url,authors,authors.affiliations"
S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_API_KEY = None

# DBLP API 配置
DBLP_API_URL = "https://dblp.org/search/publ/api"

# ---------------------------------------------------------------------------
# DBLP 搜索
# ---------------------------------------------------------------------------

def search_dblp_conference(venue_key: str, year: int, max_results: int = 1000, max_retries: int = 3) -> List[Dict]:
    """
    调用 DBLP Search API 搜索指定会议和年份的论文

    Args:
        venue_key: 会议名称（如 "CVPR"）
        year: 年份
        max_results: 最大返回数量
        max_retries: 最大重试次数

    Returns:
        论文列表，每篇包含 title, authors, dblp_url, year, conference
    """
    venue_info = DBLP_CONFERENCES.get(venue_key)
    if not venue_info:
        logger.warning("[DBLP] Unknown venue: %s", venue_key)
        return []

    papers = []
    hits_fetched = 0
    batch_size = min(max_results, 1000)

    # 构建查询列表：优先 toc 格式，备选 venue+year
    queries_to_try = []
    toc_name = venue_info.get("toc_name")
    if toc_name:
        toc_path = venue_info["toc"]
        queries_to_try.append(f"toc:db/{toc_path}/{toc_name.format(year=year)}.bht:")
    # 总是添加 venue+year 作为备选
    venue_query = venue_info.get("venue_query", venue_key)
    queries_to_try.append(f"venue:{venue_query} year:{year}")

    for query_str in queries_to_try:
        papers = []
        hits_fetched = 0
        query_failed = False

        while hits_fetched < max_results:
            params = {
                "q": query_str,
                "format": "json",
                "h": batch_size,
                "f": hits_fetched,
            }

            url = f"{DBLP_API_URL}?{urllib.parse.urlencode(params)}"
            logger.info("[DBLP] Searching %s %d (offset=%d, query=%s)", venue_key, year, hits_fetched, query_str[:60])

            success = False
            for attempt in range(max_retries):
                try:
                    if HAS_REQUESTS:
                        resp = requests.get(url, headers={"User-Agent": "ConfPapers/1.0"}, timeout=60)
                        resp.raise_for_status()
                        data = resp.json()
                    else:
                        req = urllib.request.Request(url, headers={"User-Agent": "ConfPapers/1.0"})
                        with urllib.request.urlopen(req, timeout=60) as response:
                            data = json.loads(response.read().decode('utf-8'))

                    result = data.get("result", {})
                    hits = result.get("hits", {})
                    total = int(hits.get("@total", 0))
                    hit_list = hits.get("hit", [])

                    if not hit_list:
                        logger.info("[DBLP] %s %d: no more results (total=%d)", venue_key, year, total)
                        if papers:
                            logger.info("[DBLP] %s %d: found %d papers", venue_key, year, len(papers))
                            return papers
                        # 0 results with this query, try next
                        query_failed = True
                        break

                    for hit in hit_list:
                        info = hit.get("info", {})
                        title = info.get("title", "").rstrip(".")
                        if not title:
                            continue

                        authors_info = info.get("authors", {}).get("author", [])
                        if isinstance(authors_info, dict):
                            authors_info = [authors_info]
                        authors = [a.get("text", "") for a in authors_info if a.get("text")]

                        paper = {
                            "title": title,
                            "authors": authors,
                            "dblp_url": info.get("url", ""),
                            "year": int(info.get("year", year)),
                            "conference": venue_key,
                            "doi": info.get("doi", ""),
                            "venue": info.get("venue", venue_key),
                            "source": "dblp",
                        }
                        papers.append(paper)

                    hits_fetched += len(hit_list)
                    success = True

                    if hits_fetched >= total or hits_fetched >= max_results:
                        break

                    time.sleep(1)
                    break  # 成功，退出重试循环

                except Exception as e:
                    logger.warning("[DBLP] Error (attempt %d/%d): %s", attempt + 1, max_retries, e)
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 3
                        logger.info("[DBLP] Retrying in %d seconds...", wait_time)
                        time.sleep(wait_time)
                    else:
                        logger.warning("[DBLP] Query failed for %s: %s", venue_key, query_str[:60])
                        query_failed = True

            if query_failed:
                break
            if hits_fetched >= max_results:
                break

        if papers:
            logger.info("[DBLP] %s %d: found %d papers", venue_key, year, len(papers))
            return papers
        elif query_failed:
            logger.info("[DBLP] Trying fallback query for %s %d...", venue_key, year)
            continue

    logger.warning("[DBLP] %s %d: no papers found with any query", venue_key, year)
    return []


def search_dblp_journal(venue_key: str, year: int, max_results: int = 1000, max_retries: int = 3) -> List[Dict]:
    venue_info = DBLP_JOURNALS.get(venue_key)
    if not venue_info:
        logger.warning("[DBLP] Unknown journal: %s", venue_key)
        return []

    params = {
        "q": f'venue:{venue_info["venue_query"]} year:{year}',
        "format": "json",
        "h": min(max_results, 1000),
        "f": 0,
    }
    url = f"{DBLP_API_URL}?{urllib.parse.urlencode(params)}"
    logger.info("[DBLP] Searching journal %s %d", venue_key, year)

    for attempt in range(max_retries):
        try:
            if HAS_REQUESTS:
                resp = requests.get(url, headers={"User-Agent": "ConfPapers/1.0"}, timeout=60)
                resp.raise_for_status()
                data = resp.json()
            else:
                req = urllib.request.Request(url, headers={"User-Agent": "ConfPapers/1.0"})
                with urllib.request.urlopen(req, timeout=60) as response:
                    data = json.loads(response.read().decode('utf-8'))

            hits = data.get("result", {}).get("hits", {}).get("hit", [])
            papers = []
            for hit in hits:
                info = hit.get("info", {})
                title = info.get("title", "").rstrip(".")
                if not title:
                    continue
                authors_info = info.get("authors", {}).get("author", [])
                if isinstance(authors_info, dict):
                    authors_info = [authors_info]
                authors = [a.get("text", "") for a in authors_info if a.get("text")]
                papers.append({
                    "title": title,
                    "authors": authors,
                    "dblp_url": info.get("url", ""),
                    "year": int(info.get("year", year)),
                    "conference": venue_key,
                    "venue": info.get("venue", venue_key),
                    "doi": info.get("doi", ""),
                    "source": "dblp",
                    "venue_type": "journal",
                })
            logger.info("[DBLP] %s %d: found %d journal papers", venue_key, year, len(papers))
            return papers
        except Exception as e:
            logger.warning("[DBLP] Journal error (attempt %d/%d): %s", attempt + 1, max_retries, e)
            if attempt < max_retries - 1:
                time.sleep((2 ** attempt) * 3)
    return []


def search_all_venues(year: int, venues: List[str], journals: List[str], max_per_venue: int = 1000) -> List[Dict]:
    """
    遍历所有会议搜索论文，合并去重

    Args:
        year: 年份
        venues: 会议列表
        max_per_venue: 每个会议最大拉取数

    Returns:
        去重后的论文列表
    """
    all_papers = []
    seen_titles = set()

    for venue in venues:
        logger.info("=" * 50)
        logger.info("Searching %s %d...", venue, year)

        papers = search_dblp_conference(venue, year, max_results=max_per_venue)

        for p in papers:
            title_norm = re.sub(r'[^a-z0-9\s]', '', p['title'].lower()).strip()
            if title_norm not in seen_titles:
                seen_titles.add(title_norm)
                all_papers.append(p)

        logger.info("Total unique papers so far: %d", len(all_papers))
        time.sleep(1)

    for journal in journals:
        logger.info("=" * 50)
        logger.info("Searching journal %s %d...", journal, year)

        papers = search_dblp_journal(journal, year, max_results=max_per_venue)
        for p in papers:
            title_norm = re.sub(r'[^a-z0-9\s]', '', p['title'].lower()).strip()
            if title_norm not in seen_titles:
                seen_titles.add(title_norm)
                all_papers.append(p)

        logger.info("Total unique papers so far: %d", len(all_papers))
        time.sleep(1)

    return all_papers


# ---------------------------------------------------------------------------
# 两阶段过滤：第一阶段 - 轻量关键词过滤
# ---------------------------------------------------------------------------

def load_conf_papers_config(config_path: str) -> Dict:
    """
    从 conf-papers.yaml 加载专用配置。

    Args:
        config_path: conf-papers.yaml 路径

    Returns:
        {keywords: [...], excluded_keywords: [...], default_year, default_conferences, default_journals, top_n}
    """
    import yaml

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cp = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error("Error loading conf-papers config: %s", e)
        cp = {}

    return {
        'keywords': cp.get('keywords', []),
        'excluded_keywords': cp.get('excluded_keywords', []),
        'default_year': cp.get('default_year'),
        'default_conferences': cp.get('default_conferences'),
        'default_journals': cp.get('default_journals', []),
        'top_n': cp.get('top_n', 10),
    }


def lightweight_keyword_filter(papers: List[Dict], cp_config: Dict) -> List[Dict]:
    """
    第一阶段：仅凭标题关键词做轻量相关性过滤
    使用 conf-papers.yaml 中的关键词

    Args:
        papers: DBLP 拉取的全部论文
        cp_config: conf-papers 专用配置

    Returns:
        通过关键词过滤的论文列表
    """
    # 收集所有关键词（小写）
    all_keywords = set(kw.lower() for kw in cp_config['keywords'])
    excluded_lower = set(kw.lower() for kw in cp_config['excluded_keywords'])

    filtered = []
    for paper in papers:
        title_lower = paper['title'].lower()

        # 检查排除关键词
        if any(ex in title_lower for ex in excluded_lower):
            continue

        # 检查是否匹配任何研究关键词
        matched = False
        matched_keywords = []
        for kw in all_keywords:
            if kw in title_lower:
                matched = True
                matched_keywords.append(kw)

        if matched:
            paper['_preliminary_keywords'] = matched_keywords
            filtered.append(paper)

    logger.info("[Filter] Lightweight keyword filter: %d -> %d papers", len(papers), len(filtered))
    return filtered


# ---------------------------------------------------------------------------
# Semantic Scholar 补充
# ---------------------------------------------------------------------------

def title_similarity(a: str, b: str) -> float:
    """
    归一化标题比较，用于 S2 匹配验证

    Returns:
        0.0-1.0 之间的相似度分数
    """
    def normalize(s):
        return re.sub(r'[^a-z0-9\s]', '', s.lower()).strip()

    a_norm = normalize(a)
    b_norm = normalize(b)

    if not a_norm or not b_norm:
        return 0.0

    # 使用词级别的 Jaccard 相似度
    words_a = set(a_norm.split())
    words_b = set(b_norm.split())

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b

    return len(intersection) / len(union)


def enrich_with_semantic_scholar(papers: List[Dict], max_retries: int = 3) -> List[Dict]:
    """
    使用 S2 搜索 API 按标题补充 abstract/citations/arxiv_id
    分批处理，每批之间有间隔以避免限流

    Args:
        papers: 需要补充信息的论文列表
        max_retries: 每次请求的最大重试次数

    Returns:
        补充信息后的论文列表
    """
    if not HAS_REQUESTS:
        logger.warning("[S2] requests library not available, skipping enrichment")
        for p in papers:
            p['abstract'] = None
            p['citationCount'] = 0
            p['influentialCitationCount'] = 0
            p['s2_matched'] = False
        return papers

    headers = {"User-Agent": "ConfPapers/1.0"}
    if S2_API_KEY:
        headers["x-api-key"] = S2_API_KEY

    enriched_count = 0
    total = len(papers)

    for i, paper in enumerate(papers):
        title = paper.get('title', '')
        if not title:
            paper['abstract'] = ''
            paper['citationCount'] = 0
            paper['influentialCitationCount'] = 0
            paper['s2_matched'] = False
            paper['summary'] = ''
            continue

        if (i + 1) % 10 == 0:
            logger.info("[S2] Progress: %d/%d enriched so far: %d", i + 1, total, enriched_count)

        params = {
            "query": title,
            "limit": 3,
            "fields": S2_FIELDS,
        }

        matched = False
        for attempt in range(max_retries):
            try:
                response = requests.get(S2_API_URL, params=params, headers=headers, timeout=15)
                if response.status_code == 429:
                    wait = S2_RATE_LIMIT_WAIT
                    logger.warning("[S2] Rate limit hit, waiting %d seconds...", wait)
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()

                results = data.get("data", [])
                if not results:
                    break

                best_match = None
                best_sim = 0.0
                for r in results:
                    sim = title_similarity(title, r.get('title', ''))
                    if sim > best_sim:
                        best_sim = sim
                        best_match = r

                if best_match and best_sim >= 0.6:
                    paper['abstract'] = best_match.get('abstract') or ''
                    paper['citationCount'] = best_match.get('citationCount') or 0
                    paper['influentialCitationCount'] = best_match.get('influentialCitationCount') or 0
                    paper['s2_url'] = best_match.get('url', '')

                    ext_ids = best_match.get('externalIds', {})
                    if ext_ids:
                        paper['arxiv_id'] = ext_ids.get('ArXiv')
                        paper['doi'] = paper.get('doi') or ext_ids.get('DOI', '')

                    if not paper.get('authors') and best_match.get('authors'):
                        paper['authors'] = [a.get('name', '') for a in best_match['authors'] if a.get('name')]

                    # 提取 affiliation 信息
                    if best_match.get('authors'):
                        affiliations = []
                        for a in best_match['authors']:
                            for affil in (a.get('affiliations') or []):
                                name = affil.get('name', '') if isinstance(affil, dict) else str(affil)
                                if name and name not in affiliations:
                                    affiliations.append(name)
                        if affiliations:
                            paper['affiliations'] = affiliations

                    paper['s2_matched'] = True
                    paper['s2_title_similarity'] = round(best_sim, 2)
                    enriched_count += 1
                    matched = True

                break

            except Exception as e:
                error_msg = str(e)
                is_rate_limit = "429" in error_msg or "Too Many Requests" in error_msg
                if attempt < max_retries - 1:
                    if is_rate_limit:
                        time.sleep(S2_RATE_LIMIT_WAIT)
                    else:
                        time.sleep(2 ** attempt)
                else:
                    logger.debug("[S2] Failed to enrich: %s", title[:50])

        if not matched:
            paper['abstract'] = ''
            paper['citationCount'] = 0
            paper['influentialCitationCount'] = 0
            paper['s2_matched'] = False
            paper['summary'] = ''

        # 关键：每次请求后等待 1 秒避免 429
        # S2 免费层约 1 req/sec
        time.sleep(1.0)

    logger.info("[S2] Enrichment complete: %d/%d papers enriched", enriched_count, total)
    return papers


def mark_unenriched_papers(papers: List[Dict]) -> List[Dict]:
    """为未做 S2 enrich 的论文补默认字段，保持后续评分逻辑稳定。"""
    for paper in papers:
        paper.setdefault('abstract', '')
        paper.setdefault('citationCount', 0)
        paper.setdefault('influentialCitationCount', 0)
        paper.setdefault('s2_matched', False)
        paper.setdefault('summary', '')
    return papers


# ---------------------------------------------------------------------------
# 评分
# ---------------------------------------------------------------------------

def calculate_popularity_score(paper: Dict) -> float:
    """
    基于 influentialCitationCount 和 citationCount 计算热门度

    Args:
        paper: 论文信息

    Returns:
        热门度评分 (0-SCORE_MAX)
    """
    inf_cit = paper.get('influentialCitationCount', 0)
    cit = paper.get('citationCount', 0)

    if inf_cit > 0:
        # 高影响力引用：归一化到 0-SCORE_MAX
        score = min(inf_cit / (POPULARITY_INFLUENTIAL_CITATION_FULL_SCORE / SCORE_MAX), SCORE_MAX)
    elif cit > 0:
        # 普通引用：更保守的评分
        score = min(cit / 200 * SCORE_MAX, SCORE_MAX * 0.7)
    else:
        score = 0.0

    return score


def classify_venue_priority(paper: Dict) -> str:
    """Return a venue priority tier for ranking and tie-breaking."""
    venue = paper.get('conference', '')
    venue_type = paper.get('venue_type', 'conference')

    if venue in SYSTEM_A_CONFERENCES:
        return "system_a_conference"
    if venue_type == "journal" and venue in SYSTEM_A_JOURNALS:
        return "system_a_journal"
    if venue in DBLP_CONFERENCES:
        return "other_a_conference"
    return "other"


def filter_and_score_papers(papers: List[Dict], cp_config: Dict, top_n: int = 10) -> List[Dict]:
    """
    对论文进行完整的三维评分（相关性+热门度+质量），排序取 top N
    使用 conf-papers.yaml 的关键词构建虚拟 domain 用于评分

    Args:
        papers: 论文列表（已经过 S2 补充）
        cp_config: conf-papers 专用配置
        top_n: 返回前 N 篇

    Returns:
        评分排序后的论文列表
    """
    # 构建虚拟 domain 供 calculate_relevance_score 使用
    domains = {
        "conf_papers": {
            "keywords": cp_config['keywords'],
            "arxiv_categories": ["cs.DC", "cs.OS", "cs.PF", "cs.AR", "cs.DB", "cs.NI", "cs.ET", "cs.PL", "cs.IR", "cs.LG", "cs.CL", "cs.AI"],
        }
    }
    excluded_keywords = cp_config['excluded_keywords']

    scored_papers = []

    for paper in papers:
        # 为了复用 calculate_relevance_score，需要为顶会论文补充 categories
        # 使用会议到分类的映射
        venue = paper.get('conference', '')
        venue_categories = VENUE_TO_CATEGORIES.get(venue, [])
        paper['categories'] = venue_categories

        # 用 abstract 替代 summary（兼容 calculate_relevance_score）
        if paper.get('abstract') and not paper.get('summary'):
            paper['summary'] = paper['abstract']

        # 计算相关性
        relevance, matched_domain, matched_keywords = calculate_relevance_score(
            paper, domains, excluded_keywords
        )

        if relevance == 0:
            continue

        # 计算热门度
        popularity = calculate_popularity_score(paper)

        # 计算质量
        summary = paper.get('summary', '') or paper.get('abstract', '') or ''
        quality = calculate_quality_score(summary)
        venue_priority_label = classify_venue_priority(paper)
        venue_priority_score = VENUE_PRIORITY_SCORE.get(venue_priority_label, 0.0)

        # 计算综合评分（三维度）
        normalized = {
            'relevance': (relevance / SCORE_MAX) * 10,
            'popularity': (popularity / SCORE_MAX) * 10,
            'quality': (quality / SCORE_MAX) * 10,
        }
        final_score = sum(normalized[k] * WEIGHTS_CONF[k] for k in WEIGHTS_CONF)
        final_score = round(final_score, 2)

        paper['scores'] = {
            'relevance': round(relevance, 2),
            'popularity': round(popularity, 2),
            'quality': round(quality, 2),
            'recommendation': final_score,
        }
        paper['venue_priority'] = {
            'tier': venue_priority_label,
            'score': venue_priority_score,
        }
        paper['matched_domain'] = matched_domain
        paper['matched_keywords'] = matched_keywords

        scored_papers.append(paper)

    # 按推荐评分排序
    scored_papers.sort(
        key=lambda x: (
            x.get('venue_priority', {}).get('score', 0.0),
            x['scores']['recommendation'],
            x['scores']['relevance'],
            x['scores']['popularity'],
            x.get('conference', ''),
            x.get('title', ''),
        ),
        reverse=True,
    )

    logger.info("[Score] %d papers scored, returning top %d", len(scored_papers), top_n)
    return scored_papers[:top_n]


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def main():
    # 默认配置路径：脚本所在 skill 目录下的 conf-papers.yaml
    default_config = os.path.join(os.path.dirname(_SCRIPT_DIR), 'conf-papers.yaml')

    parser = argparse.ArgumentParser(description='Search top conference papers via DBLP + Semantic Scholar')
    parser.add_argument('--config', type=str,
                        default=default_config,
                        help='Path to conf-papers.yaml config file')
    parser.add_argument('--output', type=str, default='conf_papers_filtered.json',
                        help='Output JSON file path')
    parser.add_argument('--year', type=int, default=None,
                        help='Conference year to search (default: from config)')
    parser.add_argument('--conferences', type=str, default=None,
                        help='Comma-separated conference names (default: from config)')
    parser.add_argument('--journals', type=str, default=None,
                        help='Comma-separated journal names (default: from config)')
    parser.add_argument('--top-n', type=int, default=None,
                        help='Number of top papers to return (default: from config)')
    parser.add_argument('--max-per-venue', type=int, default=1000,
                        help='Max papers to fetch per venue from DBLP')
    parser.add_argument('--skip-enrichment', action='store_true',
                        help='Skip Semantic Scholar enrichment (for debugging)')
    parser.add_argument('--max-enrich', type=int, default=None,
                        help='Only enrich top-K preliminarily filtered papers with Semantic Scholar')
    parser.add_argument('--conference-priority-only', action='store_true',
                        help='Search only conferences first, skip journals for quick validation')
    parser.add_argument('--quick', action='store_true',
                        help='Fast mode: smaller DBLP pull, conference-first, and no Semantic Scholar enrichment')
    parser.add_argument('--very-quick', action='store_true',
                        help='Very fast smoke test: smaller DBLP pull, conference-first, no enrichment, and smaller top-n')

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stderr,
    )

    if not os.path.exists(args.config):
        logger.error("配置文件不存在: %s", args.config)
        return 1

    logger.info("Loading conf-papers config from: %s", args.config)
    cp_config = load_conf_papers_config(args.config)
    logger.info("Config: %d keywords, %d excluded",
                len(cp_config['keywords']), len(cp_config['excluded_keywords']))

    # 确定年份：命令行 > 配置 > 报错
    year = args.year or cp_config.get('default_year')
    if not year:
        logger.error("未指定搜索年份。请通过 --year 参数或配置文件 conf_papers.default_year 设置。")
        return 1

    # 确定 top_n：命令行 > 配置 > 默认 10
    top_n = args.top_n or cp_config.get('top_n', 10)
    if args.very_quick and args.top_n is None:
        top_n = min(top_n, 10)

    # 确定要搜索的会议：命令行 > 配置 > 全部 7 个
    if args.conferences:
        venues = [v.strip() for v in args.conferences.split(',')]
    elif cp_config.get('default_conferences'):
        venues = list(cp_config['default_conferences'])
    else:
        venues = list(DBLP_CONFERENCES.keys())

    if args.journals:
        journals = [v.strip() for v in args.journals.split(',')]
    else:
        journals = list(cp_config.get('default_journals', []))
    if args.conference_priority_only:
        journals = []

    effective_max_per_venue = args.max_per_venue
    effective_skip_enrichment = args.skip_enrichment
    if args.quick:
        journals = []
        venues = [v for v in QUICK_PRIORITY_CONFERENCES if v in venues]
        effective_max_per_venue = min(effective_max_per_venue, 120)
        effective_skip_enrichment = True
        logger.info("Quick mode enabled: %d priority conferences only, max_per_venue=%d, skip enrichment",
                    len(venues), effective_max_per_venue)
    if args.very_quick:
        journals = []
        venues = [v for v in QUICK_PRIORITY_CONFERENCES[:8] if v in venues]
        effective_max_per_venue = min(effective_max_per_venue, 60)
        effective_skip_enrichment = True
        logger.info("Very quick mode enabled: %d priority conferences only, max_per_venue=%d, skip enrichment, compact top-n",
                    len(venues), effective_max_per_venue)

    # 验证会议名（大小写不敏感匹配）
    venue_name_map = {k.upper(): k for k in DBLP_CONFERENCES}
    valid_venues = []
    for v in venues:
        canonical = venue_name_map.get(v.upper())
        if canonical:
            valid_venues.append(canonical)
        else:
            logger.warning("Unknown conference: %s (available: %s)", v, ', '.join(DBLP_CONFERENCES.keys()))
    venues = valid_venues

    journal_name_map = {k.upper(): k for k in DBLP_JOURNALS}
    valid_journals = []
    for j in journals:
        canonical = journal_name_map.get(j.upper())
        if canonical:
            valid_journals.append(canonical)
        else:
            logger.warning("Unknown journal: %s (available: %s)", j, ', '.join(DBLP_JOURNALS.keys()))
    journals = valid_journals

    if not venues and not journals:
        logger.error("No valid venues specified")
        return 1

    logger.info("Conferences: %s", ', '.join(venues))
    logger.info("Journals: %s", ', '.join(journals))
    logger.info("Year: %d", year)

    # ========== 第一步：DBLP 搜索 ==========
    logger.info("=" * 70)
    logger.info("Step 1: Searching papers from DBLP")
    logger.info("=" * 70)

    all_papers = search_all_venues(year, venues, journals, max_per_venue=effective_max_per_venue)
    total_found = len(all_papers)
    logger.info("Total papers found from DBLP: %d", total_found)

    if not all_papers:
        logger.warning("No papers found from DBLP!")
        # 输出空结果
        output = {
            "year": year,
            "conferences_searched": venues,
            "journals_searched": journals,
            "total_found": 0,
            "total_enriched": 0,
            "total_unique": 0,
            "top_papers": [],
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        emit_json_output(output)
        return 0

    # ========== 第二步：轻量关键词过滤 ==========
    logger.info("=" * 70)
    logger.info("Step 2: Lightweight keyword filtering")
    logger.info("=" * 70)

    filtered_papers = lightweight_keyword_filter(all_papers, cp_config)
    total_filtered = len(filtered_papers)

    if not filtered_papers:
        logger.warning("No papers passed keyword filter!")
        output = {
            "year": year,
            "conferences_searched": venues,
            "journals_searched": journals,
            "total_found": total_found,
            "total_enriched": 0,
            "total_unique": 0,
            "top_papers": [],
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        emit_json_output(output)
        return 0

    # ========== 第三步：Semantic Scholar 补充 ==========
    total_enriched = 0
    if not effective_skip_enrichment:
        logger.info("=" * 70)
        enrich_candidates = filtered_papers
        skipped_enrich_count = 0
        if args.max_enrich is not None and args.max_enrich >= 0:
            enrich_candidates = filtered_papers[:args.max_enrich]
            skipped_enrich_count = max(0, len(filtered_papers) - len(enrich_candidates))
            logger.info("Step 3: Enriching with Semantic Scholar only top %d/%d preliminarily filtered papers",
                        len(enrich_candidates), len(filtered_papers))
        else:
            logger.info("Step 3: Enriching with Semantic Scholar (%d papers)", len(filtered_papers))
        logger.info("=" * 70)

        enriched_subset = enrich_with_semantic_scholar(enrich_candidates)
        remaining_subset = mark_unenriched_papers(filtered_papers[len(enrich_candidates):]) if skipped_enrich_count else []
        filtered_papers = enriched_subset + remaining_subset
        total_enriched = sum(1 for p in filtered_papers if p.get('s2_matched'))
        if skipped_enrich_count:
            logger.info("[S2] Skipped enrichment for %d lower-priority preliminarily filtered papers", skipped_enrich_count)
    else:
        logger.info("Skipping Semantic Scholar enrichment")
        filtered_papers = mark_unenriched_papers(filtered_papers)

    # ========== 第四步：评分排序 ==========
    logger.info("=" * 70)
    logger.info("Step 4: Scoring and ranking")
    logger.info("=" * 70)

    top_papers = filter_and_score_papers(filtered_papers, cp_config, top_n=top_n)

    # 清理输出中的内部字段
    for p in top_papers:
        p.pop('_preliminary_keywords', None)
        p.pop('s2_matched', None)
        p.pop('s2_title_similarity', None)
        p.pop('categories', None)
        p.pop('venue_priority', None)
        p.pop('summary', None)  # 保留 abstract，去掉重复的 summary
        # 为每篇论文补充 note_filename，与 generate_note.py 的文件名规则保持一致
        # 这样 conf-papers 生成的 wikilink 可以直接使用此字段，无需自行推断
        p['note_filename'] = title_to_note_filename(p.get('title', ''))

    # 准备输出
    output = {
        "year": year,
        "conferences_searched": venues,
        "journals_searched": journals,
        "total_found": total_found,
        "total_filtered": total_filtered,
        "total_enriched": total_enriched,
        "top_papers": top_papers,
    }

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    logger.info("Results saved to: %s", args.output)
    logger.info("Top %d papers:", len(top_papers))
    for i, p in enumerate(top_papers, 1):
        cit = p.get('citationCount', 0)
        logger.info("  %d. [%s] %s... (Score: %s, Citations: %d)",
                     i, p.get('conference', '?'), p.get('title', 'N/A')[:50],
                     p['scores']['recommendation'], cit)

    emit_json_output(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
