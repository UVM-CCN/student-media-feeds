"""
One-off cross-reference script.

Given a CSV of student newspaper outlets (with "Name of Outlet" and
"URL of Outlet" columns), find every outlet whose domain is NOT already
covered by our scraping pipeline.

Existing coverage is derived from:
    - OPML files in feeds/
    - All *.txt feed lists in the project root (extra_urls.txt, feeds_*.txt)
    - The HARD_OUTLETS list in fetch_hard_outlets.py
    - The `link` column of news_database.csv (catches anything ever scraped,
      even if its feed config isn't there anymore)

Outputs:
    data/missing_outlets.csv  — the rows of the input CSV that we don't cover.
                                Columns: Name of Outlet, URL of Outlet,
                                College/University, State

Run:
    python scripts/find_missing_outlets.py
"""

import csv
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

INPUT_CSV = "data/student-media-outlets.csv"
OUTPUT_CSV = "data/missing_outlets.csv"
DATABASE_CSV = "news_database.csv"


def normalize_domain(url: str) -> str:
    """Lowercase, strip scheme, strip www. and trailing slash."""
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def split_multi_url(raw: str) -> list[str]:
    """A URL field might contain multiple URLs separated by ' or ', ';', or ','."""
    if not raw:
        return []
    # Some entries: "https://a.com or https://b.com"
    parts = re.split(r"\s+or\s+|;\s*", raw, flags=re.IGNORECASE)
    cleaned = []
    for p in parts:
        p = p.strip().strip(",").strip()
        if p and p.lower().startswith(("http://", "https://")):
            cleaned.append(p)
    return cleaned


def load_existing_domains(project_root: str) -> set[str]:
    """Collect every domain we already cover via OPML + .txt feed lists + HARD_OUTLETS + DB."""
    domains: set[str] = set()

    # OPML files
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
                    d = normalize_domain(url)
                    if d:
                        domains.add(d)

    # .txt feed lists at project root
    for fname in os.listdir(project_root):
        if not fname.endswith(".txt") or fname == "DATA_NOTES.txt":
            continue
        try:
            with open(os.path.join(project_root, fname)) as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith("#"):
                        d = normalize_domain(url)
                        if d:
                            domains.add(d)
        except OSError:
            continue

    # HARD_OUTLETS in fetch_hard_outlets.py
    try:
        from fetch_hard_outlets import HARD_OUTLETS
        for outlet in HARD_OUTLETS:
            d = normalize_domain(outlet.get("url", ""))
            if d:
                domains.add(d)
    except ImportError:
        pass

    # links from news_database.csv
    db_path = os.path.join(project_root, DATABASE_CSV)
    if os.path.exists(db_path):
        with open(db_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d = normalize_domain(row.get("link", ""))
                if d:
                    domains.add(d)

    return domains


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    input_path = os.path.join(project_root, INPUT_CSV)
    output_path = os.path.join(project_root, OUTPUT_CSV)

    if not os.path.exists(input_path):
        print(f"ERROR: Input CSV not found: {input_path}")
        sys.exit(1)

    print(f"Loading existing tracked domains...")
    existing = load_existing_domains(project_root)
    print(f"  {len(existing)} unique domains already in pipeline")
    print()

    with open(input_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} outlets from {INPUT_CSV}")

    # Categorize
    missing: list[dict] = []
    matched: list[tuple[dict, str]] = []  # (row, matched_domain)
    no_url: list[dict] = []
    matched_domains_seen: set[str] = set()  # for counting unique matches

    for row in rows:
        raw_url = (row.get("URL of Outlet") or "").strip()
        if not raw_url:
            no_url.append(row)
            continue

        urls = split_multi_url(raw_url)
        if not urls:
            no_url.append(row)
            continue

        # Check if ANY of the listed URLs hits an existing domain
        match: str = ""
        for url in urls:
            d = normalize_domain(url)
            if d and d in existing:
                match = d
                break

        if match:
            matched.append((row, match))
            matched_domains_seen.add(match)
        else:
            missing.append(row)

    # Write missing outlets to CSV
    output_columns = ["Name of Outlet", "URL of Outlet", "College/University", "State"]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_columns, extrasaction="ignore")
        writer.writeheader()
        for row in missing:
            writer.writerow({col: row.get(col, "") for col in output_columns})

    # Summary
    print()
    print("=" * 60)
    print("CROSS-REFERENCE SUMMARY")
    print("=" * 60)
    print(f"Total outlets in input:           {len(rows)}")
    print(f"  Already tracked (matched):      {len(matched)}")
    print(f"  Missing (not yet tracked):      {len(missing)}")
    print(f"  Skipped (no URL or invalid):    {len(no_url)}")
    print()
    print(f"Unique existing domains hit:      {len(matched_domains_seen)}")
    print()
    print(f"Output written to: {OUTPUT_CSV}")

    # Show first 10 matches and first 10 misses as a sanity check
    print()
    print("=== Sanity check: first 10 already-tracked matches ===")
    for row, d in matched[:10]:
        print(f"  {row.get('Name of Outlet','?')[:40]:40}  →  {d}")

    print()
    print("=== Sanity check: first 10 missing outlets ===")
    for row in missing[:10]:
        print(f"  {row.get('Name of Outlet','?')[:40]:40}  ({row.get('State','?')})  {row.get('URL of Outlet','')[:60]}")

    # State breakdown of missing
    state_counts: dict[str, int] = {}
    for row in missing:
        s = (row.get("State") or "").strip() or "?"
        state_counts[s] = state_counts.get(s, 0) + 1
    print()
    print("=== Missing outlets by state (top 15) ===")
    for state, count in sorted(state_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {state:5}  {count}")


if __name__ == "__main__":
    main()
