"""Attach lat/long to every publication in the corpus.

Sources, in priority order:
  1. data/student-media-outlets.csv   (LAT/LONG, matched by outlet domain)
  2. ccn_nap_master.csv               (LAT/LON,  matched by program domain)
  3. name match against the same two files
  4. unresolved -> reported for geocoding by institution/city/state
"""
import os
import re
import sys
from collections import Counter
from urllib.parse import urlparse

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data")


def host(url) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    u = url.strip()
    if not u.startswith("http"):
        u = "https://" + u
    h = urlparse(u).netloc.lower().split(":")[0]
    if h.startswith("www."):
        h = h[4:]
    return h or None


def hosts_in(cell) -> list[str]:
    """A cell may hold several URLs separated by ' or ', commas, or whitespace."""
    if not isinstance(cell, str):
        return []
    parts = re.split(r"\s+or\s+|[,;]\s*|\s+", cell)
    return [h for h in (host(p) for p in parts if p.strip()) if h]


def norm_name(s) -> str:
    if not isinstance(s, str):
        return ""
    s = s.lower()
    s = re.sub(r"^the\s+", "", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def build_lookup():
    """domain -> record, name -> record, institution -> record"""
    by_host, by_name, by_inst = {}, {}, {}

    o = pd.read_csv(os.path.join(ROOT, "data", "student-media-outlets.csv"))
    for _, r in o.iterrows():
        lat, lon = r["LAT"], r["LONG"]
        if pd.isna(lat) or pd.isna(lon):
            continue
        rec = {
            "lat": float(lat), "lon": float(lon),
            "institution": r.get("College/University"),
            "state": r.get("State"),
            "outlet": r.get("Name of Outlet"),
            "source": "student-media-outlets.csv",
        }
        for h in hosts_in(r.get("URL of Outlet")):
            by_host.setdefault(h, rec)
        n = norm_name(r.get("Name of Outlet"))
        if n:
            by_name.setdefault(n, rec)
        i = norm_name(r.get("College/University"))
        if i:
            by_inst.setdefault(i, rec)

    m = pd.read_csv(os.path.join(ROOT, "ccn_nap_master.csv"))
    for _, r in m.iterrows():
        lat, lon = r.get("LAT"), r.get("LON")
        if pd.isna(lat) or pd.isna(lon):
            continue
        rec = {
            "lat": float(lat), "lon": float(lon),
            "institution": r.get("INSTITUTION"),
            "state": r.get("STATE_AB"),
            "outlet": r.get("NAME OF PROGRAM"),
            "source": "ccn_nap_master.csv",
        }
        for h in hosts_in(r.get("URL")):
            by_host.setdefault(h, rec)
        n = norm_name(r.get("NAME OF PROGRAM"))
        if n:
            by_name.setdefault(n, rec)
        i = norm_name(r.get("INSTITUTION"))
        if i:
            by_inst.setdefault(i, rec)

    return by_host, by_name, by_inst


def load_overrides() -> dict[str, dict]:
    """domain -> {institution | lat/lon, note} for outlets absent from the source files."""
    path = os.path.join(ROOT, "data", "publication_institution_overrides.csv")
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    out = {}
    for _, r in df.iterrows():
        out[str(r["domain"]).strip().lower()] = {
            "institution": r.get("institution"),
            "lat": r.get("lat"),
            "lon": r.get("lon"),
            "note": r.get("note", ""),
        }
    return out


def main():
    by_host, by_name, by_inst = build_lookup()
    overrides = load_overrides()
    print(f"lookup: {len(by_host)} domains, {len(by_name)} outlet names, "
          f"{len(by_inst)} institutions, {len(overrides)} overrides")

    n = pd.read_csv(os.path.join(ROOT, "news_database.csv"))
    # Key by DOMAIN, not by source name. Student papers reuse titles heavily —
    # "The Observer" alone spans four campuses — so name-keying would collapse
    # distinct newsrooms onto one point.
    doms: dict[str, Counter] = {}
    for src, link in zip(n["source"], n["link"]):
        h = host(link)
        if h:
            doms.setdefault(h, Counter())[str(src)] += 1

    # Outlet titles are heavily reused across campuses ("The Echo" appears at six
    # schools). Name matching is only safe for titles unique within the corpus.
    name_domains: dict[str, set[str]] = {}
    for dom, names in doms.items():
        for nm in names:
            name_domains.setdefault(norm_name(nm), set()).add(dom)
    ambiguous = {n for n, ds in name_domains.items() if len(ds) > 1}

    rows = []
    for dom, names in doms.items():
        pub = names.most_common(1)[0][0]
        total = sum(names.values())
        rec, how = None, "unresolved"

        # Overrides come first: they exist to correct bad or missing source data,
        # so a domain match must not win over an explicit correction.
        if dom in overrides:
            ov = overrides[dom]
            if pd.notna(ov["lat"]) and pd.notna(ov["lon"]):
                rec = {"lat": float(ov["lat"]), "lon": float(ov["lon"]),
                       "institution": ov["institution"], "state": None,
                       "source": "override (explicit coordinates)"}
                how = "override-coords"
            elif isinstance(ov["institution"], str):
                inst = norm_name(ov["institution"])
                if inst in by_inst:
                    rec, how = by_inst[inst], "override-institution"
        if rec is None and dom in by_host:
            rec, how = by_host[dom], "domain"
        if rec is None:
            nm = norm_name(pub)
            if nm in by_name and nm not in ambiguous:
                rec, how = by_name[nm], "name"
        rows.append({
            "domain": dom, "publication": pub, "stories": total,
            "lat": rec["lat"] if rec else None,
            "lon": rec["lon"] if rec else None,
            "institution": rec["institution"] if rec else None,
            "state": rec["state"] if rec else None,
            "match": how,
            "match_source": rec["source"] if rec else None,
        })

    df = pd.DataFrame(rows).sort_values("stories", ascending=False)
    df.to_csv(os.path.join(OUT, "publication_locations.csv"), index=False)

    tot_pubs, tot_stories = len(df), df["stories"].sum()
    got = df["lat"].notna()
    print()
    print(f"outlets (by domain):     {tot_pubs}")
    print(f"  with coordinates:      {got.sum()}  ({100*got.sum()/tot_pubs:.1f}%)")
    print(f"  unresolved:            {(~got).sum()}")
    print(f"stories:                 {tot_stories}")
    print(f"  with coordinates:      {df.loc[got,'stories'].sum()}  "
          f"({100*df.loc[got,'stories'].sum()/tot_stories:.1f}%)")
    print()
    print("match method:")
    print(df["match"].value_counts().to_string())
    print()
    print("largest unresolved publications:")
    print(df[~got].head(20)[["domain", "publication", "stories"]].to_string(index=False))

    warn_shared_coordinates(df)


def warn_shared_coordinates(df: pd.DataFrame) -> None:
    """Flag outlets stacked on one coordinate across different states.

    Geocoders that fail often return a state or country centroid, so several
    unrelated institutions landing on the identical point is a reliable signal
    of bad source data rather than a real cluster.
    """
    placed = df[df["lat"].notna()].copy()
    placed["key"] = list(zip(placed["lat"].round(5), placed["lon"].round(5)))
    suspect = []
    for key, grp in placed.groupby("key"):
        states = {s for s in grp["state"].dropna().unique()}
        if len(states) > 1:
            suspect.append((key, grp, states))
    if not suspect:
        return
    print()
    print("WARNING: coordinates shared across states — likely bad source geocoding")
    for key, grp, states in suspect:
        print(f"  {key} states={sorted(states)}")
        for _, r in grp.iterrows():
            print(f"      {r['domain']:34s} {str(r['institution'])[:40]:42s} {r['state']}")
    print("  Fix by adding a row to data/publication_institution_overrides.csv")


if __name__ == "__main__":
    main()
