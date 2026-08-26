# Pipeline reference

What every script does, what it reads, what it writes, and how to re-run it.

The nightly job (`.github/workflows/daily-scrape.yml`) runs the collection chain
automatically. The analysis chains — geocoding, the map, the benchmark lists —
are run by hand when you need fresh output.

---

## Collection (automatic, nightly)

`scrape.py` is the entry point and calls the rest in order. Running it runs
everything in this section.

```bash
python scrape.py
```

| Step | Script | Reads | Writes |
|---|---|---|---|
| 1. Fetch feeds | `scrape.py` | `feeds/*.opml`, `feeds_*.txt`, `extra_urls.txt` | `news_database.csv` |
| 2. Drop comment items | `scrape.py` | `news_database.csv` | `news_database.csv` |
| 3. Keyword + sentiment | `scrape.py` | `news_database.csv` | `news_database.csv` |
| 4. Cascade fetch | `fetch_hard_outlets.py` | outlets that block RSS | `news_database.csv` |
| 5. Theme tagging | `scrape.py` (BERTopic) | headlines | `theme` column |
| 6. Full text | `fetch_full_text.py` | `news_database.csv` | `full_text/**`, `extraction_status` |
| 7. Analytics | `analytics.py` | `news_database.csv` | `analytics/analytics.json` |
| 8. Per-outlet corpora | `build_publication_corpora.py` | `full_text/**` | `publication_corpora/*.txt`, `publication_corpora_manifest.csv`, `publication_story_index.csv` |
| 9. Bag of words | `build_bag_of_words.py` | `full_text/**` | `bag_of_words.csv` |

Validation runs after, in CI:

```bash
python scripts/validate_news_csv.py news_database.csv
```

### Two fields not to trust

Both ship in `news_database.csv` and both are known-bad. See
[the dataset summary](#dataset-summary) for the evidence.

- **`theme`** — 42.9% "Unclassified", and the rest cluster on institution names
  rather than subject, because BERTopic runs on headlines alone. Use the lexicon
  topics from `scripts/build_map_data.py` instead.
- **`sentiment_label`** — 97.1% neutral. Scored by lexicon hits over
  title+summary with a ±0.05 token-share threshold that headline-length text
  almost never clears. The distribution reflects the threshold, not the coverage.

`analytics.json`'s `total_feeds` is also wrong: `analytics.py:159` counts only
the OPML export and `extra_urls.txt`, skipping the ~1,660 URLs in the
`feeds_*.txt` lists. Cite outlets observed in the data, not that number.

---

## Geocoding and the map (manual)

Run in this order — the second reads the first's output.

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

Headline figures at the 2026-06-26 snapshot: 15,074 stories, 870 publications,
10.05M words, 98.1% extraction success, median 596 words per story, Flesch 49.1.

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
