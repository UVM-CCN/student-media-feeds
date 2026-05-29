import logging
import urllib.parse
import xml.etree.ElementTree as ET
import requests
import feedparser
import os
import re
import pandas as pd
from bs4 import BeautifulSoup
from typing import List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Common RSS path suffixes to probe when autodiscovery finds nothing
_COMMON_FEED_PATHS = [
    "/feed/",
    "/feed",
    "/rss/",
    "/rss",
    "/rss.xml",
    "/?feed=rss2",
    "/feed/rss/",
    "/news/feed/",
    "/articles.rss",
    "/index.xml",
]


def is_broken_feed_url(url: str) -> bool:
    """Returns True for Feedly internal proxy URLs that cannot be fetched directly."""
    return bool(re.search(r"feedly\.com/web/", url or "", re.IGNORECASE))


def is_valid_feed(url: str, timeout: int = 10) -> bool:
    """Checks if a URL responds with a parseable RSS/Atom feed that has at least one entry."""
    try:
        headers = {"User-Agent": "StudentMediaFeedsBot/1.0 (+https://github.com/)"}
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        return len(feed.entries) > 0
    except Exception:
        return False


def discover_feeds_from_url(url: str) -> List[str]:
    """
    Scans a website's HTML <head> for RSS/Atom feed links advertised via
    <link rel="alternate" type="application/rss+xml"> (and similar).
    """
    discovered = []
    headers = {"User-Agent": "Mozilla/5.0 (StudentMediaFeedsBot)"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        feed_types = {
            "application/rss+xml",
            "application/atom+xml",
            "application/rdf+xml",
            "text/xml",
        }

        for link in soup.find_all("link", rel="alternate"):
            if link.get("type") in feed_types:
                href = link.get("href")
                if href:
                    discovered.append(urllib.parse.urljoin(url, href))

    except Exception as e:
        logging.warning("Autodiscovery failed for %s: %s", url, e)

    return list(dict.fromkeys(discovered))  # deduplicate, preserve order


def try_common_feed_paths(site_url: str) -> Optional[str]:
    """
    Probes common RSS path suffixes on the site's root domain.
    Returns the first URL that responds as a valid feed, or None.
    """
    parsed = urllib.parse.urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    for path in _COMMON_FEED_PATHS:
        candidate = root + path
        logging.info("  Trying fallback: %s", candidate)
        if is_valid_feed(candidate):
            return candidate

    return None


def find_replacement_feed(html_url: str) -> Optional[str]:
    """
    Best-effort strategy to find a working RSS feed for a site:
    1. Try autodiscovery via <link rel="alternate"> in the page HTML.
    2. Validate each discovered URL.
    3. Fall back to probing common /feed/, /rss, etc. paths.
    Returns the first working feed URL found, or None.
    """
    logging.info("  Autodiscovering from: %s", html_url)
    candidates = discover_feeds_from_url(html_url)
    for candidate in candidates:
        logging.info("  Validating discovered URL: %s", candidate)
        if is_valid_feed(candidate):
            return candidate

    logging.info("  Autodiscovery found nothing valid; trying common path patterns...")
    return try_common_feed_paths(html_url)


def repair_opml(input_path: str, output_path: Optional[str] = None) -> str:
    """
    Reads an OPML file, replaces broken Feedly proxy xmlUrl values with real
    RSS feed URLs discovered from each entry's htmlUrl, and writes a corrected
    OPML file.

    Args:
        input_path:  Path to the source .opml file.
        output_path: Path for the repaired file. Defaults to
                     <stem>-repaired.opml in the same directory.

    Returns:
        Path to the written output file.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"OPML file not found: {input_path}")

    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}-repaired{ext}"

    # Parse while preserving the original XML structure
    ET.register_namespace("", "")
    tree = ET.parse(input_path)
    root = tree.getroot()

    broken: list[dict] = []
    fixed: list[dict] = []
    unfixed: list[dict] = []

    # Walk every <outline> element regardless of nesting depth
    for outline in root.iter("outline"):
        xml_url = outline.get("xmlUrl", "")
        html_url = outline.get("htmlUrl", "")
        title = outline.get("title") or outline.get("text", xml_url)

        if not is_broken_feed_url(xml_url):
            continue

        broken.append({"title": title, "broken_url": xml_url, "html_url": html_url})
        logging.info("[BROKEN] %s  (%s)", title, xml_url)

        if not html_url:
            logging.warning("  No htmlUrl for '%s'; cannot autodiscover.", title)
            unfixed.append({"title": title, "broken_url": xml_url, "html_url": html_url, "replacement": None})
            continue

        replacement = find_replacement_feed(html_url)

        if replacement:
            logging.info("  [FIXED] %s -> %s", title, replacement)
            outline.set("xmlUrl", replacement)
            fixed.append({"title": title, "broken_url": xml_url, "replacement": replacement})
        else:
            logging.warning("  [UNFIXED] No feed found for '%s' (%s)", title, html_url)
            unfixed.append({"title": title, "broken_url": xml_url, "html_url": html_url, "replacement": None})

    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    # Summary
    print("\n" + "=" * 60)
    print(f"OPML Repair Summary")
    print(f"  Input:   {input_path}")
    print(f"  Output:  {output_path}")
    print(f"  Broken feeds found:  {len(broken)}")
    print(f"  Successfully fixed:  {len(fixed)}")
    print(f"  Still unresolved:    {len(unfixed)}")

    if fixed:
        print("\nFixed:")
        for item in fixed:
            print(f"  [{item['title']}]")
            print(f"    was:  {item['broken_url']}")
            print(f"    now:  {item['replacement']}")

    if unfixed:
        print("\nNeeds manual attention:")
        for item in unfixed:
            print(f"  [{item['title']}]")
            print(f"    broken URL: {item['broken_url']}")
            if item.get("html_url"):
                print(f"    website:    {item['html_url']}")
    print("=" * 60 + "\n")

    return output_path


def update_static_feed_list_from_csv(csv_path: str, url_column: str, storage_path: str):
    """
    Reads a CSV using pandas, extracts URLs from a specific column,
    finds their feeds, and appends unique new feeds to a static text file.
    """
    if not os.path.exists(csv_path):
        logging.error("CSV file not found: %s", csv_path)
        return

    try:
        df = pd.read_csv(csv_path)
        if url_column not in df.columns:
            logging.error("Column '%s' not found in %s", url_column, csv_path)
            return
        source_urls = df[url_column].dropna().unique().tolist()
        logging.info("Loaded %d unique URLs from %s", len(source_urls), csv_path)
    except Exception as e:
        logging.error("Error reading CSV with pandas: %s", e)
        return

    existing_feeds: set[str] = set()
    if os.path.exists(storage_path):
        with open(storage_path, "r") as f:
            existing_feeds = {line.strip() for line in f if line.strip()}

    newly_found: list[str] = []
    for url in source_urls:
        url = str(url).strip()
        if not url.startswith("http"):
            continue

        logging.info("Checking %s...", url)
        if is_valid_feed(url):
            if url not in existing_feeds:
                newly_found.append(url)
        else:
            for feed_url in discover_feeds_from_url(url):
                if feed_url not in existing_feeds:
                    newly_found.append(feed_url)

    if newly_found:
        with open(storage_path, "a") as f:
            for feed in newly_found:
                f.write(f"{feed}\n")
        logging.info("Added %d new feeds to %s", len(newly_found), storage_path)
    else:
        logging.info("No new feeds discovered.")


if __name__ == "__main__":
    import sys
    import glob

    if len(sys.argv) >= 2 and sys.argv[1] == "repair":
        # Usage: python feed_discoverer.py repair [path/to/file.opml]
        if len(sys.argv) >= 3:
            opml_path = sys.argv[2]
        else:
            # Default: first .opml found in feeds/
            candidates = sorted(glob.glob("feeds/*.opml"))
            if not candidates:
                print("No .opml files found in feeds/. Pass a path explicitly.")
                sys.exit(1)
            opml_path = candidates[0]
        repair_opml(opml_path)

    elif len(sys.argv) > 2:
        # Usage: python feed_discoverer.py my_data.csv url_col_name
        update_static_feed_list_from_csv(sys.argv[1], sys.argv[2], "discovered_feeds.txt")

    elif len(sys.argv) == 2:
        # Usage: python feed_discoverer.py https://example.com
        target_url = sys.argv[1]
        print(f"Discovering feeds for: {target_url}")
        print(discover_feeds_from_url(target_url))

    else:
        print("Usage:")
        print("  Repair broken OPML:  python feed_discoverer.py repair [feeds/file.opml]")
        print("  Discover from URL:   python feed_discoverer.py <url>")
        print("  Update from CSV:     python feed_discoverer.py <csv_path> <url_column>")
