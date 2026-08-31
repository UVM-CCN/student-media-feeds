"""
Build the pruned JSON the dashboard reads.

The prototype dashboard called Papa.parse('news_database.csv') and parsed the
entire database in the browser. That file is now ~10MB and 24,000 rows, most of
which the page never displays — full URLs, extraction bookkeeping, per-story
confidence. Every visitor downloaded all of it and parsed it on the main thread
before anything rendered.

This pre-aggregates server-side (well, build-side) into a few tens of KB.

A measurement note that shapes the output
-----------------------------------------
Story volume in this corpus rises from 529 in 2026-02 to 4,518 in 2026-08. Very
little of that is newsrooms publishing more — it is the feed list growing as
outlets were discovered and added. So raw counts over time mostly chart the
scraper's own expansion.

Coverage change therefore has to be read as each topic's SHARE of that month's
output, which is invariant to how many outlets were being collected. Counts are
emitted too, because they matter for judging whether a share is meaningful, but
share is the honest series and the dashboard should lead with it.

Months whose total falls below MIN_MONTH_STORIES are flagged `thin` so the
dashboard can de-emphasize them: a share computed over 46 stories is noise.

Usage:
    python scripts/build_dashboard_data.py
"""
import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_CSV = os.path.join(ROOT, "news_database.csv")
LABELS_JSON = os.path.join(ROOT, "data", "topic_labels.json")
LOCATIONS_CSV = os.path.join(ROOT, "data", "publication_locations.csv")
OUT_DIR = os.path.join(ROOT, "dashboard")
OUT_JSON = os.path.join(OUT_DIR, "dashboard_data.json")
OUT_JS = os.path.join(OUT_DIR, "dashboard_data.js")

# Below this many stories in a month, a topic share is too noisy to plot.
MIN_MONTH_STORIES = 200


def month_of(value: str) -> str | None:
    m = re.match(r"(\d{4})-(\d{2})", (value or "").strip())
    return f"{m.group(1)}-{m.group(2)}" if m else None


def host(url: str) -> str | None:
    if not url or not url.strip():
        return None
    h = urlparse(url.strip()).netloc.lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h or None


def load_labels() -> dict[str, str]:
    with open(LABELS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    labels = {}
    for tid, spec in data.get("topics", {}).items():
        labels[str(tid)] = (spec.get("label") or "").strip() or f"Topic {tid}"
    return labels, data.get("model_version", "")


def load_states() -> dict[str, str]:
    """domain -> state code, for the geographic rollup."""
    out = {}
    if not os.path.exists(LOCATIONS_CSV):
        return out
    with open(LOCATIONS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            state = (row.get("state") or "").strip()
            dom = (row.get("domain") or "").strip()
            if dom and state:
                out[dom] = state
    return out


def main() -> int:
    labels, model_version = load_labels()
    states_by_domain = load_states()
    keys = [f"t{t}" for t in sorted(labels, key=int)]

    with open(SOURCE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    monthly = defaultdict(Counter)      # month -> topic key -> n
    month_total = Counter()
    state_topic = defaultdict(Counter)  # state -> topic key -> n
    state_total = Counter()
    topic_total = Counter()
    publications = set()
    classified = with_text = 0
    undated = 0

    for r in rows:
        publications.add((r.get("source") or "").strip())
        if (r.get("extraction_status") or "").strip() == "ok":
            with_text += 1
        tid = (r.get("topic_id") or "").strip()
        # `published` is the story's own date, which is what "coverage over
        # time" means. It is absent or unparseable for ~6% of rows; those are
        # counted in totals but excluded from the time series rather than
        # being silently bucketed into the capture date, which would smear
        # backfilled archives into the month they happened to be scraped.
        month = month_of(r.get("published"))
        if not month:
            undated += 1
        if not tid:
            if month:
                month_total[month] += 1
            continue
        key = f"t{tid}"
        classified += 1
        topic_total[key] += 1
        if month:
            monthly[month][key] += 1
            month_total[month] += 1
        state = states_by_domain.get(host(r.get("link", "")) or "")
        if state:
            state_topic[state][key] += 1
            state_total[state] += 1

    months = sorted(monthly)

    # Default the view to the real collection window rather than the full span.
    # `published` reaches back to 2013 because some outlets were backfilled from
    # their archives, but those 100+ months hold ~1,600 stories between them
    # against ~21,000 in the last seven. Opening on the full range would show a
    # decade of near-empty axis. The whole series is still emitted -- the
    # dashboard's range control can widen to it -- this only picks the opening
    # slice: the longest run of months ending at the present that all clear
    # MIN_MONTH_STORIES.
    default_start = len(months) - 1
    while default_start > 0 and month_total[months[default_start - 1]] >= MIN_MONTH_STORIES:
        default_start -= 1

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_version": model_version,
        "topics": [{"key": k, "label": labels[k[1:]], "total": topic_total[k]}
                   for k in keys],
        "months": months,
        "default_range": [default_start, len(months) - 1],
        "series": {k: [monthly[m][k] for m in months] for k in keys},
        "month_totals": [month_total[m] for m in months],
        # Months too thin for a share to mean anything; the dashboard should
        # render these differently rather than letting them swing the chart.
        "thin_months": [m for m in months if month_total[m] < MIN_MONTH_STORIES],
        "states": sorted(
            ({"code": s, "total": state_total[s],
              "counts": {k: v for k, v in state_topic[s].items() if v}}
             for s in state_total),
            key=lambda d: -d["total"],
        ),
        "totals": {
            "stories": len(rows),
            "classified": classified,
            "with_full_text": with_text,
            "publications": len([p for p in publications if p]),
            "undated": undated,
        },
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))

    # The dashboard ships as a directory someone copies onto a server, or opens
    # locally. Browsers block fetch() of a sibling JSON file over file://, so
    # the page loads this script-tag version instead and works either way.
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("window.DASHBOARD_DATA = ")
        json.dump(data, f, separators=(",", ":"))
        f.write(";\n")

    size = os.path.getsize(OUT_JSON) / 1024
    csv_size = os.path.getsize(SOURCE_CSV) / 1024 / 1024
    print(f"wrote {os.path.relpath(OUT_JSON, ROOT)}  ({size:.0f} KB)")
    print(f"  replaces a {csv_size:.1f} MB client-side CSV parse")
    print(f"  {len(rows):,} stories, {classified:,} classified, "
          f"{data['totals']['publications']:,} publications")
    print(f"  months {months[0]} -> {months[-1]}"
          + (f", {len(data['thin_months'])} flagged thin" if data["thin_months"] else ""))
    print(f"  opens on {months[default_start]} -> {months[-1]} "
          f"({sum(month_total[m] for m in months[default_start:]):,} stories); "
          f"earlier months reachable via the range control")
    print(f"  {len(data['states'])} states")
    print(f"  {undated:,} rows have no usable published date "
          f"(excluded from the time series)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
