# Dev Log

Project memory for agents. Newest entry first. One entry per work session or checkpoint.

<!-- dev-log:entries -->

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
