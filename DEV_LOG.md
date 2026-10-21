# Dev Log

Project memory for agents. Newest entry first. One entry per work session or checkpoint.

<!-- dev-log:entries -->

## 2026-10-21 16:30 — Merged origin/main into code-refactor (school-type schema kept)

- **Agent:** opencode / claude-haiku-5-5
- **Branch:** `code-refactor` only. **NOT merged to `main`.** Local `main` is still at `3aba7f5`; `code-refactor` is 30 commits ahead and already contains `origin/main` (`3b49583`), so the merge is ready to go to `main` later but has not been done.
- **Intent:** Resolve the merge conflicts from pulling `origin/main` (automated "Capture new stories" data commits) into `code-refactor`.
- **Code:** Merge commit `cf9428e`. Non-conflicting source changes from both sides merged cleanly: `scrape.py`, `fetch_full_text.py`, `http_compat.py`, `news_database.csv`.
- **Data:** `data/publication_locations.csv` kept on the `code-refactor` side: 15 columns including `land_grant`, `hbcu`, `community_college`, `ipeds_unitid`, `ipeds_name`, `school_type_match`. It also has origin's new `staging.thehilltoponline.com` row (941 to 942 rows). The 14 conflicted generated files (`headlines/*`, `search/*`, `dashboard_data.*`, `map_points.*`, `map/map_data.*`) were regenerated, not hand-merged.
- **Why:** Origin's version of `publication_locations.csv` has only 9 columns and no school-type labels. The dashboard cohort filter (landgrant/hbcu/community) reads those labels, so the 15-column schema was kept. Regeneration followed CI order from `.github/workflows/daily-scrape.yml`: `geocode_publications.py`, `label_school_types.py`, `build_map_data.py`, `build_dashboard_data.py`.
- **Verified:** No conflict markers remain. `python3 -m py_compile scrape.py http_compat.py fetch_full_text.py scripts/*.py` passed. `dashboard_data.json` and `map_points.json` parse. The four regeneration scripts exited 0. Landgrant cohort: 8,220 classified stories across 78 publications.
- **Not run:** `scrape.py` and the full-text restore. `full_text/` exists locally but was not checked against `news_database.csv`.
- **Open:**
  - Six institutions have no IPEDS match and are not flagged: Bloomsburg University, SUNY New Paltz, Brookhaven College, Newmark Graduate School of Journalism at CUNY, Morningside College, Emory & Henry College. Add to `data/school_type_overrides.csv` if they should be in cohorts.
  - `publication_story_index.csv` (repo root, not under `data/`) is dated Aug 31. Geocoding read it without error, but freshness is unverified. Check whether it is tracked or regenerated before trusting new-domain counts.
  - Local `main` is behind `origin/main`. Pull it before any `main` merge.
  - 27+ untracked files are not part of this merge: `analytics/title_ix_sexual_violence_*` and `data-researcher/`. Decide whether to commit them on `code-refactor`.
  - Next step: review and push `code-refactor` (not yet pushed), then decide on merging to `main`.
- **Git:** `code-refactor` @ `cf9428e`. Merge committed. Log and `AGENTS.md` left uncommitted.

