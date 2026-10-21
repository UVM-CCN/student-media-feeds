# Title IX and sexual violence in the student-media news database

**Database:** `news_database.csv`  
**Rows (denominator):** **68,581** stories  
**Analysis date:** 2026-10-20  
**Primary script:** `scripts/analyze_title_ix_sexual_violence.py`

## Headline answer

Using a full-text-inclusive keyword/regex classifier over **68,581 stories**, **964 stories (1.41%)** match the core set: **Title IX OR any sexual-violence/abuse term** (sexual violence, sexual assault, rape, sexual abuse, sexual misconduct, molestation, groping, indecent assault, nonconsensual sex, sexual coercion, sexual battery).

If "sexual harassment" is added, the count rises to **1,005 (1.47%)**. If the unrelated-but-adjacent terms (domestic violence, intimate-partner/dating violence, stalking, non-sexual harassment, trafficking, exploitation, consent) are added, the broad tracked set is **1,526 (2.23%)**.

The literal four-term version in the question (Title IX OR the phrase "sexual violence" OR sexual assault OR rape) is **843 stories (1.23%)**.

> **Field dependence:** headline-only finds **309** core stories; adding keywords/theme finds **312**; full text adds **652** more, for **964**. Full text exists for **49,490 of 68,581 stories (72.2%)**, so even the 964 figure is a lower bound for the whole database. Among full-text-covered stories, 769 are core (1.55%); among stories with no extracted body, 195 are core (1.02%).
>
> **Prominence sensitivity:** requiring a headline hit or at least three core-category regex hits yields **466 stories (0.68%)**, between the headline-only and any-mention figures. This is a reasonable "more clearly about the topic" subset.

## Data and schema (verified, not assumed)

The CSV is UTF-8, comma-delimited, with **68,581 data rows and 16 columns**. `link` is unique (68,581 unique), so each row is treated as one story. `title` is never blank. Full text is extracted body text on disk, not a CSV column.

| Column | Non-empty | Unique | Role in this analysis |
|---|---:|---:|---|
| source | 68,581 | 942 | Outlet label |
| title | 68,581 | 63,882 | Headline search |
| link | 68,581 | 68,581 | Story ID |
| published | 67,421 | 54,573 | Year trend |
| keywords | 68,527 | 63,349 | Metadata search |
| theme | 22,662 | 553 | Metadata search |
| full_text_path | 64,037 | 63,791 | Points to extracted body |
| extraction_status | 67,882 | 12 | Full-text quality |

**Text fields actually searched:**

1. **Headline only:** `title`.
2. **Metadata:** `title` + `keywords` + `theme`.
3. **Full-text inclusive:** metadata + the body portion of the file at `full_text_path` (the `# ---` header is stripped). This is the headline figure.

`publication_story_index.csv` has 23,435 stories and 19,109 URL overlaps with the database; 23,435 of its indexed files exist. It contains **0** URLs for database rows that lack full text, so it cannot fill coverage gaps. `bag_of_words.csv` is a corpus-level vocabulary table (164,981 rows, 4 columns) with no story IDs and was not used for story classification.

## Method

- Case-insensitive, Unicode word-boundary regexes. Each story is counted **once per category**, no matter how many keyword occurrences it has.
- Core set = `title_ix` OR any of: `sexual_violence`, `sexual_assault`, `rape`, `sexual_abuse`, `sexual_misconduct`, `molestation`, `groping`, `indecent_assault`, `nonconsensual_sex`, `sexual_coercion`, `sexual_battery`.
- Sexual harassment is reported separately, then added in the "expanded" definition.
- Domestic violence, intimate-partner violence, dating violence, stalking, generic harassment, sex trafficking, sexual exploitation and sexual consent are reported as **related, not core**.
- Title IX stories are split into athletics/equity context vs. sexual-harm context so the user can remove sports-equity cases if desired.
- Raw hit counts are regex occurrences across the searched text; unique-story counts are the primary measure.

## Counts by definition

| Definition | Stories | % of total | Headline only | Metadata |
|---|---:|---:|---:|---:|
| Strict literal core: Title IX OR "sexual violence" OR sexual assault OR rape | 843 | 1.23% | 270 | 273 |
| Core: Title IX OR any sexual-violence/abuse term (excl. sexual harassment) | 964 | 1.41% | 309 | 312 |
| Expanded: core + sexual harassment | 1,005 | 1.47% | 316 | 319 |
| Broad: expanded + domestic/intimate-partner/dating violence, stalking, generic harassment, trafficking, exploitation, consent | 1,526 | 2.23% | 378 | 382 |

Additional splits for Title IX:

- Title IX stories (any): **257**
- Title IX + sexual-harm context: **97**
- Title IX + athletics/equity context (any): **162**
- Title IX athletics/equity **only** (no SV/harassment): **104**
- Core excluding Title IX athletics/equity-only: **860**
- Sexual-violence/abuse terms anywhere (with or without Title IX): **798**
- Sexual-violence/abuse terms without any Title IX mention: **707**

## Per-category counts

A story can hit multiple categories, so the category counts do **not** add up to the core total.

| Category | Group | Raw regex hits | Unique stories | % of total | Headline only | Metadata | Added by full text |
|---|---|---|---|---|---|---|---|
| title ix | core | 598 | 257 | 0.37% | 53 | 53 | 204 |
| sexual violence | core | 328 | 166 | 0.24% | 52 | 52 | 114 |
| sexual assault | core | 810 | 373 | 0.54% | 88 | 88 | 285 |
| rape | core | 639 | 315 | 0.46% | 84 | 87 | 228 |
| sexual abuse | core | 250 | 134 | 0.20% | 23 | 23 | 111 |
| sexual misconduct | core | 135 | 80 | 0.12% | 16 | 16 | 64 |
| molestation | core | 9 | 6 | 0.01% | 0 | 0 | 6 |
| groping | core | 10 | 8 | 0.01% | 1 | 1 | 7 |
| indecent assault | core | 7 | 5 | 0.01% | 1 | 1 | 4 |
| nonconsensual sex | core | 12 | 9 | 0.01% | 0 | 0 | 9 |
| sexual coercion | core | 1 | 1 | 0.00% | 0 | 0 | 1 |
| sexual battery | core | 15 | 10 | 0.01% | 1 | 1 | 9 |
| sexual harassment | harassment | 124 | 79 | 0.12% | 7 | 7 | 72 |
| domestic violence | related | 317 | 201 | 0.29% | 31 | 31 | 170 |
| intimate partner violence | related | 16 | 12 | 0.02% | 1 | 1 | 11 |
| dating violence | related | 39 | 25 | 0.04% | 2 | 2 | 23 |
| stalking | related | 308 | 168 | 0.24% | 19 | 19 | 149 |
| harassment generic | related | 773 | 430 | 0.63% | 27 | 29 | 401 |
| sex trafficking | related | 81 | 37 | 0.05% | 1 | 1 | 36 |
| sexual exploitation | related | 34 | 26 | 0.04% | 1 | 1 | 25 |
| sexual consent | related | 2 | 2 | 0.00% | 0 | 0 | 2 |

`body_only_unique` is the number of stories that would be missed by a metadata-only search; `fulltext_added` is the full-text-inclusive unique count minus the metadata unique count.

## Outlet breakdown

**942** cleaned outlet labels; **355** have at least one core match. The top 10 outlets account for **18.7%** of all core matches. `source` is messy (feed names, `www.`, "RSS Results"), so labels were lightly cleaned; raw `source` is preserved in the CSV.

| Outlet | Stories | Core | Core rate | Expanded | Broad |
|---|---|---|---|---|---|
| The Cornell Daily Sun | 478 | 46 | 9.6% | 46 | 54 |
| The Daily Pennsylvanian | 415 | 23 | 5.5% | 23 | 35 |
| Indiana Daily Student | 933 | 21 | 2.3% | 23 | 34 |
| Reveille | 812 | 17 | 2.1% | 17 | 24 |
| The State News | 451 | 17 | 3.8% | 17 | 25 |
| The Observer | 417 | 13 | 3.1% | 13 | 19 |
| The Michigan Daily | 677 | 11 | 1.6% | 11 | 15 |
| The Daily Collegian | 676 | 11 | 1.6% | 11 | 12 |
| The Dartmouth | 201 | 11 | 5.5% | 11 | 20 |
| easternprogress.com | 767 | 10 | 1.3% | 10 | 11 |
| The Daily Cardinal | 323 | 10 | 3.1% | 10 | 13 |
| The Daily Northwestern | 566 | 9 | 1.6% | 10 | 15 |
| Daily Trojan | 521 | 9 | 1.7% | 9 | 15 |
| The NewsHouse | 502 | 9 | 1.8% | 9 | 13 |
| Pipe Dream | 214 | 9 | 4.2% | 10 | 11 |

Highest core rate among outlets with at least 50 stories:

| Outlet (≥50 stories) | Stories | Core | Core rate |
|---|---|---|---|
| The Cornell Daily Sun | 478 | 46 | 9.6% |
| 9th Street Journal | 78 | 7 | 9.0% |
| Flat Hat News | 78 | 7 | 9.0% |
| The Tartan | 74 | 6 | 8.1% |
| The Maine Campus | 66 | 5 | 7.6% |
| Chicago Maroon | 81 | 6 | 7.4% |
| The Herald | 111 | 8 | 7.2% |
| Gaylord News | 70 | 5 | 7.1% |
| The Retrograde | 57 | 4 | 7.0% |
| Student Senate Association, Inc.  PURCHASE PHOENIX | 60 | 4 | 6.7% |

## Year trend

Dates parse for **66,985 of 68,581** stories. The database is heavily weighted toward 2026 (captured through 2026-10-15), so the trend is a snapshot of coverage, not a population time series.

| Year | Stories | Core | Core rate | Expanded | Broad |
|---|---|---|---|---|---|
| 2019 | 49 | 0 | 0.00% | 0 | 3 |
| 2020 | 54 | 2 | 3.70% | 2 | 4 |
| 2021 | 78 | 1 | 1.28% | 1 | 1 |
| 2022 | 124 | 4 | 3.23% | 4 | 7 |
| 2023 | 214 | 6 | 2.80% | 7 | 11 |
| 2024 | 345 | 6 | 1.74% | 6 | 9 |
| 2025 | 1268 | 23 | 1.81% | 24 | 39 |
| 2026 | 64681 | 889 | 1.37% | 928 | 1409 |

Full year table (including sparse pre-2019 years) is in `title_ix_sexual_violence_years.csv`.

## Representative examples (spot-check)

| # | Category | Outlet | Date | Headline | Match field |
|---:|---|---|---|---|---|
| 1 | title_ix | All the Lehigh University News First - The Brown and White | 2026-09-15 | Jessica White assumes role as Title IX Coordinator and Equal Opportunity Compliance Coordinator | headline |
| 2 | title_ix | THE PACE CHRONICLE | 2026-04-27 | Title IX: Office of Compliance or Complacence? | headline |
| 3 | title_ix | The Et Cetera | 2026-09-17 | Title IX at Dallas College: Protecting Students from Sex-Based Discrimination | headline |
| 4 | sexual_violence | The Vermont Cynic | 2026-04-20 | A history of sexual violence activism on campus | headline |
| 5 | sexual_violence | The Lantern | 2026-09-16 | Feminist Research, Education and Engagement Center to confront sexual violence at Ohio State in kickoff event | headline |
| 6 | sexual_assault | The Houstonian | 2026-04-29 | COLUMN: SHSU students use their voices for Sexual Assault Awareness Month | headline |
| 7 | sexual_assault | collegiatetimes.com | 2026-09-13 | Sexual assault alerts on campus | headline |
| 8 | sexual_assault | Amplify Utah - The Story Room | 2024-03-31 | Cyber sexual assault: How the University of Utah is preparing for a new kind of crime | headline |
| 9 | rape | The Herald | 2025-09-30 | Call them Rapists: The Power of Language at HWS | headline |
| 10 | rape | Reveille | 2026-09-25 | A criminal investigation has opened into LSU football player who raped student on campus | headline |
| 11 | sexual_abuse | The Baylor Lariat | 2026-09-02 | Independent report finds credible sexual misconduct allegations against social work professor, adult clergy sexual abuse researcher | headline |
| 12 | sexual_abuse | The Brown Daily Herald: Top Stories | 2026-06-15 | New law revives expired clergy sexual abuse claims | headline |
| 13 | sexual_misconduct | The Hoya | 2026-09-04 | GU to Expand Sexual Misconduct Resources After Implementation of D.C. Law | headline |
| 14 | sexual_misconduct | Student Life | 2026-09-10 | Professor accused of sexual misconduct sues WashU for ‘anti-male bias’ | headline |
| 15 | molestation | Noticiero Movil | 2026-06-22 | Nearly 100 people allege widespread physical, sexual abuse in Nevada juvenile facilities | body_only |
| 16 | groping | The Cougar | 2026-08-27 | BREAKING: Sophomore groped on first day of class, suspect arrested | headline |
| 17 | indecent_assault | The University Star | 2026-10-14 | UPD investigates burglary, indecent assault at Cypress | headline |
| 18 | nonconsensual_sex | The Cornell Daily Sun | 2026-09-30 | Student Assembly to Host Public Hearing on Sexual Violence Amid Chi Phi Lawsuit, Expresses ‘Outrage’ at Cornell - The Cornell Daily Sun | body_only |
| 19 | sexual_battery | The Miami Hurricane | 2026-09-09 | Former UM urologist, professor arrested on sexual battery charges | headline |
| 20 | sexual_harassment | The Chronicle | 2026-04-23 | SGA chat leak exposes Anti-Muslim sentiments and sexual harassment in student government | headline |

"Match field" shows whether the story was caught by the headline, by metadata (keywords/theme), or only in the body.

## False-positive traps handled

Regex self-tests: **44/44 positive tests passed**, **31/31 negative (trap) tests passed**.

| False-positive trap | Pattern | Handling |
|---|---|---|
| grape, scrape, therapist, rapid, rapping, drape, rapeseed | rape | No match (word-boundary + rap-e/ed/ing/ist forms only) |
| matrix, helix, six, fix, appendix, title case | title_ix | No match (IX must follow Title/Tit1e) |
| Sussex, Essex, Middlesex, bisexual, homosexual | sexual_* | No match (whole-word 'sexual' + specific noun required) |
| child abuse, substance abuse, abuse of power | sexual_abuse | No match (bare 'abuse' is not searched) |
| stalking horse, stalker-esque, stalker-y | stalking | Excluded by context filter |
| Bambi Molesters, molest the alligators, molesting, annoying | molestation | Excluded by context filter |
| groped around in her purse, groping for answers | groping | Excluded by context filter |
| affirmative consent for data privacy | sexual_consent | No match without sexual context |

Negative tests are run through the same `scan_text()` function as the data, so context filters are tested too. Failures, if any, are listed in `title_ix_sexual_violence_regex_tests.csv`.

## Limitations

1. **Keyword matching is not topic classification.** It catches mentions, not necessarily the story's main subject. A story about free speech that mentions sexual assault in a content warning is counted; a story about "inappropriate behavior" or "misconduct" without the word "sexual" is missed.
2. **Full text is incomplete.** Only 72.2% of rows have an existing extracted body. Missing bodies are biased toward 403/404/429 extraction failures, so the full-text-inclusive count is a lower bound.
3. **Headline-only is high precision but low recall.** Headlines often use euphemisms ("misconduct", "inappropriate conduct", "survivor", "unwanted advances") that the regex set does not catch.
4. **Title IX includes athletics/equity.** 104 Title IX stories have athletics/equity context and no sexual-harm term. They are included in the core Title IX count per the question, but can be subtracted (860 core stories remain).
5. **Related terms are not sexual violence.** Domestic violence, stalking, non-sexual harassment, trafficking and consent education are reported separately and should not be merged into the headline count without a decision.
6. **Duplicate/syndicated headlines.** 4,699 rows share a title with another row. Rows are unique URLs, so they are counted as separate published stories; unique-title counts would be slightly lower.
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
