"""
Smart Scraper — Web scraping dengan content extraction, caching, dan multi-adapter.

Layer 1: Input (manual / auto-trigger / scheduled)
Layer 2: Smart Router + Adapters (HTTP, Search API, RSS)
Layer 3: Processing Pipeline (clean & extract, dedup & rank, cache)
Layer 4: Output (JSON/Markdown terstruktur)
"""
import asyncio
import hashlib
import json
import os
import re
import time
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from xml.etree import ElementTree

import httpx
from loguru import logger

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
CACHE_DIR = Path.home() / ".config" / "rav-spy" / "scraper_cache"
CACHE_TTL = 6 * 3600

def _cache_key(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def _cache_get(url: str) -> Optional[dict]:
    path = CACHE_DIR / _cache_key(url)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() - data["cached_at"] < CACHE_TTL:
            return data
        path.unlink(missing_ok=True)
    except Exception:
        path.unlink(missing_ok=True)
    return None

def _cache_set(url: str, data: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data["cached_at"] = time.time()
    path = CACHE_DIR / _cache_key(url)
    path.write_text(json.dumps(data, indent=2, default=str))

# ---------------------------------------------------------------------------
# Shared HTTP client
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id,en;q=0.9",
}

_client = httpx.AsyncClient(verify=False, timeout=15.0, headers=HEADERS, follow_redirects=True)

# ---------------------------------------------------------------------------
# Adapter 1: HTTP Fetcher — static HTML pages
# ---------------------------------------------------------------------------
async def _fetch_http(url: str) -> Optional[str]:
    try:
        res = await _client.get(url)
        if res.status_code == 200:
            return res.text
        logger.warning(f"HTTP {res.status_code} for {url}")
    except Exception as e:
        logger.debug(f"HTTP fetch error for {url}: {e}")
    return None

# ---------------------------------------------------------------------------
# Adapter 2: RSS Feed parser
# ---------------------------------------------------------------------------
async def _fetch_rss(feed_url: str, limit: int = 10) -> list[dict]:
    xml_data = await _fetch_http(feed_url)
    if not xml_data:
        return []

    items = []
    try:
        root = ElementTree.fromstring(xml_data)
        ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
        for entry in root.iter("item"):
            title = entry.findtext("title", "")
            link = entry.findtext("link", "")
            desc = entry.findtext("description", "")
            content_encoded = entry.findtext("content:encoded", "", ns)
            pub_date = entry.findtext("pubDate", "")
            summary = re.sub(r"<[^>]+>", "", content_encoded or desc).strip()
            items.append({
                "title": title.strip(),
                "url": link.strip(),
                "summary": summary[:500],
                "published": pub_date.strip(),
                "source": feed_url,
            })
            if len(items) >= limit:
                break
    except ElementTree.ParseError:
        try:
            root = ElementTree.fromstring(xml_data)
            ns_atom = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
                title = entry.findtext("{http://www.w3.org/2005/Atom}title", "")
                link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                link = link_el.get("href", "") if link_el is not None else ""
                summary_el = entry.find("{http://www.w3.org/2005/Atom}summary")
                content_el = entry.find("{http://www.w3.org/2005/Atom}content")
                summary = (summary_el or content_el)
                summary_text = re.sub(r"<[^>]+>", "", (summary.text or "") if summary is not None else "").strip()
                published = entry.findtext("{http://www.w3.org/2005/Atom}published", "")
                items.append({
                    "title": title.strip(),
                    "url": link.strip(),
                    "summary": summary_text[:500],
                    "published": published.strip(),
                    "source": feed_url,
                })
                if len(items) >= limit:
                    break
        except Exception as e:
            logger.error(f"RSS parse error: {e}")
            return []

    return items

# ---------------------------------------------------------------------------
# Adapter 3: Search engines (multi-fallback)
# ---------------------------------------------------------------------------
async def _search_ddg(query: str, max_results: int = 5) -> list[dict]:
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
    html = await _fetch_http(url)
    if not html:
        return []

    results = []
    body_pattern = re.compile(r'<div class="result__body">(.*?)</div>\s*</div>', re.DOTALL)
    bodies = body_pattern.findall(html)

    for body in bodies[:max_results]:
        title_match = re.search(r'<a class="result__a" href="([^"]+)">([^<]+)</a>', body, re.DOTALL)
        snippet_match = re.search(r'<a class="result__snippet"[^>]*>(.*?)</a>', body, re.DOTALL)
        if not title_match:
            continue
        href, title = title_match.groups()
        if "uddg=" in href:
            actual_url = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
        else:
            actual_url = href
            if actual_url.startswith("//"):
                actual_url = "https:" + actual_url
        snippet = ""
        if snippet_match:
            snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip()
        results.append({
            "title": re.sub(r"<[^>]+>", "", title).strip(),
            "url": actual_url,
            "snippet": snippet,
        })
    return results

async def _search_yahoo(query: str, max_results: int = 5) -> list[dict]:
    url = f"https://search.yahoo.com/search?q={urllib.parse.quote_plus(query)}"
    html = await _fetch_http(url)
    if not html:
        return []

    results = []
    pattern = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</h3>\s*</a>', re.DOTALL)
    matches = pattern.findall(html)
    for href, inner in matches[:max_results * 2]:
        h3_match = re.search(r'<h3[^>]*>(.*?)</h3>', inner + "</h3>", re.DOTALL)
        if h3_match:
            title = re.sub(r"<[^>]+>", "", h3_match.group(1)).strip()
        else:
            title = re.sub(r"<[^>]+>", "", inner).strip()
        actual_url = href
        if "/RU=" in href:
            ru_part = href.split("/RU=")[1].split("/RK=")[0]
            actual_url = urllib.parse.unquote(ru_part)
        if not title or not actual_url.startswith("http") or "yahoo.com" in actual_url:
            continue
        snippet_match = re.search(r'<div class="compText"[^>]*>(.*?)</div>', html[html.find(href):html.find(href)+500], re.DOTALL)
        snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip() if snippet_match else ""
        results.append({"title": title, "url": actual_url, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results

async def _search_engines(query: str, max_results: int = 5) -> list[dict]:
    for engine in (_search_ddg, _search_yahoo):
        try:
            results = await engine(query, max_results)
            if results:
                logger.info(f"Search results from {engine.__name__}: {len(results)} items")
                return results
        except Exception as e:
            logger.debug(f"{engine.__name__} failed: {e}")
    return []

# ---------------------------------------------------------------------------
# Processing Pipeline
# ---------------------------------------------------------------------------
def _extract_content(html: str, url: str = "") -> dict:
    """Clean HTML and extract meaningful content."""
    title = ""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if title_match:
        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    body_html = body_match.group(1) if body_match else html

    text = re.sub(r"<script[^>]*>.*?</script>", "", body_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<nav[^>]*>.*?</nav>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<footer[^>]*>.*?</footer>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<header[^>]*>.*?</header>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 40]
    if not lines:
        lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 20]
    content_text = "\n".join(lines[:50])

    return {
        "title": title,
        "content": content_text[:5000],
        "word_count": len(content_text.split()),
        "url": url,
    }

def _dedup_and_rank(results: list[dict], query: str = "") -> list[dict]:
    seen_urls = set()
    ranked = []
    keywords = query.lower().split() if query else []

    for r in results:
        url = r.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)

        if keywords:
            score = 0
            text = (r.get("title", "") + " " + r.get("content", "") + " " + r.get("summary", "")).lower()
            for kw in keywords:
                score += text.count(kw)
            r["_score"] = score
        else:
            r["_score"] = 0
        ranked.append(r)

    ranked.sort(key=lambda x: x["_score"], reverse=True)
    return ranked

# ---------------------------------------------------------------------------
# Smart Scrape — single URL
# ---------------------------------------------------------------------------
def _clean_raw(text: str, max_lines: int = 8) -> str:
    """Bersihkan teks mentah: ambil hanya baris informatif, buang navigasi."""
    lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 60]
    if not lines:
        lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 30]
    cleaned = "\n".join(lines[:max_lines])
    return cleaned[:1500]

async def _ai_summarize(text: str, query: str = "") -> str | None:
    from ai_module.fast_ai import fast_ai
    if not fast_ai.enabled:
        logger.warning("FastAI disabled — no API key or disabled via env")
        return None
    try:
        result = await fast_ai.summarize(text, query=query)
        if result:
            logger.info(f"AI summarization OK ({len(result)} chars)")
        else:
            logger.warning("AI summarization returned None")
        return result
    except Exception as e:
        logger.error(f"AI summarization error: {e}")
        return None

async def scrape_url(url: str, force: bool = False, use_ai: bool = True) -> dict:
    if not force:
        cached = _cache_get(url)
        if cached and (not use_ai or cached.get("ai_summary")):
            return {**cached, "cached": True}

    html = await _fetch_http(url)
    if not html:
        return {"error": f"Gagal mengambil halaman: {url}", "url": url}

    extracted = _extract_content(html, url)
    result = {
        "url": url,
        "title": extracted["title"],
        "content": extracted["content"],
        "word_count": extracted["word_count"],
        "cached": False,
    }

    if use_ai and extracted["content"]:
        summary = await _ai_summarize(extracted["content"], query=url)
        if summary:
            result["ai_summary"] = summary
        else:
            logger.warning(f"AI returned None for {url}, using clean fallback")

    if not result.get("ai_summary") and extracted["content"]:
        logger.info("Falling back to _clean_raw")
        result["ai_summary"] = _clean_raw(extracted["content"])

    _cache_set(url, result)
    return result

# ---------------------------------------------------------------------------
# Smart Search — search web THEN scrape each result
# ---------------------------------------------------------------------------
async def smart_search(query: str, max_results: int = 3, max_words_per_page: int = 1500, use_ai: bool = True) -> str:
    cached = _cache_get(f"search::{query}")
    if cached:
        return cached["result"]

    logger.info(f"Smart search: {query}")
    search_results = await _search_engines(query, max_results=max_results * 2)
    if not search_results:
        return f"❌ Tidak ditemukan hasil untuk: {query}"

    enriched = []
    for sr in search_results[:max_results]:
        page = await scrape_url(sr["url"], use_ai=use_ai)
        if "error" in page:
            enriched.append({
                "title": sr["title"],
                "url": sr["url"],
                "summary": sr.get("snippet", ""),
            })
            continue
        enriched.append({
            "title": page["title"] or sr["title"],
            "url": sr["url"],
            "summary": page.get("ai_summary") or sr.get("snippet", ""),
        })

    ranked = _dedup_and_rank(enriched, query)

    lines = [f"🔍 {query}\n"]
    for i, r in enumerate(ranked, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['url']}")
        summary = r.get("summary", "")
        if summary:
            for line in summary.strip().split("\n"):
                if line.strip():
                    lines.append(f"   {line.strip()}")
        lines.append("")

    result_text = "\n".join(lines).strip()
    if not result_text:
        return f"❌ Tidak ditemukan hasil untuk: {query}"
    _cache_set(f"search::{query}", {"result": result_text})
    return result_text

# ---------------------------------------------------------------------------
# RSS Reader — fetch + extract items
# ---------------------------------------------------------------------------
async def read_rss(feed_url: str, limit: int = 10) -> str:
    cached = _cache_get(f"rss::{feed_url}")
    if cached:
        return cached["result"]

    items = await _fetch_rss(feed_url, limit=limit)
    if not items:
        return f"❌ Gagal mengambil RSS feed: {feed_url}"

    lines = [f"📡 RSS Feed: {feed_url}", ""]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item['title']}")
        lines.append(f"   {item['url']}")
        if item.get("published"):
            lines.append(f"   🕐 {item['published']}")
        if item.get("summary"):
            lines.append("")
            lines.append(item["summary"][:500])
        lines.append("")

    result_text = "\n".join(lines)
    _cache_set(f"rss::{feed_url}", {"result": result_text})
    return result_text

# ---------------------------------------------------------------------------
# Scheduled / Auto scraper
# ---------------------------------------------------------------------------
_scheduled_jobs: dict[str, dict] = {}

async def run_scheduled_jobs(notify_func):
    """Background task: periodically run scheduled scraper jobs."""
    while True:
        now = time.time()
        for job_id, job in list(_scheduled_jobs.items()):
            if job.get("next_run", 0) <= now:
                try:
                    logger.info(f"Running scheduled scraper job: {job_id}")
                    if job["type"] == "search":
                        result = await smart_search(job["query"], max_results=3)
                        await notify_func(f"📰 Scrape Scheduled: {job['query']}\n\n{result[:2000]}")
                    elif job["type"] == "rss":
                        result = await read_rss(job["url"], limit=5)
                        await notify_func(f"📡 RSS Update: {job['url']}\n\n{result[:2000]}")
                    job["next_run"] = now + job.get("interval", 21600)
                except Exception as e:
                    logger.error(f"Scheduled scrape job {job_id} error: {e}")
        await asyncio.sleep(60)

def add_scheduled_job(job_id: str, job_type: str, target: str, interval: int = 21600):
    _scheduled_jobs[job_id] = {
        "type": job_type,
        "query": target if job_type == "search" else "",
        "url": target if job_type == "rss" else "",
        "interval": interval,
        "next_run": time.time(),
    }

def remove_scheduled_job(job_id: str) -> bool:
    return _scheduled_jobs.pop(job_id, None) is not None

def list_scheduled_jobs() -> list[dict]:
    return [{"id": k, **v} for k, v in _scheduled_jobs.items()]

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
async def close():
    await _client.aclose()
