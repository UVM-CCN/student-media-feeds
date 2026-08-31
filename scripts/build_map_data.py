"""Build map/map_data.json: per-publication, per-topic story counts with coordinates.

Run scripts/geocode_publications.py first — this reads data/publication_locations.csv.

Topics come from the frozen centroid model (scripts/train_topic_model.py, applied
by scripts/apply_topics.py), read straight off the topic_id column. This replaced
a hand-written keyword lexicon of ten "beats".

The lexicon was a reasonable heuristic, but it meant the map and the dashboard
answered the same question with two different classifiers, so their topic mixes
could not be read against each other. Since the point of the dashboard is
comparing coverage across both time and geography, the two views have to share
one scheme. They now do.

Keys are t0..t9 rather than label slugs, so that renaming a topic in
data/topic_labels.json changes only what the legend reads — never the data
shape, and never what a saved link to a filtered view resolves to.
"""
import json
import os
from collections import Counter, defaultdict
from urllib.parse import urlparse

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "map")
SOURCE_CSV = os.path.join(ROOT, "news_database.csv")
LABELS_JSON = os.path.join(ROOT, "data", "topic_labels.json")

# Assignments below this cosine similarity sit between topics. They are still
# counted in a newsroom's total, but not attributed to a topic — the same
# treatment the old lexicon gave stories with no clear beat signal.
MIN_CONFIDENCE = 0.0


def host(url) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    h = urlparse(url.strip()).netloc.lower().split(":")[0]
    if h.startswith("www."):
        h = h[4:]
    return h or None


def load_labels() -> dict[str, str]:
    """topic_id -> human label. Falls back to a placeholder if unlabeled."""
    if not os.path.exists(LABELS_JSON):
        return {}
    with open(LABELS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for tid, spec in data.get("topics", {}).items():
        label = (spec.get("label") or "").strip()
        out[str(tid)] = label or f"Topic {tid}"
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    locs = pd.read_csv(os.path.join(ROOT, "data", "publication_locations.csv"))
    # Keyed by domain: student papers reuse titles across campuses, so a name
    # key would merge distinct newsrooms onto one point.
    loc_by_domain = {
        r["domain"]: r for _, r in locs.iterrows()
        if pd.notna(r["lat"]) and pd.notna(r["lon"])
    }

    labels = load_labels()
    if not labels:
        raise SystemExit("No data/topic_labels.json — run scripts/train_topic_model.py")

    df = pd.read_csv(SOURCE_CSV, dtype=str).fillna("")
    df = df[df["extraction_status"] == "ok"]

    counts: dict[str, Counter] = defaultdict(Counter)
    classified = skipped = unassigned = low_conf = 0
    for link, tid, conf in zip(df["link"], df.get("topic_id", ""),
                               df.get("topic_confidence", "")):
        dom = host(link)
        if dom is None or dom not in loc_by_domain:
            skipped += 1
            continue
        counts[dom]["total"] += 1
        tid = (tid or "").strip()
        if not tid:
            unassigned += 1
            continue
        try:
            if float(conf or 0) < MIN_CONFIDENCE:
                low_conf += 1
                continue
        except ValueError:
            pass
        counts[dom][f"t{tid}"] += 1
        classified += 1

    keys = [f"t{t}" for t in sorted(labels, key=int)]

    points = []
    for dom, c in counts.items():
        r = loc_by_domain[dom]
        rec = {"n": r["publication"], "d": dom,
               "lat": round(float(r["lat"]), 5),
               "lon": round(float(r["lon"]), 5), "t": c["total"]}
        if isinstance(r["institution"], str):
            rec["i"] = r["institution"]
        if isinstance(r["state"], str):
            rec["s"] = r["state"]
        for k in keys:
            if c[k]:
                rec[k] = c[k]
        points.append(rec)
    points.sort(key=lambda p: -p["t"])

    totals = Counter()
    for p in points:
        for k in keys:
            totals[k] += p.get(k, 0)

    data = {
        "topics": [{"key": f"t{t}", "label": labels[t]}
                   for t in sorted(labels, key=int)],
        "topic_totals": dict(totals),
        "model_version": json.load(open(LABELS_JSON, encoding="utf-8"))
                             .get("model_version", ""),
        "points": points,
    }
    path = os.path.join(OUT, "map_data.json")
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    # Browsers block fetch() of local JSON over file://, so also emit a script-tag
    # version. This is what map/index.html loads, so it opens by double-clicking.
    with open(os.path.join(OUT, "map_data.js"), "w") as f:
        f.write("window.MAP_DATA = ")
        json.dump(data, f, separators=(",", ":"))
        f.write(";\n")

    print(f"points (located outlets):      {len(points)}")
    print(f"stories placed:                {sum(p['t'] for p in points)}")
    print(f"  assigned to a topic:         {classified}")
    print(f"  no topic assigned:           {unassigned}")
    if low_conf:
        print(f"  below confidence floor:      {low_conf}")
    print(f"stories at unlocated outlets:  {skipped}")
    print(f"map_data.json:                 {os.path.getsize(path)/1024:.0f} KB")
    print()
    for k, v in totals.most_common():
        label = next(t["label"] for t in data["topics"] if t["key"] == k)
        print(f"  {v:>6}  {label}")


if __name__ == "__main__":
    main()
