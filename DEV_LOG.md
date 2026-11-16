# Dev Log

Project memory for agents. Newest entry first. One entry per work session or checkpoint.

<!-- dev-log:entries -->

## 2026-11-16 — Added The Duke Chronicle

- **Agent:** Copilot
- **Intent:** Add The Duke Chronicle to the news database and CI collection.
- **Code:** Added the advertised feed to `extra_urls.txt` for both CI schedules; shared a 10-second host delay between feed and full-text requests, used the existing browser User-Agent override, and excluded the outlet from topic-model retraining. The existing hard-outlet entry remains skipped because the feed works.
- **Data:** Captured 20 feed entries in `news_database.csv`, pending the normal nightly full-text extraction. The outlet was already in the location directory.
- **Why:** The identifying bot User-Agent receives HTTP 403; the site's robots.txt requests a 10-second crawl delay and no AI model training. The user confirmed the Hugging Face dataset is private and approved public headline metadata.
- **Verified:** Live feed returned 20 entries and one article yielded extractable text; three focused tests passed, CSV schema validation passed, and Pylance reported no syntax errors.
- **Open:** Full-text extraction and dashboard updates occur in the next nightly CI run; the CI Hugging Face destination must remain private.

## 2026-11-04 — Report 2 (local vs national elections), Sep 1–Nov 4 window

- **Agent:** opencode / deepseek-v4-pro
- **Intent:** Re-run the local-vs-national elections report over the refreshed Sep 1 – Nov 4, 2026 window, extending the prior pass (which stopped at Oct 26), with the required LOCAL-vs-NATIONAL comparison, student-government break-out, weekly trend, topic-mix vs dashboard categories, and a fresh precision spot-check on both the original gate and the expanded-gate additions.
- **Code:** Reused `01_classify.py` (dual gate unchanged) and `05_stats_aug2026.py`. New scripts: `08_report_sep2026.py` (weekly ISO-week table + jurisdiction chart, late-Oct/early-Nov delta vs the Sep 1–Oct 26 baseline, topic mix vs `data/topic_labels.json`, 20 evenly-spaced verification sample), `09_sample_sep2026.py` (30 expanded-only + 20 original-gate precision samples), `10_record_labels_sep2026.py` (labels + precision print).
- **Data:** Deduped window universe 54,146 (59,212 ok rows). Expanded gate 2,193 matches (4.05%), original 2,066 (3.82%), raw pre-dedupe 2,261/2,130. Split (expanded): BOTH_UNCLEAR 967 / NATIONAL 779 / LOCAL 447; 153 student-gov (145 LOCAL). Non-SG: LOCAL 302 vs NATIONAL 777 (~2.6× national). Timing: LOCAL leads through late Sep (student-gov season), NATIONAL overtakes early Oct and dominates through Election Day; **new Oct 27–Nov 4 = 526 stories (11% local / 33% national / 56% state-mixed), only 4 student-gov**. Precision: combined 50-sample strict 94% / loose 98%; expanded-only additions 30-sample strict 93.3% (0 FP). Error families: "midterm=exams" FPs (~18), body-count FP (1), "U.S. House District N" jurisdiction tie (1), stray body "midterm" mislabeling a local board race.
- **Why:** `keyword_trends/` was deleted, so this themed report runs the reusable `analysis-local-vs-national-elections` classifier, not the keyword_trends tool.
- **Verified:** Classifier re-run reproduces the existing `summary_sep2026.json` exactly; `08`–`10` run clean; 4 charts + weekly/topicmix/verification/precision CSVs written. Body coverage 84.6% universe / 71.9% matches (newest captures outrun backfill).
- **Open:** Corpus-index subset (`publication_story_index.csv`) ends 2026-08-31, so 0 of this window's matches overlap it by exact URL (94% by domain). Not committed (data-researcher/ is gitignored).
- **Git:** `main`; no commit made (per task).

## 2026-11-04 — Report: Sports betting / sports gambling, Sep 1–Nov 4 window

- **Agent:** opencode / deepseek-v4-pro
- **Intent:** Re-run the sports-betting/gambling report over the refreshed Sep 1 – Nov 4, 2026 window (the prior pass stopped at Oct 22), with the athlete-pressure / money-in-college-sports sub-analysis and a fresh precision spot-check.
- **Code:** Reused `01_match.py`, `06_athlete_pressure.py`, `07_athlete_review.py`, `05_stats_aug2026.py` (matcher rules unchanged). Two tiny, traceable edits: `07_athlete_review.py` now reads `athlete_review_labels{SFX}.csv` (so the Aug labels survive), and `05_stats_aug2026.py` writes `timeseries_daily{SFX}.png` (so the Aug chart survives). New scripts: `make_sep_review_labels.py` (derives the Sep athlete-review labels from the Aug labels with set-equality asserts — the threat/education sets are identical, help drops only row 21695), `08_weekly_and_mix.py` (weekly corpus/matches/share + topic mix vs `data/topic_labels.json`), `09_precision_sample.py`, `10_record_precision_labels.py`.
- **Data:** Deduped window universe 54,146 (59,212 ok rows; 5,066 dupes). 173 matches (0.32%), raw pre-dedupe 177; match types strong 159 / generic-with-sports 12 / prediction-market 2. Monthly Sep 111 / Oct 60 / Nov 2. Novig/Sweeney cluster 84 (48.6%); weekly share spikes to 0.62% in W39–W40 then slides to ~0.10% by W45. **New (Oct 23–Nov 4): 11 matches** (Kalshi college-admissions markets, betting-out-of-elections, NBA partnerships, campus survey solicitations; 3 in the Novig cluster). Athlete pressure (manual review): threats 13 (10 incident/survey, 3 opinion, 0 FP), education 7 (3 program, 1 advocacy, 1 proposal, 2 FP), help 11 (5 helpline/expert, 3 boilerplate, 2 school resources, 1 FP). Precision: 25-sample spot-check strict 18/25 (72%), loose 96%, 1 FP.
- **Why:** Dataset refreshed through Nov 4; the newest ~9 days (Oct 27+) have **zero full-text bodies** (backfill not caught up), so the tail is title-only and the headline count there is a lower bound — flagged as a new caveat.
- **Verified:** All 47 report hyperlinks resolve to dataset rows (3 appear "missing" only because tracking params were stripped); 5 chart links resolve; Sep-labels set on charts.
- **Open:** None.
- **Git:** not committed (data-researcher/ is gitignored; DEV_LOG.md untracked).

## 2026-11-04 — Report: Title IX / sexual assault / sexual violence, Sep 1–Nov 4 window

- **Agent:** opencode / deepseek-v4-pro
- **Intent:** Re-run the Title IX/sexual-violence report over the refreshed Sep 1 – Nov 4, 2026 window, extending the prior Sep 1 – Oct 26 pass, and add the required rigor (precision spot-checks, Greek/party context sub-analysis, topic mix, "what's new").
- **Code:** `data-researcher/analysis-title-ix-sexual-violence/08_precision_spotcheck.py` (draws 30-match + 30-Greek/party samples, seed 20261104), `09_record_labels.py` (labels + precision print), `10_stats_sep2026.py` (weekly/monthly tables, topic mix vs `data/topic_labels.json`, context, what's-new, 5 charts with corrected "Sep 1" labels), `11_verification_sample.py` (20 evenly-spaced examples + Oct 27–Nov 4 listing). Reuses `load_stories.build`, `01_match.py`, `07_context_flags.py` (matcher rules unchanged).
- **Data:** Deduped window universe 54,146; 874 matches (1.61%); monthly Sep 161 / Oct 703 / Nov 10. Event-driven: 67 pre-Sep-21 vs 807 post; Chi Phi mentioned in 275 (31.5%); Greek-life flag 296 (33.9%), party-near-SV 117. New (Oct 27–Nov 4): 34 matches, 0.53% (3.78/day vs 15.0/day prior), 0 Chi Phi. Precision: matches 25/30 strict (83.3%), loose 100%; Greek/party context 28/30 (93.3%), 2 FPs = "party" word-sense (legal "party to a crime", political "pro-family party").
- **Why:** `keyword_trends/` was deleted and this is a themed report, so it runs the reusable `analysis-title-ix-sexual-violence` matcher, not the keyword_trends tool.
- **Verified:** `01_match.py`/`07_context_flags.py` pickles (t9_scored/t9_context_sep2026.pkl) already present and consistent with the 59,212 ok window rows; `08`–`11` run clean; `summary_sep2026.json` + 5 PNGs + precision/verification CSVs written. Body coverage now 84.6% (newest captures outran backfill; 57 matches head-only).
- **Open:** Corpus-index subset (`publication_story_index.csv`) ends 2026-08-31, so 0 of this window's matches overlap it. Not committed (data-researcher/ is gitignored).
- **Git:** `main`; no commit made (per task).

## 2026-11-04 — Report 1 (free speech / First Amendment / censorship), Sep 1–Nov 4 window

- **Agent:** opencode / deepseek-v4-pro
- **Intent:** Rebuild the free-speech matcher (the `keyword_trends` tool it previously used was deleted) and re-run the topic report over the refreshed Sep 1 – Nov 4, 2026 window, extending the prior Sep 1 – Oct 26 report.
- **Code:** `data-researcher/analysis-free-speech-first-amendment-censorship/match_freespeech.py` (self-contained matcher reconstructing the four documented rules, first-match attribution, no `\bfree press\b`); `report_analysis.py` (aggregates, weekly/topic/outlet tables, verification + precision samples, 4 charts). Reuses `load_stories.build`.
- **Data:** Deduped window universe 54,146 (was 45,567 on the Oct 26 snapshot); 403 matched stories (0.74%); rule composition free_speech 282 / censorship 49 / first_amendment 45 / book_ban_precise 27. Wave receded: weekly share 1.00% (W39 Sep 21–27) → 0.15% (W44) / 0.19% (W45 partial). Only 11 new matches Oct 27–Nov 4. Precision spot-check 22/30 strict (73%), 1 clear FP (print-edition "Free Speech Zone" ToC pollution).
- **Why:** `keyword_trends/` now holds only a stale `.pyc`; the report-4 file was historical ordering, so this uses the report-1 slot per instructions.
- **Verified:** `match_freespeech.py` and `report_analysis.py` both run clean; `summary_sepnov2026.json`, `matches_deduped_sepnov2026.csv`, `precision_sample_sepnov2026.csv`, and 4 PNGs written.
- **Open:** None for this report. Not committed (data-researcher/ is gitignored).
- **Git:** `main`; no commit made (per task).

## 2026-10-26 — Added "Private" university-type cohort from IPEDS CONTROL

- **Agent:** opencode / glm-5.3-flash-free
- **Intent:** Let the dashboard filter to private institutions only, parallel to the existing land-grant/HBCU flags.
- **Code:** `scripts/label_school_types.py` gains `is_private()` (IPEDS `CONTROL` 2=private nonprofit, 3=private for-profit, else False) and a new `private` column written to `publication_locations.csv`; added to the fuzzy-match key whitelist too. `scripts/build_dashboard_data.py` adds `private` to `COHORTS` with wire letter `p` in `COHORT_LETTER`/`source_flags`/map pubs. `student-media-tracker/index.html` adds the Private button after Land-grant, `private:"p"` in COHORT_LETTER/COHORT_LABEL, updates the IPEDS metadata message, and skips the "small cohorts run thin" note for private (large cohort).
- **Data:** `data/publication_locations.csv` now has a `private` column (393 of 941 rows true; 28,743 stories = 35.9%); dashboard rebuilt — `dashboard_data.js/.json` 5 cohorts, private = 25,100 classified stories / 432 publications; 75 headline shards rewritten with per-cohort private samples.
- **Why:** CONTROL already exists in `data/all-schools-2023.csv`, so no new data source; unmatched institutions get private=False like the other flags, so they appear only under All.
- **Verified:** Both scripts re-run; `node` parse of `dashboard_data.js` shows cohorts all/landgrant/hbcu/community/private with private totals; 417 publications carry the `p` flag incl. spot-checks (e.g. 9th Street Journal).
- **Open:** None.
- **Git:** `main` @ `d495687`, ~88 files uncommitted (data rebuild + code; not committed).

## 2026-10-26 — Default timeseries chart to 7-day average

- **Agent:** Copilot
- **Intent:** Show smoothed timeseries data by default when the dashboard loads.
- **Code:** Updated the smoothing control's initial accessible state and chart state to select 7-day avg; Reset now restores that default.
- **Why:** Make the more readable smoothed series the initial chart view.
- **Verified:** Confirmed the initial and reset state use `smooth: true`, with matching `aria-pressed` values.
- **Open:** None.

## 2026-10-26 — Re-ran and replaced the three Aug-2026-window reports with expanded coverage

- **Agent:** opencode / glm-5.3-flash-free
- **Intent:** Refresh the Title IX, elections, and sports-betting reports over the re-merged dataset (deduped window universe 48,058 → 47,305 after commit ee83989), expand election-window term coverage, and add new sub-analyses.
- **Code:** `analysis-local-vs-national-elections/01_classify.py` now runs a dual gate (original 1,394 / expanded 1,480 matches, +86 from candidates/debates/forums/guides/logistics terms with manual-read guard fixes); `06_sample_expanded.py` + `07_record_expanded_labels.py` added (sampled expanded-gate precision: strict 26/30 = 86.7%, jurisdiction OK 25/29). `analysis-title-ix-sexual-violence/07_context_flags.py` added (Greek 279, inst-failure 198, gang-rape 138 etc.); `06_stats_aug2026.py` fixed a split-boundary bug (Sep-20 daytime stories fell out of both pre/post halves; now 92 pre + 685 post = 777) plus context charts. `analysis-sports-betting-gambling/06_athlete_pressure.py` + `07_athlete_review.py` added: threats 13 (10 real reports / 3 opinion), education 7 (3 programs; 2 FP), help 12 (5 helpline-data/expert, 4 boilerplate, 2 school resources, 1 FP); Novig/Sweeney cluster = 81 of 161; manual labels assert-locked in `athlete_review_labels.csv`.
- **Data:** Verified full-text bodies present for 100% of the 47,305 deduped window rows (window http_403 = 4,429, not the 5,689+ from the task brief); latest dated story Oct 22, 2026 (partial day).
- **Why:** Dataset was re-merged between passes, so old windowed counts (795/1,442/166) were stale; the elections brief asked for candidate/debate/logistics-style coverage the original gate missed; conference-reviewed education/help were polluted by marketing "campaigns", sports-medicine "trainer", and SEO casino advertorials, hence tighter proximity rules + manual labels.
- **Verified:** All three `analysis-*/summary_aug2026.json` + charts regenerated; all 9 chart links in the reports resolve; corpus-index carry-overs re-checked (R1 14/777, R2 69/1,394 + 2/86, R3 0/161).
- **Open:** Reports 1–3 in `data-researcher/reports/` are uncommitted (data-researcher/ is gitignored); UNF "presidential candidate" election FP remains unguarded; casino advertorials still ride some feeds (near-misses only); Oct 22 is a partial capture day.
- **Git:** `main` @ `ee83989`, `DEV_LOG.md` untracked.
