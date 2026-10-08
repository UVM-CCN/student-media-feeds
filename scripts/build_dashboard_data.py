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
OUTLETS_CSV = os.path.join(ROOT, "data", "student-media-outlets.csv")
# Renamed from "dashboard" in 6519a50. The rename moved the committed files but
# not this constant, so the nightly kept writing to a recreated dashboard/ while
# the page served from student-media-tracker/ went stale.
OUT_DIR = os.path.join(ROOT, "student-media-tracker")
OUT_JSON = os.path.join(OUT_DIR, "dashboard_data.json")
OUT_JS = os.path.join(OUT_DIR, "dashboard_data.js")
# The map's per-publication grid. Kept out of dashboard_data.js deliberately: it
# is ~7x that file's size and feeds a section below the fold, so the page defers
# it rather than making first paint wait on it.
MAP_JSON = os.path.join(OUT_DIR, "map_points.json")
MAP_JS = os.path.join(OUT_DIR, "map_points.js")
HEADLINES_DIR = os.path.join(OUT_DIR, "headlines")

# Headlines per day-topic cell for the drill-down. The median cell holds 3
# stories and the 90th percentile 19, so six shows most cells whole and gives a
# fair look at the big ones.
HEADLINE_SAMPLE = 6

# The samples are written one file per month rather than one file overall, for
# two reasons that point the same way:
#
#   * Git. The set is ~2MB and a single file would be rewritten whole every
#     night, so each daily commit would store another ~2MB blob -- git cannot
#     delta a one-line JSON payload. Split by month, only the current month's
#     file changes; the other 113 stay byte-identical and are stored once. Of
#     those, 92 are under 5KB and will never change again.
#   * Load time. A reader opening one day in August pulls that month's ~300KB,
#     not the whole archive.
#
# Each file registers itself into one shared object, so several months can be
# loaded together without clobbering each other.


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


def sample_cell(items: list, k: int) -> list:
    """
    Up to `k` stories from one day-topic cell, spread across publications.

    Taking the first k in file order would usually return one newsroom's whole
    output -- the CSV is grouped by feed -- which answers "what did this paper
    publish" rather than "what did this topic look like that day". Round-robin
    over sources shows breadth first and only doubles up on a paper once every
    other paper in the cell has appeared. Sorted throughout so a rebuild that
    adds no stories produces no diff.
    """
    by_source: dict[str, list] = defaultdict(list)
    for it in items:
        by_source[it[1]].append(it)
    for group in by_source.values():
        group.sort(key=lambda x: (x[0], x[2]))
    sources = sorted(by_source)
    out: list = []
    depth = 0
    while len(out) < k:
        added = False
        for s in sources:
            if depth < len(by_source[s]):
                out.append(by_source[s][depth])
                added = True
                if len(out) >= k:
                    break
        if not added:
            break
        depth += 1
    return out


def write_pair(json_path: str, js_path: str, var: str, data) -> None:
    """Same payload twice: JSON for tooling, a script-tag assignment for the
    page. Browsers block fetch() of a sibling file over file://, so the .js is
    what the dashboard actually loads -- see the note in main()."""
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    with open(js_path, "w", encoding="utf-8") as f:
        f.write(f"window.{var} = ")
        json.dump(data, f, separators=(",", ":"))
        f.write(";\n")


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


def load_places() -> dict[str, dict]:
    """domain -> {lat, lon, publication, institution, state} for located outlets."""
    out = {}
    if not os.path.exists(LOCATIONS_CSV):
        return out
    with open(LOCATIONS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dom = (row.get("domain") or "").strip()
            lat, lon = (row.get("lat") or "").strip(), (row.get("lon") or "").strip()
            if not (dom and lat and lon):
                continue
            try:
                out[dom] = {
                    "lat": round(float(lat), 5), "lon": round(float(lon), 5),
                    "n": (row.get("publication") or "").strip(),
                    "i": (row.get("institution") or "").strip(),
                    "s": (row.get("state") or "").strip(),
                }
            except ValueError:
                continue
    return out


def load_home_urls() -> dict[str, str]:
    """host -> the outlet's home URL as listed in the outlets sheet."""
    out = {}
    if not os.path.exists(OUTLETS_CSV):
        return out
    with open(OUTLETS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # A few cells hold two URLs ("a or b"); the first is the main one.
            parts = (row.get("URL of Outlet") or "").replace(",", " ").split()
            url = parts[0] if parts else ""
            if url.startswith("http") and host(url):
                out.setdefault(host(url), url)
    return out


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
    places = load_places()
    # domain -> day -> topic key -> n. Sparse: only 24k of a possible 8.3M cells
    # are non-zero, so this stays small enough to ship whole.
    geo_cells: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    keys = [f"t{t}" for t in sorted(labels, key=int)]

    with open(SOURCE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    daily = defaultdict(Counter)        # day -> topic key -> n
    day_total = Counter()               # day -> every story published that day
    day_classified = Counter()          # day -> stories that carry a topic
    captured_on = Counter()             # day -> stories the pipeline ingested
    cells = defaultdict(list)           # (day, topic key) -> [(title, source, link)]
    state_topic = defaultdict(Counter)  # state -> topic key -> n
    state_total = Counter()
    topic_total = Counter()
    publications = set()
    source_domains: dict[str, Counter] = defaultdict(Counter)  # source -> link host -> n
    classified = with_text = 0
    undated = 0

    for r in rows:
        src = (r.get("source") or "").strip()
        publications.add(src)
        if src:
            source_domains[src][host(r.get("link", "")) or ""] += 1
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
            title = (r.get("title") or "").strip()
            if title:
                cells[(day, key)].append(
                    (title, (r.get("source") or "").strip(), (r.get("link") or "").strip()))
        dom = host(r.get("link", "")) or ""
        state = states_by_domain.get(dom)
        if state:
            state_topic[state][key] += 1
            state_total[state] += 1
        # Same row, same filters, keyed for the map. Undated rows are skipped for
        # the same reason they are skipped in the time series: they belong to no
        # day, so no brush range can honestly include them.
        if day and dom in places:
            geo_cells[dom][day][key] += 1

    # One entry per publication for the "View all publications" list. Name and
    # college come from the located outlet when a source's links resolve to one;
    # otherwise the feed's own source name is shown with no college.
    home_urls = load_home_urls()
    pub_list = []
    for src, doms in source_domains.items():
        dom = next((d for d, _ in doms.most_common() if d in places), None)
        place = places.get(dom)
        if not dom:
            dom = next((d for d, _ in doms.most_common() if d), "")
        pub_list.append({"n": (place and place["n"]) or src,
                         "c": (place and place["i"]) or "",
                         "u": home_urls.get(dom) or (f"https://{dom}" if dom else "")})
    pub_list.sort(key=lambda p: (p["n"].lower(), p["c"].lower()))

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
        "publications": pub_list,
    }

    os.makedirs(OUT_DIR, exist_ok=True)

    by_month: dict[str, dict] = defaultdict(dict)
    for (d, key), items in sorted(cells.items()):
        if d > cutoff:
            continue
        by_month[d[:7]].setdefault(d, {})[key] = {
            "n": len(items),
            "s": [list(x) for x in sample_cell(items, HEADLINE_SAMPLE)],
        }

    os.makedirs(HEADLINES_DIR, exist_ok=True)
    written = 0
    for month, payload in by_month.items():
        path = os.path.join(HEADLINES_DIR, f"{month}.js")
        body = ('(window.DASHBOARD_HEADLINES=window.DASHBOARD_HEADLINES||{})'
                f'[{json.dumps(month)}]=' + json.dumps(payload, separators=(",", ":")) + ";\n")
        # Only touch a file whose contents actually changed, so an unchanged
        # month keeps its mtime and stays out of the nightly commit.
        if not os.path.exists(path) or open(path, encoding="utf-8").read() != body:
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            written += 1
    # The manifest goes in the main payload so the page knows which months exist
    # without probing for files that are not there.
    data["headline_shards"] = sorted(by_month)
    data["headline_sample"] = HEADLINE_SAMPLE

    # The dashboard ships as a directory someone copies onto a server, or opens
    # locally. Browsers block fetch() of a sibling JSON file over file://, so
    # the page loads the script-tag version instead and works either way. The
    # month files are loaded the same way, but only when a reader drills into a
    # day -- the page injects that month's <script> on demand.
    write_pair(OUT_JSON, OUT_JS, "DASHBOARD_DATA", data)

    # ---- map grid -------------------------------------------------------
    # Indices, not strings: `c` is keyed by the publication's index in `pubs`
    # and then by the day's index in `days`, which is the same index the
    # dashboard's brush already works in. The map can therefore filter on the
    # live brush range with no date parsing and no month-boundary rounding.
    day_index = {d: i for i, d in enumerate(days)}
    pubs, cells_out = [], {}
    for dom in sorted(geo_cells):
        by_day = {}
        for day, topics in geo_cells[dom].items():
            di = day_index.get(day)
            if di is None:          # outside the emitted window (partial last day)
                continue
            by_day[str(di)] = {k[1:]: n for k, n in topics.items()}
        if not by_day:
            continue
        place = places[dom]
        cells_out[str(len(pubs))] = by_day
        pubs.append({"d": dom, **place})

    map_data = {
        "generated_at": built.isoformat(timespec="seconds"),
        "model_version": model_version,
        "pubs": pubs,
        "c": cells_out,
    }
    write_pair(MAP_JSON, MAP_JS, "MAP_POINTS", map_data)
    n_cells = sum(len(v) for v in cells_out.values())
    print(f"wrote {os.path.relpath(MAP_JS, ROOT)}  "
          f"({os.path.getsize(MAP_JS) / 1024:.0f} KB): "
          f"{len(pubs):,} located publications, {n_cells:,} publication-days")

    size = os.path.getsize(OUT_JSON) / 1024
    csv_size = os.path.getsize(SOURCE_CSV) / 1024 / 1024
    print(f"wrote {os.path.relpath(OUT_JSON, ROOT)}  ({size:.0f} KB)")
    print(f"  replaces a {csv_size:.1f} MB client-side CSV parse")
    hl_bytes = sum(os.path.getsize(os.path.join(HEADLINES_DIR, f"{m}.js")) for m in by_month)
    cells_out = sum(len(day) for month in by_month.values() for day in month.values())
    print(f"wrote {os.path.relpath(HEADLINES_DIR, ROOT)}/  "
          f"({len(by_month)} monthly files, {hl_bytes / 1024 / 1024:.2f} MB total, "
          f"{written} rewritten this run): up to {HEADLINE_SAMPLE} headlines for each of "
          f"{cells_out:,} day-topic cells, loaded a month at a time on demand")
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
