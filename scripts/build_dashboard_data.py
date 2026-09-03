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

Coverage change therefore has to be read as each topic's SHARE of that day's
output, which is invariant to how many outlets were being collected. Counts are
emitted too, because they matter for judging whether a share is meaningful, but
share is the honest series and the dashboard should lead with it.

Days whose total falls below MIN_DAY_STORIES are flagged `thin` so the dashboard
can de-emphasize them: a share computed over 4 stories is noise.

Why the axis is daily, and only the days that exist
---------------------------------------------------
The series is emitted per calendar day. Two consequences worth knowing:

  * Student papers publish on a school week. Median output since March 2026 runs
    ~140 stories on Tue–Thu against ~43 on Sunday, so every daily series carries
    a strong weekly sawtooth that is publishing rhythm, not coverage change.
    The dashboard offers a 7-day average for exactly this reason — a 7-day
    window is the one that cancels the cycle instead of blurring it.

  * Only days that actually hold a story are emitted, not a contiguous calendar.
    `published` reaches back to 2011 because some outlets were backfilled from
    their archives, but just 922 of those 5,611 calendar days carry anything.
    Emitting the empty 82% would quadruple the payload to describe nothing. The
    dashboard plots these on a time scale, so each day still sits at its true
    date and the gaps stay visible as gaps.

Usage:
    python scripts/build_dashboard_data.py
"""
import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_CSV = os.path.join(ROOT, "news_database.csv")
LABELS_JSON = os.path.join(ROOT, "data", "topic_labels.json")
LOCATIONS_CSV = os.path.join(ROOT, "data", "publication_locations.csv")
OUT_DIR = os.path.join(ROOT, "dashboard")
OUT_JSON = os.path.join(OUT_DIR, "dashboard_data.json")
OUT_JS = os.path.join(OUT_DIR, "dashboard_data.js")

# Below this many stories in a day, a topic share is too noisy to plot. Set
# against the weekend floor rather than the weekday median: Saturdays and
# Sundays run 43-60 stories in the dense era, and flagging every weekend as
# unreliable would gray out two days in seven of otherwise good data.
MIN_DAY_STORIES = 30

# Window used to pick the opening range. A single quiet day should not end the
# run, so the test is on a trailing 7-day average -- which is also the window
# that cancels the publish-week cycle.
DEFAULT_WINDOW = 7

# Share of the corpus a calendar year must hold to be part of the range the
# brush spans by default. RSS feeds only serve a publisher's recent items, so
# everything before the scraper started is whatever each outlet's feed happened
# to still be carrying -- 2024 is 316 stories, 2011 is 13. Those years are real
# data but they are not a sample, and spanning the brush across fifteen of them
# spends nearly all of its width on 6% of the corpus. The dashboard opens on
# the qualifying years and puts the rest behind a checkbox.
RECENT_YEAR_SHARE = 0.05


def day_of(value: str) -> str | None:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", (value or "").strip())
    return m.group(0) if m else None


def last_complete_day(today: date) -> str:
    """
    The most recent day the corpus can describe honestly: yesterday.

    Capture runs through the night and extraction trails it, so today is always
    a partial day -- a few hours of one timezone's publishing, with most of it
    not yet extracted and therefore in no topic. Plotted, that reads as a cliff
    in every series. It also drops any story a feed dated into the future.
    """
    return (today - timedelta(days=1)).isoformat()


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

    daily = defaultdict(Counter)        # day -> topic key -> n
    day_total = Counter()               # day -> every story published that day
    day_classified = Counter()          # day -> stories that carry a topic
    captured_on = Counter()             # day -> stories the pipeline ingested
    state_topic = defaultdict(Counter)  # state -> topic key -> n
    state_total = Counter()
    topic_total = Counter()
    publications = set()
    classified = with_text = 0
    undated = 0

    for r in rows:
        publications.add((r.get("source") or "").strip())
        cap = day_of(r.get("captured_at"))
        if cap:
            captured_on[cap] += 1
        if (r.get("extraction_status") or "").strip() == "ok":
            with_text += 1
        tid = (r.get("topic_id") or "").strip()
        # `published` is the story's own date, which is what "coverage over
        # time" means. It is absent or unparseable for ~6% of rows; those are
        # counted in totals but excluded from the time series rather than
        # being silently bucketed into the capture date, which would smear
        # backfilled archives into the month they happened to be scraped.
        day = day_of(r.get("published"))
        if not day:
            undated += 1
        if not tid:
            if day:
                day_total[day] += 1
            continue
        key = f"t{tid}"
        classified += 1
        topic_total[key] += 1
        if day:
            daily[day][key] += 1
            day_total[day] += 1
            day_classified[day] += 1
        state = states_by_domain.get(host(r.get("link", "")) or "")
        if state:
            state_topic[state][key] += 1
            state_total[state] += 1

    built = datetime.now(timezone.utc)
    cutoff = last_complete_day(built.date())
    all_days = sorted(set(daily) | set(day_total))
    days = [d for d in all_days if d <= cutoff]
    partial = sum(day_total[d] for d in all_days if d > cutoff)
    if not days:
        print("ERROR: no complete days in the corpus", flush=True)
        return 1

    # Default the view to the real collection window rather than the full span.
    # `published` reaches back to 2011 because some outlets were backfilled from
    # their archives, but those years hold a few hundred stories between them
    # against ~24,000 in the last six months. Opening on the full range would
    # show fifteen years of near-empty axis. The whole series is still emitted
    # -- the dashboard's brush can widen to it -- this only picks the opening
    # slice: the longest run of days ending at the present whose trailing
    # DEFAULT_WINDOW-day average clears MIN_DAY_STORIES.
    def trailing_avg(i: int) -> float:
        end = date.fromisoformat(days[i])
        # Over calendar days, not emitted days: a gap has to count as the zero
        # it is, or a run of sparse days separated by empty weeks would average
        # as though the empty weeks never happened.
        total = sum(day_classified.get((end - timedelta(days=k)).isoformat(), 0)
                    for k in range(DEFAULT_WINDOW))
        return total / DEFAULT_WINDOW

    default_start = len(days) - 1
    while default_start > 0 and trailing_avg(default_start - 1) >= MIN_DAY_STORIES:
        default_start -= 1

    # Earliest calendar year holding at least RECENT_YEAR_SHARE of the dated
    # corpus, and the index its January 1st falls on. This is the far edge of
    # the brush until the reader asks for the full archive. Deriving it from
    # the data rather than hardcoding a year means it follows the corpus: once
    # a second year clears the bar, the default span covers both.
    year_total = Counter()
    for d, n in day_total.items():
        year_total[d[:4]] += n
    dated = sum(year_total.values()) or 1
    qualifying = sorted(y for y, n in year_total.items()
                        if n / dated >= RECENT_YEAR_SHARE)
    recent_year = qualifying[0] if qualifying else days[0][:4]
    recent_start = next((i for i, d in enumerate(days) if d[:4] >= recent_year),
                        default_start)

    data = {
        "generated_at": built.isoformat(timespec="seconds"),
        # Last complete day, and what the pipeline ingested on it. `captured_at`
        # is when a story entered the database, not when it was published, so
        # this answers "what did the overnight run bring in" -- which is a
        # different question from "what was published yesterday" (day_totals'
        # last entry) and a different number, since a night's run also picks up
        # older stories still sitting in a feed.
        "as_of": cutoff,
        "added_on_as_of": captured_on.get(cutoff, 0),
        "model_version": model_version,
        "topics": [{"key": k, "label": labels[k[1:]], "total": topic_total[k]}
                   for k in keys],
        "days": days,
        "default_range": [default_start, len(days) - 1],
        # Far edge of the brush before the reader opts into the full archive.
        "recent_start": recent_start,
        "recent_year": recent_year,
        "series": {k: [daily[d][k] for d in days] for k in keys},
        "day_totals": [day_total[d] for d in days],
        # Shares divide by this, not by day_totals. Full-text extraction lags
        # capture by a day or two, and an unextracted story has no topic — so
        # dividing by every story published would drag the newest days toward
        # zero across all ten topics and read as a coverage collapse that never
        # happened. day_totals stays the honest volume figure for the KPI and
        # the brush strip; this is the honest denominator for a share.
        "day_classified": [day_classified[d] for d in days],
        # Days too thin for a share to mean anything; the dashboard should
        # render these differently rather than letting them swing the chart.
        # Measured on the classified count, since that is what a share divides
        # by -- a 400-story day with 4 extracted is still a 4-story sample.
        "thin_days": [d for d in days if day_classified[d] < MIN_DAY_STORIES],
        "min_day_stories": MIN_DAY_STORIES,
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
    print(f"  series stops at {cutoff} (last complete day); "
          f"{partial:,} stories dated after it held back as a partial day")
    print(f"  {data['added_on_as_of']:,} stories captured on {cutoff}")
    span = (date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days + 1
    print(f"  days {days[0]} -> {days[-1]}: {len(days):,} with stories "
          f"out of {span:,} calendar days"
          + (f", {len(data['thin_days'])} flagged thin "
             f"(under {MIN_DAY_STORIES} stories)" if data["thin_days"] else ""))
    pre = sum(day_total[d] for d in days[:recent_start])
    print(f"  brush spans {days[recent_start]} -> {days[-1]} until the reader asks "
          f"for the full archive ({recent_year}+ clears {RECENT_YEAR_SHARE:.0%} "
          f"of the corpus; the {recent_start:,} earlier days hold {pre:,} stories)")
    print(f"  opens on {days[default_start]} -> {days[-1]} "
          f"({sum(day_total[d] for d in days[default_start:]):,} stories over "
          f"{len(days) - default_start:,} days); "
          f"earlier days reachable via the brush")
    print(f"  {len(data['states'])} states")
    print(f"  {undated:,} rows have no usable published date "
          f"(excluded from the time series)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
