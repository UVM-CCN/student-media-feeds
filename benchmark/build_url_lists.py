"""Build website-URL lists for benchmarking against another scraper.

Produces two lists:
  A. candidates  - every site we monitor, whether or not it ever returned a story
  B. productive  - only sites that actually yielded stories in our corpus
"""
import csv
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.dirname(os.path.abspath(__file__))

TXT_LISTS = [
    "feeds_student_media_outlets.txt",
    "feeds_top_student_newspapers.txt",
    "feeds_news_labs.txt",
    "extra_urls.txt",
]

# Trailing path segments that mark a feed rather than a site.
FEED_TAIL = re.compile(
    r"/(feed|feeds|rss|rss\.xml|atom|atom\.xml|index\.xml|feed\.xml|rss2|"
    r"front-page/feed|posts/default|\?feed=\w+)/?$",
    re.I,
)


# Navigational paths left behind by feed-URL stripping; they are not outlet homes.
GENERIC_PATH = re.compile(
    r"^/(search|home|news|contact|about|blog|articles?|stories|category/.*|"
    r"author/.*|tag/.*|section/.*|index\.\w+|.*\.xml)$",
    re.I,
)
# Hosts that serve many separate outlets, where the path IS the outlet identity.
MULTI_TENANT = re.compile(
    r"(^|\.)(blogs?|sites)\.|wixsite\.com|wordpress\.com|blogspot\.com|"
    r"weebly\.com|squarespace\.com|medium\.com",
    re.I,
)


def site_root(url: str) -> str | None:
    """Reduce a feed URL to the site it belongs to."""
    url = url.strip()
    if not url or url.startswith("#"):
        return None
    if "feedly.com/web/" in url.lower():
        return None  # placeholder, never resolvable
    p = urlparse(url)
    if not p.scheme.startswith("http") or not p.netloc:
        return None

    host = p.netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]

    path = p.path
    # strip repeated feed markers (e.g. /blogs/x/front-page/feed/)
    prev = None
    while prev != path:
        prev = path
        path = FEED_TAIL.sub("", path)
    path = path.rstrip("/")

    # Keep a path only where it identifies the outlet, not a nav page.
    if path and (GENERIC_PATH.match(path) or not MULTI_TENANT.search(host)):
        # a non-multi-tenant host with a deep path is almost always over-specific
        if GENERIC_PATH.match(path) or path.count("/") > 1:
            path = ""

    return f"https://{host}{path}"


def collect_candidates() -> dict[str, set[str]]:
    """site_root -> set of origin list names"""
    out: dict[str, set[str]] = {}

    def add(u, origin):
        s = site_root(u)
        if s:
            out.setdefault(s, set()).add(origin)

    for name in TXT_LISTS:
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                add(line, name)

    opml = os.path.join(ROOT, "feeds", "feedly-export-20260130.opml")
    if os.path.exists(opml):
        for outline in ET.parse(opml).getroot().iter("outline"):
            add(outline.get("xmlUrl", ""), "feedly-export.opml")

    master = os.path.join(ROOT, "ccn_nap_master.csv")
    if os.path.exists(master):
        with open(master, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                add(row.get("URL", ""), "ccn_nap_master.csv")

    return out


def collect_productive() -> list[tuple[str, str, int]]:
    """(site_root, publication name, story count) for sites that produced stories."""
    import pandas as pd

    n = pd.read_csv(os.path.join(ROOT, "news_database.csv"))
    per_site: dict[str, Counter] = {}
    for src, link in zip(n["source"], n["link"]):
        p = urlparse(str(link))
        if not p.netloc:
            continue
        host = p.netloc.lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        root = f"https://{host}"
        per_site.setdefault(root, Counter())[str(src)] += 1

    rows = []
    for root, names in per_site.items():
        rows.append((root, names.most_common(1)[0][0], sum(names.values())))
    rows.sort(key=lambda r: -r[2])
    return rows


def write_plain(path, urls):
    with open(path, "w") as f:
        f.write("\n".join(urls) + "\n")


def main():
    cand = collect_candidates()
    prod = collect_productive()
    prod_roots = {r[0] for r in prod}

    write_plain(os.path.join(OUT, "sites_all.txt"),
                sorted(set(cand) | {r[0] for r in prod}))

    with open(os.path.join(OUT, "sites_productive.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site_url", "publication", "stories_in_our_corpus"])
        w.writerows(prod)
    write_plain(os.path.join(OUT, "sites_productive.txt"), [r[0] for r in prod])

    overlap = len(prod_roots & set(cand))
    print(f"candidate sites (deduplicated):     {len(cand)}")
    print(f"productive sites (yielded stories): {len(prod)}")
    print(f"  of which appear in candidates:    {overlap}")
    print(f"  not traceable to a monitored list:{len(prod) - overlap}")
    print()
    print("candidates by origin list:")
    origin = Counter()
    for origins in cand.values():
        for o in origins:
            origin[o] += 1
    for o, c in origin.most_common():
        print(f"  {c:>5}  {o}")
    print()
    print("sample candidate URLs:")
    for u in sorted(cand)[:6]:
        print("  ", u)


if __name__ == "__main__":
    main()
