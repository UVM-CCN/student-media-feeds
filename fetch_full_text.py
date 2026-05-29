"""
Full-text article extractor.

Fetches the HTML page at each story's `link`, extracts the article body using
trafilatura, and stores it as a .txt file in
`full_text/<first-2-chars-of-hash>/<sha1-hash>.txt`.

Designed as a single idempotent function:

    process_pending_stories()

It can be called two ways:

1. **One-time historical backfill** — run directly:
       python fetch_full_text.py
   It will iterate the entire news_database.csv and fetch full text for any
   story that hasn't been processed yet. Safe to interrupt and re-run.

2. **Daily incremental run** — imported from scrape.py and called at the end
   of `run_daily_update()`. New stories added by the nightly scrape have an
   empty `extraction_status` and will be picked up automatically.

State tracking lives in a new `extraction_status` column on news_database.csv:
    ""        — not yet attempted (will be processed)
    "ok"      — extracted successfully (skipped on future runs)
    "empty"   — fetched but extractor returned nothing
                (paywall, JS-rendered, very short page) — skipped on future runs
    "http_404", "http_403", "http_410" — terminal client errors, skipped
    "http_429", "http_5xx", "timeout", "error" — transient, retried next run

Politeness defaults are conservative because we run against ~100 small student
news sites that may not tolerate aggressive crawling:
    - Per-domain minimum delay of 2s + jitter
    - Hard 30s request timeout
    - Up to 3 retries with exponential backoff
    - Honors Retry-After header on 429s
    - Identifies the bot in User-Agent
"""

import csv
import datetime
import hashlib
import logging
import os
import random
import sys
import time
import urllib.parse
from typing import Optional

import requests
import trafilatura


FULL_TEXT_DIR = "full_text"
LOG_FILE = "full_text_scrape.log"
USER_AGENT = (
    "StudentMediaFeedsBot/1.0 (academic research; "
    "+https://github.com/UVM-CCN/student-media-feeds)"
)

MIN_DOMAIN_DELAY_SECONDS = 2.0
DOMAIN_JITTER_RANGE = (0.5, 1.5)
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
CHECKPOINT_INTERVAL = 25  # save CSV progress every N stories during backfill

# Statuses we consider "done" — never retry these
TERMINAL_STATUSES = {"ok", "empty", "http_404", "http_403", "http_410"}

# Tracks the last request time per hostname so we can throttle politely.
# Module-level so it persists across calls within a single Python process.
_last_request_by_domain: dict[str, float] = {}


def url_to_path(url: str) -> str:
    """Map a story URL to a sharded .txt file path."""
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return os.path.join(FULL_TEXT_DIR, h[:2], f"{h}.txt")


def _get_domain(url: str) -> str:
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def _throttle_for_domain(domain: str) -> None:
    """Block until enough time has elapsed since the last request to this domain."""
    if not domain:
        return
    now = time.time()
    elapsed = now - _last_request_by_domain.get(domain, 0.0)
    if elapsed < MIN_DOMAIN_DELAY_SECONDS:
        wait = MIN_DOMAIN_DELAY_SECONDS - elapsed + random.uniform(*DOMAIN_JITTER_RANGE)
        time.sleep(wait)
    _last_request_by_domain[domain] = time.time()


def _fetch_html(url: str) -> tuple[Optional[str], str]:
    """
    Fetch HTML with retries and per-domain throttling.
    Returns (html_or_none, status_label). status_label is "ok" on success or
    one of the failure labels documented in the module docstring.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    domain = _get_domain(url)

    for attempt in range(MAX_RETRIES):
        _throttle_for_domain(domain)
        try:
            r = requests.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=True,
            )
        except requests.exceptions.Timeout:
            logging.warning("Timeout for %s (attempt %d/%d)", url, attempt + 1, MAX_RETRIES)
            if attempt == MAX_RETRIES - 1:
                return None, "timeout"
            time.sleep(2 ** attempt)
            continue
        except requests.exceptions.RequestException as e:
            logging.warning("Request error for %s: %s (attempt %d/%d)", url, e, attempt + 1, MAX_RETRIES)
            if attempt == MAX_RETRIES - 1:
                return None, "error"
            time.sleep(2 ** attempt)
            continue

        status = r.status_code

        if status == 200:
            return r.text, "ok"
        if status in (404, 403, 410):
            return None, f"http_{status}"
        if status == 429:
            try:
                wait = int(r.headers.get("Retry-After", 2 ** attempt * 5))
            except (TypeError, ValueError):
                wait = 2 ** attempt * 5
            logging.warning("429 for %s; sleeping %ds then retrying", url, wait)
            time.sleep(wait)
            if attempt == MAX_RETRIES - 1:
                return None, "http_429"
            continue
        if 500 <= status < 600:
            wait = 2 ** attempt + random.uniform(0, 1)
            logging.warning("HTTP %d for %s; retry in %.1fs", status, url, wait)
            time.sleep(wait)
            if attempt == MAX_RETRIES - 1:
                return None, "http_5xx"
            continue

        # Any other HTTP status — record it and stop retrying
        return None, f"http_{status}"

    return None, "error"


def _extract_article(html: str, url: str) -> Optional[str]:
    """
    Extract the article body from raw HTML. Returns the text or None if
    trafilatura could not find article content (typical for JS-rendered pages
    or paywalled stubs).
    """
    try:
        text = trafilatura.extract(
            html,
            url=url,
            favor_recall=True,
            include_comments=False,
            include_tables=False,
        )
    except Exception as e:
        logging.warning("trafilatura error for %s: %s", url, e)
        return None

    if not text:
        return None
    stripped = text.strip()
    return stripped if stripped else None


def _write_article_file(url: str, story: dict, text: str) -> str:
    """Write the extracted text with a small metadata header. Returns the file path."""
    path = url_to_path(url)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    extracted_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    header = (
        f"# Title: {story.get('title', '')}\n"
        f"# URL: {url}\n"
        f"# Source: {story.get('source', '')}\n"
        f"# Published: {story.get('published', '')}\n"
        f"# Extracted: {extracted_at}\n"
        f"# ---\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(text)
    return path


def _process_story(story: dict) -> str:
    """
    Fetch + extract a single story. Returns the new extraction_status.
    Does not mutate the row; caller is responsible for writing it back.
    """
    url = (story.get("link") or "").strip()
    if not url:
        return "no_url"

    # If the .txt file already exists, treat as already done — avoids re-fetching
    # if the CSV column was reset or lost.
    if os.path.exists(url_to_path(url)):
        return "ok"

    html, fetch_status = _fetch_html(url)
    if fetch_status != "ok":
        logging.warning("Fetch failed for %s: %s", url, fetch_status)
        return fetch_status

    text = _extract_article(html, url)
    if not text:
        logging.info("Extractor returned empty for %s", url)
        return "empty"

    _write_article_file(url, story, text)
    logging.info("Extracted %d words from %s", len(text.split()), url)
    return "ok"


def _read_csv(csv_path: str) -> tuple[list[str], list[dict]]:
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    return fieldnames, rows


def _write_csv_atomic(csv_path: str, fieldnames: list[str], rows: list[dict]) -> None:
    tmp = csv_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({fn: row.get(fn, "") for fn in fieldnames})
    os.replace(tmp, csv_path)


def process_pending_stories(csv_path: str = "news_database.csv") -> dict:
    """
    Iterate the CSV and fetch full text for any story not yet successfully
    processed. Idempotent and safe to interrupt: progress is checkpointed to
    disk every CHECKPOINT_INTERVAL stories.

    Returns a dict of counts: processed, ok, failed, skipped, total.
    """
    if not os.path.exists(csv_path):
        logging.error("CSV not found: %s", csv_path)
        return {"processed": 0, "ok": 0, "failed": 0, "skipped": 0, "total": 0}

    fieldnames, rows = _read_csv(csv_path)

    # Ensure the status column exists in the on-disk schema
    if "extraction_status" not in fieldnames:
        fieldnames.append("extraction_status")
        for row in rows:
            row.setdefault("extraction_status", "")

    total = len(rows)
    counts = {"processed": 0, "ok": 0, "failed": 0, "skipped": 0, "total": total}
    pending_indexes = [
        i for i, row in enumerate(rows)
        if (row.get("extraction_status") or "").strip() not in TERMINAL_STATUSES
    ]
    counts["skipped"] = total - len(pending_indexes)

    if not pending_indexes:
        logging.info("No pending stories. Total in DB: %d", total)
        return counts

    logging.info(
        "Starting full-text extraction. pending=%d already_done=%d total=%d",
        len(pending_indexes), counts["skipped"], total,
    )

    for n, i in enumerate(pending_indexes, 1):
        row = rows[i]
        logging.info("[%d/%d] %s", n, len(pending_indexes), row.get("link", ""))
        status = _process_story(row)
        row["extraction_status"] = status
        counts["processed"] += 1
        if status == "ok":
            counts["ok"] += 1
        else:
            counts["failed"] += 1

        if n % CHECKPOINT_INTERVAL == 0:
            _write_csv_atomic(csv_path, fieldnames, rows)
            logging.info(
                "Checkpoint: processed=%d ok=%d failed=%d",
                counts["processed"], counts["ok"], counts["failed"],
            )

    _write_csv_atomic(csv_path, fieldnames, rows)
    logging.info(
        "Done. processed=%d ok=%d failed=%d skipped=%d total=%d",
        counts["processed"], counts["ok"], counts["failed"], counts["skipped"], total,
    )
    return counts


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    _configure_logging()
    process_pending_stories()


if __name__ == "__main__":
    main()
