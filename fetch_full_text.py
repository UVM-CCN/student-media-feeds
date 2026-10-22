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

State tracking lives in two new columns on news_database.csv:

    extraction_status:
        ""        — not yet attempted (will be processed)
        "ok"      — extracted successfully (skipped on future runs)
        "empty"   — fetched but extractor returned nothing
                    (paywall, JS-rendered, very short page) — skipped on future runs
        "http_404", "http_410" — terminal client errors, skipped
        "http_403" — transient bot/rate-limit challenge. Retried on a cooldown
                    (see MAX_HTTP_403_ATTEMPTS / HTTP_403_COOLDOWN_HOURS), not
                    treated as final.
        "http_429", "http_5xx", "timeout", "error" — transient, retried next run

    extraction_attempts / extraction_attempted_at:
        How many fetch attempts a row has had and when the last one happened.
        Only used to pace retries of 403s; success still clears the status to
        "ok" and needs no history.

    full_text_path:
        Relative path to the .txt file (e.g. "full_text/ab/abcdef...txt") when
        extraction_status == "ok", else empty. Lets you join stories to their
        text directly in pandas without knowing the hashing scheme.

Politeness defaults are conservative because we run against ~100 small student
news sites that may not tolerate aggressive crawling:
    - Per-domain minimum delay of 2s + jitter (overridable for sites that ask
      for a longer Crawl-delay; see --delay)
    - Hard 30s request timeout
    - Up to 3 retries with exponential backoff
    - Honors Retry-After header on 429s
    - Identifies the bot in User-Agent, but uses a browser TLS fingerprint
      (curl_cffi) because several hosts block the plain requests fingerprint
      with a 403 regardless of User-Agent.
"""

import csv
import datetime
import hashlib
import logging
import os
import random
import sys
import threading
import time
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

import requests
import trafilatura

from http_compat import user_agent_for

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pip install curl_cffi; requirements.txt includes it
    curl_requests = None


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
IMPERSONATE_PROFILE = "chrome120"  # curl_cffi browser TLS fingerprint

# Domains are fetched in parallel, but each domain is handled by exactly one
# worker so MIN_DOMAIN_DELAY_SECONDS still serializes requests to any single
# host. Politeness per host is unchanged; only cross-host idle time is reclaimed.
MAX_WORKERS = 8

# A host that fails this many times in a row is almost always broken for every
# URL on it (expired cert, blanket rate-limit, dead domain) rather than
# story-by-story. Once the breaker opens, the rest of that host's queue is left
# untouched — status stays blank, so the next run retries it from scratch.
DOMAIN_FAILURE_THRESHOLD = 8

# Retry-After is advisory and some hosts return absurd values. Honor it, but
# never let one story park a worker for minutes.
MAX_RETRY_AFTER_SECONDS = 60

# Statuses we consider "done" — never retry these.
#
# 403 is deliberately absent. Cloudflare and similar edges return 403 to
# datacenter IPs and to request patterns they dislike, then serve the same URL
# normally later. Treating it as terminal is what left 203 College Heights
# Herald stories unextracted for two months while the article pages were
# reachable the whole time. It is retried on a cooldown instead.
TERMINAL_STATUSES = {"ok", "empty", "http_404", "http_410"}

# A 403 is retried at most this many times, one cooldown apart. Six weeks of
# retries is enough to ride out a block or a bad deploy; after that the host is
# assumed to reject this pipeline and the row stops consuming a slot.
MAX_HTTP_403_ATTEMPTS = 6
HTTP_403_COOLDOWN_HOURS = 24 * 7

# Bookkeeping columns written alongside extraction_status/full_text_path.
ATTEMPT_COLUMNS = ("extraction_attempts", "extraction_attempted_at")

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


def _throttle_for_domain(domain: str, min_delay: Optional[float] = None) -> None:
    """Block until enough time has elapsed since the last request to this domain."""
    if not domain:
        return
    delay = MIN_DOMAIN_DELAY_SECONDS if min_delay is None else min_delay
    now = time.time()
    elapsed = now - _last_request_by_domain.get(domain, 0.0)
    if elapsed < delay:
        wait = delay - elapsed + random.uniform(*DOMAIN_JITTER_RANGE)
        time.sleep(wait)
    _last_request_by_domain[domain] = time.time()


def _is_timeout(exc: Exception) -> bool:
    """True for both requests and curl_cffi timeout classes."""
    return "timeout" in type(exc).__name__.lower() or "timed out" in str(exc).lower()


def _fetch_html(url: str, domain_delay: Optional[float] = None) -> tuple[Optional[str], str]:
    """
    Fetch HTML with retries and per-domain throttling.
    Returns (html_or_none, status_label). status_label is "ok" on success or
    one of the failure labels documented in the module docstring.
    """
    headers = {
        "User-Agent": user_agent_for(url, USER_AGENT),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    domain = _get_domain(url)

    for attempt in range(MAX_RETRIES):
        _throttle_for_domain(domain, domain_delay)
        try:
            if curl_requests is not None:
                # Browser TLS fingerprint: several outlets return 403 to the
                # plain requests/urllib3 fingerprint even with a normal UA.
                r = curl_requests.get(
                    url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    impersonate=IMPERSONATE_PROFILE,
                    allow_redirects=True,
                )
            else:
                r = requests.get(
                    url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    allow_redirects=True,
                )
        except Exception as e:  # noqa: BLE001 - both client libraries
            if _is_timeout(e):
                logging.warning("Timeout for %s (attempt %d/%d)", url, attempt + 1, MAX_RETRIES)
                if attempt == MAX_RETRIES - 1:
                    return None, "timeout"
            else:
                logging.warning("Request error for %s: %s (attempt %d/%d)", url, e, attempt + 1, MAX_RETRIES)
                if attempt == MAX_RETRIES - 1:
                    return None, "error"
            time.sleep(2 ** attempt)
            continue

        status = r.status_code

        if status == 200:
            return r.text, "ok"
        if status in (404, 403, 410):
            # One shot only: if a browser fingerprint still gets 403, the host
            # is rejecting this client and hammering it just makes that worse.
            # The caller retries it on the 403 cooldown.
            return None, f"http_{status}"
        if status == 429:
            try:
                wait = int(r.headers.get("Retry-After", 2 ** attempt * 5))
            except (TypeError, ValueError):
                wait = 2 ** attempt * 5
            wait = min(wait, MAX_RETRY_AFTER_SECONDS)
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


def _process_story(story: dict, domain_delay: Optional[float] = None) -> tuple[str, str]:
    """
    Fetch + extract a single story.
    Returns (extraction_status, full_text_path). Path is "" when status != "ok".
    Does not mutate the row; caller is responsible for writing it back.
    """
    url = (story.get("link") or "").strip()
    if not url:
        return "no_url", ""

    path = url_to_path(url)

    # If the .txt file already exists, treat as already done — avoids re-fetching
    # if the CSV column was reset or lost.
    if os.path.exists(path):
        return "ok", path

    html, fetch_status = _fetch_html(url, domain_delay)
    if fetch_status != "ok":
        logging.warning("Fetch failed for %s: %s", url, fetch_status)
        return fetch_status, ""

    text = _extract_article(html, url)
    if not text:
        logging.info("Extractor returned empty for %s", url)
        return "empty", ""

    _write_article_file(url, story, text)
    logging.info("Extracted %d words from %s", len(text.split()), url)
    return "ok", path


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


def _as_int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _parse_ts(value: Any) -> Optional[datetime.datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _is_pending(row: dict, retry_http_403: bool) -> bool:
    """
    Whether a row should be fetched in this run.

    Everything except the terminal set is pending, but a 403 is retried only
    once its cooldown has elapsed (bounded by MAX_HTTP_403_ATTEMPTS). Rows that
    failed with 403 before attempt tracking existed have no timestamp; those are
    left alone unless --retry-http-403 asks for them, so enabling the new policy
    does not re-fetch thousands of historical rows in one night.
    """
    status = (row.get("extraction_status") or "").strip()
    if status in TERMINAL_STATUSES:
        return False
    if status != "http_403":
        return True
    if _as_int(row.get("extraction_attempts")) >= MAX_HTTP_403_ATTEMPTS:
        return False
    attempted = _parse_ts(row.get("extraction_attempted_at"))
    if attempted is None:
        return retry_http_403
    age = datetime.datetime.now(datetime.timezone.utc) - attempted
    return age.total_seconds() >= HTTP_403_COOLDOWN_HOURS * 3600


def process_pending_stories(csv_path: str = "news_database.csv",
                            max_workers: int = MAX_WORKERS,
                            domain: Optional[str] = None,
                            retry_http_403: bool = False,
                            domain_delay: Optional[float] = None) -> dict:
    """
    Fetch full text for any story not yet successfully processed.

    Idempotent and safe to interrupt: progress is checkpointed to disk every
    CHECKPOINT_INTERVAL stories, and terminal statuses are never retried.

    Work is grouped by domain and the groups run concurrently. Each domain is
    owned by a single worker for the whole run, so the per-domain delay still
    serializes requests to any one host — the concurrency only reclaims the
    idle time previously spent waiting on one host while every other host sat
    untouched.

    A host that fails DOMAIN_FAILURE_THRESHOLD times in a row trips a circuit
    breaker and the rest of its queue is skipped for this run. Those rows keep
    their existing status, so the next run picks them up again. This is what
    keeps one broken host (expired cert, blanket 429) from consuming the entire
    run.

    Args:
        domain: restrict the run to one host (e.g. "wkuherald.com"). Lets one
            outlet be recovered without touching the rest of the corpus.
        retry_http_403: include rows that failed with 403 before attempt
            tracking existed. Off by default so a normal nightly does not
            re-fetch every historical 403; the cooldown covers new ones.
        domain_delay: minimum seconds between requests to one host. Set to a
            site's robots.txt Crawl-delay when it exceeds the default.

    Returns a dict of counts: processed, ok, failed, deferred, skipped, total.
    """
    if not os.path.exists(csv_path):
        logging.error("CSV not found: %s", csv_path)
        return {"processed": 0, "ok": 0, "failed": 0, "deferred": 0,
                "skipped": 0, "total": 0}

    fieldnames, rows = _read_csv(csv_path)

    # Ensure the tracking columns exist in the on-disk schema
    for col in ("extraction_status", "full_text_path", *ATTEMPT_COLUMNS):
        if col not in fieldnames:
            fieldnames.append(col)
            for row in rows:
                row.setdefault(col, "")

    total = len(rows)
    counts = {"processed": 0, "ok": 0, "failed": 0, "deferred": 0,
              "skipped": 0, "total": total}
    eligible = [i for i, row in enumerate(rows) if _is_pending(row, retry_http_403)]
    counts["skipped"] = total - len(eligible)
    pending_indexes = [
        i for i in eligible
        if not domain or _get_domain((rows[i].get("link") or "").strip()) == domain
    ]
    if domain:
        logging.info("Domain filter %s: %d of %d pending rows match",
                     domain, len(pending_indexes), len(eligible))

    if not pending_indexes:
        logging.info("No pending stories. Total in DB: %d", total)
        return counts

    by_domain: dict[str, list[int]] = defaultdict(list)
    for i in pending_indexes:
        by_domain[_get_domain((rows[i].get("link") or "").strip())].append(i)

    logging.info(
        "Starting full-text extraction. pending=%d domains=%d workers=%d "
        "already_done=%d total=%d",
        len(pending_indexes), len(by_domain), max_workers,
        counts["skipped"], total,
    )

    lock = threading.Lock()
    progress = {"done": 0}

    def run_domain(domain_name: str, indexes: list[int]) -> None:
        consecutive_failures = 0
        for position, i in enumerate(indexes):
            if consecutive_failures >= DOMAIN_FAILURE_THRESHOLD:
                remaining = len(indexes) - position
                logging.warning(
                    "Circuit breaker open for %s after %d consecutive failures; "
                    "deferring %d remaining stories to the next run",
                    domain_name, consecutive_failures, remaining,
                )
                with lock:
                    counts["deferred"] += remaining
                return

            status, path = _process_story(rows[i], domain_delay)

            with lock:
                rows[i]["extraction_status"] = status
                rows[i]["full_text_path"] = path
                if status != "ok":
                    # Stamp failed attempts so a 403 can be paced on its
                    # cooldown instead of re-fetched every run.
                    rows[i]["extraction_attempts"] = str(
                        _as_int(rows[i].get("extraction_attempts")) + 1)
                    rows[i]["extraction_attempted_at"] = datetime.datetime.now(
                        datetime.timezone.utc).isoformat()
                counts["processed"] += 1
                if status == "ok":
                    counts["ok"] += 1
                else:
                    counts["failed"] += 1
                progress["done"] += 1
                done = progress["done"]
                if done % CHECKPOINT_INTERVAL == 0:
                    _write_csv_atomic(csv_path, fieldnames, rows)
                    logging.info(
                        "[%d/%d] checkpoint: ok=%d failed=%d deferred=%d",
                        done, len(pending_indexes), counts["ok"],
                        counts["failed"], counts["deferred"],
                    )

            consecutive_failures = 0 if status == "ok" else consecutive_failures + 1

    # Largest domains first so one long queue cannot become the tail that every
    # other worker waits on.
    ordered = sorted(by_domain.items(), key=lambda kv: len(kv[1]), reverse=True)
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(run_domain, d, idx) for d, idx in ordered]
            for fut in as_completed(futures):
                exc = fut.exception()
                if exc:
                    logging.error("Domain worker failed: %s", exc)
    finally:
        # Always persist whatever finished, including on KeyboardInterrupt.
        with lock:
            _write_csv_atomic(csv_path, fieldnames, rows)

    logging.info(
        "Done. processed=%d ok=%d failed=%d deferred=%d skipped=%d total=%d",
        counts["processed"], counts["ok"], counts["failed"],
        counts["deferred"], counts["skipped"], total,
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
    import argparse

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--csv", default="news_database.csv")
    parser.add_argument("--domain",
                        help="only fetch stories whose link is on this host, "
                             "e.g. wkuherald.com")
    parser.add_argument("--retry-http-403", action="store_true",
                        help="also retry rows that failed with 403 before "
                             "attempt tracking existed")
    parser.add_argument("--delay", type=float, default=None,
                        help="minimum seconds between requests to one host "
                             "(use a site's robots.txt Crawl-delay)")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()

    _configure_logging()
    process_pending_stories(
        args.csv,
        max_workers=args.max_workers,
        domain=args.domain,
        retry_http_403=args.retry_http_403,
        domain_delay=args.delay,
    )


if __name__ == "__main__":
    main()
