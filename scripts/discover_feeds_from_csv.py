"""
Generic feed-discovery script: given a CSV with a URL column, probe each URL
for an RSS/Atom feed and write the discovered feed URLs to an output .txt file.

Usage:
    python scripts/discover_feeds_from_csv.py <csv_path> <url_column> <output_txt>

Example:
    python scripts/discover_feeds_from_csv.py \\
        "new-data-to-add/News Lab URLs for RSS feeds - June 12, 2026 - News Labs.csv" \\
        "Official Web Link" \\
        feeds_news_labs.txt

Behavior:
- Loads every URL already tracked (OPML feeds in feeds/, plus any *.txt feed lists
  in the project root) and skips outlets whose domain is already covered.
- Skips unsuitable domains (social media, university dept pages, etc.).
- For each candidate URL, in order:
    1. Check if the URL itself is already a feed
    2. Autodiscover via <link rel="alternate"> in HTML <head>
    3. Try common feed paths (/feed/, /rss, etc.)
- Adds a short delay between outlets to be polite.
- Writes one feed URL per line to the output file. Existing file is overwritten.
- Prints a summary at the end listing outlets where no feed could be found.
"""
import csv
import os
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from feed_discoverer import discover_feeds_from_url, is_valid_feed, try_common_feed_paths

# Domains that will never have scrapeable RSS feeds for student journalism
SKIP_DOMAINS = {
    "youtube.com", "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "wakelet.com", "substack.com", "x.com", "tiktok.com",
}

# URL path fragments that signal a university dept page rather than a publication
SKIP_PATH_FRAGMENTS = [
    "/academics/", "/programs/", "/undergraduate/", "/departments/",
    "/college-of-", "/school-of-", "/scripps-college/",
]

# Delay between outlets so we don't hammer any single discovery target
SLEEP_BETWEEN_OUTLETS = 1.5


def load_existing_domains(project_root: str) -> set[str]:
    """Collect domains we already track via OPML or .txt feed lists."""
    domains: set[str] = set()

    opml_dir = os.path.join(project_root, "feeds")
    if os.path.isdir(opml_dir):
        for fname in os.listdir(opml_dir):
            if not fname.lower().endswith(".opml"):
                continue
            try:
                tree = ET.parse(os.path.join(opml_dir, fname))
            except ET.ParseError:
                continue
            for outline in tree.getroot().iter("outline"):
                for attr in ("htmlUrl", "xmlUrl"):
                    url = outline.get(attr, "")
                    if url:
                        host = urllib.parse.urlparse(url).netloc.lower()
                        host = host[4:] if host.startswith("www.") else host
                        if host:
                            domains.add(host)

    # Pick up any .txt feed list at the project root
    for fname in os.listdir(project_root):
        if not fname.endswith(".txt"):
            continue
        if fname in ("DATA_NOTES.txt",):
            continue
        path = os.path.join(project_root, fname)
        try:
            with open(path) as f:
                for line in f:
                    url = line.strip()
                    if not url or url.startswith("#"):
                        continue
                    host = urllib.parse.urlparse(url).netloc.lower()
                    host = host[4:] if host.startswith("www.") else host
                    if host:
                        domains.add(host)
        except OSError:
            continue

    return domains


def load_existing_feed_urls(project_root: str) -> set[str]:
    """Collect feed URLs already in any .txt feed list, so we don't write duplicates."""
    urls: set[str] = set()
    for fname in os.listdir(project_root):
        if not fname.endswith(".txt") or fname == "DATA_NOTES.txt":
            continue
        try:
            with open(os.path.join(project_root, fname)) as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith("#"):
                        urls.add(url)
        except OSError:
            continue
    return urls


def split_multi_url(raw: str) -> list[str]:
    """A URL field may contain multiple URLs separated by ' or ', ';', or ','."""
    if not raw:
        return []
    parts = re.split(r"\s+or\s+|;\s*", raw, flags=re.IGNORECASE)
    cleaned = []
    for p in parts:
        p = p.strip().strip(",").strip()
        if p and p.lower().startswith(("http://", "https://")):
            cleaned.append(p)
    return cleaned


def should_skip(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    domain = domain[4:] if domain.startswith("www.") else domain

    if any(domain.endswith(d) for d in SKIP_DOMAINS):
        return True

    path = parsed.path.lower()
    if any(frag in path for frag in SKIP_PATH_FRAGMENTS):
        return True

    return False


def is_noise_feed(url: str) -> bool:
    """Filter out feeds that aren't article content or are format-duplicates."""
    lower = url.lower()
    # WordPress comments feeds — would scrape comment threads as if they were stories
    if "/comments/feed" in lower:
        return True
    # Atom/RSS duplicate variants when /feed/ already exists as the canonical form
    if lower.endswith("/feed/rss/") or lower.endswith("/feed/rss"):
        return True
    if lower.endswith("/feed/atom/") or lower.endswith("/feed/atom"):
        return True
    if "type=atom" in lower:
        return True
    # Podcast feeds — audio, not article content
    if "/feed/podcast" in lower or "/podcast/feed" in lower:
        return True
    return False


def discover_feed_for_site(site_url: str) -> list[str]:
    """Return all feeds discovered for a site (may be empty, one, or multiple)."""
    # 1. Is the URL itself a feed?
    if is_valid_feed(site_url):
        return [site_url]

    # 2. Autodiscovery
    discovered = discover_feeds_from_url(site_url)
    valid = [u for u in discovered if is_valid_feed(u) and not is_noise_feed(u)]
    if valid:
        return valid

    # 3. Common path fallback
    fallback = try_common_feed_paths(site_url)
    if fallback and not is_noise_feed(fallback):
        return [fallback]

    return []


def run(csv_path: str, url_column: str, output_path: str) -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if not os.path.exists(csv_path):
        print(f"ERROR: CSV not found: {csv_path}")
        sys.exit(1)

    print(f"Loading existing tracked domains and feeds...")
    existing_domains = load_existing_domains(project_root)
    existing_feeds = load_existing_feed_urls(project_root)
    print(f"  {len(existing_domains)} domains already tracked")
    print(f"  {len(existing_feeds)} feed URLs already in .txt lists")
    print()

    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if rows and url_column not in rows[0]:
        print(f"ERROR: Column '{url_column}' not found in CSV. Available columns:")
        for col in rows[0]:
            print(f"  - {col}")
        sys.exit(1)

    candidates: list[tuple[str, str]] = []
    skipped_no_url = 0
    skipped_tracked = 0
    skipped_unsuitable = 0
    seen_urls: set[str] = set()

    for row in rows:
        raw_url = (row.get(url_column) or "").strip()
        urls = split_multi_url(raw_url)
        if not urls:
            skipped_no_url += 1
            continue

        name = (
            row.get("Newspaper Name")
            or row.get("Name of News Lab")
            or row.get("Name of Outlet")
            or row.get("NAME OF PROGRAM")
            or row.get("name")
            or ""
        ).strip()

        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            domain = urllib.parse.urlparse(url).netloc.lower()
            domain = domain[4:] if domain.startswith("www.") else domain

            if domain in existing_domains:
                skipped_tracked += 1
                continue

            if should_skip(url):
                print(f"  [SKIP unsuitable] {url}")
                skipped_unsuitable += 1
                continue

            candidates.append((name or domain, url))

    print(f"Candidates to probe: {len(candidates)}")
    print(f"Skipped (no URL):           {skipped_no_url}")
    print(f"Skipped (already tracked):  {skipped_tracked}")
    print(f"Skipped (unsuitable):       {skipped_unsuitable}")
    print()

    found: list[tuple[str, str]] = []  # (name, feed_url)
    unfound: list[tuple[str, str]] = []  # (name, site_url)

    for i, (name, site_url) in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] {name}")
        print(f"  Probing: {site_url}")

        try:
            feeds = discover_feed_for_site(site_url)
        except Exception as e:
            print(f"  [ERROR] {e}")
            unfound.append((name, site_url))
            time.sleep(SLEEP_BETWEEN_OUTLETS)
            continue

        if feeds:
            for feed_url in feeds:
                if feed_url in existing_feeds:
                    print(f"  [DUPLICATE] {feed_url}")
                    continue
                print(f"  [FOUND] {feed_url}")
                found.append((name, feed_url))
                existing_feeds.add(feed_url)
        else:
            print(f"  [NOT FOUND]")
            unfound.append((name, site_url))

        time.sleep(SLEEP_BETWEEN_OUTLETS)

    # Preserve any existing entries in the output file so re-runs are additive
    existing_lines: list[str] = []
    if os.path.exists(output_path):
        with open(output_path) as f:
            existing_lines = [line.rstrip("\n") for line in f]

    new_lines = []
    for name, url in found:
        new_lines.append(f"# {name}")
        new_lines.append(url)

    if not existing_lines and not new_lines:
        print()
        print(f"No new feeds found. Nothing written to {output_path}")
    else:
        with open(output_path, "w") as f:
            if existing_lines:
                for line in existing_lines:
                    f.write(line + "\n")
            else:
                f.write(f"# Feeds discovered from {os.path.basename(csv_path)}\n")
            for line in new_lines:
                f.write(line + "\n")
        print()
        if found:
            print(f"Appended {len(found)} new feed URLs to {output_path}")
        else:
            print(f"No new feeds this run; {output_path} unchanged")

    print()
    print("=" * 60)
    print(f"Discovery complete")
    print(f"  New feeds found:        {len(found)}")
    print(f"  Outlets with no feed:   {len(unfound)}")
    if unfound:
        print()
        print(f"No feed found for:")
        for name, url in unfound:
            print(f"  {name} | {url}")
    print("=" * 60)


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    csv_path = sys.argv[1]
    url_column = sys.argv[2]
    output_path = sys.argv[3]
    run(csv_path, url_column, output_path)


if __name__ == "__main__":
    main()
