"""Label every institution in the publication database by university type.

Adds three boolean columns to data/publication_locations.csv — land_grant,
hbcu, community_college — plus audit columns recording which IPEDS record
(if any) each institution matched:

  land_grant / hbcu   IPEDS HD 2023 flags (LANDGRNT==1 / HBCU==1; 2 means no,
                      negative values mean not available and are read as no).
  community_college   Name heuristic: the institution name contains the word
                      "Community" or "Technical" (word-boundary match, checked
                      against both our name and the matched IPEDS name). The
                      user-specified rule; it misses systems that dropped the
                      word from their name (e.g. "Dallas College").

Matching runs in tiers, best first:

  1. override   data/school_type_overrides.csv pins an institution to an IPEDS
                UNITID. For mergers and renames no string matcher can see
                (Bloomsburg University -> Commonwealth University of
                Pennsylvania) and for fuzzy failures worth fixing by hand.
  2. exact      Normalized name (or IPEDS alias) equality — covers ~85% of
                institutions. Normalization matches geocode_publications.py:
                lowercase, drop a leading "the", strip non-alphanumerics.
  3. fuzzy      Prefix ("Austin Community College" -> "... District"),
                token-subset ("CUNY Baruch College" -> "CUNY Bernard M Baruch
                College") or high string similarity, ranked by state agreement,
                then active status, then similarity. Anything still unmatched
                is reported so it can be added to the overrides file.

Institutions with no IPEDS match keep land_grant/hbcu = False (unknown, really)
and still get the name-based community_college flag. Downstream, stories at
unmatched institutions appear only in the dashboard's "All" cohort.

Run after scripts/geocode_publications.py, which regenerates the CSV nightly
and would otherwise drop these columns:

    python scripts/geocode_publications.py
    python scripts/label_school_types.py
"""
import csv
import difflib
import os
import re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IPEDS_CSV = os.path.join(ROOT, "data", "all-schools-2023.csv")
LOCATIONS_CSV = os.path.join(ROOT, "data", "publication_locations.csv")
OVERRIDES_CSV = os.path.join(ROOT, "data", "school_type_overrides.csv")

NEW_COLUMNS = ["land_grant", "hbcu", "community_college",
               "ipeds_unitid", "ipeds_name", "school_type_match"]

# Name-based community-college rule: word-boundary match, case-insensitive.
CC_RE = re.compile(r"\bcommunity\b|\btechnical\b", re.IGNORECASE)

# A fuzzy candidate must clear this similarity to be considered at all.
MIN_RATIO = 0.80
# Stopwords carry no identity ("University of X" vs "University of Y"), so
# token-subset matching ignores them; everything else, including
# "university"/"college", stays, since those words do discriminate
# ("Bloomsburg University" is not "Bloomsburg College").
TOKEN_STOP = {"the", "of", "and", "at", "for", "in", "on", "to", "de", "del",
              "la", "las", "el", "a", "an", "&", "-"}


def norm_name(s) -> str:
    """Same normalization as geocode_publications.py."""
    if not isinstance(s, str):
        return ""
    s = s.lower()
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def tokens(s) -> frozenset:
    return frozenset(t for t in re.split(r"[^a-z0-9]+", (s or "").lower())
                     if len(t) > 1 and t not in TOKEN_STOP)


def flag(value) -> bool:
    """IPEDS indicator columns: 1 = yes, 2 = no, negatives = not available."""
    return (value or "").strip() == "1"


def load_ipeds():
    """-> (records, by_norm, by_unitid). by_norm indexes INSTNM and IALIAS."""
    records, by_norm, by_unitid = [], defaultdict(list), {}
    with open(IPEDS_CSV, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            rec = {
                "unitid": (row.get("UNITID") or "").strip(),
                "name": (row.get("INSTNM") or "").strip(),
                "state": (row.get("STABBR") or "").strip().upper(),
                "active": (row.get("CYACTIVE") or "").strip() == "1",
                "hbcu": flag(row.get("HBCU")),
                "land_grant": flag(row.get("LANDGRNT")),
                "norm": norm_name(row.get("INSTNM")),
                "tokens": tokens(row.get("INSTNM")),
            }
            records.append(rec)
            by_unitid[rec["unitid"]] = rec
            if rec["norm"]:
                by_norm[rec["norm"]].append(rec)
            # Aliases ("AAMU", "UAB", ...) join exact matching when usable.
            # IPEDS pads inapplicable cells with -1/-2/-3 and stray spaces.
            alias = (row.get("IALIAS") or "").strip()
            an = norm_name(alias)
            if len(an) >= 4 and an != rec["norm"]:
                by_norm[an].append(rec)
    return records, by_norm, by_unitid


def load_overrides() -> dict:
    """normalized institution name -> UNITID."""
    out = {}
    if not os.path.exists(OVERRIDES_CSV):
        return out
    with open(OVERRIDES_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            inst = norm_name(row.get("institution"))
            unitid = (row.get("ipeds_unitid") or "").strip()
            if inst and unitid:
                out[inst] = unitid
    return out


def best(cands, state):
    """Rank candidates: state agreement first, then active, then similarity."""
    def key(c):
        return (1 if state and c["state"] == state else 0,
                1 if c["active"] else 0, c["score"])
    return max(cands, key=key)


def fuzzy_match(inst, state, records):
    """Tier-3 match: prefix / token-subset / high similarity, in that order.

    Prefix and token-subset hits outrank raw similarity because similarity
    alone loves the wrong pair — "Arizona State University" is 0.93 similar to
    "Arkansas State University" and only 0.79 to the real target, "Arizona
    State University Campus Immersion". The structural rules get that right;
    state agreement breaks what remains.
    """
    n = norm_name(inst)
    tks = tokens(inst)
    if not n:
        return None
    # Cheap gate: a real match shares a substantial token or a long prefix,
    # which keeps SequenceMatcher off the ~5M pairs that cannot win.
    pool = [r for r in records
            if (r["tokens"] & tks) or r["norm"].startswith(n[:8]) or n.startswith(r["norm"][:8])]
    cands = []
    for r in pool:
        ratio = difflib.SequenceMatcher(None, n, r["norm"]).ratio()
        if r["norm"].startswith(n) or n.startswith(r["norm"]):
            tier = 3                                   # one name extends the other
        elif tks <= r["tokens"]:
            # Our words all appear in theirs: they add a district suffix, a
            # middle name, or a campus word ("El Camino College" -> "El Camino
            # Community College District"). Renames can stretch similarity thin
            # ("Humboldt State University" is only 0.48 from "California State
            # Polytechnic University-Humboldt"), so a low floor just screens out
            # pairs that share almost nothing beyond stopwords.
            tier = 2 if ratio >= 0.50 else 0
        elif r["tokens"] <= tks:
            # Theirs is a shorter generic form of ours ("Fordham University
            # Lincoln Center" -> "Fordham University"). This direction is the
            # dangerous one: "University of Vermont" is a token-subset of
            # "Northern Vermont University - Johnson" and nothing else, so a
            # real mismatch scores 0.51 while true short forms score 0.68+.
            tier = 2 if ratio >= 0.60 else 0
        else:
            tier = 0
        if tier == 0 and ratio < MIN_RATIO:
            continue
        cands.append({**r, "score": (tier, round(ratio, 4))})
    if not cands:
        return None
    m = best(cands, state)
    # A tier-0 match is only a similarity score; require it to be strong.
    if m["score"][0] == 0 and m["score"][1] < MIN_RATIO:
        return None
    return m


def match_all(rows):
    """institution name -> (record|None, method). Matched once per distinct name."""
    records, by_norm, by_unitid = load_ipeds()
    overrides = load_overrides()
    print(f"IPEDS: {len(records)} institutions, {len(overrides)} overrides")

    cache = {}
    for r in rows:
        inst = (r.get("institution") or "").strip()
        state = (r.get("state") or "").strip().upper()
        if not inst or (inst, state) in cache:
            continue
        n = norm_name(inst)
        rec, how = None, "none"

        uid = overrides.get(n)
        if uid and uid in by_unitid:
            rec, how = by_unitid[uid], "override"
        elif n in by_norm:
            rec, how = best([{**c, "score": (0, 1.0)} for c in by_norm[n]], state), "exact"
        else:
            m = fuzzy_match(inst, state, records)
            if m:
                rec = {k: m[k] for k in ("unitid", "name", "state", "active",
                                         "hbcu", "land_grant", "norm", "tokens")}
                how = f"fuzzy:{m['score'][1]:.2f}"
        cache[(inst, state)] = (rec, how)
    return cache


def main() -> int:
    for path, what in ((IPEDS_CSV, "IPEDS HD 2023"), (LOCATIONS_CSV, "publication database")):
        if not os.path.exists(path):
            print(f"ERROR: {what} not found at {path}")
            return 1

    with open(LOCATIONS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    for col in NEW_COLUMNS:
        if col not in fieldnames:
            fieldnames.append(col)

    matches = match_all(rows)

    label_counts = defaultdict(int)
    story_counts = defaultdict(int)
    unmatched = defaultdict(int)
    fuzzy_report = []
    total_stories = 0

    for r in rows:
        inst = (r.get("institution") or "").strip()
        try:
            stories = int(r.get("stories") or 0)
        except ValueError:
            stories = 0
        total_stories += stories
        rec, how = matches.get((inst, (r.get("state") or "").strip().upper()), (None, "none"))

        # Community college is name-based and needs no IPEDS match; check both
        # our name and the matched IPEDS name ("Edmonds Community College" is
        # "Edmonds College" in IPEDS 2023, and either name alone would miss it).
        cc = bool(CC_RE.search(inst)) or bool(rec and CC_RE.search(rec["name"]))
        lg = bool(rec and rec["land_grant"])
        hb = bool(rec and rec["hbcu"])

        if not inst:
            how = "no-institution"
        r["land_grant"] = lg
        r["hbcu"] = hb
        r["community_college"] = cc
        r["ipeds_unitid"] = rec["unitid"] if rec else ""
        r["ipeds_name"] = rec["name"] if rec else ""
        r["school_type_match"] = how if inst else "no-institution"

        if inst:
            label_counts["land_grant"] += lg
            label_counts["hbcu"] += hb
            label_counts["community_college"] += cc
            story_counts["land_grant"] += stories if lg else 0
            story_counts["hbcu"] += stories if hb else 0
            story_counts["community_college"] += stories if cc else 0
            if rec is None:
                unmatched[inst] += stories
            elif how.startswith("fuzzy"):
                fuzzy_report.append((inst, rec["name"], how, stories))

    with open(LOCATIONS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    inst_total = len({(r.get("institution") or "").strip() for r in rows} - {""})
    print(f"\nwrote {os.path.relpath(LOCATIONS_CSV, ROOT)}: {len(rows)} rows, "
          f"{inst_total} distinct institutions, {total_stories:,} stories")
    print("\nlabels (rows / stories):")
    for k in ("land_grant", "hbcu", "community_college"):
        print(f"  {k:20s} {label_counts[k]:4d} rows  {story_counts[k]:7,d} stories "
              f"({100 * story_counts[k] / max(1, total_stories):.1f}%)")

    by_method = defaultdict(int)
    for (rec, how) in matches.values():
        by_method[how.split(":")[0]] += 1
    print("\nmatch method (distinct institution+state pairs):")
    for k in sorted(by_method, key=lambda x: -by_method[x]):
        print(f"  {k:10s} {by_method[k]}")

    if fuzzy_report:
        print(f"\nfuzzy matches ({len(fuzzy_report)}) — review for wrong pairs:")
        for inst, name, how, s in sorted(fuzzy_report, key=lambda x: -x[3]):
            print(f"  {inst[:44]:44s} -> {name[:52]:52s} {how} ({s} stories)")

    if unmatched:
        print(f"\nunmatched institutions ({len(unmatched)}) — add the important ones "
              f"to data/school_type_overrides.csv:")
        for inst, s in sorted(unmatched.items(), key=lambda x: -x[1]):
            print(f"  {s:6d} stories  {inst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
