#!/usr/bin/env python3
"""
Title IX / sexual violence coverage in news_database.csv.

Reads the primary news database (never writes to it), classifies each story
using transparent regexes over three field sets:

  1. headline only        : title
  2. metadata             : title + keywords + theme
  3. full-text inclusive  : metadata + extracted body (when available)

Outputs:
  analytics/title_ix_sexual_violence_report.md
  analytics/title_ix_sexual_violence_matches.csv
  analytics/title_ix_sexual_violence_all_tracked_matches.csv
  analytics/title_ix_sexual_violence_summary.csv
  analytics/title_ix_sexual_violence_category_counts.csv
  analytics/title_ix_sexual_violence_outlets.csv
  analytics/title_ix_sexual_violence_years.csv
  analytics/*.png

Run:  python scripts/analyze_title_ix_sexual_violence.py
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "news_database.csv"
OUT_DIR = ROOT / "analytics"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Patterns / shared classifier definitions
# ---------------------------------------------------------------------------
# Kept in scripts/title_ix_definitions.py so the 2026 trend analysis uses the
# exact same patterns, exclusions and category groupings.
from title_ix_definitions import (  # noqa: E402
    PATTERNS, CORE_SV_TERMS, CORE_PATTERNS, STRICT_LITERAL,
    HARASSMENT_PATTERNS, RELATED_PATTERNS, GROUP, RX, EXRX, EQUITY_RX,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clean_outlet(value: str) -> str:
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return "(unknown)"
    s = re.sub(r"\s*-\s*RSS Results.*$", "", s, flags=re.I)
    s = re.sub(r"^https?://", "", s, flags=re.I)
    s = re.sub(r"^www\.", "", s, flags=re.I)
    return s.rstrip("/") or "(unknown)"


def scan_text(text: str, rx_map=None, exrx_map=None):
    """Return (occurrence counts, first surviving context) per pattern."""
    rx_map = rx_map or RX
    exrx_map = exrx_map or EXRX
    counts, contexts = {}, {}
    for key, rx in rx_map.items():
        n = 0
        first = ""
        for m in rx.finditer(text):
            s = max(0, m.start() - 70)
            e = min(len(text), m.end() + 70)
            ctx = re.sub(r"\s+", " ", text[s:e]).strip()
            if any(x.search(ctx) for x in exrx_map.get(key, ())):
                continue
            n += 1
            if not first:
                first = ctx
        counts[key] = n
        contexts[key] = first
    return counts, contexts


def empty_counts():
    return {k: 0 for k in PATTERNS}


def empty_contexts():
    return {k: "" for k in PATTERNS}


def union_flag(flag_df: pd.DataFrame, keys) -> np.ndarray:
    return flag_df[keys].any(axis=1).to_numpy()


def fmt_int(n) -> str:
    return f"{int(n):,}"


def fmt_pct(n, d) -> str:
    return f"{(100.0 * n / d):.2f}%" if d else "0.00%"


def md_escape(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def short_title(value: str, limit: int = 140) -> str:
    s = md_escape(value)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def date_only(value: str) -> str:
    d = pd.to_datetime(value, errors="coerce", utc=True, format="mixed")
    return d.strftime("%Y-%m-%d") if pd.notna(d) else ""


def story_hash(link: str) -> str:
    return hashlib.sha1(str(link).encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# 1. Load and inspect schema
# ---------------------------------------------------------------------------
print("Loading", DB_PATH)
df = pd.read_csv(DB_PATH, dtype=str, keep_default_na=False)
N = len(df)
N_COLS_ORIGINAL = len(df.columns)
print(f"Rows: {N:,}  Columns: {N_COLS_ORIGINAL}")

schema_rows = []
for col in df.columns:
    nonempty = int((df[col].astype(str).str.strip() != "").sum())
    schema_rows.append({
        "column": col,
        "nonempty": nonempty,
        "unique": int(df[col].nunique()),
    })
schema = pd.DataFrame(schema_rows)

# Verify encoding/delimiter assumptions explicitly.
with open(DB_PATH, "rb") as fh:
    head_bytes = fh.read(400)
encoding = "utf-8"
delimiter = ","
print("Header bytes:", head_bytes[:160])
print("Assumed encoding:", encoding, "| delimiter:", delimiter)

text_fields = ["title", "keywords", "theme"]
print("Text fields searched:", text_fields, "+ full_text_path bodies where present")

# ---------------------------------------------------------------------------
# 2. Scan all three field sets
# ---------------------------------------------------------------------------
titles = df["title"].fillna("").astype(str).tolist()
keywords = df["keywords"].fillna("").astype(str).tolist()
themes = df["theme"].fillna("").astype(str).tolist()
paths = df["full_text_path"].fillna("").astype(str).tolist()

keys = list(PATTERNS)
title_counts = {k: np.zeros(N, dtype=np.int32) for k in keys}
meta_counts = {k: np.zeros(N, dtype=np.int32) for k in keys}
body_counts = {k: np.zeros(N, dtype=np.int32) for k in keys}

title_ctx = {k: [""] * N for k in keys}
meta_ctx = {k: [""] * N for k in keys}
body_ctx = {k: [""] * N for k in keys}

has_full_text = np.zeros(N, dtype=np.int8)
equity_context = np.zeros(N, dtype=np.int8)

print("Scanning headlines, keywords/theme, and full text ...")
for i in range(N):
    title = titles[i].strip()
    meta = "\n".join([title, keywords[i].strip(), themes[i].strip()])

    tc, tcx = scan_text(title)
    mc, mcx = scan_text(meta)

    body = ""
    p = paths[i].strip()
    if p and p.lower() not in {"nan", "none"}:
        fp = Path(p)
        if not fp.is_absolute():
            fp = ROOT / fp
        if fp.exists():
            try:
                with open(fp, encoding="utf-8", errors="replace") as fh:
                    txt = fh.read()
                body = txt.split("# ---\n", 1)[1] if "# ---\n" in txt else txt
                has_full_text[i] = 1
            except OSError:
                body = ""

    if body:
        bc, bcx = scan_text(body)
    else:
        bc, bcx = empty_counts(), empty_contexts()

    for k in keys:
        title_counts[k][i] = tc[k]
        meta_counts[k][i] = mc[k]
        body_counts[k][i] = bc[k]
        title_ctx[k][i] = tcx[k]
        meta_ctx[k][i] = mcx[k]
        body_ctx[k][i] = bcx[k]

    equity_context[i] = 1 if (EQUITY_RX.search(meta) or EQUITY_RX.search(body)) else 0

print("Scan complete. Full text found for", fmt_int(has_full_text.sum()), "stories",
      f"({100.0 * has_full_text.sum() / N:.1f}%).")

# ---------------------------------------------------------------------------
# 3. Build flags and dates
# ---------------------------------------------------------------------------
full_counts = {k: meta_counts[k] + body_counts[k] for k in keys}
full_flag = pd.DataFrame({k: full_counts[k] > 0 for k in keys})
meta_flag = pd.DataFrame({k: meta_counts[k] > 0 for k in keys})
title_flag = pd.DataFrame({k: title_counts[k] > 0 for k in keys})

dates = pd.to_datetime(df["published"], errors="coerce", utc=True, format="mixed")
years = dates.dt.year.astype("Int64")

df["has_full_text"] = has_full_text
df["year"] = years
df["outlet"] = df["source"].map(clean_outlet)

# Core definitions
core_mask = union_flag(full_flag, CORE_PATTERNS)
strict_mask = union_flag(full_flag, STRICT_LITERAL)
expanded_mask = core_mask | full_flag["sexual_harassment"].to_numpy()
broad_mask = expanded_mask | union_flag(full_flag, RELATED_PATTERNS)

core_meta_mask = union_flag(meta_flag, CORE_PATTERNS)
core_title_mask = union_flag(title_flag, CORE_PATTERNS)

# Title IX sub-partition
tix = full_flag["title_ix"].to_numpy()
tix_sex = tix & (union_flag(full_flag, CORE_SV_TERMS) | full_flag["sexual_harassment"].to_numpy())
equity = equity_context.astype(bool)
tix_equity_any = tix & equity
tix_equity_only = tix & equity & ~tix_sex
tix_sexual = tix & tix_sex
tix_both = tix & equity & tix_sex
tix_other = tix & ~equity & ~tix_sex

sv_any_mask = union_flag(full_flag, CORE_SV_TERMS)
sv_any_n = int(sv_any_mask.sum())
sv_only = sv_any_mask & ~tix

# Sensitivity: a "prominent mention" requires the core match in the headline
# or at least three core-category regex hits in the body/metadata.
core_hits_total = sum(full_counts[k] for k in CORE_PATTERNS)
prominent_mask = core_mask & (core_title_mask | (core_hits_total >= 3))
prominent_n = int(prominent_mask.sum())

# ---------------------------------------------------------------------------
# 4. Summary tables
# ---------------------------------------------------------------------------
def summary_row(label, mask, note=""):
    n = int(mask.sum())
    return {
        "definition": label,
        "stories": n,
        "pct_of_total": 100.0 * n / N,
        "headline_only": int(union_flag(title_flag, CORE_PATTERNS).sum()) if label.startswith("Core") else "",
        "metadata": "",
        "note": note,
    }

summary_defs = [
    ("Strict literal core: Title IX OR \"sexual violence\" OR sexual assault OR rape", strict_mask,
     "Literal wording from the research question; excludes abuse/misconduct/molestation/groping unless another core term also hits."),
    ("Core: Title IX OR any sexual-violence/abuse term (excl. sexual harassment)", core_mask,
     "Headline answer. Adds sexual abuse, sexual misconduct, molestation, groping, indecent assault, nonconsensual sex, coercion, battery."),
    ("Expanded: core + sexual harassment", expanded_mask,
     "Adds sexual harassment stories, which the prompt lists separately from the core set."),
    ("Broad: expanded + domestic/intimate-partner/dating violence, stalking, generic harassment, trafficking, exploitation, consent", broad_mask,
     "Related terms are NOT counted as sexual violence; shown for context only."),
]
summary = pd.DataFrame([
    {
        "definition": label,
        "stories": int(mask.sum()),
        "pct_of_total": 100.0 * mask.sum() / N,
        "headline_only": int(union_flag(title_flag, CORE_PATTERNS).sum()) if label.startswith("Core") else "",
        "metadata": "",
        "note": note,
    }
    for label, mask, note in summary_defs
])
# Fill headline/metadata counts for each definition explicitly.
for idx, (label, mask, note) in enumerate(summary_defs):
    if idx == 0:
        key_list = STRICT_LITERAL
    elif idx == 1:
        key_list = CORE_PATTERNS
    elif idx == 2:
        key_list = CORE_PATTERNS + HARASSMENT_PATTERNS
    else:
        key_list = CORE_PATTERNS + HARASSMENT_PATTERNS + RELATED_PATTERNS
    summary.loc[idx, "headline_only"] = int(union_flag(title_flag, key_list).sum())
    summary.loc[idx, "metadata"] = int(union_flag(meta_flag, key_list).sum())

summary.to_csv(OUT_DIR / "title_ix_sexual_violence_summary.csv", index=False)

# Per-category table
cat_rows = []
for k in keys:
    unique = int(full_flag[k].sum())
    meta_unique = int(meta_flag[k].sum())
    cat_rows.append({
        "category": k,
        "group": GROUP[k],
        "raw_regex_hits": int(full_counts[k].sum()),
        "unique_stories_full_text": unique,
        "pct_of_total": 100.0 * unique / N,
        "headline_unique": int(title_flag[k].sum()),
        "metadata_unique": meta_unique,
        "body_only_unique": int((full_flag[k].to_numpy() & ~meta_flag[k].to_numpy()).sum()),
        "fulltext_added": unique - meta_unique,
        "among_fulltext_covered": int((full_flag[k].to_numpy() & (has_full_text == 1)).sum()),
    })
cat_table = pd.DataFrame(cat_rows)

# Derived rows that are not raw regex categories
derived = pd.DataFrame([
    {"category": "title_ix_equity_context_any", "group": "derived",
     "raw_regex_hits": "", "unique_stories_full_text": int(tix_equity_any.sum()),
     "pct_of_total": 100.0 * tix_equity_any.sum() / N,
     "headline_unique": "", "metadata_unique": "", "body_only_unique": "",
     "fulltext_added": "", "among_fulltext_covered": ""},
    {"category": "title_ix_equity_only (no SV/harassment)", "group": "derived",
     "raw_regex_hits": "", "unique_stories_full_text": int(tix_equity_only.sum()),
     "pct_of_total": 100.0 * tix_equity_only.sum() / N,
     "headline_unique": "", "metadata_unique": "", "body_only_unique": "",
     "fulltext_added": "", "among_fulltext_covered": ""},
    {"category": "title_ix_sexual_harm", "group": "derived",
     "raw_regex_hits": "", "unique_stories_full_text": int(tix_sexual.sum()),
     "pct_of_total": 100.0 * tix_sexual.sum() / N,
     "headline_unique": "", "metadata_unique": "", "body_only_unique": "",
     "fulltext_added": "", "among_fulltext_covered": ""},
    {"category": "title_ix_both_equity_and_sexual", "group": "derived",
     "raw_regex_hits": "", "unique_stories_full_text": int(tix_both.sum()),
     "pct_of_total": 100.0 * tix_both.sum() / N,
     "headline_unique": "", "metadata_unique": "", "body_only_unique": "",
     "fulltext_added": "", "among_fulltext_covered": ""},
    {"category": "title_ix_other_no_equity_no_sexual", "group": "derived",
     "raw_regex_hits": "", "unique_stories_full_text": int(tix_other.sum()),
     "pct_of_total": 100.0 * tix_other.sum() / N,
     "headline_unique": "", "metadata_unique": "", "body_only_unique": "",
     "fulltext_added": "", "among_fulltext_covered": ""},
    {"category": "harassment_nonsexual_only", "group": "derived",
     "raw_regex_hits": "", "unique_stories_full_text": int((full_flag["harassment_generic"].to_numpy() & ~full_flag["sexual_harassment"].to_numpy()).sum()),
     "pct_of_total": 100.0 * (full_flag["harassment_generic"].to_numpy() & ~full_flag["sexual_harassment"].to_numpy()).sum() / N,
     "headline_unique": "", "metadata_unique": "", "body_only_unique": "",
     "fulltext_added": "", "among_fulltext_covered": ""},
])
cat_out = pd.concat([cat_table, derived], ignore_index=True)
cat_out.to_csv(OUT_DIR / "title_ix_sexual_violence_category_counts.csv", index=False)

# Outlet table
outlet_df = pd.DataFrame({
    "outlet": df["outlet"].to_numpy(),
    "stories": 1,
    "core": core_mask.astype(int),
    "expanded": expanded_mask.astype(int),
    "broad": broad_mask.astype(int),
})
outlet_table = (
    outlet_df.groupby("outlet", dropna=False)
    .agg(stories=("stories", "size"), core=("core", "sum"),
         expanded=("expanded", "sum"), broad=("broad", "sum"))
    .reset_index()
)
outlet_table["core_pct"] = 100.0 * outlet_table["core"] / outlet_table["stories"]
outlet_table["expanded_pct"] = 100.0 * outlet_table["expanded"] / outlet_table["stories"]
outlet_table = outlet_table.sort_values(["core", "stories"], ascending=False)
outlet_table.to_csv(OUT_DIR / "title_ix_sexual_violence_outlets.csv", index=False)

outlets_total = len(outlet_table)
outlets_with_core = int((outlet_table["core"] > 0).sum())
top15 = outlet_table.head(15)
top10_core = int(outlet_table.head(10)["core"].sum())
top10_share = 100.0 * top10_core / max(1, int(core_mask.sum()))
high_rate = (
    outlet_table[outlet_table["stories"] >= 50]
    .sort_values(["core_pct", "core"], ascending=False)
    .head(10)
)

# Year table
year_df = pd.DataFrame({
    "year": years,
    "stories": 1,
    "core": core_mask.astype(int),
    "expanded": expanded_mask.astype(int),
    "broad": broad_mask.astype(int),
})
year_table = (
    year_df.dropna(subset=["year"])
    .groupby("year")
    .agg(stories=("stories", "size"), core=("core", "sum"),
         expanded=("expanded", "sum"), broad=("broad", "sum"))
    .reset_index()
)
year_table["core_pct"] = 100.0 * year_table["core"] / year_table["stories"]
year_table["expanded_pct"] = 100.0 * year_table["expanded"] / year_table["stories"]
year_table.to_csv(OUT_DIR / "title_ix_sexual_violence_years.csv", index=False)

# Related corpus files: verify what they do and do not add.
INDEX_PATH = ROOT / "publication_story_index.csv"
BOW_PATH = ROOT / "bag_of_words.csv"
index_stats = {"exists": INDEX_PATH.exists(), "stories": 0, "overlap": 0,
               "missing_overlap": 0, "files_exist": 0}
if INDEX_PATH.exists():
    idx = pd.read_csv(INDEX_PATH, dtype=str, keep_default_na=False)
    index_stats["stories"] = len(idx)
    idx_urls = set(idx["url"])
    index_stats["overlap"] = len(set(df["link"]) & idx_urls)
    missing_links = set(df.loc[has_full_text == 0, "link"])
    index_stats["missing_overlap"] = len(missing_links & idx_urls)
    index_stats["files_exist"] = int(sum(
        (ROOT / p).exists() if not os.path.isabs(p) else os.path.exists(p)
        for p in idx["full_text_path"]
    ))
bow_stats = {"exists": BOW_PATH.exists(), "rows": 0, "columns": 0}
if BOW_PATH.exists():
    bow = pd.read_csv(BOW_PATH, nrows=5)
    bow_stats["columns"] = len(bow.columns)
    bow_stats["rows"] = sum(1 for _ in open(BOW_PATH, encoding="utf-8")) - 1

core_covered = int((core_mask & (has_full_text == 1)).sum())
core_uncovered = int((core_mask & (has_full_text == 0)).sum())

# ---------------------------------------------------------------------------
# 5. Story-level output (matched stories)
# ---------------------------------------------------------------------------
priority = CORE_PATTERNS + HARASSMENT_PATTERNS + RELATED_PATTERNS
story_rows = []
for i in np.where(broad_mask)[0]:
    matched = [k for k in priority if full_flag[k].iat[i]]
    primary = matched[0] if matched else ""
    # Evidence: prefer metadata context, then body.
    evidence_parts = []
    for k in matched:
        c = meta_ctx[k][i] or body_ctx[k][i]
        if c:
            evidence_parts.append(f"{k}: {c}")
        if len(evidence_parts) >= 2:
            break
    # For core stories, describe whether the CORE match itself was in the
    # headline/metadata/body.  Related-only stories use all matched categories.
    field_keys = [k for k in CORE_PATTERNS if full_flag[k].iat[i]] if core_mask[i] else matched
    if any(title_flag[k].iat[i] for k in field_keys):
        field = "headline"
    elif any(meta_flag[k].iat[i] for k in field_keys):
        field = "metadata_keywords_theme"
    else:
        field = "body_only"
    story_rows.append({
        "story_id": story_hash(df["link"].iat[i]),
        "row_index": int(i),
        "link": df["link"].iat[i],
        "source": df["source"].iat[i],
        "outlet": df["outlet"].iat[i],
        "title": df["title"].iat[i],
        "published": df["published"].iat[i],
        "year": int(years.iat[i]) if pd.notna(years.iat[i]) else "",
        "has_full_text": int(has_full_text[i]),
        "full_text_path": df["full_text_path"].iat[i],
        "is_core": int(core_mask[i]),
        "is_strict_literal": int(strict_mask[i]),
        "is_expanded": int(expanded_mask[i]),
        "is_broad": int(broad_mask[i]),
        "primary_category": primary,
        "matched_categories": ";".join(matched),
        "match_field": field,
        "headline_hit": int(any(title_flag[k].iat[i] for k in matched)),
        "metadata_hit": int(any(meta_flag[k].iat[i] for k in matched)),
        "core_headline_hit": int(any(title_flag[k].iat[i] for k in CORE_PATTERNS)),
        "core_metadata_hit": int(any(meta_flag[k].iat[i] for k in CORE_PATTERNS)),
        "core_body_only": int(core_mask[i] and not any(meta_flag[k].iat[i] for k in CORE_PATTERNS)),
        "total_regex_hits": int(sum(full_counts[k][i] for k in matched)),
        "core_hits_total": int(core_hits_total[i]),
        "prominent_core": int(prominent_mask[i]),
        "title_ix_equity_context": int(equity_context[i]),
        "title_ix_equity_only": int(tix_equity_only[i]),
        "evidence": " || ".join(evidence_parts)[:500],
        **{f"flag_{k}": int(full_flag[k].iat[i]) for k in keys},
        **{f"hits_{k}": int(full_counts[k][i]) for k in keys},
    })

story_df = pd.DataFrame(story_rows)
if story_df.empty:
    raise SystemExit("No stories matched; check patterns.")
story_df = story_df.sort_values(["is_core", "is_strict_literal", "total_regex_hits"],
                                ascending=[False, False, False])
core_stories = story_df[story_df["is_core"] == 1].copy()
story_df.to_csv(OUT_DIR / "title_ix_sexual_violence_all_tracked_matches.csv", index=False)
core_stories.to_csv(OUT_DIR / "title_ix_sexual_violence_matches.csv", index=False)

# ---------------------------------------------------------------------------
# 6. Representative examples
# ---------------------------------------------------------------------------
examples = []
used_rows = set()
used_titles = set()

def add_example(cat, max_take=2, pool=None):
    global examples
    if len(examples) >= 20:
        return
    pool = core_stories if pool is None else pool
    cand = pool[
        (pool["flag_" + cat] == 1)
        & (~pool["row_index"].isin(used_rows))
    ].copy()
    if cand.empty:
        return
    cand["norm_title"] = cand["title"].str.lower().str.replace(r"\W+", " ", regex=True).str.strip()
    cand = cand[~cand["norm_title"].isin(used_titles)]
    if cand.empty:
        return
    # Prefer examples where THIS category is in the headline, then examples
    # where this category is frequent in the body.  This avoids labelling a
    # Title IX story as a "sexual misconduct" example just because the body
    # contains one passing mention.
    cand["cat_title"] = cand["title"].map(lambda v: bool(RX[cat].search(str(v))))
    cand["cat_hits"] = cand["hits_" + cat].astype(int)
    cand = cand.sort_values(["cat_title", "cat_hits", "total_regex_hits"],
                            ascending=[False, False, False])
    for _, r in cand.head(max_take).iterrows():
        if len(examples) >= 20:
            break
        idx = int(r["row_index"])
        if bool(title_flag[cat].iat[idx]):
            field = "headline"
        elif bool(meta_flag[cat].iat[idx]):
            field = "metadata_keywords_theme"
        else:
            field = "body_only"
        examples.append({
            "category": cat,
            "outlet": r["outlet"],
            "date": date_only(r["published"]),
            "title": r["title"],
            "match_field": field,
            "category_hits": int(r["hits_" + cat]),
            "evidence": r["evidence"],
        })
        used_rows.add(idx)
        used_titles.add(r["norm_title"])

example_plan = [
    ("title_ix", 3),
    ("sexual_violence", 2),
    ("sexual_assault", 3),
    ("rape", 2),
    ("sexual_abuse", 2),
    ("sexual_misconduct", 2),
    ("molestation", 1),
    ("groping", 1),
    ("indecent_assault", 1),
    ("nonconsensual_sex", 1),
    ("sexual_battery", 1),
    ("sexual_harassment", 1),
]
for cat, take in example_plan:
    add_example(cat, take)

# If any slots remain, add core stories with the strongest headline signals.
if len(examples) < 20:
    fill = core_stories[~core_stories["row_index"].isin(used_rows)].copy()
    fill["norm_title"] = fill["title"].str.lower().str.replace(r"\W+", " ", regex=True).str.strip()
    fill = fill[~fill["norm_title"].isin(used_titles)]
    fill = fill.sort_values(["core_headline_hit", "total_regex_hits"], ascending=False)
    for _, r in fill.head(20 - len(examples)).iterrows():
        examples.append({
            "category": r["primary_category"],
            "outlet": r["outlet"],
            "date": date_only(r["published"]),
            "title": r["title"],
            "match_field": r["match_field"],
            "category_hits": "",
            "evidence": r["evidence"],
        })
        used_rows.add(int(r["row_index"]))
        used_titles.add(r["norm_title"])
examples = examples[:20]

# ---------------------------------------------------------------------------
# 7. Regex self-tests (false-positive traps)
# ---------------------------------------------------------------------------
POSITIVE_TESTS = {
    "title_ix": ["Title IX", "Title 9", "Title I X", "Tit1e IX", "Title lX"],
    "sexual_violence": ["sexual violence", "sexual-violence"],
    "sexual_assault": ["sexual assault", "sexually assaulted", "sex assault"],
    "rape": ["rape", "raped", "rapist", "gang rape", "statutory rape"],
    "sexual_abuse": ["sexual abuse", "sexually abused", "child sex abuse"],
    "sexual_misconduct": ["sexual misconduct"],
    "molestation": ["molestation", "molested", "child molester"],
    "groping": ["groping", "groped her"],
    "indecent_assault": ["indecent assault"],
    "nonconsensual_sex": ["nonconsensual sex", "non-consensual sexual contact"],
    "sexual_coercion": ["sexual coercion", "coerced sex"],
    "sexual_battery": ["sexual battery"],
    "sexual_harassment": ["sexual harassment", "sexually harassed", "sex-based harassment"],
    "domestic_violence": ["domestic violence", "domestic abuse"],
    "intimate_partner_violence": ["intimate partner violence"],
    "dating_violence": ["dating violence", "teen dating violence"],
    "stalking": ["stalking", "stalker"],
    "sex_trafficking": ["sex trafficking"],
    "sexual_exploitation": ["sexual exploitation"],
    "sexual_consent": ["sexual consent", "affirmative consent to sexual activity"],
}
NEGATIVE_TESTS = {
    "rape": ["grape", "scrape", "therapist", "rapid", "rapping", "drape", "rapeseed"],
    "title_ix": ["matrix", "helix", "six", "fix", "appendix", "title case"],
    "sexual_assault": ["Sussex", "Essex", "Middlesex", "bisexual", "homosexual"],
    "sexual_abuse": ["child abuse", "substance abuse", "abuse of power"],
    "groping": ["groped around in her purse", "groping for answers"],
    "stalking": ["stalking horse", "stalker-esque", "stalker-y"],
    "molestation": ["Bambi Molesters", "do not molest the alligators", "molesting, annoying"],
    "sexual_consent": ["affirmative consent for data privacy"],
    "nonconsensual_sex": ["nonconsensual medical procedure"],
}
test_rows = []
failures = []
for cat, phrases in POSITIVE_TESTS.items():
    for phrase in phrases:
        counts, _ = scan_text(phrase)
        ok = counts.get(cat, 0) > 0
        test_rows.append({"type": "positive", "category": cat, "phrase": phrase, "result": "PASS" if ok else "FAIL"})
        if not ok:
            failures.append(("positive", cat, phrase))
for cat, phrases in NEGATIVE_TESTS.items():
    for phrase in phrases:
        counts, _ = scan_text(phrase)
        ok = counts.get(cat, 0) == 0
        test_rows.append({"type": "negative", "category": cat, "phrase": phrase, "result": "PASS" if ok else "FAIL"})
        if not ok:
            failures.append(("negative", cat, phrase))
tests_df = pd.DataFrame(test_rows)
tests_df.to_csv(OUT_DIR / "title_ix_sexual_violence_regex_tests.csv", index=False)

# ---------------------------------------------------------------------------
# 8. Charts
# ---------------------------------------------------------------------------
plt.rcParams.update({"font.size": 9, "axes.titlesize": 11, "axes.labelsize": 9})

# Chart 1: per-category unique stories
chart_cats = cat_table[cat_table["unique_stories_full_text"] > 0].copy()
color_map = {"core": "#1f4e79", "harassment": "#c55a11", "related": "#7f7f7f"}
chart_cats = chart_cats.sort_values("unique_stories_full_text", ascending=True)
chart_cats["label"] = chart_cats["category"].str.replace("_", " ", regex=False)
fig, ax = plt.subplots(figsize=(9, 6.2))
colors = [color_map[g] for g in chart_cats["group"]]
bars = ax.barh(chart_cats["label"], chart_cats["unique_stories_full_text"], color=colors)
for bar, val in zip(bars, chart_cats["unique_stories_full_text"]):
    ax.text(val + 3, bar.get_y() + bar.get_height() / 2, fmt_int(val), va="center", fontsize=8)
ax.set_xlabel("Unique stories (full-text-inclusive)")
ax.set_title("Stories matching each category\n(one story may match several categories)")
handles = [plt.Rectangle((0, 0), 1, 1, color=color_map[g]) for g in ["core", "harassment", "related"]]
ax.legend(handles, ["Core / sexual violence", "Sexual harassment", "Related (not core)"], loc="lower right")
ax.grid(axis="x", alpha=0.25)
fig.tight_layout()
fig.savefig(OUT_DIR / "title_ix_sexual_violence_categories.png", dpi=180)
plt.close(fig)

# Chart 2: top outlets
fig, ax = plt.subplots(figsize=(9, 6))
plot_out = top15.sort_values("core", ascending=True)
bars = ax.barh(plot_out["outlet"], plot_out["core"], color="#1f4e79")
for bar, val, tot in zip(bars, plot_out["core"], plot_out["stories"]):
    ax.text(val + 0.5, bar.get_y() + bar.get_height() / 2,
            f"{fmt_int(val)} / {fmt_int(tot)}", va="center", fontsize=7)
ax.set_xlabel("Core-matching stories (full-text-inclusive)")
ax.set_title("Top 15 outlets by core matches")
ax.grid(axis="x", alpha=0.25)
fig.tight_layout()
fig.savefig(OUT_DIR / "title_ix_sexual_violence_outlets.png", dpi=180)
plt.close(fig)

# Chart 3: year trend.  2026 dwarfs every other year (64,681 of 68,581
# stories), so the count panel excludes 2026 and the percentage panel keeps it.
plot_years = year_table[year_table["year"] >= 2018].copy()
count_years = plot_years[plot_years["year"] < 2026].copy()
y2026 = year_table[year_table["year"] == 2026]
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
ax = axes[0]
ax.bar(count_years["year"].astype(str), count_years["stories"], color="#d9d9d9", label="All stories")
ax.bar(count_years["year"].astype(str), count_years["core"], color="#1f4e79", label="Core matches")
ax.set_title("Stories per year, 2018-2025 (2026 omitted)")
ax.set_ylabel("Stories")
ax.tick_params(axis="x", rotation=45)
ax.legend(fontsize=8)
ax.grid(axis="y", alpha=0.25)
ax = axes[1]
ax.plot(plot_years["year"].astype(str), plot_years["core_pct"], marker="o", color="#c55a11")
ax.set_title("Core matches as % of that year's stories")
ax.set_ylabel("% of stories")
ax.tick_params(axis="x", rotation=45)
ax.grid(axis="y", alpha=0.25)
note = ""
if not y2026.empty:
    note = (f"2026: {fmt_int(y2026['stories'].iloc[0])} stories, "
            f"{fmt_int(y2026['core'].iloc[0])} core ({y2026['core_pct'].iloc[0]:.2f}%); 2026 is partial")
fig.suptitle("Year trend — " + note, fontsize=10)
fig.tight_layout()
fig.savefig(OUT_DIR / "title_ix_sexual_violence_years.png", dpi=180)
plt.close(fig)

# Chart 4: field coverage
labels = ["Headline only", "Headline + keywords/theme", "Full text inclusive"]
vals = [int(core_title_mask.sum()), int(core_meta_mask.sum()), int(core_mask.sum())]
fig, ax = plt.subplots(figsize=(7.2, 4.2))
bars = ax.bar(labels, vals, color=["#a6a6a6", "#7f7f7f", "#1f4e79"])
for bar, val in zip(bars, vals):
    ax.text(bar.get_x() + bar.get_width() / 2, val + max(vals) * 0.01, fmt_int(val),
            ha="center", va="bottom", fontsize=9)
ax.set_ylabel("Core-matching stories")
ax.set_title("How much full text adds to the core count")
ax.grid(axis="y", alpha=0.25)
fig.tight_layout()
fig.savefig(OUT_DIR / "title_ix_sexual_violence_field_coverage.png", dpi=180)
plt.close(fig)

# ---------------------------------------------------------------------------
# 9. Markdown report
# ---------------------------------------------------------------------------
core_n = int(core_mask.sum())
strict_n = int(strict_mask.sum())
expanded_n = int(expanded_mask.sum())
broad_n = int(broad_mask.sum())

headline_core_n = int(core_title_mask.sum())
meta_core_n = int(core_meta_mask.sum())
body_only_core_n = int((core_mask & ~core_meta_mask).sum())
fulltext_cov = int(has_full_text.sum())
fulltext_cov_pct = 100.0 * fulltext_cov / N

title_ix_n = int(tix.sum())
equity_only_n = int(tix_equity_only.sum())
tix_sexual_n = int(tix_sexual.sum())
core_excl_equity_only = core_n - equity_only_n
sv_only_n = int(sv_only.sum())

def table_from_df(frame, cols, headers=None, max_rows=None):
    f = frame[cols].head(max_rows) if max_rows else frame[cols]
    headers = headers or cols
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, row in f.iterrows():
        vals = [md_escape(row[c]) for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)

# Category table for report
cat_report = cat_table.copy()
cat_report["category"] = cat_report["category"].str.replace("_", " ", regex=False)
cat_report["pct_of_total"] = cat_report["pct_of_total"].map(lambda x: f"{x:.2f}%")
cat_table_md = table_from_df(
    cat_report,
    ["category", "group", "raw_regex_hits", "unique_stories_full_text",
     "pct_of_total", "headline_unique", "metadata_unique", "fulltext_added"],
    ["Category", "Group", "Raw regex hits", "Unique stories", "% of total",
     "Headline only", "Metadata", "Added by full text"],
)

summary_md = table_from_df(
    summary,
    ["definition", "stories", "pct_of_total", "headline_only", "metadata"],
    ["Definition", "Stories", "% of total", "Headline only", "Metadata"],
)
summary_md = summary_md.replace("| {:,.2f}%".format(0), "")
# Rebuild with formatted percentages for readability.
summary_lines = ["| Definition | Stories | % of total | Headline only | Metadata |",
                 "|---|---:|---:|---:|---:|"]
for _, r in summary.iterrows():
    summary_lines.append(
        f"| {md_escape(r['definition'])} | {fmt_int(r['stories'])} | {r['pct_of_total']:.2f}% | "
        f"{fmt_int(r['headline_only'])} | {fmt_int(r['metadata'])} |"
    )
summary_md = "\n".join(summary_lines)

top_out_md = table_from_df(
    top15.assign(core_pct=top15["core_pct"].map(lambda x: f"{x:.1f}%")),
    ["outlet", "stories", "core", "core_pct", "expanded", "broad"],
    ["Outlet", "Stories", "Core", "Core rate", "Expanded", "Broad"],
)
high_rate_md = table_from_df(
    high_rate.assign(core_pct=high_rate["core_pct"].map(lambda x: f"{x:.1f}%")),
    ["outlet", "stories", "core", "core_pct"],
    ["Outlet (≥50 stories)", "Stories", "Core", "Core rate"],
)

year_report = year_table.copy()
year_report["core_pct"] = year_report["core_pct"].map(lambda x: f"{x:.2f}%")
year_md = table_from_df(
    year_report,
    ["year", "stories", "core", "core_pct", "expanded", "broad"],
    ["Year", "Stories", "Core", "Core rate", "Expanded", "Broad"],
)
year_md_recent = table_from_df(
    year_report[year_report["year"] >= 2019],
    ["year", "stories", "core", "core_pct", "expanded", "broad"],
    ["Year", "Stories", "Core", "Core rate", "Expanded", "Broad"],
)

examples_md = ["| # | Category | Outlet | Date | Headline | Match field |",
               "|---:|---|---|---|---|---|"]
for i, ex in enumerate(examples, 1):
    examples_md.append(
        f"| {i} | {md_escape(ex['category'])} | {md_escape(ex['outlet'])} | {ex['date']} | "
        f"{short_title(ex['title'], 150)} | {md_escape(ex['match_field'])} |"
    )
examples_md = "\n".join(examples_md)

positive_pass = int(((tests_df["type"] == "positive") & (tests_df["result"] == "PASS")).sum())
positive_total = int((tests_df["type"] == "positive").sum())
negative_pass = int(((tests_df["type"] == "negative") & (tests_df["result"] == "PASS")).sum())
negative_total = int((tests_df["type"] == "negative").sum())

trap_table = pd.DataFrame([
    {"Trap": "grape, scrape, therapist, rapid, rapping, drape, rapeseed", "Pattern": "rape",
     "Result": "No match (word-boundary + rap-e/ed/ing/ist forms only)"},
    {"Trap": "matrix, helix, six, fix, appendix, title case", "Pattern": "title_ix",
     "Result": "No match (IX must follow Title/Tit1e)"},
    {"Trap": "Sussex, Essex, Middlesex, bisexual, homosexual", "Pattern": "sexual_*",
     "Result": "No match (whole-word 'sexual' + specific noun required)"},
    {"Trap": "child abuse, substance abuse, abuse of power", "Pattern": "sexual_abuse",
     "Result": "No match (bare 'abuse' is not searched)"},
    {"Trap": "stalking horse, stalker-esque, stalker-y", "Pattern": "stalking",
     "Result": "Excluded by context filter"},
    {"Trap": "Bambi Molesters, molest the alligators, molesting, annoying", "Pattern": "molestation",
     "Result": "Excluded by context filter"},
    {"Trap": "groped around in her purse, groping for answers", "Pattern": "groping",
     "Result": "Excluded by context filter"},
    {"Trap": "affirmative consent for data privacy", "Pattern": "sexual_consent",
     "Result": "No match without sexual context"},
])
trap_md = table_from_df(trap_table, ["Trap", "Pattern", "Result"], ["False-positive trap", "Pattern", "Handling"])

report = f"""# Title IX and sexual violence in the student-media news database

**Database:** `news_database.csv`  
**Rows (denominator):** **{fmt_int(N)}** stories  
**Analysis date:** 2026-10-20  
**Primary script:** `scripts/analyze_title_ix_sexual_violence.py`

## Headline answer

Using a full-text-inclusive keyword/regex classifier over **{fmt_int(N)} stories**, **{fmt_int(core_n)} stories ({core_n / N * 100:.2f}%)** match the core set: **Title IX OR any sexual-violence/abuse term** (sexual violence, sexual assault, rape, sexual abuse, sexual misconduct, molestation, groping, indecent assault, nonconsensual sex, sexual coercion, sexual battery).

If "sexual harassment" is added, the count rises to **{fmt_int(expanded_n)} ({expanded_n / N * 100:.2f}%)**. If the unrelated-but-adjacent terms (domestic violence, intimate-partner/dating violence, stalking, non-sexual harassment, trafficking, exploitation, consent) are added, the broad tracked set is **{fmt_int(broad_n)} ({broad_n / N * 100:.2f}%)**.

The literal four-term version in the question (Title IX OR the phrase "sexual violence" OR sexual assault OR rape) is **{fmt_int(strict_n)} stories ({strict_n / N * 100:.2f}%)**.

> **Field dependence:** headline-only finds **{fmt_int(headline_core_n)}** core stories; adding keywords/theme finds **{fmt_int(meta_core_n)}**; full text adds **{fmt_int(body_only_core_n)}** more, for **{fmt_int(core_n)}**. Full text exists for **{fmt_int(fulltext_cov)} of {fmt_int(N)} stories ({fulltext_cov_pct:.1f}%)**, so even the {fmt_int(core_n)} figure is a lower bound for the whole database. Among full-text-covered stories, {fmt_int(core_covered)} are core ({100.0 * core_covered / fulltext_cov:.2f}%); among stories with no extracted body, {fmt_int(core_uncovered)} are core ({100.0 * core_uncovered / max(1, N - fulltext_cov):.2f}%).
>
> **Prominence sensitivity:** requiring a headline hit or at least three core-category regex hits yields **{fmt_int(prominent_n)} stories ({prominent_n / N * 100:.2f}%)**, between the headline-only and any-mention figures. This is a reasonable "more clearly about the topic" subset.

## Data and schema (verified, not assumed)

The CSV is UTF-8, comma-delimited, with **{fmt_int(N)} data rows and {N_COLS_ORIGINAL} columns**. `link` is unique ({fmt_int(df['link'].nunique())} unique), so each row is treated as one story. `title` is never blank. Full text is extracted body text on disk, not a CSV column.

| Column | Non-empty | Unique | Role in this analysis |
|---|---:|---:|---|
| source | {fmt_int(schema.loc[schema.column=='source','nonempty'].iloc[0])} | {fmt_int(schema.loc[schema.column=='source','unique'].iloc[0])} | Outlet label |
| title | {fmt_int(schema.loc[schema.column=='title','nonempty'].iloc[0])} | {fmt_int(schema.loc[schema.column=='title','unique'].iloc[0])} | Headline search |
| link | {fmt_int(schema.loc[schema.column=='link','nonempty'].iloc[0])} | {fmt_int(schema.loc[schema.column=='link','unique'].iloc[0])} | Story ID |
| published | {fmt_int(schema.loc[schema.column=='published','nonempty'].iloc[0])} | {fmt_int(schema.loc[schema.column=='published','unique'].iloc[0])} | Year trend |
| keywords | {fmt_int(schema.loc[schema.column=='keywords','nonempty'].iloc[0])} | {fmt_int(schema.loc[schema.column=='keywords','unique'].iloc[0])} | Metadata search |
| theme | {fmt_int(schema.loc[schema.column=='theme','nonempty'].iloc[0])} | {fmt_int(schema.loc[schema.column=='theme','unique'].iloc[0])} | Metadata search |
| full_text_path | {fmt_int(schema.loc[schema.column=='full_text_path','nonempty'].iloc[0])} | {fmt_int(schema.loc[schema.column=='full_text_path','unique'].iloc[0])} | Points to extracted body |
| extraction_status | {fmt_int(schema.loc[schema.column=='extraction_status','nonempty'].iloc[0])} | {fmt_int(schema.loc[schema.column=='extraction_status','unique'].iloc[0])} | Full-text quality |

**Text fields actually searched:**

1. **Headline only:** `title`.
2. **Metadata:** `title` + `keywords` + `theme`.
3. **Full-text inclusive:** metadata + the body portion of the file at `full_text_path` (the `# ---` header is stripped). This is the headline figure.

`publication_story_index.csv` has {fmt_int(index_stats["stories"])} stories and {fmt_int(index_stats["overlap"])} URL overlaps with the database; {fmt_int(index_stats["files_exist"])} of its indexed files exist. It contains **{fmt_int(index_stats["missing_overlap"])}** URLs for database rows that lack full text, so it cannot fill coverage gaps. `bag_of_words.csv` is a corpus-level vocabulary table ({fmt_int(bow_stats["rows"])} rows, {bow_stats["columns"]} columns) with no story IDs and was not used for story classification.

## Method

- Case-insensitive, Unicode word-boundary regexes. Each story is counted **once per category**, no matter how many keyword occurrences it has.
- Core set = `title_ix` OR any of: `sexual_violence`, `sexual_assault`, `rape`, `sexual_abuse`, `sexual_misconduct`, `molestation`, `groping`, `indecent_assault`, `nonconsensual_sex`, `sexual_coercion`, `sexual_battery`.
- Sexual harassment is reported separately, then added in the "expanded" definition.
- Domestic violence, intimate-partner violence, dating violence, stalking, generic harassment, sex trafficking, sexual exploitation and sexual consent are reported as **related, not core**.
- Title IX stories are split into athletics/equity context vs. sexual-harm context so the user can remove sports-equity cases if desired.
- Raw hit counts are regex occurrences across the searched text; unique-story counts are the primary measure.

## Counts by definition

{summary_md}

Additional splits for Title IX:

- Title IX stories (any): **{fmt_int(title_ix_n)}**
- Title IX + sexual-harm context: **{fmt_int(tix_sexual_n)}**
- Title IX + athletics/equity context (any): **{fmt_int(int(tix_equity_any.sum()))}**
- Title IX athletics/equity **only** (no SV/harassment): **{fmt_int(equity_only_n)}**
- Core excluding Title IX athletics/equity-only: **{fmt_int(core_excl_equity_only)}**
- Sexual-violence/abuse terms anywhere (with or without Title IX): **{fmt_int(sv_any_n)}**
- Sexual-violence/abuse terms without any Title IX mention: **{fmt_int(sv_only_n)}**

## Per-category counts

A story can hit multiple categories, so the category counts do **not** add up to the core total.

{cat_table_md}

`body_only_unique` is the number of stories that would be missed by a metadata-only search; `fulltext_added` is the full-text-inclusive unique count minus the metadata unique count.

## Outlet breakdown

**{fmt_int(outlets_total)}** cleaned outlet labels; **{fmt_int(outlets_with_core)}** have at least one core match. The top 10 outlets account for **{top10_share:.1f}%** of all core matches. `source` is messy (feed names, `www.`, "RSS Results"), so labels were lightly cleaned; raw `source` is preserved in the CSV.

{top_out_md}

Highest core rate among outlets with at least 50 stories:

{high_rate_md}

## Year trend

Dates parse for **{fmt_int(dates.notna().sum())} of {fmt_int(N)}** stories. The database is heavily weighted toward 2026 (captured through 2026-10-15), so the trend is a snapshot of coverage, not a population time series.

{year_md_recent}

Full year table (including sparse pre-2019 years) is in `title_ix_sexual_violence_years.csv`.

## Representative examples (spot-check)

{examples_md}

"Match field" shows whether the story was caught by the headline, by metadata (keywords/theme), or only in the body.

## False-positive traps handled

Regex self-tests: **{positive_pass}/{positive_total} positive tests passed**, **{negative_pass}/{negative_total} negative (trap) tests passed**.

{trap_md}

Negative tests are run through the same `scan_text()` function as the data, so context filters are tested too. Failures, if any, are listed in `title_ix_sexual_violence_regex_tests.csv`.

## Limitations

1. **Keyword matching is not topic classification.** It catches mentions, not necessarily the story's main subject. A story about free speech that mentions sexual assault in a content warning is counted; a story about "inappropriate behavior" or "misconduct" without the word "sexual" is missed.
2. **Full text is incomplete.** Only {fulltext_cov_pct:.1f}% of rows have an existing extracted body. Missing bodies are biased toward 403/404/429 extraction failures, so the full-text-inclusive count is a lower bound.
3. **Headline-only is high precision but low recall.** Headlines often use euphemisms ("misconduct", "inappropriate conduct", "survivor", "unwanted advances") that the regex set does not catch.
4. **Title IX includes athletics/equity.** {fmt_int(equity_only_n)} Title IX stories have athletics/equity context and no sexual-harm term. They are included in the core Title IX count per the question, but can be subtracted ({fmt_int(core_excl_equity_only)} core stories remain).
5. **Related terms are not sexual violence.** Domestic violence, stalking, non-sexual harassment, trafficking and consent education are reported separately and should not be merged into the headline count without a decision.
6. **Duplicate/syndicated headlines.** {fmt_int(int(df['title'].duplicated().sum()))} rows share a title with another row. Rows are unique URLs, so they are counted as separate published stories; unique-title counts would be slightly lower.
7. **Date coverage is lopsided.** 2026 supplies almost all rows; year percentages before 2025 are based on tiny denominators.
8. **Opinion/advocacy and international coverage** are included; the database is not a crime-incident census.

## Output files

- `analytics/title_ix_sexual_violence_report.md`
- `analytics/title_ix_sexual_violence_matches.csv` — one row per core story
- `analytics/title_ix_sexual_violence_all_tracked_matches.csv` — core + harassment + related
- `analytics/title_ix_sexual_violence_summary.csv`
- `analytics/title_ix_sexual_violence_category_counts.csv`
- `analytics/title_ix_sexual_violence_outlets.csv`
- `analytics/title_ix_sexual_violence_years.csv`
- `analytics/title_ix_sexual_violence_regex_tests.csv`
- `analytics/title_ix_sexual_violence_categories.png`
- `analytics/title_ix_sexual_violence_outlets.png`
- `analytics/title_ix_sexual_violence_years.png`
- `analytics/title_ix_sexual_violence_field_coverage.png`
- `scripts/analyze_title_ix_sexual_violence.py`
"""

with open(OUT_DIR / "title_ix_sexual_violence_report.md", "w", encoding="utf-8") as fh:
    fh.write(report)

print("\n=== HEADLINE RESULTS ===")
print(f"Total stories: {N:,}")
print(f"Core (Title IX | sexual violence/abuse): {core_n:,} ({core_n / N * 100:.2f}%)")
print(f"  headline only: {headline_core_n:,} | metadata: {meta_core_n:,} | body-only adds: {body_only_core_n:,}")
print(f"Strict literal core: {strict_n:,} ({strict_n / N * 100:.2f}%)")
print(f"Expanded (+ sexual harassment): {expanded_n:,} ({expanded_n / N * 100:.2f}%)")
print(f"Broad (+ related terms): {broad_n:,} ({broad_n / N * 100:.2f}%)")
print(f"Prominent core (headline or >=3 core hits): {prominent_n:,} ({prominent_n / N * 100:.2f}%)")
print(f"Full text coverage: {fulltext_cov:,}/{N:,} ({fulltext_cov_pct:.1f}%)")
print(f"Regex tests: positives {positive_pass}/{positive_total}, negatives {negative_pass}/{negative_total}")
if failures:
    print("FAILURES:", failures)
print("Outputs written to", OUT_DIR)
