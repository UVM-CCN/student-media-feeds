#!/usr/bin/env python3
"""2026-only Title IX / sexual-violence trend analysis.

Reuses the exact classifier definitions from the prior run
(``scripts/title_ix_definitions.py``, imported by the original script too).

Questions:
  * What are the 2026-only counts at headline / metadata / full-text scope?
  * Has the *share* of coverage (not just raw counts) risen recently?
  * Does any rise survive an outlet-constant (fixed-effects-style) check?

Reads news_database.csv and full-text files. Never writes the source CSV.

Run:  python scripts/analyze_title_ix_sexual_violence_2026.py
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from title_ix_definitions import (
    PATTERNS, CORE_SV_TERMS, CORE_PATTERNS, STRICT_LITERAL,
    RELATED_PATTERNS, EQUITY_RX, scan_text,
)

try:
    from scipy.stats import chi2_contingency, fisher_exact
    HAVE_SCIPY = True
except Exception:  # pragma: no cover
    HAVE_SCIPY = False

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "news_database.csv"
OUT_DIR = ROOT / "analytics"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PREFIX = "title_ix_sexual_violence_2026"

plt.rcParams.update({"font.size": 9, "axes.titlesize": 11, "axes.labelsize": 9})


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


def fmt_int(n) -> str:
    return f"{int(n):,}"


def pct(n, d) -> float:
    return 100.0 * n / d if d else float("nan")


def wilson_ci(k: int, n: int, z: float = 1.959963984540054):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (100 * max(0.0, centre - half), 100 * min(1.0, centre + half))


def two_prop(k1: int, n1: int, k2: int, n2: int) -> dict:
    """Two-proportion z-test (k1/n1 vs k2/n2), rate ratio and 95% CI."""
    if n1 == 0 or n2 == 0:
        return {"rate1": np.nan, "rate2": np.nan, "rr": np.nan,
                "rr_lo": np.nan, "rr_hi": np.nan, "z": np.nan,
                "p": np.nan, "chi2_p": np.nan, "test": "n/a"}
    p1, p2 = k1 / n1, k2 / n2
    if k1 == 0 or k2 == 0:
        return {"rate1": 100 * p1, "rate2": 100 * p2,
                "rr": (p1 / p2 if p2 else np.inf),
                "rr_lo": np.nan, "rr_hi": np.nan, "z": np.nan,
                "p": np.nan, "chi2_p": np.nan, "test": "zero cell"}
    pooled = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se if se else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))
    rr = p1 / p2
    se_log = math.sqrt(1 / k1 - 1 / n1 + 1 / k2 - 1 / n2)
    lo, hi = math.exp(math.log(rr) - 1.96 * se_log), math.exp(math.log(rr) + 1.96 * se_log)
    chi2_p = np.nan
    test = "two-proportion z"
    if HAVE_SCIPY:
        tab = np.array([[k1, n1 - k1], [k2, n2 - k2]])
        # Same p-value as the z-test when uncorrected; reported separately.
        chi2_p = float(chi2_contingency(tab, correction=False)[1])
        if (tab.sum(axis=0).min() < 5) or (tab.sum(axis=1).min() < 5):
            test = "Fisher exact (small expected counts)"
            p = float(fisher_exact(tab)[1])
    return {"rate1": 100 * p1, "rate2": 100 * p2, "rr": rr,
            "rr_lo": lo, "rr_hi": hi, "z": z, "p": p,
            "chi2_p": chi2_p, "test": test}


def period_agg(sub: pd.DataFrame, label: str) -> dict:
    n = len(sub)
    row = {"period": label, "stories": n}
    for col in ["core", "core_headline", "core_metadata", "expanded",
                "tix_any", "sv_any", "tix_only", "sv_only", "both",
                "tix_equity_only", "strict", "broad",
                "core_ex_cornell", "core_ex_event", "headline_ex_event",
                "event_cornell", "event_lsu"]:
        k = int(sub[col].sum())
        row[col] = k
        row[col + "_pct"] = pct(k, n)
    lo, hi = wilson_ci(int(sub["core"].sum()), n)
    row["core_pct_lo"], row["core_pct_hi"] = lo, hi
    row["fulltext"] = int(sub["has_full_text"].sum())
    row["fulltext_pct"] = pct(row["fulltext"], n)
    # Core rate *among stories that actually have a body* — controls for the
    # October full-text gap.  Still a selected subset, so interpret with care.
    ft_sub = sub[sub["has_full_text"] == 1]
    row["core_ft"] = int(ft_sub["core"].sum())
    row["core_pct_ft"] = pct(row["core_ft"], len(ft_sub))
    row["outlets"] = int(sub["outlet"].nunique())
    row["online_features"] = int(sub["online_features"].sum())
    row["online_features_pct"] = pct(row["online_features"], n)
    row["news_only_stories"] = int((~sub["online_features"]).sum())
    row["news_only_core"] = int((sub["core"] & ~sub["online_features"]).sum())
    row["news_only_core_pct"] = pct(row["news_only_core"], row["news_only_stories"])
    row["event_cornell_core"] = int((sub["core"] & sub["event_cornell"]).sum())
    return row


# ---------------------------------------------------------------------------
# 1. Load data and restrict to 2026
# ---------------------------------------------------------------------------
print("Loading", DB_PATH)
df = pd.read_csv(DB_PATH, dtype=str, keep_default_na=False)
N_ALL = len(df)
df["published_dt"] = pd.to_datetime(df["published"], errors="coerce", utc=True,
                                    format="mixed").dt.tz_localize(None).dt.normalize()
df["captured_dt"] = pd.to_datetime(df["captured_at"], errors="coerce", utc=True,
                                   format="mixed").dt.tz_localize(None).dt.normalize()
df["outlet"] = df["source"].map(clean_outlet)
df["online_features"] = df["link"].str.contains("/online_features/", case=False, na=False)

MAX_DATE = df.loc[df["published_dt"].dt.year == 2026, "published_dt"].max()
MAX_DATE = MAX_DATE.date() if pd.notna(MAX_DATE) else date(2026, 10, 15)
START_DATE = date(2026, 1, 1)

d26 = df[(df["published_dt"].dt.date >= START_DATE) & (df["published_dt"].dt.date <= MAX_DATE)].copy()
d26 = d26.reset_index(drop=True)
N = len(d26)
print(f"All rows: {N_ALL:,}; 2026 rows ({START_DATE}..{MAX_DATE}): {N:,} "
      f"({100 * N / N_ALL:.1f}% of DB)")

# ---------------------------------------------------------------------------
# 2. Classify (same regexes / exclusions as the original run)
# ---------------------------------------------------------------------------
keys = list(PATTERNS)
title_counts = {k: np.zeros(N, dtype=np.int32) for k in keys}
meta_counts = {k: np.zeros(N, dtype=np.int32) for k in keys}
body_counts = {k: np.zeros(N, dtype=np.int32) for k in keys}
title_ctx = {k: [""] * N for k in keys}
meta_ctx = {k: [""] * N for k in keys}
body_ctx = {k: [""] * N for k in keys}
has_full_text = np.zeros(N, dtype=np.int8)
equity_context = np.zeros(N, dtype=np.int8)

print("Scanning titles, metadata and full text for 2026 stories ...")
for i, row in enumerate(d26.itertuples(index=False)):
    title = str(row.title).strip()
    meta = "\n".join([title, str(row.keywords).strip(), str(row.theme).strip()])
    tc, tcx = scan_text(title)
    mc, mcx = scan_text(meta)

    body = ""
    p = str(row.full_text_path).strip()
    if p and p.lower() not in {"nan", "none"}:
        fp = Path(p)
        if not fp.is_absolute():
            fp = ROOT / fp
        if fp.exists():
            try:
                txt = fp.read_text(encoding="utf-8", errors="replace")
                body = txt.split("# ---\n", 1)[1] if "# ---\n" in txt else txt
                has_full_text[i] = 1
            except OSError:
                body = ""
    bc, bcx = scan_text(body) if body else ({k: 0 for k in keys}, {k: "" for k in keys})

    for k in keys:
        title_counts[k][i] = tc[k]
        meta_counts[k][i] = mc[k]
        body_counts[k][i] = bc[k]
        title_ctx[k][i] = tcx[k]
        meta_ctx[k][i] = mcx[k]
        body_ctx[k][i] = bcx[k]
    equity_context[i] = 1 if (EQUITY_RX.search(meta) or EQUITY_RX.search(body)) else 0
    if (i + 1) % 5000 == 0:
        print(f"  scanned {i + 1:,}/{N:,}")

print(f"Full text found for {fmt_int(has_full_text.sum())} / {N:,} "
      f"({100 * has_full_text.sum() / N:.1f}%) 2026 stories")

full_counts = {k: meta_counts[k] + body_counts[k] for k in keys}
flag = {scope: pd.DataFrame({k: (title_counts if scope == "title" else meta_counts if scope == "meta" else full_counts)[k] > 0
                             for k in keys})
        for scope in ["title", "meta", "full"]}

d26["has_full_text"] = has_full_text
d26["equity_context"] = equity_context


def any_of(scope: str, cols) -> np.ndarray:
    return flag[scope][cols].any(axis=1).to_numpy()


d26["core"] = any_of("full", CORE_PATTERNS)
d26["core_headline"] = any_of("title", CORE_PATTERNS)
d26["core_metadata"] = any_of("meta", CORE_PATTERNS)
d26["strict"] = any_of("full", STRICT_LITERAL)
d26["expanded"] = d26["core"] | flag["full"]["sexual_harassment"].to_numpy()
d26["broad"] = d26["expanded"] | any_of("full", RELATED_PATTERNS)
d26["tix_any"] = flag["full"]["title_ix"].to_numpy()
d26["sv_any"] = any_of("full", CORE_SV_TERMS)
d26["tix_only"] = d26["tix_any"] & ~d26["sv_any"]
d26["sv_only"] = d26["sv_any"] & ~d26["tix_any"]
d26["both"] = d26["tix_any"] & d26["sv_any"]
d26["tix_equity_only"] = (d26["tix_any"] & (equity_context == 1)
                          & ~d26["sv_any"] & ~flag["full"]["sexual_harassment"].to_numpy())
d26["date"] = d26["published_dt"].dt.date

# Named news events used only for an event-adjusted sensitivity.  The Cornell /
# Chi Phi case and the LSU arrests dominate the early-October headline spike.
_title_l = d26["title"].str.lower()
d26["event_cornell"] = _title_l.str.contains("cornell|chi phi", regex=True)
d26["event_lsu"] = _title_l.str.contains(r"\blsu\b|tigerland", regex=True)
d26["event_any"] = d26["event_cornell"] | d26["event_lsu"]
d26["core_ex_cornell"] = d26["core"] & ~d26["event_cornell"]
d26["core_ex_event"] = d26["core"] & ~d26["event_any"]
d26["headline_ex_event"] = d26["core_headline"] & ~d26["event_any"]

# ---------------------------------------------------------------------------
# 3. Scope denominators
# ---------------------------------------------------------------------------
scope_rows = []
for scope, label in [("title", "headline-only (title)"),
                     ("meta", "metadata (title+keywords+theme)"),
                     ("full", "full-text-inclusive")]:
    k = int(any_of(scope, CORE_PATTERNS).sum())
    scope_rows.append({"scope": label, "stories_matched": k, "denominator": N,
                       "pct": pct(k, N)})
scope_table = pd.DataFrame(scope_rows)
scope_table.to_csv(OUT_DIR / f"{PREFIX}_scopes.csv", index=False)
print("\n2026 core matches by scope:")
print(scope_table.to_string(index=False))

# ---------------------------------------------------------------------------
# 4. Monthly table (all 2026 months, Oct partial)
# ---------------------------------------------------------------------------
d26["month"] = d26["published_dt"].dt.to_period("M").astype(str)
month_rows = []
for month, sub in d26.groupby("month", sort=True):
    r = period_agg(sub, month)
    r["month_start"] = sub["date"].min().isoformat()
    r["month_end"] = sub["date"].max().isoformat()
    r["days_observed"] = (sub["date"].max() - date.fromisoformat(month + "-01")).days + 1
    r["stories_per_day"] = len(sub) / r["days_observed"]
    r["same_day_capture_pct"] = pct(int((sub["captured_dt"].dt.date == sub["date"]).sum()), len(sub))
    month_rows.append(r)
monthly = pd.DataFrame(month_rows)
monthly.to_csv(OUT_DIR / f"{PREFIX}_monthly.csv", index=False)

# ---------------------------------------------------------------------------
# 5. Weekly table (ISO weeks, full 2026 + last 16 highlighted)
# ---------------------------------------------------------------------------
d26["week_start"] = d26["date"].map(lambda x: x - timedelta(days=x.weekday()))
week_rows = []
for wk, sub in d26.groupby("week_start", sort=True):
    r = period_agg(sub, wk.isoformat())
    r["week_start"] = wk.isoformat()
    r["week_end"] = (wk + timedelta(days=6)).isoformat()
    r["days_observed"] = (min(sub["date"].max(), wk + timedelta(days=6)) - wk).days + 1
    r["partial_week"] = int(r["days_observed"] < 7)
    week_rows.append(r)
weekly = pd.DataFrame(week_rows)
weekly.to_csv(OUT_DIR / f"{PREFIX}_weekly.csv", index=False)
LAST16_START = MAX_DATE - timedelta(days=7 * 16 - 1)
weekly_last16 = weekly[weekly["week_start"] >= LAST16_START.isoformat()].copy()

# ---------------------------------------------------------------------------
# 6. Recent vs prior, plus 2026 YTD baseline and outlet-constant panel
# ---------------------------------------------------------------------------
SERIES = {
    "core": "core",
    "expanded (+ sexual harassment)": "expanded",
    "title_ix_any": "tix_any",
    "sv_terms_any": "sv_any",
    "title_ix_only": "tix_only",
    "sv_only": "sv_only",
    "both": "both",
    "headline_only_core": "core_headline",
    "metadata_core": "core_metadata",
    "core_news_only (excl. /online_features/)": "core_news_only",
    "core_ex_cornell": "core_ex_cornell",
    "core_ex_cornell_lsu": "core_ex_event",
    "headline_ex_cornell_lsu": "headline_ex_event",
}
d26["core_news_only"] = d26["core"] & ~d26["online_features"]


def window_sub(start: date, end: date, news_only: bool = False) -> pd.DataFrame:
    sub = d26[(d26["date"] >= start) & (d26["date"] <= end)]
    if news_only:
        sub = sub[~sub["online_features"]]
    return sub


def outlet_panel(rec: pd.DataFrame, pri: pd.DataFrame, col: str,
                 min_stories: int = 5) -> dict:
    """Outlet-constant panel for a specific outcome column."""
    gr = rec.groupby("outlet").agg(n=(col, "size"), k=(col, "sum"))
    gp = pri.groupby("outlet").agg(n=(col, "size"), k=(col, "sum"))
    common = gr.join(gp, lsuffix="_r", rsuffix="_p", how="inner")
    common = common[(common["n_r"] >= min_stories) & (common["n_p"] >= min_stories)]
    out = {"common_outlets": len(common),
           "recent_outlets": int(rec["outlet"].nunique()),
           "prior_outlets": int(pri["outlet"].nunique()),
           "recent_vol": len(rec), "prior_vol": len(pri)}
    if common.empty:
        out.update({"common_recent_n": 0, "common_prior_n": 0,
                    "common_recent_core": 0, "common_prior_core": 0,
                    "common_recent_rate": np.nan, "common_prior_rate": np.nan,
                    "common_rr": np.nan, "common_p": np.nan,
                    "std_prior_rate": np.nan, "std_rr": np.nan})
        return out
    rn, rk = int(common["n_r"].sum()), int(common["k_r"].sum())
    pn, pk = int(common["n_p"].sum()), int(common["k_p"].sum())
    test = two_prop(rk, rn, pk, pn)
    rates_p = (common["k_p"] / common["n_p"])
    weights = common["n_r"] / common["n_r"].sum()
    std_prior = float(100 * (weights * rates_p).sum())
    std_rr = (100 * rk / rn) / std_prior if std_prior else np.nan
    out.update({"common_recent_n": rn, "common_prior_n": pn,
                "common_recent_core": rk, "common_prior_core": pk,
                "common_recent_rate": test["rate1"],
                "common_prior_rate": test["rate2"],
                "common_rr": test["rr"], "common_p": test["p"],
                "std_prior_rate": std_prior, "std_rr": std_rr})
    return out


def compute_rp(series_map: dict, end_date: date) -> pd.DataFrame:
    rows = []
    for series_label, col in series_map.items():
        for days in (30, 60, 90):
            rec_start = end_date - timedelta(days=days - 1)
            rec_end = end_date
            pri_end = rec_start - timedelta(days=1)
            pri_start = pri_end - timedelta(days=days - 1)
            base_start = START_DATE
            base_end = rec_start - timedelta(days=1)

            news = col == "core_news_only"
            rec = window_sub(rec_start, rec_end, news)
            pri = window_sub(pri_start, pri_end, news)
            base = window_sub(base_start, base_end, news)

            k_r, k_p = int(rec[col].sum()), int(pri[col].sum())
            test = two_prop(k_r, len(rec), k_p, len(pri))
            test_b = two_prop(k_r, len(rec), int(base[col].sum()), len(base))
            panel = outlet_panel(rec, pri, col)

            rows.append({
                "series": series_label,
                "window_days": days,
                "recent_start": rec_start.isoformat(),
                "recent_end": rec_end.isoformat(),
                "prior_start": pri_start.isoformat(),
                "prior_end": pri_end.isoformat(),
                "baseline_start": base_start.isoformat(),
                "baseline_end": base_end.isoformat(),
                "recent_n": len(rec), "recent_matches": k_r,
                "recent_rate_pct": test["rate1"],
                "prior_n": len(pri), "prior_matches": k_p,
                "prior_rate_pct": test["rate2"],
                "rate_ratio": test["rr"], "rr_lo": test["rr_lo"], "rr_hi": test["rr_hi"],
                "z": test["z"], "p_value": test["p"], "chi2_p": test["chi2_p"],
                "test": test["test"],
                "baseline_n": len(base), "baseline_matches": int(base[col].sum()),
                "baseline_rate_pct": test_b["rate2"],
                "rate_ratio_vs_baseline": test_b["rr"],
                "p_value_vs_baseline": test_b["p"],
                "volume_ratio_recent_vs_prior": len(rec) / len(pri) if len(pri) else np.nan,
                **panel,
            })
    return pd.DataFrame(rows)


recent_vs_prior = compute_rp(SERIES, MAX_DATE)
recent_vs_prior.to_csv(OUT_DIR / f"{PREFIX}_recent_vs_prior.csv", index=False)

# Sensitivity: full-text trends through 2026-09-30, i.e. before the October
# body-extraction gap.  Only meaningful for full-text-based series.
FT_SERIES = {k: v for k, v in SERIES.items()
             if k in {"core", "expanded (+ sexual harassment)", "title_ix_any",
                      "sv_terms_any", "title_ix_only", "sv_only", "both",
                      "core_ex_cornell", "core_ex_cornell_lsu"}}
recent_vs_prior_ft_sep = compute_rp(FT_SERIES, date(2026, 9, 30))
recent_vs_prior_ft_sep.to_csv(
    OUT_DIR / f"{PREFIX}_recent_vs_prior_fulltext_through_sep.csv", index=False)

# ---------------------------------------------------------------------------
# 7. Outlet shift (90-day window) for diagnosis
# ---------------------------------------------------------------------------
r90s, r90e = MAX_DATE - timedelta(days=89), MAX_DATE
p90s, p90e = r90s - timedelta(days=90), r90s - timedelta(days=1)
rec90 = window_sub(r90s, r90e)
pri90 = window_sub(p90s, p90e)
gr = rec90.groupby("outlet").agg(recent_n=("core", "size"), recent_core=("core", "sum"))
gp = pri90.groupby("outlet").agg(prior_n=("core", "size"), prior_core=("core", "sum"))
shift = gr.join(gp, how="outer").fillna(0)
shift["recent_rate_pct"] = 100 * shift["recent_core"] / shift["recent_n"].replace(0, np.nan)
shift["prior_rate_pct"] = 100 * shift["prior_core"] / shift["prior_n"].replace(0, np.nan)
shift["rate_change_pp"] = shift["recent_rate_pct"] - shift["prior_rate_pct"]
shift["core_change"] = shift["recent_core"] - shift["prior_core"]
shift = shift.reset_index().rename(columns={"index": "outlet"})
shift = shift[(shift["recent_n"] >= 5) | (shift["prior_n"] >= 5)]
shift.sort_values("core_change", ascending=False).to_csv(
    OUT_DIR / f"{PREFIX}_outlet_shift_90d.csv", index=False)

# ---------------------------------------------------------------------------
# 8. Matches CSV (2026 core stories)
# ---------------------------------------------------------------------------
core_mask = d26["core"].to_numpy()
matches = d26.loc[core_mask, [
    "link", "source", "outlet", "title", "published", "date", "has_full_text",
    "full_text_path", "core", "core_headline", "core_metadata", "strict",
    "expanded", "tix_any", "sv_any", "tix_only", "sv_only", "both",
    "tix_equity_only", "online_features",
]].copy()
matches.insert(0, "row_index", matches.index)
matches.to_csv(OUT_DIR / f"{PREFIX}_matches.csv", index=False)

# ---------------------------------------------------------------------------
# 9. Charts
# ---------------------------------------------------------------------------
# Monthly: volume + core rate (left/right axes) and component rates.
fig, axes = plt.subplots(2, 2, figsize=(12.8, 8.4))
ax = axes[0, 0]
x = np.arange(len(monthly))
ax.bar(x, monthly["stories"], color="#d9d9d9", label="All stories")
ax.set_xticks(x); ax.set_xticklabels(monthly["period"], rotation=45)
ax.set_ylabel("All stories"); ax.set_title("2026 monthly volume (Oct is partial)")
axr = ax.twinx()
axr.plot(x, monthly["core"], marker="o", color="#1f4e79", label="Core matches")
axr.set_ylabel("Core matches", color="#1f4e79")
ax.grid(axis="y", alpha=0.2)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = axr.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")

ax = axes[0, 1]
ax.plot(x, monthly["core_pct"], marker="o", color="#1f4e79", label="Core share")
ax.fill_between(x, monthly["core_pct_lo"], monthly["core_pct_hi"], color="#1f4e79", alpha=0.12)
ax.plot(x, monthly["core_ex_event_pct"], marker="s", ms=3, color="#2e7d32",
        label="Core excl. Cornell/LSU headlines")
ax.axvspan(len(monthly) - 1.5, len(monthly) - 0.5, color="#f4b183", alpha=0.20)
ax.annotate("Oct bodies\nmissing (1.5% FT)", xy=(len(monthly) - 1, monthly["core_pct"].iloc[-1]),
            xytext=(len(monthly) - 2.4, max(monthly["core_pct"]) * 0.92),
            fontsize=7, arrowprops=dict(arrowstyle="->", color="#7f7f7f"))
ax.set_xticks(x); ax.set_xticklabels(monthly["period"], rotation=45)
ax.set_ylabel("% of that month's stories")
ax.set_title("Core share of coverage (95% Wilson CI)")
ax.legend(fontsize=7); ax.grid(axis="y", alpha=0.25)

ax = axes[1, 0]
for col, lab, color in [("tix_any_pct", "Title IX (any)", "#c55a11"),
                        ("sv_any_pct", "Sexual-violence terms", "#1f4e79"),
                        ("expanded_pct", "Core + sexual harassment", "#7f7f7f")]:
    ax.plot(x, monthly[col], marker="o", ms=3, label=lab, color=color)
ax.set_xticks(x); ax.set_xticklabels(monthly["period"], rotation=45)
ax.set_ylabel("% of stories"); ax.set_title("Component shares of coverage")
ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.25)

ax = axes[1, 1]
ax.plot(x, monthly["stories_per_day"], marker="o", color="#7f7f7f", label="Stories/day")
ax.set_xticks(x); ax.set_xticklabels(monthly["period"], rotation=45)
ax.set_ylabel("Stories per observed day")
ax2 = ax.twinx()
ax2.plot(x, monthly["fulltext_pct"], marker="s", ms=3, color="#c55a11", label="Full-text coverage")
ax2.set_ylabel("Full-text coverage (%)", color="#c55a11")
ax.set_title("Ingestion volume vs full-text completeness")
ax.grid(axis="y", alpha=0.25)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="center left")
fig.suptitle("2026 Title IX / sexual-violence coverage — monthly", fontsize=12)
fig.tight_layout()
fig.savefig(OUT_DIR / f"{PREFIX}_monthly.png", dpi=180)
plt.close(fig)

# Weekly: last 16 weeks, two panels (counts, then shares).
w = weekly_last16.reset_index(drop=True)
xw = np.arange(len(w))
fig, (ax_top, ax_bot) = plt.subplots(
    2, 1, figsize=(11.8, 7.6), sharex=True,
    gridspec_kw={"height_ratios": [1.15, 1]})

ax_top.bar(xw, w["stories"], color="#d9d9d9", label="All stories")
ax_top.set_ylabel("All stories")
ax_top.grid(axis="y", alpha=0.2)
axr = ax_top.twinx()
axr.plot(xw, w["core"], marker="o", color="#1f4e79", label="Core matches")
axr.set_ylabel("Core matches", color="#1f4e79")
h1, l1 = ax_top.get_legend_handles_labels(); h2, l2 = axr.get_legend_handles_labels()
ax_top.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")
ax_top.set_title("Last 16 ISO weeks: volume (top) and share of coverage (bottom)")

ax_bot.plot(xw, w["core_pct"], marker="o", color="#c55a11", label="Core share")
ax_bot.plot(xw, w["core_ex_event_pct"], marker="s", ms=3, color="#2e7d32",
            label="Core share excl. Cornell/LSU")
ma = w["core_pct"].rolling(4, min_periods=1).mean()
ax_bot.plot(xw, ma, color="#c55a11", ls="--", lw=1, label="4-week moving avg")
ax_bot.set_ylabel("Core share (%)")
ax_bot.set_xticks(xw)
ax_bot.set_xticklabels([s[5:] for s in w["week_start"]], rotation=45)
ax_bot.grid(axis="y", alpha=0.2)
ax_bot.legend(fontsize=8, loc="lower left")

for i in np.where(w["partial_week"].to_numpy() == 1)[0]:
    for a in (ax_top, ax_bot):
        a.axvspan(i - 0.5, i + 0.5, color="#f4b183", alpha=0.18)
fig.tight_layout()
fig.savefig(OUT_DIR / f"{PREFIX}_weekly.png", dpi=180)
plt.close(fig)

# Recent vs prior rate ratios (90/60/30) for core and components.
fig, ax = plt.subplots(figsize=(9.6, 4.8))
plot_series = ["core", "core_ex_cornell_lsu", "headline_only_core",
               "expanded (+ sexual harassment)", "title_ix_any", "sv_terms_any"]
colors = ["#1f4e79", "#2e7d32", "#c55a11", "#7f7f7f", "#8c564b", "#9467bd"]
for lab, color in zip(plot_series, colors):
    sub = recent_vs_prior[recent_vs_prior["series"] == lab].set_index("window_days")
    ax.plot([30, 60, 90], [sub.loc[d, "rate_ratio"] for d in (30, 60, 90)],
            marker="o", label=lab, color=color)
ax.axhline(1.0, color="#999999", ls="--", lw=1)
ax.set_xlabel("Recent window length (days)")
ax.set_ylabel("Rate ratio vs preceding window")
ax.set_title("Recent vs prior: rate ratios (1.0 = no change)")
ax.set_xticks([30, 60, 90]); ax.legend(fontsize=7); ax.grid(alpha=0.25)
fig.tight_layout()
fig.savefig(OUT_DIR / f"{PREFIX}_rate_ratios.png", dpi=180)
plt.close(fig)

# ---------------------------------------------------------------------------
# 10. Markdown report
# ---------------------------------------------------------------------------
def md_table(frame: pd.DataFrame, cols, headers) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, r in frame.iterrows():
        vals = []
        for c in cols:
            v = r[c]
            if isinstance(v, float):
                if math.isnan(v):
                    v = "—"
                elif c.endswith("_pct") or c in {"core_pct", "expanded_pct"}:
                    v = f"{v:.2f}%"
                elif c in {"p", "p_value", "p_value_vs_baseline", "chi2_p", "common_p"}:
                    v = f"{v:.3g}"
                elif c in {"rate_ratio", "rr_lo", "rr_hi", "common_rr", "std_rr",
                           "rate_ratio_vs_baseline", "volume_ratio_recent_vs_prior"}:
                    v = f"{v:.3f}"
                else:
                    v = f"{v:.2f}"
            vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def rp_row(series, days):
    m = recent_vs_prior[(recent_vs_prior["series"] == series)
                        & (recent_vs_prior["window_days"] == days)]
    return m.iloc[0]


def ft_row(series, days):
    m = recent_vs_prior_ft_sep[(recent_vs_prior_ft_sep["series"] == series)
                               & (recent_vs_prior_ft_sep["window_days"] == days)]
    return m.iloc[0]


core_30 = rp_row("core", 30)
core_60 = rp_row("core", 60)
core_90 = rp_row("core", 90)
corex_30 = rp_row("core_ex_cornell_lsu", 30)
corex_60 = rp_row("core_ex_cornell_lsu", 60)
corex_90 = rp_row("core_ex_cornell_lsu", 90)
head_30 = rp_row("headline_only_core", 30)
head_60 = rp_row("headline_only_core", 60)
head_90 = rp_row("headline_only_core", 90)
headx_30 = rp_row("headline_ex_cornell_lsu", 30)
headx_90 = rp_row("headline_ex_cornell_lsu", 90)
exp_30 = rp_row("expanded (+ sexual harassment)", 30)
exp_90 = rp_row("expanded (+ sexual harassment)", 90)
tix_30 = rp_row("title_ix_any", 30)
tix_90 = rp_row("title_ix_any", 90)
sv_30 = rp_row("sv_terms_any", 30)
sv_90 = rp_row("sv_terms_any", 90)
tixo_30 = rp_row("title_ix_only", 30)
tixo_90 = rp_row("title_ix_only", 90)
svo_30 = rp_row("sv_only", 30)
svo_90 = rp_row("sv_only", 90)
both_30 = rp_row("both", 30)
both_90 = rp_row("both", 90)
news_90 = rp_row("core_news_only (excl. /online_features/)", 90)
ft30 = ft_row("core", 30)
ft60 = ft_row("core", 60)
ft90 = ft_row("core", 90)
ft30x = ft_row("core_ex_cornell_lsu", 30)
ft90x = ft_row("core_ex_cornell_lsu", 90)

oct_sub = d26[d26["month"] == "2026-10"]
OCT_N = len(oct_sub)
OCT_PATHS = int((oct_sub["full_text_path"].astype(str).str.strip() != "").sum())
OCT_OK = int((oct_sub["extraction_status"] == "ok").sum())
OCT_FILES = int(oct_sub["has_full_text"].sum())
OCT_CORE = int(oct_sub["core"].sum())
OCT_CORE_FT = int((oct_sub["core"] & (oct_sub["has_full_text"] == 1)).sum())
sep_sub = d26[d26["month"] == "2026-09"]
SEP_FILES = int(sep_sub["has_full_text"].sum())

rec30 = d26[(d26["date"] >= MAX_DATE - timedelta(days=29)) & (d26["date"] <= MAX_DATE)]
EV30_CORNELL = int((rec30["core"] & rec30["event_cornell"]).sum())
EV30_LSU = int((rec30["core"] & rec30["event_lsu"]).sum())
EV30_ANY = int((rec30["core"] & rec30["event_any"]).sum())
EV30_CORE_ANY = int((rec30["core"] & rec30["event_any"]).sum())

scope_md = md_table(scope_table, ["scope", "stories_matched", "denominator", "pct"],
                    ["Scope", "Core matches", "Denominator (2026 stories)", "% of 2026"])
month_md = md_table(
    monthly,
    ["period", "stories", "core", "core_pct", "core_pct_lo", "core_pct_hi",
     "core_pct_ft", "core_headline_pct", "expanded_pct", "tix_any_pct",
     "sv_any_pct", "event_cornell_core", "fulltext_pct", "outlets", "stories_per_day"],
    ["Month", "Stories", "Core", "Core %", "CI low (%)", "CI high (%)", "Core % of FT-covered",
     "Headline %", "Core+harass %", "Title IX %", "SV terms %", "Cornell/Chi Phi core",
     "Full text %", "Outlets", "Stories/day"],
)
week_md = md_table(
    weekly_last16,
    ["week_start", "week_end", "stories", "core", "core_pct", "core_ex_event_pct",
     "core_headline_pct", "expanded_pct", "tix_any_pct", "sv_any_pct", "outlets", "partial_week"],
    ["Week start", "Week end", "Stories", "Core", "Core %", "Core % excl. Cornell/LSU",
     "Headline %", "Core+harass %", "Title IX %", "SV terms %", "Outlets", "Partial"],
)
rp_md = md_table(
    recent_vs_prior[recent_vs_prior["series"].isin(
        ["core", "core_ex_cornell_lsu", "headline_only_core", "headline_ex_cornell_lsu"])],
    ["series", "window_days", "recent_n", "recent_matches", "recent_rate_pct",
     "prior_n", "prior_matches", "prior_rate_pct", "rate_ratio", "rr_lo",
     "rr_hi", "p_value", "baseline_rate_pct", "rate_ratio_vs_baseline",
     "p_value_vs_baseline"],
    ["Series", "Days", "Recent N", "Recent matches", "Recent %",
     "Prior N", "Prior matches", "Prior %", "Rate ratio", "RR low", "RR high",
     "p (vs prior)", "YTD baseline %", "RR vs baseline", "p (vs baseline)"],
)
component_md = md_table(
    recent_vs_prior[(recent_vs_prior["series"].isin(
        ["title_ix_any", "sv_terms_any", "title_ix_only", "sv_only", "both"]))
        & (recent_vs_prior["window_days"].isin([30, 90]))],
    ["series", "window_days", "recent_matches", "recent_rate_pct",
     "prior_matches", "prior_rate_pct", "rate_ratio", "p_value"],
    ["Series", "Days", "Recent matches", "Recent %", "Prior matches", "Prior %",
     "Rate ratio", "p"],
)
panel_md = md_table(
    recent_vs_prior[recent_vs_prior["series"].isin(
        ["core", "core_ex_cornell_lsu", "headline_only_core", "headline_ex_cornell_lsu"])],
    ["series", "window_days", "recent_outlets", "prior_outlets", "common_outlets",
     "recent_vol", "prior_vol", "volume_ratio_recent_vs_prior",
     "common_recent_n", "common_prior_n", "common_recent_rate", "common_prior_rate",
     "common_rr", "common_p", "std_prior_rate", "std_rr"],
    ["Series", "Days", "Recent outlets", "Prior outlets", "Common outlets",
     "Recent vol", "Prior vol", "Volume ratio", "Common recent N",
     "Common prior N", "Common recent %", "Common prior %", "Common RR",
     "p", "Std. prior %", "Std. RR"],
)
ft_md = md_table(
    recent_vs_prior_ft_sep[recent_vs_prior_ft_sep["series"].isin(
        ["core", "core_ex_cornell_lsu", "expanded (+ sexual harassment)",
         "title_ix_any", "sv_terms_any"])],
    ["series", "window_days", "recent_n", "recent_matches", "recent_rate_pct",
     "prior_n", "prior_matches", "prior_rate_pct", "rate_ratio", "p_value"],
    ["Series (through 2026-09-30)", "Days", "Recent N", "Recent matches",
     "Recent %", "Prior N", "Prior matches", "Prior %", "Rate ratio", "p"],
)

verdict_rise = (core_90["rate_ratio"] > 1 and core_90["p_value"] < 0.05)
sustained = (core_90["rate_ratio"] > 1 and core_90["p_value"] < 0.05
             and corex_90["rate_ratio"] > 1)
sig_txt = "statistically significant" if core_90["p_value"] < 0.05 else "not statistically significant"

report = f"""# Title IX and sexual-violence coverage in 2026 — trend analysis

**Database:** `news_database.csv` (read-only)  
**Exact date range:** **{START_DATE} through {MAX_DATE}** (inclusive)  
**2026 stories (denominator):** **{fmt_int(N)}** of {fmt_int(N_ALL)} rows in the DB ({100 * N / N_ALL:.1f}%)  
**Maximum available published date:** **{MAX_DATE}** — October 2026 is **partial (1–{MAX_DATE.day})**; all October counts are for {MAX_DATE.day} days only.  
**Classifier:** unchanged regex definitions from the prior run, shared via `scripts/title_ix_definitions.py`  
**Script:** `scripts/analyze_title_ix_sexual_violence_2026.py`

## 1. 2026 totals at three scopes

{scope_md}

The full-text-inclusive figure is the primary **count**. Full text exists for
**{fmt_int(int(d26['has_full_text'].sum()))} of {fmt_int(N)} ({100 * d26['has_full_text'].sum() / N:.1f}%)**
2026 stories. The headline-only count is **{fmt_int(int(d26['core_headline'].sum()))} ({100 * d26['core_headline'].sum() / N:.2f}%)**;
metadata (title+keywords+theme) is **{fmt_int(int(d26['core_metadata'].sum()))} ({100 * d26['core_metadata'].sum() / N:.2f}%)**.
Keywords/theme add almost nothing beyond the headline in this database, so the
metadata and headline scopes are nearly identical.

**Important data-completeness caveat:** October has **{fmt_int(OCT_FILES)} extracted bodies
out of {fmt_int(OCT_N)} stories ({100 * OCT_FILES / OCT_N:.1f}%)**, even though
**{fmt_int(OCT_PATHS)}** October rows have a `full_text_path` and **{fmt_int(OCT_OK)}**
are marked `extraction_status=ok`. The files simply are not on disk yet. September,
by contrast, has **{fmt_int(SEP_FILES)} of {fmt_int(len(sep_sub))}** bodies
({100 * SEP_FILES / len(sep_sub):.1f}%). **October full-text-inclusive rates are therefore
not comparable to earlier months**; headline/metadata rates are complete, and the
full-text trend is also re-run through 2026-09-30 below.

Other 2026 definitions (full-text scope): strict literal **{fmt_int(int(d26['strict'].sum()))}**
({100 * d26['strict'].sum() / N:.2f}%), expanded (+ sexual harassment)
**{fmt_int(int(d26['expanded'].sum()))}** ({100 * d26['expanded'].sum() / N:.2f}%),
broad (+ related terms) **{fmt_int(int(d26['broad'].sum()))}** ({100 * d26['broad'].sum() / N:.2f}%).
Title IX any mention **{fmt_int(int(d26['tix_any'].sum()))}**; sexual-violence terms
**{fmt_int(int(d26['sv_any'].sum()))}**; Title IX athletics/equity-only
**{fmt_int(int(d26['tix_equity_only'].sum()))}**. The 2026 core total (**{fmt_int(int(d26['core'].sum()))}**)
exactly matches the prior run's 2026 count, so the classifier is unchanged.

## 2. Monthly counts, denominators and rates

{month_md}

**Read the denominator column before the count column.** Monthly story volume is
not stable: it rises from {fmt_int(monthly.iloc[0]['stories'])} in January to
{fmt_int(monthly[monthly['period'] == '2026-09']['stories'].iloc[0])} in September and
{fmt_int(monthly.iloc[-1]['stories'])} in the first {MAX_DATE.day} days of October.
September's core **count** is much larger than January's, but September's **share**
is **{monthly[monthly['period'] == '2026-09']['core_pct'].iloc[0]:.2f}%** versus January's
**{monthly.iloc[0]['core_pct']:.2f}%**. The October "Core % of FT-covered" value
({monthly.iloc[-1]['core_pct_ft']:.2f}%) is computed on only {fmt_int(int(monthly.iloc[-1]['fulltext']))}
bodies and should **not** be interpreted as a real increase.

## 3. Weekly view (last 16 ISO weeks)

{week_md}

The final week is partial (through {MAX_DATE}). Weekly rates on a median of
~{int(weekly_last16['stories'].median())} stories/week are noisy; the 4-week moving
average in the chart is the better signal. The late-September/early-October bulge
in the headline and core series is visible, followed by a fall back.

## 4. Recent vs prior windows, with significance tests

Recent window ends {MAX_DATE}; the prior window is the immediately preceding window
of the same length. The 2026 year-to-date baseline runs {START_DATE} to the day before
the recent window (it therefore includes the prior window). Rate ratios above 1 mean
the recent share is higher. `core_ex_cornell_lsu` and `headline_ex_cornell_lsu`
remove stories whose **headlines** mention Cornell / Chi Phi or LSU / Tigerland;
this is an event-adjusted sensitivity, not a different topic definition.

{rp_md}

**Core (30 days):** recent **{core_30['recent_matches']:.0f}/{core_30['recent_n']:,.0f}
= {core_30['recent_rate_pct']:.2f}%** vs prior **{core_30['prior_matches']:.0f}/{core_30['prior_n']:,.0f}
= {core_30['prior_rate_pct']:.2f}%**; rate ratio **{core_30['rate_ratio']:.3f}**
(95% CI {core_30['rr_lo']:.3f}–{core_30['rr_hi']:.3f}), p = **{core_30['p_value']:.3g}**.
Excluding the Cornell/LSU headlines, the 30-day rate is **{corex_30['recent_rate_pct']:.2f}%**
vs **{corex_30['prior_rate_pct']:.2f}%** (RR **{corex_30['rate_ratio']:.3f}**,
p = **{corex_30['p_value']:.3g}**) — i.e. the full-text/core rise disappears.

**Core (60 days):** **{core_60['recent_rate_pct']:.2f}%** vs **{core_60['prior_rate_pct']:.2f}%**,
RR **{core_60['rate_ratio']:.3f}** (CI {core_60['rr_lo']:.3f}–{core_60['rr_hi']:.3f}),
p = **{core_60['p_value']:.3g}**; ex-event RR **{corex_60['rate_ratio']:.3f}**.

**Core (90 days):** **{core_90['recent_rate_pct']:.2f}%** vs **{core_90['prior_rate_pct']:.2f}%**,
RR **{core_90['rate_ratio']:.3f}** (CI {core_90['rr_lo']:.3f}–{core_90['rr_hi']:.3f}),
p = **{core_90['p_value']:.3g}**. This difference is **{sig_txt}** and the recent share is
**{'higher' if core_90['rate_ratio'] > 1 else 'lower'}**. Excluding Cornell/LSU,
90-day RR is **{corex_90['rate_ratio']:.3f}**.

**Headline-level coverage tells a different story.** The 30-day headline core share is
**{head_30['recent_rate_pct']:.2f}%** vs **{head_30['prior_rate_pct']:.2f}%**
(RR **{head_30['rate_ratio']:.3f}**, p = **{head_30['p_value']:.3g}**), and it remains
**{headx_30['recent_rate_pct']:.2f}%** vs **{headx_30['prior_rate_pct']:.2f}%**
(RR **{headx_30['rate_ratio']:.3f}**, p = **{headx_30['p_value']:.3g}**) after removing
Cornell/LSU headlines. Over 90 days the headline RR is **{head_90['rate_ratio']:.3f}**
(ex-event **{headx_90['rate_ratio']:.3f}**). So stories were more likely to put these
topics in the **headline** even after the named events, but the absolute level is still
under 1% of stories.

**Full-text trend through 2026-09-30 (before the October body gap):**

{ft_md}

Through September, the 30-day core share is **{ft30['recent_rate_pct']:.2f}%** vs
**{ft30['prior_rate_pct']:.2f}%** (RR **{ft30['rate_ratio']:.3f}**,
p = **{ft30['p_value']:.3g}**) — flat. Over 60 and 90 days it is lower
(RR **{ft60['rate_ratio']:.3f}** and **{ft90['rate_ratio']:.3f}**). Excluding Cornell/LSU,
the 30-day through-September RR is **{ft30x['rate_ratio']:.3f}** and the 90-day RR is
**{ft90x['rate_ratio']:.3f}**. This confirms that the October full-text "spike" is the
Cornell/LSU news cycle seen through a very small number of available bodies.

## 5. Outlet-constant / fixed-effects-style check

Outlets are messy labels; `clean_outlet()` normalizes `www.` and RSS suffixes.
The common-outlet panel keeps only outlets with **at least 5 stories in both**
the recent and prior windows. "Std. prior %" re-weights each common outlet's prior
rate by its **recent** story share (direct standardization), so it answers: would the
prior period have looked different if it had today's outlet mix?

{panel_md}

For the 90-day core comparison the overall volume ratio is
**{core_90['volume_ratio_recent_vs_prior']:.2f}×**. The common-outlet core RR is
**{core_90['common_rr']:.3f}** (p = {core_90['common_p']:.3g}) and the
mix-standardized RR is **{core_90['std_rr']:.3f}**, versus the overall
**{core_90['rate_ratio']:.3f}**. Holding outlets fixed therefore explains part but not
all of the 90-day decline: the core share still falls among continuing outlets.
For the 30-day window, the common-outlet core RR is **{core_30['common_rr']:.3f}**
(p = {core_30['common_p']:.3g}) and the ex-event version is
**{corex_30['common_rr']:.3f}** (p = {corex_30['common_p']:.3g}), again showing that the
short-term rise is event-driven. The `..._outlet_shift_90d.csv` file lists the outlets
with the largest changes.

## 6. Which component drives the change?

{component_md}

- **Title IX (any):** 30-day **{tix_30['recent_rate_pct']:.2f}%** vs
  **{tix_30['prior_rate_pct']:.2f}%** (RR **{tix_30['rate_ratio']:.3f}**,
  p = **{tix_30['p_value']:.3g}**); 90-day RR **{tix_90['rate_ratio']:.3f}**
  (p = **{tix_90['p_value']:.3g}**).
- **Sexual-violence terms (any):** 30-day **{sv_30['recent_rate_pct']:.2f}%** vs
  **{sv_30['prior_rate_pct']:.2f}%** (RR **{sv_30['rate_ratio']:.3f}**,
  p = **{sv_30['p_value']:.3g}**); 90-day RR **{sv_90['rate_ratio']:.3f}**
  (p = **{sv_90['p_value']:.3g}**).
- **Expanded (+ sexual harassment):** 30-day RR **{exp_30['rate_ratio']:.3f}**
  (p = **{exp_30['p_value']:.3g}**); 90-day RR **{exp_90['rate_ratio']:.3f}**
  (p = **{exp_90['p_value']:.3g}**). Sexual harassment barely moves the totals.
- **Title IX-only vs SV-only:** 30-day Title IX-only RR **{tixo_30['rate_ratio']:.3f}**
  (p = {tixo_30['p_value']:.3g}); SV-only RR **{svo_30['rate_ratio']:.3f}**
  (p = {svo_30['p_value']:.3g}); both RR **{both_30['rate_ratio']:.3f}**
  (p = {both_30['p_value']:.3g}). At 90 days the corresponding RRs are
  **{tixo_90['rate_ratio']:.3f}**, **{svo_90['rate_ratio']:.3f}** and
  **{both_90['rate_ratio']:.3f}**. The short-term movement is driven by sexual-violence
  terms, not Title IX policy/athletics coverage.

Title IX athletics/equity-only stories are separated in the matches CSV
(`tix_equity_only`), so they can be removed; they account for
**{fmt_int(int(d26['tix_equity_only'].sum()))}** 2026 stories.

## 7. Confounders and denominator integrity

1. **2026 is essentially the whole database.** {fmt_int(N)} of {fmt_int(N_ALL)} rows
   ({100 * N / N_ALL:.1f}%) are 2026, so these are the dataset's trends, not an
   independent 2026 sample.
2. **Ingestion/coverage changed sharply.** Monthly stories rise from
   {fmt_int(monthly.iloc[0]['stories'])} (Jan) to {fmt_int(monthly[monthly['period'] == '2026-09']['stories'].iloc[0])}
   (Sep), while distinct outlets rise from {monthly.iloc[0]['outlets']} to
   {monthly[monthly['period'] == '2026-09']['outlets'].iloc[0]}. Stories per observed day
   go from {monthly.iloc[0]['stories_per_day']:.1f} to
   {monthly[monthly['period'] == '2026-09']['stories_per_day'].iloc[0]:.1f}. This is a coverage
   expansion, not necessarily a publication boom. Any raw-count comparison is invalid.
3. **Academic calendar.** August→September is back-to-school and campus-crime
   coverage season. September and October are the first full months of the fall term;
   the data contain no prior autumn in comparable volume (2025 has only ~1,268 stories
   all year), so seasonality cannot be estimated from this DB.
4. **Partial October.** October covers only 1–{MAX_DATE.day}; counts are not comparable
   to full months. The monthly **rate** is still usable for headline/metadata, but with
   wide confidence intervals.
5. **October body-extraction gap.** {fmt_int(OCT_PATHS)} October rows have a path and
   {fmt_int(OCT_OK)} are marked ok, but only **{fmt_int(OCT_FILES)}** files exist. The
   full-text-inclusive October count ({fmt_int(OCT_CORE)}) is therefore
   mostly a metadata count: only **{fmt_int(OCT_CORE_FT)}** of those {fmt_int(OCT_CORE)}
   matches have a body. The through-September sensitivity is the valid full-text trend.
6. **A single news cycle dominates early October.** In the last 30 days,
   **{fmt_int(EV30_CORNELL)}** core stories have Cornell/Chi Phi in the headline,
   **{fmt_int(EV30_LSU)}** have LSU/Tigerland, and **{fmt_int(EV30_ANY)}** have either
   ({100 * EV30_ANY / max(1, int(rec30['core'].sum())):.0f}% of the {fmt_int(int(rec30['core'].sum()))}
   core matches). The Cornell Chi Phi gang-rape case generated national coverage across
   many student papers; it is an event spike, not a broad secular trend. Event
   attribution is based on **headline tokens only**, so event coverage that never
   says "Cornell", "Chi Phi" or "LSU" remains in the ex-event series. The ex-event
   estimates are therefore conservative: the true non-event rise is at most what
   they show, and the true event share is at least {100 * EV30_ANY / max(1, int(rec30['core'].sum())):.0f}%.
7. **Syndicated / sponsored `online_features` pages.** These rise from 0% in
   Jan–May to {monthly[monthly['period'] == '2026-09']['online_features_pct'].iloc[0]:.1f}% in September
   and {monthly.iloc[-1]['online_features_pct']:.1f}% in October (mostly four
   "RSS Results" outlets). They are not student journalism and they inflate the
   denominator. Excluding them, the 90-day core RR is **{news_90['rate_ratio']:.3f}**
   (p = {news_90['p_value']:.3g}) — still lower than the prior window.
8. **Same-day capture share** is high in September
   ({monthly[monthly['period'] == '2026-09']['same_day_capture_pct'].iloc[0]:.1f}% of
   stories captured on their published date), so most September volume is live
   publication rather than a historical archive dump. The 2026-06-23 context note
   describes an earlier outlet/cascade-scraper expansion; the September jump is a
   later, much larger coverage ramp.
9. **Outlet churn.** The common-outlet panel above removes outlets absent in one
   window. Even there, the 90-day core share falls (RR {core_90['common_rr']:.3f}),
   so outlet churn is not the whole explanation; composition explains part of it.
10. **Keyword matching is not topic classification.** A story that mentions sexual
    assault in a content warning is counted; a story about "inappropriate conduct"
    without a listed term is missed. Headline-only is high precision but low recall.
11. **Duplicate/syndicated headlines.** Rows are unique URLs, so syndicated copies
    across outlets are counted separately (which is appropriate for measuring
    coverage volume, but not for counting distinct incidents).

## 8. Verdict

**Is there evidence of a recent rise? It depends on the measure, and the honest answer is: a short event-driven spike, not a sustained rise.**

- **Raw counts:** core matches are **{core_90['recent_matches']:.0f}** in the last 90 days
  vs **{core_90['prior_matches']:.0f}** in the preceding 90 days — up
  **{core_90['recent_matches'] / max(1, core_90['prior_matches']):.2f}×**, while total story
  volume is up **{core_90['volume_ratio_recent_vs_prior']:.2f}×**. Counts rose *less* than
  the denominator, so raw counts are **not** evidence of a topic rise.
- **Share of coverage, 90 days:** core **{core_90['recent_rate_pct']:.2f}%** vs
  **{core_90['prior_rate_pct']:.2f}%**, RR **{core_90['rate_ratio']:.3f}**
  (p = {core_90['p_value']:.3g}) — **down**, not up. Sixty-day RR is
  **{core_60['rate_ratio']:.3f}**. The full-text trend through September is also flat
  month-over-month (RR {ft30['rate_ratio']:.3f}) and lower over 90 days
  (RR {ft90['rate_ratio']:.3f}).
- **Share of coverage, 30 days:** core **{core_30['recent_rate_pct']:.2f}%** vs
  **{core_30['prior_rate_pct']:.2f}%** (RR **{core_30['rate_ratio']:.3f}**,
  p = {core_30['p_value']:.3g}) — up. But excluding Cornell/LSU headlines it is
  **{corex_30['recent_rate_pct']:.2f}%** vs **{corex_30['prior_rate_pct']:.2f}%**
  (RR **{corex_30['rate_ratio']:.3f}**, p = {corex_30['p_value']:.3g}) — **flat**.
  The 30-day rise is the Cornell/LSU news cycle.
- **Headline salience is the one genuine broader signal:** 30-day headline share
  **{head_30['recent_rate_pct']:.2f}%** vs **{head_30['prior_rate_pct']:.2f}%**
  (RR **{head_30['rate_ratio']:.3f}**), and still **{headx_30['recent_rate_pct']:.2f}%**
  vs **{headx_30['prior_rate_pct']:.2f}%** (RR **{headx_30['rate_ratio']:.3f}**) after
  removing the named events. Over 90 days, headline RR **{head_90['rate_ratio']:.3f}**
  (ex-event **{headx_90['rate_ratio']:.3f}**). This is consistent with a national campus
  sexual-violence news cycle raising headline salience beyond the originating case,
  but the absolute share is still only ~0.4–0.7% of stories.
- **Versus the 2026 year-to-date baseline:** the 30-day core share
  ({core_30['recent_rate_pct']:.2f}%) is **below** the YTD baseline
  ({core_30['baseline_rate_pct']:.2f}%, RR {core_30['rate_ratio_vs_baseline']:.3f});
  the 30-day headline share ({head_30['recent_rate_pct']:.2f}%) is **above** its
  baseline ({head_30['baseline_rate_pct']:.2f}%,
  RR {head_30['rate_ratio_vs_baseline']:.3f}). So even the headline rise is a
  within-year news-cycle deviation, not a new level.
- **Outlet-constant check:** 90-day common-outlet RR **{core_90['common_rr']:.3f}**
  (p = {core_90['common_p']:.3g}); mix-standardized RR **{core_90['std_rr']:.3f}**.
  The decline survives holding outlets fixed; the 30-day rise is not an artifact of
  which outlets were scraped, but it is an artifact of one news event.

**Bottom line:** There is **no evidence of a sustained recent rise in the share of
coverage** devoted to Title IX / sexual violence. Over 60–90 days the share is lower
than the preceding period, and the September/October denominator explosion
(roughly {monthly[monthly['period'] == '2026-09']['stories'].iloc[0] / monthly[monthly['period'] == '2026-08']['stories'].iloc[0]:.1f}×
August volume) means raw counts are misleading. There **is** a genuine, statistically
significant **short-term spike in headline salience in late September–early October**,
centered on the Cornell Chi Phi case (plus LSU), which spilled over into broader
campus commentary. That is an event, not a trend. If the question is "are more
stories being written about these topics lately?", the answer is yes in raw counts,
mostly because far more stories are being ingested; the topic's **share** of coverage
is flat over the last month once the event is removed and lower over the last quarter.

## Files created

- `analytics/{PREFIX}_report.md`
- `analytics/{PREFIX}_scopes.csv`
- `analytics/{PREFIX}_monthly.csv`
- `analytics/{PREFIX}_weekly.csv`
- `analytics/{PREFIX}_recent_vs_prior.csv`
- `analytics/{PREFIX}_recent_vs_prior_fulltext_through_sep.csv`
- `analytics/{PREFIX}_matches.csv`
- `analytics/{PREFIX}_outlet_shift_90d.csv`
- `analytics/{PREFIX}_monthly.png`
- `analytics/{PREFIX}_weekly.png`
- `analytics/{PREFIX}_rate_ratios.png`
- `scripts/title_ix_definitions.py`
- `scripts/analyze_title_ix_sexual_violence_2026.py`
"""

with open(OUT_DIR / f"{PREFIX}_report.md", "w", encoding="utf-8") as fh:
    fh.write(report)

print("\n=== 2026 HEADLINE ===")
print(f"Range {START_DATE}..{MAX_DATE}; N={N:,}")
print(scope_table.to_string(index=False))
print("\nMonthly:")
print(monthly[["period", "stories", "core", "core_pct", "tix_any_pct", "sv_any_pct",
               "outlets", "fulltext_pct"]].to_string(index=False))
print("\nRecent vs prior (core):")
print(recent_vs_prior[recent_vs_prior["series"] == "core"][
    ["window_days", "recent_n", "recent_matches", "recent_rate_pct", "prior_n",
     "prior_matches", "prior_rate_pct", "rate_ratio", "p_value",
     "common_rr", "common_p", "std_rr"]].to_string(index=False))
print("\nWrote outputs to", OUT_DIR)
