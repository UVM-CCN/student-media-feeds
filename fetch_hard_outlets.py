"""
Cascade fetcher for student journalism outlets that block standard RSS access.

For each outlet, tries strategies in order until one succeeds:

    1. WordPress REST API at /wp-json/wp/v2/posts
       Many WordPress-backed papers expose this even when their RSS feed is
       Cloudflare-blocked. The API returns title, body, date, byline, etc.
       in a single JSON response. No browser needed.

    2. Sitemap + per-article fetch with curl_cffi
       Sitemaps are intended for search engines and rarely blocked. We pull
       the article URLs, then fetch each one with curl_cffi which mimics a
       real Chrome TLS fingerprint to bypass most Cloudflare protection.
       Article body is extracted with trafilatura.

Outlets that fail both strategies are reported at the end for follow-up.
Headless browser (Playwright) is intentionally NOT a fallback — that's the
next phase if too many outlets still fail here.

Stories are appended to news_database.csv with the same schema as the RSS
scraper. Full article text is written to full_text/<hash>.txt with the
metadata header used elsewhere in the pipeline. Keywords and sentiment are
backfilled at the end via the same NewsPipeline.enrich_missing_metadata()
that the daily scrape uses.

Usage:
    python fetch_hard_outlets.py

Requires:
    pip install curl_cffi trafilatura beautifulsoup4
"""

import csv
import datetime
import logging
import os
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Optional

import trafilatura
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    print(
        "ERROR: curl_cffi is required.\n"
        "Install with: pip install curl_cffi",
        file=sys.stderr,
    )
    sys.exit(1)

from scrape import NewsPipeline
from fetch_full_text import url_to_path


CSV_PATH = "news_database.csv"
LOG_FILE = "fetch_hard_outlets.log"
USER_AGENT = (
    "StudentMediaFeedsBot/1.0 (academic research; "
    "+https://github.com/UVM-CCN/student-media-feeds)"
)
MIN_DOMAIN_DELAY = 2.0
DEFAULT_MAX_STORIES_PER_OUTLET = 100  # used for one-off backfills
DAILY_MAX_STORIES_PER_OUTLET = 25     # used when scrape.py calls us each night
REQUEST_TIMEOUT = 30
IMPERSONATE_PROFILE = "chrome120"  # curl_cffi browser fingerprint

# Common sitemap paths, tried in order
SITEMAP_CANDIDATES = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/news-sitemap.xml",
    "/post-sitemap.xml",
    "/post-sitemap1.xml",
    "/sitemap-posts.xml",
    "/article-sitemap.xml",
    "/sitemap/posts.xml",
]

# Outlets flagged with skip=True are not probed on each daily run. They failed
# the cascade on 2026-06-22 (sitemap unavailable or all article fetches blocked)
# and would otherwise waste 5+ minutes per nightly run. Flip skip back to False
# once a workaround is identified (e.g., Playwright headless, manual feed URL,
# or a site-specific scraper).
HARD_OUTLETS = [
    {"name": "The Harvard Crimson", "url": "https://www.thecrimson.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "The Yale Daily News", "url": "https://yaledailynews.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "The Daily Pennsylvanian", "url": "https://www.thedp.com"},
    {"name": "The Cornell Daily Sun", "url": "https://cornellsun.com"},
    {"name": "The Daily Tar Heel", "url": "https://www.dailytarheel.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "The Independent Florida Alligator", "url": "https://www.alligator.org"},
    {"name": "The Purdue Exponent", "url": "https://www.purdueexponent.org"},
    {"name": "Daily Bruin", "url": "https://dailybruin.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "Indiana Daily Student", "url": "https://www.idsnews.com"},
    {"name": "The Daily Collegian", "url": "https://www.collegian.psu.edu"},
    {"name": "The State News", "url": "https://statenews.com"},
    {"name": "The Daily Cardinal", "url": "https://www.dailycardinal.com"},
    {"name": "The Shorthorn", "url": "https://www.theshorthorn.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "The Duke Chronicle", "url": "https://www.dukechronicle.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "The Johns Hopkins News-Letter", "url": "https://www.jhunewsletter.com"},
    {"name": "The Dartmouth", "url": "https://www.thedartmouth.com"},
    {"name": "The Emory Wheel", "url": "https://emorywheel.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "Rice Thresher", "url": "https://ricethresher.org",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "The Ball State Daily News", "url": "https://www.ballstatedailynews.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "The Oklahoma Daily", "url": "https://oudaily.com"},
    {"name": "The Daily Gamecock", "url": "https://www.dailygamecock.com"},
    {"name": "The Daily Kansan", "url": "https://www.dailykansan.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "The Daily Nebraskan", "url": "https://www.dailynebraskan.com"},
    {"name": "The Daily O'Collegian", "url": "https://www.ocolly.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "The Montana Kaimin", "url": "https://www.montanakaimin.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    {"name": "The FSView & Florida Flambeau", "url": "https://www.fsview.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
    # Verify-only case: RSS URL was correct but Cloudflare-blocked.
    # WP API and sitemap also failed in cascade; skip until a workaround exists.
    {"name": "The Minnesota Daily", "url": "https://mndaily.com",
     "skip": True, "skip_reason": "cascade failed 2026-06-22"},
]

_last_request_by_domain: dict[str, float] = {}


def _domain_of(url: str) -> str:
    netloc = urllib.parse.urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _throttle(url: str) -> None:
    """Enforce a minimum delay between requests to the same host."""
    domain = _domain_of(url)
    if not domain:
        return
    elapsed = time.time() - _last_request_by_domain.get(domain, 0.0)
    if elapsed < MIN_DOMAIN_DELAY:
        time.sleep(MIN_DOMAIN_DELAY - elapsed)
    _last_request_by_domain[domain] = time.time()


def _http_get(session, url: str, accept: str = "*/*") -> Optional[object]:
    """Wrapper around curl_cffi GET with throttling and exception handling."""
    _throttle(url)
    try:
        return session.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": accept},
            timeout=REQUEST_TIMEOUT,
            impersonate=IMPERSONATE_PROFILE,
            allow_redirects=True,
        )
    except Exception as e:
        logging.debug("HTTP error for %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Strategy 1: WordPress REST API
# ---------------------------------------------------------------------------

def try_wordpress_api(outlet: dict, session, max_stories: int) -> Optional[list[dict]]:
    """Return a list of stories from /wp-json/wp/v2/posts or None if unavailable."""
    base = outlet["url"].rstrip("/")
    api_root = f"{base}/wp-json/wp/v2/posts"
    per_page = min(50, max_stories)
    stories: list[dict] = []

    # Page through up to enough posts to hit max_stories
    max_pages = max(1, (max_stories + per_page - 1) // per_page)
    for page in range(1, max_pages + 1):
        url = f"{api_root}?per_page={per_page}&page={page}"
        r = _http_get(session, url, accept="application/json")
        if r is None or r.status_code != 200:
            return None if page == 1 else stories[:max_stories]
        try:
            data = r.json()
        except Exception:
            return None if page == 1 else stories[:max_stories]
        if not isinstance(data, list) or not data:
            break
        for post in data:
            try:
                title_html = post.get("title", {}).get("rendered", "")
                content_html = post.get("content", {}).get("rendered", "")
                stories.append({
                    "title": BeautifulSoup(title_html, "html.parser").get_text(strip=True),
                    "link": post.get("link", ""),
                    "published": post.get("date_gmt") or post.get("date") or "",
                    "content_html": content_html,
                })
            except Exception as e:
                logging.debug("Could not parse WP post: %s", e)
        if len(stories) >= max_stories or len(data) < per_page:
            break

    return stories[:max_stories] if stories else None


# ---------------------------------------------------------------------------
# Strategy 2: Sitemap + curl_cffi article fetch
# ---------------------------------------------------------------------------

def _localname(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_sitemap(xml_text: str) -> tuple[list[dict], list[str]]:
    """Return (article URLs with lastmod, child sitemap URLs)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return [], []

    article_urls: list[dict] = []
    child_sitemaps: list[str] = []

    if _localname(root.tag) == "sitemapindex":
        for sm in root:
            loc_el = next((c for c in sm if _localname(c.tag) == "loc"), None)
            if loc_el is not None and loc_el.text:
                child_sitemaps.append(loc_el.text.strip())
    elif _localname(root.tag) == "urlset":
        for url_el in root:
            loc = lastmod = None
            for c in url_el:
                t = _localname(c.tag)
                if t == "loc" and c.text:
                    loc = c.text.strip()
                elif t == "lastmod" and c.text:
                    lastmod = c.text.strip()
            if loc:
                article_urls.append({"url": loc, "lastmod": lastmod or ""})

    return article_urls, child_sitemaps


def _fetch_sitemap(session, url: str) -> Optional[str]:
    r = _http_get(session, url, accept="application/xml,text/xml,*/*")
    if r is None or r.status_code != 200:
        return None
    text = r.text
    if "<urlset" not in text and "<sitemapindex" not in text:
        return None
    return text


def try_sitemap(outlet: dict, session, max_stories: int) -> Optional[list[dict]]:
    """Discover articles via sitemap, fetch each with curl_cffi + trafilatura."""
    base = outlet["url"].rstrip("/")
    article_urls: list[dict] = []
    visited: set[str] = set()

    for path in SITEMAP_CANDIDATES:
        sitemap_url = f"{base}{path}"
        if sitemap_url in visited:
            continue
        visited.add(sitemap_url)

        xml_text = _fetch_sitemap(session, sitemap_url)
        if not xml_text:
            continue

        articles, children = _parse_sitemap(xml_text)
        if articles:
            article_urls.extend(articles)
            logging.info("    sitemap %s yielded %d article URLs", sitemap_url, len(articles))
            break

        if children:
            # Index sitemap. Prefer children whose names suggest posts/articles.
            preferred = [c for c in children if any(k in c.lower() for k in ("post", "article", "news"))]
            queue = preferred or children
            for child_url in queue[:5]:  # cap fanout to keep runtime sane
                if child_url in visited:
                    continue
                visited.add(child_url)
                child_xml = _fetch_sitemap(session, child_url)
                if not child_xml:
                    continue
                sub_articles, _ = _parse_sitemap(child_xml)
                article_urls.extend(sub_articles)
            if article_urls:
                logging.info("    sitemap index %s yielded %d article URLs", sitemap_url, len(article_urls))
                break

    if not article_urls:
        return None

    # Sort newest-first by lastmod (empty lastmods sink to bottom) and cap.
    article_urls.sort(key=lambda x: x.get("lastmod") or "", reverse=True)
    article_urls = article_urls[:max_stories]

    stories: list[dict] = []
    for i, art in enumerate(article_urls, 1):
        url = art["url"]
        r = _http_get(session, url, accept="text/html,*/*")
        if r is None or r.status_code != 200:
            continue
        html_text = r.text

        text = trafilatura.extract(html_text, url=url, include_comments=False, include_tables=False)
        if not text or not text.strip():
            continue

        title = ""
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            else:
                h1 = soup.find("h1")
                if h1:
                    title = h1.get_text(strip=True)
        except Exception:
            pass

        stories.append({
            "title": title or "No Title",
            "link": url,
            "published": art.get("lastmod", ""),
            "content_text": text.strip(),
        })

        if i % 25 == 0:
            logging.info("    fetched %d/%d articles", i, len(article_urls))

    return stories if stories else None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _write_full_text(url: str, story: dict, source_name: str) -> str:
    """Write extracted text + metadata header to full_text/. Returns relative path."""
    text = story.get("content_text")
    if not text:
        html_content = story.get("content_html", "")
        text = BeautifulSoup(html_content, "html.parser").get_text("\n", strip=True)

    path = url_to_path(url)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    extracted_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    header = (
        f"# Title: {story.get('title', '')}\n"
        f"# URL: {url}\n"
        f"# Source: {source_name}\n"
        f"# Published: {story.get('published', '')}\n"
        f"# Extracted: {extracted_at}\n"
        f"# ---\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(text)
    return path


def prepare_rows(outlet: dict, stories: list[dict], existing_links: set[str]) -> list[dict]:
    """Filter out duplicates, write full-text files, return row dicts ready to append."""
    captured_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rows = []
    for story in stories:
        link = (story.get("link") or "").strip()
        if not link or link in existing_links:
            continue
        path = _write_full_text(link, story, outlet["name"])
        rows.append({
            "source": outlet["name"],
            "title": story.get("title") or "No Title",
            "link": link,
            "published": story.get("published", ""),
            "captured_at": captured_at,
            "theme": "",
            "keywords": "",
            "sentiment_label": "",
            "sentiment_score": "",
            "extraction_status": "ok",
            "full_text_path": path,
        })
        existing_links.add(link)
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_outlets(max_stories: int = DEFAULT_MAX_STORIES_PER_OUTLET) -> dict:
    """
    Run the cascade on every non-skipped outlet. Returns a summary dict.

    Called both by main() (standalone, max_stories=100 backfill) and from
    scrape.py's run_daily_update() (max_stories=25 incremental).
    """
    pipeline = NewsPipeline(CSV_PATH)
    existing_links = pipeline.get_existing_links()
    session = curl_requests.Session()

    all_new_rows: list[dict] = []
    results: list[tuple[str, str, int]] = []  # (name, strategy, count)

    for outlet in HARD_OUTLETS:
        if outlet.get("skip"):
            reason = outlet.get("skip_reason", "no reason given")
            logging.info("Skipping %s (%s)", outlet["name"], reason)
            results.append((outlet["name"], "skipped", 0))
            continue

        logging.info("=" * 60)
        logging.info("Processing: %s (%s)", outlet["name"], outlet["url"])

        strategy = "failed"
        stories: Optional[list[dict]] = None

        stories = try_wordpress_api(outlet, session, max_stories)
        if stories:
            logging.info("  WordPress API: %d stories", len(stories))
            strategy = "wp_api"
        else:
            logging.info("  WordPress API: unavailable")
            stories = try_sitemap(outlet, session, max_stories)
            if stories:
                logging.info("  Sitemap+curl_cffi: %d stories", len(stories))
                strategy = "sitemap"
            else:
                logging.info("  Sitemap: unavailable")

        added = 0
        if stories:
            rows = prepare_rows(outlet, stories, existing_links)
            all_new_rows.extend(rows)
            added = len(rows)
            logging.info("  Added %d new rows (%d duplicates filtered)", added, len(stories) - added)

        results.append((outlet["name"], strategy, added))

    if all_new_rows:
        logging.info("Appending %d new rows to %s...", len(all_new_rows), CSV_PATH)
        pipeline._append_rows_atomic(all_new_rows)
        logging.info("Backfilling keyword/sentiment metadata...")
        pipeline.enrich_missing_metadata()

    # Summary
    wp_count = sum(1 for r in results if r[1] == "wp_api")
    sitemap_count = sum(1 for r in results if r[1] == "sitemap")
    failed_count = sum(1 for r in results if r[1] == "failed")
    skipped_count = sum(1 for r in results if r[1] == "skipped")
    total_stories = sum(r[2] for r in results)

    logging.info("=" * 60)
    logging.info("HARD-OUTLETS CASCADE SUMMARY")
    logging.info("=" * 60)
    logging.info("Outlets attempted:                       %d", len(results) - skipped_count)
    logging.info("  Recovered via WordPress API:           %d", wp_count)
    logging.info("  Recovered via Sitemap+curl_cffi:       %d", sitemap_count)
    logging.info("  Failed:                                %d", failed_count)
    logging.info("Outlets skipped (known failures):        %d", skipped_count)
    logging.info("Total new stories added:                 %d", total_stories)
    logging.info("")
    logging.info("Per-outlet results:")
    for name, strategy, count in results:
        logging.info("  %-40s  %-10s  %d stories", name, strategy, count)

    return {
        "attempted": len(results) - skipped_count,
        "wp_api": wp_count,
        "sitemap": sitemap_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "total_new_stories": total_stories,
        "per_outlet": results,
    }


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )
    process_outlets(max_stories=DEFAULT_MAX_STORIES_PER_OUTLET)


if __name__ == "__main__":
    main()
