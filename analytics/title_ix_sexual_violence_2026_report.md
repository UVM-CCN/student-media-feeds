# Title IX and sexual-violence coverage in 2026 — trend analysis

**Database:** `news_database.csv` (read-only)  
**Exact date range:** **2026-01-01 through 2026-10-15** (inclusive)  
**2026 stories (denominator):** **64,681** of 68,581 rows in the DB (94.3%)  
**Maximum available published date:** **2026-10-15** — October 2026 is **partial (1–15)**; all October counts are for 15 days only.  
**Classifier:** unchanged regex definitions from the prior run, shared via `scripts/title_ix_definitions.py`  
**Script:** `scripts/analyze_title_ix_sexual_violence_2026.py`

## 1. 2026 totals at three scopes

| Scope | Core matches | Denominator (2026 stories) | % of 2026 |
|---|---|---|---|
| headline-only (title) | 290 | 64681 | 0.45 |
| metadata (title+keywords+theme) | 293 | 64681 | 0.45 |
| full-text-inclusive | 889 | 64681 | 1.37 |

The full-text-inclusive figure is the primary **count**. Full text exists for
**46,046 of 64,681 (71.2%)**
2026 stories. The headline-only count is **290 (0.45%)**;
metadata (title+keywords+theme) is **293 (0.45%)**.
Keywords/theme add almost nothing beyond the headline in this database, so the
metadata and headline scopes are nearly identical.

**Important data-completeness caveat:** October has **230 extracted bodies
out of 15,529 stories (1.5%)**, even though
**13,559** October rows have a `full_text_path` and **13,559**
are marked `extraction_status=ok`. The files simply are not on disk yet. September,
by contrast, has **26,319 of 28,311** bodies
(93.0%). **October full-text-inclusive rates are therefore
not comparable to earlier months**; headline/metadata rates are complete, and the
full-text trend is also re-run through 2026-09-30 below.

Other 2026 definitions (full-text scope): strict literal **785**
(1.21%), expanded (+ sexual harassment)
**928** (1.43%),
broad (+ related terms) **1,409** (2.18%).
Title IX any mention **239**; sexual-violence terms
**735**; Title IX athletics/equity-only
**95**. The 2026 core total (**889**)
exactly matches the prior run's 2026 count, so the classifier is unchanged.

## 2. Monthly counts, denominators and rates

| Month | Stories | Core | Core % | CI low (%) | CI high (%) | Core % of FT-covered | Headline % | Core+harass % | Title IX % | SV terms % | Cornell/Chi Phi core | Full text % | Outlets | Stories/day |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-01 | 362 | 3 | 0.83% | 0.28 | 2.41 | 0.86 | 0.00% | 0.83% | 0.28% | 0.55% | 0 | 96.13% | 79 | 11.68 |
| 2026-02 | 672 | 16 | 2.38% | 1.47 | 3.83 | 2.43 | 0.15% | 2.38% | 0.30% | 2.23% | 0 | 98.07% | 132 | 24.00 |
| 2026-03 | 1516 | 32 | 2.11% | 1.50 | 2.96 | 2.15 | 0.20% | 2.24% | 0.79% | 1.65% | 0 | 98.15% | 190 | 48.90 |
| 2026-04 | 3752 | 69 | 1.84% | 1.46 | 2.32 | 1.90 | 0.21% | 1.89% | 0.67% | 1.52% | 1 | 96.83% | 443 | 125.07 |
| 2026-05 | 3698 | 66 | 1.78% | 1.41 | 2.26 | 1.84 | 0.16% | 1.81% | 0.49% | 1.43% | 2 | 97.05% | 485 | 119.29 |
| 2026-06 | 3172 | 58 | 1.83% | 1.42 | 2.36 | 1.89 | 0.22% | 1.89% | 0.60% | 1.36% | 1 | 96.66% | 337 | 105.73 |
| 2026-07 | 2314 | 44 | 1.90% | 1.42 | 2.54 | 2.08 | 0.26% | 1.94% | 0.78% | 1.30% | 0 | 91.53% | 213 | 74.65 |
| 2026-08 | 5355 | 64 | 1.20% | 0.94 | 1.52 | 1.37 | 0.19% | 1.31% | 0.32% | 1.03% | 2 | 85.83% | 412 | 172.74 |
| 2026-09 | 28311 | 348 | 1.23% | 1.11 | 1.36 | 1.30 | 0.25% | 1.30% | 0.31% | 1.06% | 36 | 92.96% | 664 | 943.70 |
| 2026-10 | 15529 | 189 | 1.22% | 1.06 | 1.40 | 4.78 | 1.14% | 1.24% | 0.24% | 1.00% | 55 | 1.48% | 658 | 1035.27 |

**Read the denominator column before the count column.** Monthly story volume is
not stable: it rises from 362 in January to
28,311 in September and
15,529 in the first 15 days of October.
September's core **count** is much larger than January's, but September's **share**
is **1.23%** versus January's
**0.83%**. The October "Core % of FT-covered" value
(4.78%) is computed on only 230
bodies and should **not** be interpreted as a real increase.

## 3. Weekly view (last 16 ISO weeks)

| Week start | Week end | Stories | Core | Core % | Core % excl. Cornell/LSU | Headline % | Core+harass % | Title IX % | SV terms % | Outlets | Partial |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-06-29 | 2026-07-05 | 613 | 15 | 2.45% | 2.45% | 0.65% | 2.45% | 1.31% | 1.14% | 119 | 0 |
| 2026-07-06 | 2026-07-12 | 549 | 14 | 2.55% | 2.37% | 0.00% | 2.55% | 1.09% | 1.82% | 102 | 0 |
| 2026-07-13 | 2026-07-19 | 606 | 8 | 1.32% | 1.32% | 0.00% | 1.32% | 0.33% | 1.16% | 101 | 0 |
| 2026-07-20 | 2026-07-26 | 386 | 5 | 1.30% | 1.30% | 0.26% | 1.55% | 0.26% | 1.04% | 108 | 0 |
| 2026-07-27 | 2026-08-02 | 491 | 8 | 1.63% | 1.63% | 0.41% | 1.63% | 0.61% | 1.22% | 122 | 0 |
| 2026-08-03 | 2026-08-09 | 537 | 8 | 1.49% | 1.30% | 0.19% | 1.68% | 0.74% | 1.12% | 121 | 0 |
| 2026-08-10 | 2026-08-16 | 646 | 10 | 1.55% | 1.55% | 0.00% | 1.86% | 0.15% | 1.55% | 138 | 0 |
| 2026-08-17 | 2026-08-23 | 1048 | 13 | 1.24% | 1.24% | 0.00% | 1.34% | 0.38% | 0.86% | 185 | 0 |
| 2026-08-24 | 2026-08-30 | 2322 | 24 | 1.03% | 1.03% | 0.26% | 1.08% | 0.30% | 0.90% | 317 | 0 |
| 2026-08-31 | 2026-09-06 | 5014 | 51 | 1.02% | 0.98% | 0.18% | 1.08% | 0.18% | 0.92% | 398 | 0 |
| 2026-09-07 | 2026-09-13 | 6175 | 72 | 1.17% | 1.13% | 0.23% | 1.20% | 0.28% | 1.00% | 462 | 0 |
| 2026-09-14 | 2026-09-20 | 6828 | 65 | 0.95% | 0.89% | 0.15% | 1.01% | 0.22% | 0.82% | 521 | 0 |
| 2026-09-21 | 2026-09-27 | 7069 | 91 | 1.29% | 1.10% | 0.18% | 1.41% | 0.34% | 1.05% | 545 | 0 |
| 2026-09-28 | 2026-10-04 | 7629 | 123 | 1.61% | 0.96% | 0.88% | 1.69% | 0.37% | 1.48% | 575 | 0 |
| 2026-10-05 | 2026-10-11 | 7525 | 81 | 1.08% | 0.76% | 1.05% | 1.10% | 0.27% | 0.84% | 588 | 0 |
| 2026-10-12 | 2026-10-18 | 4324 | 62 | 1.43% | 1.23% | 1.39% | 1.43% | 0.35% | 1.13% | 458 | 1 |

The final week is partial (through 2026-10-15). Weekly rates on a median of
~1685 stories/week are noisy; the 4-week moving
average in the chart is the better signal. The late-September/early-October bulge
in the headline and core series is visible, followed by a fall back.

## 4. Recent vs prior windows, with significance tests

Recent window ends 2026-10-15; the prior window is the immediately preceding window
of the same length. The 2026 year-to-date baseline runs 2026-01-01 to the day before
the recent window (it therefore includes the prior window). Rate ratios above 1 mean
the recent share is higher. `core_ex_cornell_lsu` and `headline_ex_cornell_lsu`
remove stories whose **headlines** mention Cornell / Chi Phi or LSU / Tigerland;
this is an event-adjusted sensitivity, not a different topic definition.

| Series | Days | Recent N | Recent matches | Recent % | Prior N | Prior matches | Prior % | Rate ratio | RR low | RR high | p (vs prior) | YTD baseline % | RR vs baseline | p (vs baseline) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| core | 30 | 31324 | 410 | 1.31% | 16610 | 172 | 1.04% | 1.264 | 1.059 | 1.509 | 0.0093 | 1.44% | 0.912 | 0.165 |
| core | 60 | 47934 | 582 | 1.21% | 5187 | 85 | 1.64% | 0.741 | 0.591 | 0.929 | 0.0091 | 1.83% | 0.662 | 3.16e-09 |
| core | 90 | 50060 | 613 | 1.22% | 10556 | 201 | 1.90% | 0.643 | 0.549 | 0.753 | 3.53e-08 | 1.89% | 0.649 | 1.37e-09 |
| headline_only_core | 30 | 31324 | 228 | 0.73% | 16610 | 30 | 0.18% | 4.030 | 2.755 | 5.894 | 6.57e-15 | 0.19% | 3.916 | 6.26e-25 |
| headline_only_core | 60 | 47934 | 258 | 0.54% | 5187 | 9 | 0.17% | 3.102 | 1.597 | 6.026 | 0.000418 | 0.19% | 2.817 | 7.08e-09 |
| headline_only_core | 90 | 50060 | 262 | 0.52% | 10556 | 22 | 0.21% | 2.511 | 1.626 | 3.878 | 1.66e-05 | 0.19% | 2.733 | 1.26e-07 |
| core_ex_cornell_lsu | 30 | 31324 | 311 | 0.99% | 16610 | 167 | 1.01% | 0.987 | 0.819 | 1.191 | 0.895 | 1.40% | 0.708 | 1.76e-06 |
| core_ex_cornell_lsu | 60 | 47934 | 478 | 1.00% | 5187 | 83 | 1.60% | 0.623 | 0.495 | 0.785 | 5.45e-05 | 1.80% | 0.555 | 3.04e-16 |
| core_ex_cornell_lsu | 90 | 50060 | 508 | 1.01% | 10556 | 196 | 1.86% | 0.547 | 0.464 | 0.644 | 2.18e-13 | 1.85% | 0.547 | 2.86e-16 |
| headline_ex_cornell_lsu | 30 | 31324 | 150 | 0.48% | 16610 | 29 | 0.17% | 2.743 | 1.844 | 4.080 | 2.02e-07 | 0.18% | 2.662 | 2.39e-11 |
| headline_ex_cornell_lsu | 60 | 47934 | 179 | 0.37% | 5187 | 8 | 0.15% | 2.421 | 1.193 | 4.913 | 0.0113 | 0.19% | 2.017 | 0.000226 |
| headline_ex_cornell_lsu | 90 | 50060 | 182 | 0.36% | 10556 | 22 | 0.21% | 1.744 | 1.121 | 2.714 | 0.0124 | 0.19% | 1.898 | 0.00129 |

**Core (30 days):** recent **410/31,324
= 1.31%** vs prior **172/16,610
= 1.04%**; rate ratio **1.264**
(95% CI 1.059–1.509), p = **0.0093**.
Excluding the Cornell/LSU headlines, the 30-day rate is **0.99%**
vs **1.01%** (RR **0.987**,
p = **0.895**) — i.e. the full-text/core rise disappears.

**Core (60 days):** **1.21%** vs **1.64%**,
RR **0.741** (CI 0.591–0.929),
p = **0.0091**; ex-event RR **0.623**.

**Core (90 days):** **1.22%** vs **1.90%**,
RR **0.643** (CI 0.549–0.753),
p = **3.53e-08**. This difference is **statistically significant** and the recent share is
**lower**. Excluding Cornell/LSU,
90-day RR is **0.547**.

**Headline-level coverage tells a different story.** The 30-day headline core share is
**0.73%** vs **0.18%**
(RR **4.030**, p = **6.57e-15**), and it remains
**0.48%** vs **0.17%**
(RR **2.743**, p = **2.02e-07**) after removing
Cornell/LSU headlines. Over 90 days the headline RR is **2.511**
(ex-event **1.744**). So stories were more likely to put these
topics in the **headline** even after the named events, but the absolute level is still
under 1% of stories.

**Full-text trend through 2026-09-30 (before the October body gap):**

| Series (through 2026-09-30) | Days | Recent N | Recent matches | Recent % | Prior N | Prior matches | Prior % | Rate ratio | p |
|---|---|---|---|---|---|---|---|---|---|
| core | 30 | 28311 | 348 | 1.23% | 5325 | 63 | 1.18% | 1.039 | 0.779 |
| core | 60 | 33636 | 411 | 1.22% | 5304 | 97 | 1.83% | 0.668 | 0.000294 |
| core | 90 | 35805 | 449 | 1.25% | 10618 | 198 | 1.86% | 0.672 | 2.42e-06 |
| expanded (+ sexual harassment) | 30 | 28311 | 369 | 1.30% | 5325 | 69 | 1.30% | 1.006 | 0.964 |
| expanded (+ sexual harassment) | 60 | 33636 | 438 | 1.30% | 5304 | 100 | 1.89% | 0.691 | 0.00072 |
| expanded (+ sexual harassment) | 90 | 35805 | 477 | 1.33% | 10618 | 203 | 1.91% | 0.697 | 1.26e-05 |
| title_ix_any | 30 | 28311 | 89 | 0.31% | 5325 | 17 | 0.32% | 0.985 | 0.953 |
| title_ix_any | 60 | 33636 | 106 | 0.32% | 5304 | 35 | 0.66% | 0.478 | 0.000102 |
| title_ix_any | 90 | 35805 | 120 | 0.34% | 10618 | 65 | 0.61% | 0.547 | 6.92e-05 |
| sv_terms_any | 30 | 28311 | 299 | 1.06% | 5325 | 54 | 1.01% | 1.041 | 0.782 |
| sv_terms_any | 60 | 33636 | 353 | 1.05% | 5304 | 70 | 1.32% | 0.795 | 0.0776 |
| sv_terms_any | 90 | 35805 | 381 | 1.06% | 10618 | 155 | 1.46% | 0.729 | 0.000803 |
| core_ex_cornell_lsu | 30 | 28311 | 304 | 1.07% | 5325 | 61 | 1.15% | 0.937 | 0.643 |
| core_ex_cornell_lsu | 60 | 33636 | 365 | 1.09% | 5304 | 95 | 1.79% | 0.606 | 9.75e-06 |
| core_ex_cornell_lsu | 90 | 35805 | 402 | 1.12% | 10618 | 194 | 1.83% | 0.615 | 1.5e-08 |

Through September, the 30-day core share is **1.23%** vs
**1.18%** (RR **1.039**,
p = **0.779**) — flat. Over 60 and 90 days it is lower
(RR **0.668** and **0.672**). Excluding Cornell/LSU,
the 30-day through-September RR is **0.937** and the 90-day RR is
**0.615**. This confirms that the October full-text "spike" is the
Cornell/LSU news cycle seen through a very small number of available bodies.

## 5. Outlet-constant / fixed-effects-style check

Outlets are messy labels; `clean_outlet()` normalizes `www.` and RSS suffixes.
The common-outlet panel keeps only outlets with **at least 5 stories in both**
the recent and prior windows. "Std. prior %" re-weights each common outlet's prior
rate by its **recent** story share (direct standardization), so it answers: would the
prior period have looked different if it had today's outlet mix?

| Series | Days | Recent outlets | Prior outlets | Common outlets | Recent vol | Prior vol | Volume ratio | Common recent N | Common prior N | Common recent % | Common prior % | Common RR | p | Std. prior % | Std. RR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| core | 30 | 712 | 569 | 416 | 31324 | 16610 | 1.886 | 27438 | 16101 | 1.33 | 1.03 | 1.294 | 0.00548 | 1.07 | 1.252 |
| core | 60 | 749 | 339 | 160 | 47934 | 5187 | 9.241 | 21421 | 4709 | 1.37 | 1.64 | 0.839 | 0.168 | 1.56 | 0.882 |
| core | 90 | 754 | 727 | 558 | 50060 | 10556 | 4.742 | 43524 | 9523 | 1.35 | 1.89 | 0.712 | 5.6e-05 | 1.67 | 0.806 |
| headline_only_core | 30 | 712 | 569 | 416 | 31324 | 16610 | 1.886 | 27438 | 16101 | 0.72 | 0.19 | 3.853 | 1.04e-13 | 0.19 | 3.856 |
| headline_only_core | 60 | 749 | 339 | 160 | 47934 | 5187 | 9.241 | 21421 | 4709 | 0.64 | 0.15 | 4.334 | 3.4e-05 | 0.16 | 4.074 |
| headline_only_core | 90 | 754 | 727 | 558 | 50060 | 10556 | 4.742 | 43524 | 9523 | 0.57 | 0.22 | 2.594 | 1.26e-05 | 0.14 | 4.072 |
| core_ex_cornell_lsu | 30 | 712 | 569 | 416 | 31324 | 16610 | 1.886 | 27438 | 16101 | 1.00 | 1.00 | 0.999 | 0.989 | 1.04 | 0.961 |
| core_ex_cornell_lsu | 60 | 749 | 339 | 160 | 47934 | 5187 | 9.241 | 21421 | 4709 | 1.01 | 1.59 | 0.633 | 0.000541 | 1.49 | 0.675 |
| core_ex_cornell_lsu | 90 | 754 | 727 | 558 | 50060 | 10556 | 4.742 | 43524 | 9523 | 1.12 | 1.84 | 0.608 | 9.17e-09 | 1.61 | 0.693 |
| headline_ex_cornell_lsu | 30 | 712 | 569 | 416 | 31324 | 16610 | 1.886 | 27438 | 16101 | 0.46 | 0.18 | 2.550 | 2.35e-06 | 0.18 | 2.535 |
| headline_ex_cornell_lsu | 60 | 749 | 339 | 160 | 47934 | 5187 | 9.241 | 21421 | 4709 | 0.39 | 0.13 | 3.041 | 0.00555 | 0.12 | 3.116 |
| headline_ex_cornell_lsu | 90 | 754 | 727 | 558 | 50060 | 10556 | 4.742 | 43524 | 9523 | 0.40 | 0.22 | 1.813 | 0.00884 | 0.14 | 2.845 |

For the 90-day core comparison the overall volume ratio is
**4.74×**. The common-outlet core RR is
**0.712** (p = 5.6e-05) and the
mix-standardized RR is **0.806**, versus the overall
**0.643**. Holding outlets fixed therefore explains part but not
all of the 90-day decline: the core share still falls among continuing outlets.
For the 30-day window, the common-outlet core RR is **1.294**
(p = 0.00548) and the ex-event version is
**0.999** (p = 0.989), again showing that the
short-term rise is event-driven. The `..._outlet_shift_90d.csv` file lists the outlets
with the largest changes.

## 6. Which component drives the change?

| Series | Days | Recent matches | Recent % | Prior matches | Prior % | Rate ratio | p |
|---|---|---|---|---|---|---|---|
| title_ix_any | 30 | 98 | 0.31% | 41 | 0.25% | 1.267 | 0.201 |
| title_ix_any | 90 | 148 | 0.30% | 66 | 0.63% | 0.473 | 2.12e-07 |
| sv_terms_any | 30 | 346 | 1.10% | 147 | 0.89% | 1.248 | 0.0234 |
| sv_terms_any | 90 | 519 | 1.04% | 155 | 1.47% | 0.706 | 0.000122 |
| title_ix_only | 30 | 64 | 0.20% | 25 | 0.15% | 1.357 | 0.193 |
| title_ix_only | 90 | 94 | 0.19% | 46 | 0.44% | 0.431 | 1.41e-06 |
| sv_only | 30 | 312 | 1.00% | 131 | 0.79% | 1.263 | 0.024 |
| sv_only | 90 | 465 | 0.93% | 135 | 1.28% | 0.726 | 0.000963 |
| both | 30 | 34 | 0.11% | 16 | 0.10% | 1.127 | 0.693 |
| both | 90 | 54 | 0.11% | 20 | 0.19% | 0.569 | 0.0291 |

- **Title IX (any):** 30-day **0.31%** vs
  **0.25%** (RR **1.267**,
  p = **0.201**); 90-day RR **0.473**
  (p = **2.12e-07**).
- **Sexual-violence terms (any):** 30-day **1.10%** vs
  **0.89%** (RR **1.248**,
  p = **0.0234**); 90-day RR **0.706**
  (p = **0.000122**).
- **Expanded (+ sexual harassment):** 30-day RR **1.247**
  (p = **0.0119**); 90-day RR **0.663**
  (p = **2.11e-07**). Sexual harassment barely moves the totals.
- **Title IX-only vs SV-only:** 30-day Title IX-only RR **1.357**
  (p = 0.193); SV-only RR **1.263**
  (p = 0.024); both RR **1.127**
  (p = 0.693). At 90 days the corresponding RRs are
  **0.431**, **0.726** and
  **0.569**. The short-term movement is driven by sexual-violence
  terms, not Title IX policy/athletics coverage.

Title IX athletics/equity-only stories are separated in the matches CSV
(`tix_equity_only`), so they can be removed; they account for
**95** 2026 stories.

## 7. Confounders and denominator integrity

1. **2026 is essentially the whole database.** 64,681 of 68,581 rows
   (94.3%) are 2026, so these are the dataset's trends, not an
   independent 2026 sample.
2. **Ingestion/coverage changed sharply.** Monthly stories rise from
   362 (Jan) to 28,311
   (Sep), while distinct outlets rise from 79 to
   664. Stories per observed day
   go from 11.7 to
   943.7. This is a coverage
   expansion, not necessarily a publication boom. Any raw-count comparison is invalid.
3. **Academic calendar.** August→September is back-to-school and campus-crime
   coverage season. September and October are the first full months of the fall term;
   the data contain no prior autumn in comparable volume (2025 has only ~1,268 stories
   all year), so seasonality cannot be estimated from this DB.
4. **Partial October.** October covers only 1–15; counts are not comparable
   to full months. The monthly **rate** is still usable for headline/metadata, but with
   wide confidence intervals.
5. **October body-extraction gap.** 13,559 October rows have a path and
   13,559 are marked ok, but only **230** files exist. The
   full-text-inclusive October count (189) is therefore
   mostly a metadata count: only **11** of those 189
   matches have a body. The through-September sensitivity is the valid full-text trend.
6. **A single news cycle dominates early October.** In the last 30 days,
   **88** core stories have Cornell/Chi Phi in the headline,
   **11** have LSU/Tigerland, and **99** have either
   (24% of the 410
   core matches). The Cornell Chi Phi gang-rape case generated national coverage across
   many student papers; it is an event spike, not a broad secular trend. Event
   attribution is based on **headline tokens only**, so event coverage that never
   says "Cornell", "Chi Phi" or "LSU" remains in the ex-event series. The ex-event
   estimates are therefore conservative: the true non-event rise is at most what
   they show, and the true event share is at least 24%.
7. **Syndicated / sponsored `online_features` pages.** These rise from 0% in
   Jan–May to 14.2% in September
   and 10.6% in October (mostly four
   "RSS Results" outlets). They are not student journalism and they inflate the
   denominator. Excluding them, the 90-day core RR is **0.719**
   (p = 3.96e-05) — still lower than the prior window.
8. **Same-day capture share** is high in September
   (69.8% of
   stories captured on their published date), so most September volume is live
   publication rather than a historical archive dump. The 2026-06-23 context note
   describes an earlier outlet/cascade-scraper expansion; the September jump is a
   later, much larger coverage ramp.
9. **Outlet churn.** The common-outlet panel above removes outlets absent in one
   window. Even there, the 90-day core share falls (RR 0.712),
   so outlet churn is not the whole explanation; composition explains part of it.
10. **Keyword matching is not topic classification.** A story that mentions sexual
    assault in a content warning is counted; a story about "inappropriate conduct"
    without a listed term is missed. Headline-only is high precision but low recall.
11. **Duplicate/syndicated headlines.** Rows are unique URLs, so syndicated copies
    across outlets are counted separately (which is appropriate for measuring
    coverage volume, but not for counting distinct incidents).

## 8. Verdict

**Is there evidence of a recent rise? It depends on the measure, and the honest answer is: a short event-driven spike, not a sustained rise.**

- **Raw counts:** core matches are **613** in the last 90 days
  vs **201** in the preceding 90 days — up
  **3.05×**, while total story
  volume is up **4.74×**. Counts rose *less* than
  the denominator, so raw counts are **not** evidence of a topic rise.
- **Share of coverage, 90 days:** core **1.22%** vs
  **1.90%**, RR **0.643**
  (p = 3.53e-08) — **down**, not up. Sixty-day RR is
  **0.741**. The full-text trend through September is also flat
  month-over-month (RR 1.039) and lower over 90 days
  (RR 0.672).
- **Share of coverage, 30 days:** core **1.31%** vs
  **1.04%** (RR **1.264**,
  p = 0.0093) — up. But excluding Cornell/LSU headlines it is
  **0.99%** vs **1.01%**
  (RR **0.987**, p = 0.895) — **flat**.
  The 30-day rise is the Cornell/LSU news cycle.
- **Headline salience is the one genuine broader signal:** 30-day headline share
  **0.73%** vs **0.18%**
  (RR **4.030**), and still **0.48%**
  vs **0.17%** (RR **2.743**) after
  removing the named events. Over 90 days, headline RR **2.511**
  (ex-event **1.744**). This is consistent with a national campus
  sexual-violence news cycle raising headline salience beyond the originating case,
  but the absolute share is still only ~0.4–0.7% of stories.
- **Versus the 2026 year-to-date baseline:** the 30-day core share
  (1.31%) is **below** the YTD baseline
  (1.44%, RR 0.912);
  the 30-day headline share (0.73%) is **above** its
  baseline (0.19%,
  RR 3.916). So even the headline rise is a
  within-year news-cycle deviation, not a new level.
- **Outlet-constant check:** 90-day common-outlet RR **0.712**
  (p = 5.6e-05); mix-standardized RR **0.806**.
  The decline survives holding outlets fixed; the 30-day rise is not an artifact of
  which outlets were scraped, but it is an artifact of one news event.

**Bottom line:** There is **no evidence of a sustained recent rise in the share of
coverage** devoted to Title IX / sexual violence. Over 60–90 days the share is lower
than the preceding period, and the September/October denominator explosion
(roughly 5.3×
August volume) means raw counts are misleading. There **is** a genuine, statistically
significant **short-term spike in headline salience in late September–early October**,
centered on the Cornell Chi Phi case (plus LSU), which spilled over into broader
campus commentary. That is an event, not a trend. If the question is "are more
stories being written about these topics lately?", the answer is yes in raw counts,
mostly because far more stories are being ingested; the topic's **share** of coverage
is flat over the last month once the event is removed and lower over the last quarter.

## Files created

- `analytics/title_ix_sexual_violence_2026_report.md`
- `analytics/title_ix_sexual_violence_2026_scopes.csv`
- `analytics/title_ix_sexual_violence_2026_monthly.csv`
- `analytics/title_ix_sexual_violence_2026_weekly.csv`
- `analytics/title_ix_sexual_violence_2026_recent_vs_prior.csv`
- `analytics/title_ix_sexual_violence_2026_recent_vs_prior_fulltext_through_sep.csv`
- `analytics/title_ix_sexual_violence_2026_matches.csv`
- `analytics/title_ix_sexual_violence_2026_outlet_shift_90d.csv`
- `analytics/title_ix_sexual_violence_2026_monthly.png`
- `analytics/title_ix_sexual_violence_2026_weekly.png`
- `analytics/title_ix_sexual_violence_2026_rate_ratios.png`
- `scripts/title_ix_definitions.py`
- `scripts/analyze_title_ix_sexual_violence_2026.py`
