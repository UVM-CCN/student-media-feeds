"""Build map/map_data.json: per-publication, per-topic story counts with coordinates.

Run scripts/geocode_publications.py first — this reads data/publication_locations.csv.

Topics are assigned by keyword lexicon over article body text. This is a transparent
heuristic, not a trained classifier; each story is counted once, under its strongest
beat, and stories with no clear signal are left unassigned.
"""
import json
import os
import re
from collections import Counter, defaultdict
from urllib.parse import urlparse

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "map")
HEADER_END = "# ---"
MIN_WORDS = 50          # below this a document is too thin to classify
MIN_SIGNAL = 1.0        # beat hits per 1000 tokens required to assign a topic

BEATS = {
    "sports": ("Sports & athletics", """team teams game games season seasons coach coaches
        player players athlete athletes tournament championship league conference score
        scored win wins won loss losses basketball football baseball softball soccer
        volleyball hockey lacrosse track swimming wrestling ncaa playoff roster inning
        quarter halftime"""),
    "campus": ("Campus administration", """administration administrator president provost
        chancellor dean trustee trustees regents board faculty senate policy policies tuition
        enrollment accreditation budget funding department academic curriculum degree
        graduation commencement dormitory housing residence hall union bookstore"""),
    "politics": ("Politics & government", """election elections vote votes voter voters ballot
        campaign candidate candidates democrat democrats republican republicans senate house
        congress legislature legislative bill legislation governor mayor council federal
        government policy political administration trump biden law lawmakers"""),
    "crime": ("Crime, courts & safety", """police officer officers arrest arrested charged
        charges court judge trial lawsuit sued attorney prosecutor investigation crime
        criminal victim assault shooting theft burglary sentence sentenced guilty verdict
        jail prison safety emergency"""),
    "arts": ("Arts & culture", """music album band concert performance perform festival art
        artist artists gallery exhibit theater theatre play film movie director actor dance
        singer song museum literature poetry book novel review culture"""),
    "health": ("Health & wellness", """health mental medical hospital clinic doctor patient
        patients nurse disease illness virus covid vaccine treatment therapy counseling
        wellness stress anxiety depression care healthcare medicine drug drugs"""),
    "business": ("Business & labor", """business businesses company companies market economy
        economic employer employee employees worker workers union labor strike wage wages job
        jobs hiring industry startup entrepreneur revenue profit inflation cost costs price
        prices"""),
    "environment": ("Environment & climate", """climate environment environmental energy solar
        wind carbon emissions pollution water river lake forest wildlife conservation
        sustainability renewable recycling farm farming agriculture drought flood weather"""),
    "immigration": ("Immigration & identity", """immigrant immigrants immigration ice
        deportation visa asylum refugee border citizenship latino hispanic black african asian
        indigenous native lgbtq queer transgender diversity equity inclusion race racial
        identity community"""),
    "housing": ("Housing & development", """housing rent rental tenant tenants landlord
        apartment affordable homeless homelessness development developer construction zoning
        neighborhood property real estate building project"""),
}

WORD = re.compile(r"[a-z]+")


def strip_header(text: str) -> str:
    i = text.find(HEADER_END)
    return text[i + len(HEADER_END):] if i != -1 else text


def classify(text: str, vocab: dict[str, set[str]]) -> str | None:
    toks = Counter(WORD.findall(text.lower()))
    total = max(1, sum(toks.values()))
    scores = {k: sum(toks[w] for w in v if w in toks) / total * 1000
              for k, v in vocab.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= MIN_SIGNAL else None


def host(url) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    h = urlparse(url.strip()).netloc.lower().split(":")[0]
    if h.startswith("www."):
        h = h[4:]
    return h or None


def main():
    os.makedirs(OUT, exist_ok=True)
    locs = pd.read_csv(os.path.join(ROOT, "data", "publication_locations.csv"))
    # Keyed by domain: student papers reuse titles across campuses, so a name
    # key would merge distinct newsrooms onto one point.
    loc_by_domain = {
        r["domain"]: r for _, r in locs.iterrows()
        if pd.notna(r["lat"]) and pd.notna(r["lon"])
    }

    idx = pd.read_csv(os.path.join(ROOT, "publication_story_index.csv"))
    vocab = {k: set(v[1].split()) for k, v in BEATS.items()}

    counts: dict[str, Counter] = defaultdict(Counter)
    classified = skipped = 0
    for url, path in zip(idx["url"], idx["full_text_path"]):
        dom = host(url)
        if dom is None or dom not in loc_by_domain:
            skipped += 1
            continue
        try:
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                body = strip_header(f.read())
        except OSError:
            continue
        if len(body.split()) < MIN_WORDS:
            continue
        counts[dom]["total"] += 1
        beat = classify(body, vocab)
        if beat:
            counts[dom][beat] += 1
            classified += 1

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
        for k in BEATS:
            if c[k]:
                rec[k] = c[k]
        points.append(rec)
    points.sort(key=lambda p: -p["t"])

    totals = Counter()
    for p in points:
        for k in BEATS:
            totals[k] += p.get(k, 0)

    data = {
        "topics": [{"key": k, "label": v[0]} for k, v in BEATS.items()],
        "topic_totals": dict(totals),
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

    print(f"points (located outlets):     {len(points)}")
    print(f"stories placed:                {sum(p['t'] for p in points)}")
    print(f"  assigned to a topic:         {classified}")
    print(f"stories at unlocated outlets:  {skipped}")
    print(f"map_data.json:                 {os.path.getsize(path)/1024:.0f} KB")
    print()
    for k, v in totals.most_common():
        print(f"  {v:>5}  {BEATS[k][0]}")


if __name__ == "__main__":
    main()
