# Pipeline reference

What every script does, what it reads, what it writes, and how to re-run it.

The nightly job (`.github/workflows/daily-scrape.yml`) runs the collection chain
and the map rebuild automatically. The remaining analysis chains — the benchmark
lists, feed discovery — are run by hand when you need fresh output.

---

## Where the data lives

The corpus is split across two homes, and which one a file belongs to is not
arbitrary:

| Home | Holds | Why |
|---|---|---|
| **GitHub** | `news_database.csv`, `analytics/analytics.json`, `map/map_data.*`, `data/publication_locations.csv`, all code | Small, diffable, and what the dashboard reads. |
| **Hugging Face** (`center-for-community-news/student-media-feeds`) | `stories.parquet` (metadata + every article body), `publication_corpora/`, `bag_of_words.csv`, `publication_story_index.csv` | Heavy and append-only. Committing it churned megabytes nightly and bloated the repo. |

`full_text/` is **not** in git. The Hub is its canonical home, and
`huggingface/restore_full_text.py` rehydrates it from `stories.parquet` at the
start of every nightly run.

Two invariants hold this together. Break either one and the corpus corrupts
quietly rather than loudly:

1. **The restore is fail-closed.** If it cannot rebuild what
   `news_database.csv` claims exists, it exits non-zero and the run stops.
   Without this, `build_publication_corpora.py` would regenerate the corpora
   from only that night's new stories, and the sync step would then publish
   that truncated corpus over the good one.

2. **The Hub push happens before the git commit.** `news_database.csv` records
   `extraction_status="ok"` for stories whose body lives only on the Hub. If
   git were committed first and the Hub push then failed, the committed CSV
   would reference bodies that exist nowhere. Publishing text first means a
   committed `ok` is always backed by something already on the Hub.

This repo previously violated both, which is how 8,404 rows on `main` came to
be marked `ok` with no file behind them: the runner extracted the text, the
commit step staged only `news_database.csv analytics/`, and the text was
discarded with the runner.

---

## Collection (automatic, nightly)

`scrape.py` is the entry point and calls the rest in order. Running it runs
everything in this section.

```bash
python scrape.py
```

| Step | Script | Reads | Writes |
|---|---|---|---|
| 0. Restore corpus | `huggingface/restore_full_text.py` | Hub `stories.parquet` | `full_text/**` |
| 1. Fetch feeds | `scrape.py` | `feeds/*.opml`, `feeds_*.txt`, `extra_urls.txt` | `news_database.csv` |
| 2. Drop comment items | `scrape.py` | `news_database.csv` | `news_database.csv` |
| 3. Keyword + sentiment | `scrape.py` | `news_database.csv` | `news_database.csv` |
| 4. Cascade fetch | `fetch_hard_outlets.py` | outlets that block RSS | `news_database.csv` |
| 5. Theme tagging | `scrape.py` (BERTopic) | headlines | `theme` column |
| 6. Full text | `fetch_full_text.py` | `news_database.csv` | `full_text/**`, `extraction_status` |
| 7. Analytics | `analytics.py` | `news_database.csv` | `analytics/analytics.json` |
| 8. Per-outlet corpora | `build_publication_corpora.py` | `full_text/**` | `publication_corpora/*.txt`, `publication_corpora_manifest.csv`, `publication_story_index.csv` |
| 9. Bag of words | `build_bag_of_words.py` | `full_text/**` | `bag_of_words.csv` |
| 10. Map data | `scripts/geocode_publications.py`, `scripts/build_map_data.py` | `publication_story_index.csv`, `data/*.csv` | `data/publication_locations.csv`, `map/map_data.*` |
| 7b. Assign topics | `scripts/apply_topics.py` | `full_text/**`, `models/topic_model.joblib` | `topic_id`, `topic_confidence`, `topic_model_version` |
| 11. Publish corpus | `huggingface/build_hf_dataset.py`, `huggingface/sync_to_hf.py` | `news_database.csv`, `full_text/**`, corpora | Hub dataset |

Validation runs after, in CI:

```bash
python scripts/validate_news_csv.py news_database.csv
```

### Two fields not to trust

Both ship in `news_database.csv` and both are known-bad. See
[the dataset summary](#dataset-summary) for the evidence.

- **`theme`** — deprecated, no longer written. 38% "Unclassified", and the rest
  clustered on institution names rather than subject ("Wvu | Mountaineers |
  Syracuse | Usc"), because BERTopic ran on headlines alone and was refit on
  each night's new batch, so labels were never comparable between runs. Use
  `topic_id` with `data/topic_labels.json` instead. The column is retained so
  history stays intact.
- **`sentiment_label`** — 97.1% neutral. Scored by lexicon hits over
  title+summary with a ±0.05 token-share threshold that headline-length text
  almost never clears. The distribution reflects the threshold, not the coverage.

`analytics.json`'s `total_feeds` is also wrong: `analytics.py:159` counts only
the OPML export and `extra_urls.txt`, skipping the ~1,660 URLs in the
`feeds_*.txt` lists. Cite outlets observed in the data, not that number.

---

## Topics

Topics are **discovered once and frozen**, then applied without refitting.

```bash
python scripts/train_topic_model.py     # by hand, rarely -> models/topic_model.joblib
python scripts/apply_topics.py          # nightly, in CI -> topic_id on each row
```

`train_topic_model.py` embeds the corpus (all-MiniLM-L6-v2, first 200 words of
each body), clusters with spherical k-means, and persists the L2-normalized
centroids. `apply_topics.py` embeds new stories and assigns each to the nearest
centroid by cosine similarity. It fits nothing.

Why frozen centroids rather than a topic model's own inference:

- **Refitting nightly is what broke `theme`.** Every run produced a different
  model, so a label from one night meant nothing on another.
- **A frozen BERTopic is not much better.** Its `transform()` runs UMAP then
  HDBSCAN `approximate_predict`, which is non-deterministic near cluster
  boundaries and routes uncertain documents to an outlier class.
- **LDA was tried and rejected.** On this corpus it grouped by *register*
  rather than subject — it put film reviews and primary-election coverage in one
  topic because both are written in an evaluative first-person voice.

A centroid is a fixed vector, so cosine similarity to it is deterministic
forever, and the similarity doubles as a confidence score.

### What is stored where

`topic_id`, `topic_confidence` and `topic_model_version` go in
`news_database.csv`. Human labels do **not** — they live in
`data/topic_labels.json` and resolve when the map and dashboard data are built.
Renaming a topic therefore never requires reprocessing the corpus.

### Retraining

The model is frozen, so it cannot discover topics that emerge later. When you
retrain, `topic_model_version` changes and `apply_topics.py --reassign-all`
re-labels the corpus. The version stamp is what makes that seam visible instead
of letting a mixed-model time series look continuous.

`scripts/text_quality.py` filters items that are not stories (image pages, CMS
stubs) and strips template leakage before any of this. 41 files carried SNO
theme markup that trafilatura missed — one is 38.6% CSS by character count, and
its repeated tokens were enough to fill a topic's description with stylesheet
fragments.

---

## Geocoding and the map

These now run nightly as part of the workflow (steps 10 above), so the map no
longer drifts behind the database the way it did when it was regenerated by
hand. To rebuild locally, run them in this order — the second reads the first's
output.

```bash
python scripts/geocode_publications.py   # -> data/publication_locations.csv
python scripts/build_map_data.py         # -> map/map_data.js, map/map_data.json
```

Then open `map/index.html` in a browser. No server needed: the data ships as a
script tag because browsers block `fetch()` of local JSON over `file://`.

### `scripts/geocode_publications.py`

Attaches lat/long to every outlet in the corpus.

**Reads** `news_database.csv`, `data/student-media-outlets.csv`,
`ccn_nap_master.csv`, `data/publication_institution_overrides.csv`
**Writes** `data/publication_locations.csv`

Resolution order — an override wins over a domain match, because several
overrides exist to *correct* bad source coordinates rather than fill gaps:

1. **override, explicit coordinates** — for outlets with no host campus
2. **override, institution** — domain mapped to a named institution, whose
   coordinates come from the source files
3. **domain** — outlet URL matched against the two source files
4. **name** — outlet title matched, but only for titles unique in the corpus

Current coverage: 893 of 903 outlets (98.9%), 14,972 of 15,073 stories (99.3%).

The script prints a **warning when one coordinate is shared by institutions in
different states** — the signature of a geocoder returning a centroid on
failure. Fix anything it flags by adding a row to the overrides file. See
[map/README.md](../map/README.md) for the errors already corrected.

### `scripts/build_map_data.py`

Classifies stories by topic and joins them to coordinates.

**Reads** `publication_story_index.csv`, `full_text/**`,
`data/publication_locations.csv`
**Writes** `map/map_data.js`, `map/map_data.json`

Topics are ten keyword lexicons defined in `BEATS` at the top of the file. Each
story is scored as beat hits per 1000 tokens, assigned to its strongest beat, and
left unassigned below `MIN_SIGNAL`. To change the taxonomy, edit `BEATS` and
re-run — nothing else needs to change, the map reads the topic list from the data.

This is a transparent heuristic, not a trained classifier. Describe it that way
in any writeup.

### Why everything is keyed by domain

Student papers reuse titles heavily: "The Observer" publishes at Fordham, Notre
Dame/Saint Mary's, Case Western, Illinois-Springfield, and Central Washington.
42 titles in the corpus span multiple campuses, covering 1,584 stories. Keying on
the `source` name collapses them onto one point at whichever campus matched
first, so the locations table, the map points, and the popups all key on domain.

### `map/index.html`

Standalone Leaflet page. Loads Leaflet, `leaflet.heat`, and Carto basemap tiles
from CDNs, so it needs a network connection but no build step.

- **Topic** selects which lexicon drives the heat layer.
- **Weighting** switches between raw story count and each outlet's share of its
  own output. Share is damped by `log10(total+1)/2` so a newsroom with two
  stories can't outrank one with two hundred. Disabled under "All coverage",
  where share is meaningless — every outlet is 100% of itself.
- The colour ramp rescales to the **selected topic's own min and max**, so the
  legend always reports the range actually on screen. The floor (`FLOOR = 0.12`)
  keeps the weakest outlet visible instead of fading it to nothing.
- Popups chart **all ten categories** in one fixed order, so two popups can be
  compared directly. The selected topic's bar is highlighted.

Tests:

```bash
node map/test/test_map.js
```

Stubs Leaflet and the DOM, then exercises every topic in both weighting modes and
checks the popup chart. Run it after editing the page script.

---

## Benchmark lists (manual, occasional)

Website URLs for comparing this pipeline against another scraper.

```bash
python benchmark/build_url_lists.py
```

**Writes** `benchmark/sites_all.txt` (1,003 URLs),
`benchmark/sites_productive.txt` (903), `benchmark/sites_productive.csv`

These are site URLs, not the RSS feed URLs the pipeline consumes. See
[benchmark/README.md](../benchmark/README.md) for which list to send and how to
make the comparison fair.

---

## Feed discovery (manual, occasional)

| Script | Purpose |
|---|---|
| `feed_discoverer.py` | Probe a URL column in a CSV for a working RSS feed |
| `scripts/discover_feeds_from_csv.py` | Generic wrapper: CSV in, discovered feeds out |
| `scripts/discover_from_ccn.py` | One-off, runs discovery against `ccn_nap_master.csv` |
| `scripts/find_missing_outlets.py` | One-off, cross-references outlet lists to find gaps |

Discovered feeds are appended to the `feeds_*.txt` lists, which step 1 reads on
the next nightly run.

---

## Dataset summary

Corpus-level statistics — scale, publication spread, topic structure, linguistic
profile, and known limitations — are maintained as a published summary rather
than in this repo. Regenerate the underlying numbers from
`news_database.csv` and `full_text/**` when the corpus changes materially.

Headline figures at the 2026-08-26 reconciliation: 23,278 stories, 872
publications, spanning 2026-02-03 to 2026-08-26. This merged the nightly CI
database with the local corpus, which had drifted into two copies neither of
which was a superset of the other — see `scripts/merge_news_databases.py`.

The earlier 2026-06-26 snapshot read 15,074 stories / 870 publications. That
figure covered only the local copy.

---

## Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

Install CPU-only torch first. The default PyPI wheel is the CUDA build, which
pulls several GB of `nvidia-*` packages and fills the GitHub Actions runner's
disk. Nothing in the pipeline uses a GPU. The nightly workflow does the same.
