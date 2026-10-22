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

University-type cohorts
-----------------------
Every time-series aggregate is emitted once per cohort — all / landgrant /
hbcu / community — so the page can subset every view by university type
without touching story rows. Flags come from data/publication_locations.csv
(scripts/label_school_types.py, matched against IPEDS 2023) and join on the
story's link domain. Cohorts overlap (many HBCUs are also land-grant) and
"all" additionally holds stories whose institution never matched IPEDS, so
the parts do not sum to the whole.

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
# Every story, not a sample, for search.html. See write_search_index().
SEARCH_DIR = os.path.join(OUT_DIR, "search")

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

# Calendar date the dashboard opens on: the left edge of the default brush
# range. Overrides the data-derived walk below when set.
DEFAULT_OPEN = "2026-09-01"

# University-type cohorts the dashboard can subset by. Flags come from
# scripts/label_school_types.py (columns on data/publication_locations.csv,
# matched against IPEDS 2023). Cohorts OVERLAP — many HBCUs are also
# land-grant — and "all" additionally holds every story whose institution
# never matched IPEDS, so the parts never sum to the whole. Every aggregate
# the page reads (series, day totals, KPIs, brush defaults) is emitted once
# per cohort; the map and the drawer filter on the same flags client-side.
COHORTS = ("all", "landgrant", "hbcu", "community")
# One letter per flag, used as the compact wire form in publications,
# source_flags, and map_points pubs.
COHORT_LETTER = (("landgrant", "g"), ("hbcu", "h"), ("community", "c"))


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


def load_school_flags() -> dict[str, str]:
    """domain -> subset of "ghc" (land-grant / HBCU / community college).

    Written nightly by scripts/label_school_types.py. Every row counts, not
    just the located ones: the time series includes outlets the map has never
    placed, and dropping them here would silently bias every cohort toward
    the geocoded subset.
    """
    def truthy(v):
        return (v or "").strip().lower() in ("1", "true", "yes")
    out = {}
    if not os.path.exists(LOCATIONS_CSV):
        return out
    with open(LOCATIONS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dom = (row.get("domain") or "").strip()
            if not dom:
                continue
            letters = ""
            if truthy(row.get("land_grant")):
                letters += "g"
            if truthy(row.get("hbcu")):
                letters += "h"
            if truthy(row.get("community_college")):
                letters += "c"
            out[dom] = letters
    return out


def write_search_index(rows: list, labels: dict, keys: list, built: datetime) -> None:
    """
    The full story list for search.html, sharded by published month.

    The headline shards hold at most HEADLINE_SAMPLE stories per day-topic
    cell, which is right for a drill-down and wrong for search: a keyword hit
    outside the sample would simply not exist. So search gets every row, cut
    to the five fields it shows -- ~14MB across the corpus, which is why it is
    split by month like the headlines. The page loads only the months its date
    range touches, and an old month's file never changes, so git stores it once.

    Unlike the dashboard series, nothing is held back after the last complete
    day: a partial day distorts a share, but a story found by search is just as
    real for having been published this morning. Undated rows get their own
    file, which the page loads only when asked.

    Each shard carries its own source table, so a newly discovered outlet adds
    an entry to the current month rather than renumbering every past file.
    """
    by_month: dict[str, list] = defaultdict(list)
    seen = set()
    for r in rows:
        title = (r.get("title") or "").strip()
        link = (r.get("link") or "").strip()
        if not title or not link or link in seen:
            continue
        seen.add(link)
        day = day_of(r.get("published"))
        tid = (r.get("topic_id") or "").strip()
        by_month[day[:7] if day else "undated"].append(
            (day or "", int(tid) if tid.isdigit() else None,
             (r.get("source") or "").strip(), title, link))

    os.makedirs(SEARCH_DIR, exist_ok=True)
    written = 0
    months = []
    for month, items in sorted(by_month.items()):
        items.sort(key=lambda x: (x[0], x[2], x[3], x[4]))
        sources = sorted({x[2] for x in items})
        src_index = {s: i for i, s in enumerate(sources)}
        payload = {
            "src": sources,
            # [day of month (0 when undated), topic id or null, source index,
            #  title, link]
            "rows": [[int(d[8:10]) if d else 0, t, src_index[s], title, link]
                     for d, t, s, title, link in items],
        }
        body = ('(window.SEARCH_SHARDS=window.SEARCH_SHARDS||{})'
                f'[{json.dumps(month)}]=' + json.dumps(payload, separators=(",", ":")) + ";\n")
        path = os.path.join(SEARCH_DIR, f"{month}.js")
        if not os.path.exists(path) or open(path, encoding="utf-8").read() != body:
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            written += 1
        if month != "undated":
            months.append([month, len(items)])

    manifest = {
        "generated_at": built.isoformat(timespec="seconds"),
        "topics": [{"key": k, "id": int(k[1:]), "label": labels[k[1:]]} for k in keys],
        "months": months,
        "undated": len(by_month.get("undated", [])),
        "total": len(seen),
    }
    with open(os.path.join(SEARCH_DIR, "index.js"), "w", encoding="utf-8") as f:
        f.write("window.SEARCH_INDEX = ")
        json.dump(manifest, f, separators=(",", ":"))
        f.write(";\n")
    size = sum(os.path.getsize(os.path.join(SEARCH_DIR, f"{m}.js")) for m in by_month)
    print(f"wrote {os.path.relpath(SEARCH_DIR, ROOT)}/  "
          f"({len(by_month)} files, {size / 1024 / 1024:.2f} MB total, "
          f"{written} rewritten this run): {len(seen):,} unique stories for search")


def main() -> int:
    labels, model_version = load_labels()
    states_by_domain = load_states()
    places = load_places()
    school_flags = load_school_flags()
    # domain -> day -> topic key -> n. Sparse: only 24k of a possible 8.3M cells
    # are non-zero, so this stays small enough to ship whole.
    geo_cells: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    keys = [f"t{t}" for t in sorted(labels, key=int)]

    with open(SOURCE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Every time-series counter exists once per cohort; "all" is the corpus the
    # page used to show as its only view. A story joins each cohort its outlet's
    # domain carries a flag for, so one row can land in up to four of them.
    daily = {c: defaultdict(Counter) for c in COHORTS}   # day -> topic key -> n
    day_total = {c: Counter() for c in COHORTS}          # day -> every story published
    day_classified = {c: Counter() for c in COHORTS}     # day -> stories with a topic
    captured_on = {c: Counter() for c in COHORTS}        # day -> stories ingested
    topic_total = {c: Counter() for c in COHORTS}
    publications = {c: set() for c in COHORTS}
    row_stats = {c: Counter() for c in COHORTS}          # stories/classified/with_text/undated
    cells = defaultdict(list)           # (day, topic key) -> [(title, source, link)]
    state_topic = defaultdict(Counter)  # state -> topic key -> n
    state_total = Counter()
    source_domains: dict[str, Counter] = defaultdict(Counter)  # source -> link host -> n

    for r in rows:
        src = (r.get("source") or "").strip()
        dom = host(r.get("link", "")) or ""
        if src:
            source_domains[src][dom] += 1
        letters = school_flags.get(dom, "")
        cs = ["all"] + [c for c, ch in COHORT_LETTER if ch in letters]
        for c in cs:
            publications[c].add(src)
            row_stats[c]["stories"] += 1
        cap = day_of(r.get("captured_at"))
        if cap:
            for c in cs:
                captured_on[c][cap] += 1
        if (r.get("extraction_status") or "").strip() == "ok":
            for c in cs:
                row_stats[c]["with_text"] += 1
        tid = (r.get("topic_id") or "").strip()
        # `published` is the story's own date, which is what "coverage over
        # time" means. It is absent or unparseable for ~6% of rows; those are
        # counted in totals but excluded from the time series rather than
        # being silently bucketed into the capture date, which would smear
        # backfilled archives into the month they happened to be scraped.
        day = day_of(r.get("published"))
        if not day:
            for c in cs:
                row_stats[c]["undated"] += 1
        if not tid:
            if day:
                for c in cs:
                    day_total[c][day] += 1
            continue
        key = f"t{tid}"
        for c in cs:
            row_stats[c]["classified"] += 1
            topic_total[c][key] += 1
        if day:
            for c in cs:
                daily[c][day][key] += 1
                day_total[c][day] += 1
                day_classified[c][day] += 1
            title = (r.get("title") or "").strip()
            if title:
                cells[(day, key)].append(
                    (title, (r.get("source") or "").strip(), (r.get("link") or "").strip(),
                     school_flags.get(dom, "")))
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
    # otherwise the feed's own source name is shown with no college. "f" carries
    # the school-type letters; source_flags repeats them keyed by the exact
    # source string the headline shards store, which is what the drawer filters
    # a day's stories against — its "n" can differ from the source name.
    home_urls = load_home_urls()
    pub_list = []
    source_flags = {}
    for src, doms in source_domains.items():
        dom = next((d for d, _ in doms.most_common() if d in places), None)
        place = places.get(dom)
        if not dom:
            dom = next((d for d, _ in doms.most_common() if d), "")
        entry = {"n": (place and place["n"]) or src,
                 "c": (place and place["i"]) or "",
                 "u": home_urls.get(dom) or (f"https://{dom}" if dom else "")}
        letters = school_flags.get(dom, "")
        if letters:
            entry["f"] = letters
            source_flags[src] = letters
        pub_list.append(entry)
    pub_list.sort(key=lambda p: (p["n"].lower(), p["c"].lower()))

    built = datetime.now(timezone.utc)
    cutoff = last_complete_day(built.date())
    # The day axis is the whole corpus ("all" cohort). Cohorts ride the same
    # axis with zeros where they published nothing, so one brush index means
    # the same calendar day in every view and the map's per-day keys stay
    # valid across a cohort switch.
    all_days = sorted(set(daily["all"]) | set(day_total["all"]))
    days = [d for d in all_days if d <= cutoff]
    partial = sum(day_total["all"][d] for d in all_days if d > cutoff)
    if not days:
        print("ERROR: no complete days in the corpus", flush=True)
        return 1

    def cohort_ranges(c: str) -> tuple[int, int, str]:
        """(default_start, recent_start, recent_year) for one cohort."""
        dc, dt = day_classified[c], day_total[c]

        # Earliest calendar year holding at least RECENT_YEAR_SHARE of the
        # cohort's dated corpus, and the index its January 1st falls on. This
        # is the far edge of the brush until the reader asks for the full
        # archive. Deriving it from the data rather than hardcoding a year
        # means it follows the corpus: once a second year clears the bar, the
        # default span covers both.
        year_total = Counter()
        for d, n in dt.items():
            year_total[d[:4]] += n
        dated = sum(year_total.values()) or 1
        qualifying = sorted(y for y, n in year_total.items()
                            if n / dated >= RECENT_YEAR_SHARE)
        recent_year = qualifying[0] if qualifying else days[0][:4]

        # Default the view to the real collection window rather than the full
        # span. `published` reaches back to 2011 because some outlets were
        # backfilled from their archives, but those years hold a few hundred
        # stories between them against ~24,000 in the last six months. Opening
        # on the full range would show fifteen years of near-empty axis. The
        # whole series is still emitted -- the dashboard's brush can widen to
        # it -- this only picks the opening slice: the longest run of days
        # ending at the present whose trailing DEFAULT_WINDOW-day average
        # clears MIN_DAY_STORIES.
        def trailing_avg(i: int) -> float:
            end = date.fromisoformat(days[i])
            # Over calendar days, not emitted days: a gap has to count as the
            # zero it is, or a run of sparse days separated by empty weeks
            # would average as though the empty weeks never happened.
            total = sum(dc.get((end - timedelta(days=k)).isoformat(), 0)
                        for k in range(DEFAULT_WINDOW))
            return total / DEFAULT_WINDOW

        default_start = len(days) - 1
        while default_start > 0 and trailing_avg(default_start - 1) >= MIN_DAY_STORIES:
            default_start -= 1

        # A small cohort (HBCU, community college) never sustains
        # MIN_DAY_STORIES a day, so the walk stops immediately and the view
        # would open on a single thin day -- honest, but unreadable. Open on
        # the cohort's whole recent span instead: it is the brush domain the
        # cohort gets anyway, and over months even a small cohort holds enough
        # stories for a share comparison.
        recent_start = next((i for i, d in enumerate(days) if d[:4] >= recent_year),
                            default_start)
        if len(days) - default_start < DEFAULT_WINDOW:
            default_start = min(default_start, recent_start)

        if DEFAULT_OPEN:
            open_i = next((i for i, d in enumerate(days) if d >= DEFAULT_OPEN),
                          len(days) - 1)
            default_start = min(open_i, len(days) - 1)

        return default_start, recent_start, recent_year

    def cohort_payload(c: str) -> dict:
        default_start, recent_start, recent_year = cohort_ranges(c)
        st = row_stats[c]
        return {
            "series": {k: [daily[c][d][k] for d in days] for k in keys},
            "day_totals": [day_total[c][d] for d in days],
            # Shares divide by day_classified, not by day_totals. Full-text
            # extraction lags capture by a day or two, and an unextracted
            # story has no topic — so dividing by every story published would
            # drag the newest days toward zero across all ten topics and read
            # as a coverage collapse that never happened. day_totals stays the
            # honest volume figure for the KPI and the brush strip; this is
            # the honest denominator for a share.
            "day_classified": [day_classified[c][d] for d in days],
            # Days too thin for a share to mean anything; the dashboard should
            # render these differently rather than letting them swing the
            # chart. Measured on the classified count, since that is what a
            # share divides by -- a 400-story day with 4 extracted is still a
            # 4-story sample. A small cohort runs thin most days by nature.
            "thin_days": [d for d in days if day_classified[c][d] < MIN_DAY_STORIES],
            "default_range": [default_start, len(days) - 1],
            # Far edge of the brush before the reader opts into the full archive.
            "recent_start": recent_start,
            "recent_year": recent_year,
            # `captured_at` is when a story entered the database, not when it
            # was published, so this answers "what did the overnight run bring
            # in" -- a different question from "what was published yesterday"
            # (day_totals' last entry) and a different number, since a night's
            # run also picks up older stories still sitting in a feed.
            "added_on_as_of": captured_on[c].get(cutoff, 0),
            "topic_totals": {k: topic_total[c][k] for k in keys if topic_total[c][k]},
            "totals": {
                "stories": st["stories"],
                "classified": st["classified"],
                "with_full_text": st["with_text"],
                "publications": len([p for p in publications[c] if p]),
                "undated": st["undated"],
            },
        }

    data = {
        "generated_at": built.isoformat(timespec="seconds"),
        # Last complete day. Per-cohort capture counts live in
        # cohorts[c].added_on_as_of.
        "as_of": cutoff,
        "model_version": model_version,
        # Labels are global and size-ordered by the whole corpus; per-cohort
        # totals live in cohorts[c].topic_totals.
        "topics": [{"key": k, "label": labels[k[1:]], "total": topic_total["all"][k]}
                   for k in keys],
        "days": days,
        "min_day_stories": MIN_DAY_STORIES,
        "cohorts": {c: cohort_payload(c) for c in COHORTS},
        # Source name -> school-type letters ("g"/"h"/"c"), for filtering the
        # drawer's headline samples client-side without per-story flags.
        "source_flags": source_flags,
        "states": sorted(
            ({"code": s, "total": state_total[s],
              "counts": {k: v for k, v in state_topic[s].items() if v}}
             for s in state_total),
            key=lambda d: -d["total"],
        ),
        "publications": pub_list,
    }

    os.makedirs(OUT_DIR, exist_ok=True)

    by_month: dict[str, dict] = defaultdict(dict)
    for (d, key), items in sorted(cells.items()):
        if d > cutoff:
            continue
        cell = {
            "n": len(items),
            "s": [list(x[:3]) for x in sample_cell(items, HEADLINE_SAMPLE)],
        }
        # A cohort's drawer must sample that cohort's stories, not filter the
        # corpus-wide sample: a 6-story sample from a 150-story cell can hold no
        # community-college paper at all, even when 30 of the 150 are from one.
        per_cohort = {}
        for c, ch in COHORT_LETTER:
            sub = [x for x in items if ch in x[3]]
            if sub:
                per_cohort[c] = [list(x[:3]) for x in sample_cell(sub, HEADLINE_SAMPLE)]
        if per_cohort:
            cell["c"] = per_cohort
        by_month[d[:7]].setdefault(d, {})[key] = cell

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
    write_search_index(rows, labels, keys, built)

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
        pub = {"d": dom, **place}
        letters = school_flags.get(dom, "")
        if letters:
            # School-type flags ("g"/"h"/"c"), so the map can follow the
            # dashboard's University-type filter without a second lookup table.
            pub["f"] = letters
        pubs.append(pub)

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

    all_c = data["cohorts"]["all"]
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
    print(f"  {len(rows):,} stories, {row_stats['all']['classified']:,} classified, "
          f"{all_c['totals']['publications']:,} publications")
    print(f"  series stops at {cutoff} (last complete day); "
          f"{partial:,} stories dated after it held back as a partial day")
    print(f"  {all_c['added_on_as_of']:,} stories captured on {cutoff}")
    span = (date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days + 1
    print(f"  days {days[0]} -> {days[-1]}: {len(days):,} with stories "
          f"out of {span:,} calendar days"
          + (f", {len(all_c['thin_days'])} flagged thin "
             f"(under {MIN_DAY_STORIES} stories)" if all_c["thin_days"] else ""))
    pre = sum(day_total["all"][d] for d in days[:all_c["recent_start"]])
    print(f"  brush spans {days[all_c['recent_start']]} -> {days[-1]} until the reader asks "
          f"for the full archive ({all_c['recent_year']}+ clears {RECENT_YEAR_SHARE:.0%} "
          f"of the corpus; the {all_c['recent_start']:,} earlier days hold {pre:,} stories)")
    print(f"  opens on {days[all_c['default_range'][0]]} -> {days[-1]} "
          f"({sum(day_total['all'][d] for d in days[all_c['default_range'][0]:]):,} stories over "
          f"{len(days) - all_c['default_range'][0]:,} days); "
          f"earlier days reachable via the brush")
    print("  cohorts (classified stories / publications / thin days):")
    for c in COHORTS:
        cc = data["cohorts"][c]
        print(f"    {c:10s} {cc['totals']['classified']:7,d} / "
              f"{cc['totals']['publications']:4d} / {len(cc['thin_days']):4d}  "
              f"opens {days[cc['default_range'][0]]}, brush from {cc['recent_year']}")
    print(f"  {len(data['states'])} states")
    print(f"  {row_stats['all']['undated']:,} rows have no usable published date "
          f"(excluded from the time series)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
