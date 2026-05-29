"""
One-off script: run feed discovery against CCN master CSV outlets
not already covered by the OPML in feeds/.

Writes newly discovered feed URLs to extra_urls.txt.
"""
import csv
import os
import sys
import urllib.parse
import xml.etree.ElementTree as ET

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from feed_discoverer import discover_feeds_from_url, is_valid_feed

# Domains that will never have scrapeable RSS feeds
SKIP_DOMAINS = {
    "youtube.com", "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "wakelet.com", "substack.com",
}

# URL fragments that indicate a university dept page rather than a publication
SKIP_PATH_FRAGMENTS = [
    "/academics/", "/programs/", "/undergraduate/", "/departments/",
    "/college-of-", "/school-of-", "/scripps-college/",
]


def load_opml_domains(opml_dir: str) -> set[str]:
    domains = set()
    for fname in os.listdir(opml_dir):
        if not fname.lower().endswith(".opml"):
            continue
        tree = ET.parse(os.path.join(opml_dir, fname))
        for outline in tree.getroot().iter("outline"):
            for attr in ("htmlUrl", "xmlUrl"):
                url = outline.get(attr, "")
                if url:
                    host = urllib.parse.urlparse(url).netloc.lstrip("www.")
                    if host:
                        domains.add(host)
    return domains


def clean_url(raw: str) -> list[str]:
    """Normalize a URL field that may be malformed or contain multiple URLs."""
    # Fix the common CSV artifact where : was replaced with ,
    raw = raw.replace("http,//", "http://").replace("https,//", "https://")

    # Split on semicolons (some entries have multiple URLs)
    parts = [p.strip() for p in raw.split(";") if p.strip()]

    cleaned = []
    for p in parts:
        if p.startswith("http"):
            cleaned.append(p)
    return cleaned


def should_skip(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lstrip("www.")

    if any(domain.endswith(d) for d in SKIP_DOMAINS):
        return True

    path = parsed.path.lower()
    if any(frag in path for frag in SKIP_PATH_FRAGMENTS):
        return True

    return False


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    opml_dir = os.path.join(base, "feeds")
    ccn_csv = os.path.join(base, "ccn_nap_master.csv")
    output_file = os.path.join(base, "extra_urls.txt")

    print("Loading existing OPML domains...")
    opml_domains = load_opml_domains(opml_dir)
    print(f"  {len(opml_domains)} domains already tracked")

    # Load existing extra_urls.txt so we don't add duplicates
    existing_feeds: set[str] = set()
    if os.path.exists(output_file):
        with open(output_file) as f:
            existing_feeds = {line.strip() for line in f if line.strip()}
    print(f"  {len(existing_feeds)} feeds already in extra_urls.txt")

    with open(ccn_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Build list of candidate URLs not already in OPML
    candidates: list[tuple[str, str]] = []  # (name, url)
    skipped_no_url = 0
    skipped_tracked = 0
    skipped_unsuitable = 0

    for row in rows:
        raw_url = row.get("URL", "").strip()
        name = row.get("NAME OF PROGRAM", "").strip()

        if not raw_url:
            skipped_no_url += 1
            continue

        urls = clean_url(raw_url)
        if not urls:
            skipped_no_url += 1
            continue

        for url in urls:
            domain = urllib.parse.urlparse(url).netloc.lstrip("www.")

            if domain in opml_domains:
                skipped_tracked += 1
                continue

            if should_skip(url):
                print(f"  [SKIP unsuitable] {name} | {url}")
                skipped_unsuitable += 1
                continue

            candidates.append((name, url))

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique_candidates: list[tuple[str, str]] = []
    for name, url in candidates:
        if url not in seen_urls:
            seen_urls.add(url)
            unique_candidates.append((name, url))

    print(f"\nCandidates to probe: {len(unique_candidates)}")
    print(f"Skipped (no URL): {skipped_no_url}")
    print(f"Skipped (already tracked): {skipped_tracked}")
    print(f"Skipped (unsuitable domain/path): {skipped_unsuitable}")
    print()

    found: list[str] = []
    unfound: list[tuple[str, str]] = []

    for i, (name, site_url) in enumerate(unique_candidates, 1):
        print(f"[{i}/{len(unique_candidates)}] {name}")
        print(f"  Probing: {site_url}")

        # First: check if the URL itself is already a valid feed
        if is_valid_feed(site_url):
            print(f"  [FEED] Site URL is itself a feed: {site_url}")
            if site_url not in existing_feeds:
                found.append(site_url)
            continue

        # Second: autodiscover via <link rel="alternate">
        discovered = discover_feeds_from_url(site_url)
        valid = [u for u in discovered if is_valid_feed(u)]

        if valid:
            for feed_url in valid:
                print(f"  [FOUND] {feed_url}")
                if feed_url not in existing_feeds:
                    found.append(feed_url)
            continue

        # Third: try common path patterns
        from feed_discoverer import try_common_feed_paths
        fallback = try_common_feed_paths(site_url)
        if fallback and fallback not in existing_feeds:
            print(f"  [FALLBACK] {fallback}")
            found.append(fallback)
            continue

        print(f"  [NOT FOUND]")
        unfound.append((name, site_url))

    # Write results
    if found:
        with open(output_file, "a") as f:
            for url in found:
                f.write(url + "\n")

    # Summary
    print("\n" + "=" * 60)
    print(f"Discovery complete")
    print(f"  New feeds found:      {len(found)}")
    print(f"  Outlets with no feed: {len(unfound)}")
    if found:
        print(f"\nAdded to {output_file}:")
        for url in found:
            print(f"  {url}")
    if unfound:
        print(f"\nNo feed found for:")
        for name, url in unfound:
            print(f"  {name} | {url}")
    print("=" * 60)


if __name__ == "__main__":
    main()
