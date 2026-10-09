# Student Media Feeds

A Python-based RSS feed aggregator designed to track and archive news stories from student media outlets across the United States. The pipeline automatically fetches, deduplicates, and stores articles in a CSV database.

## TODO
- [x] add frontend
- [x] categorzie by theme
- [x] add time series analysis
- [ ] integrate SOCKs tools?
- [ ] Revisit [data/splc_feed_discovery_results.csv](data/splc_feed_discovery_results.csv) (SPLC colleges not yet in our database) and see if more can be added to the pipeline. Filter on `Revisit = yes`: 27 outlets were added in `feeds_splc_discovered.txt`; 284 remain, mostly sites with no feed found, sites that blocked the probe (403/429, try `fetch_hard_outlets.py`), stale URLs, outlets missing a URL, and 72 whose domain is already tracked but whose college label doesn't match.

## Overview

This repository contains an automated news scraping system that:
- Discovers RSS feeds from OPML exports (e.g., from Feedly, Inoreader, etc.)
- Fetches new articles from student news publications daily
- Deduplicates stories to avoid storing the same article twice
- Maintains a comprehensive CSV database of all captured stories
- Runs automatically via GitHub Actions at 11:59 PM UTC every day

## Repository Structure

```
.
├── scrape.py                          # Main pipeline entry point; calls the steps below
├── fetch_full_text.py                 # Full-text article extractor -> full_text/
├── fetch_hard_outlets.py              # Cascade fetcher for outlets that block RSS
├── analytics.py                       # Aggregate report -> analytics/analytics.json
├── build_publication_corpora.py       # Per-publication text corpora
├── build_bag_of_words.py              # Corpus-wide word frequencies
├── feed_discoverer.py                 # Probes a CSV URL column for RSS feeds
│
├── news_database.csv                  # Story database (one row per article)
├── publication_story_index.csv        # Story -> publication -> full-text path
├── publication_corpora_manifest.csv   # Per-publication corpus stats
├── bag_of_words.csv                   # Word frequencies across the corpus
├── ccn_nap_master.csv                 # CCN program master list (has LAT/LON)
│
├── data/
│   ├── student-media-outlets.csv      # Outlet directory with LAT/LONG
│   ├── missing_outlets.csv            # Outlets not yet in the feed lists
│   ├── publication_locations.csv      # Generated: outlet -> coordinates
│   └── publication_institution_overrides.csv  # Manual geocoding fixes
│
├── scripts/
│   ├── geocode_publications.py        # Attach coordinates to every outlet
│   ├── build_map_data.py              # Topic-classify stories -> map data
│   ├── validate_news_csv.py           # CI schema check
│   └── discover_*.py, find_missing_outlets.py   # Feed discovery helpers
│
├── map/                               # Interactive Leaflet coverage heatmap
├── benchmark/                         # Site-URL lists for scraper comparison
├── docs/PIPELINE.md                   # What each script does and how to re-run
│
├── feeds/, feeds_*.txt, extra_urls.txt   # Feed inputs
├── full_text/                         # Extracted article bodies (hashed paths)
├── publication_corpora/               # Per-publication concatenated text
├── .github/workflows/daily-scrape.yml # Nightly GitHub Actions run
└── README.md                          # This file
```

## Documentation

- **[docs/PIPELINE.md](docs/PIPELINE.md)** — what every script does, what it
  reads and writes, and how to re-run each chain. Start here.
- **[map/README.md](map/README.md)** — the coverage map: geocoding sources,
  source-data corrections, and how to read the two weighting modes.
- **[benchmark/README.md](benchmark/README.md)** — URL lists for comparing this
  pipeline against another scraper, and a fair-comparison protocol.

## Setup

### Prerequisites

- Python 3.11 or higher
- pip (Python package manager)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd student-media-feeds
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   # CPU-only torch first — the default PyPI wheel is the CUDA build and pulls
   # several GB of nvidia-* packages. Nothing here uses a GPU.
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   pip install -r requirements.txt
   ```

### Adding Feed Sources

The scraper automatically discovers feeds from multiple sources:

#### Option 1: OPML Files (Recommended)

Place any `.opml` file in the `feeds/` directory. The scraper will automatically detect and parse all OPML files in this folder.

**To export OPML from popular RSS readers:**
- **Feedly:** Settings → OPML → Export
- **Inoreader:** Settings → Import/Export → Export to OPML file
- **Feeder:** Settings → Feeds → Export OPML

#### Option 2: Root Directory OPML

Place a file named `feeds.opml` in the repository root for backward compatibility.

#### Option 3: Plain Text URL List

Create `extra_urls.txt` in the repository root with one RSS feed URL per line:
```
https://example.edu/news/feed/
https://studentnews.edu/rss
```

## Usage

### Running Locally

To run the scraper manually:

```bash
python scrape.py
```

The script will:
1. Search for OPML files in the `feeds/` directory
2. Parse all RSS feed URLs
3. Fetch stories from each feed
4. Add new stories to `news_database.csv` (skipping duplicates)
5. Log progress and summary statistics

### Automated Daily Runs

The GitHub Actions workflow (`.github/workflows/daily-scrape.yml`) automatically:
- Runs at **11:59 PM UTC** every day
- Sets up Python and installs dependencies
- Executes `scrape.py`
- Commits and pushes any updates to `news_database.csv`

**To manually trigger the workflow:**
1. Go to the "Actions" tab in GitHub
2. Select "Daily News Scrape"
3. Click "Run workflow"

### Adjusting the Schedule

To change the run time, edit `.github/workflows/daily-scrape.yml` and modify the cron expression:

```yaml
schedule:
  - cron: '59 23 * * *'  # Format: minute hour day month day-of-week (UTC)
```

**Common timezone conversions:**
- 11:59 PM EST/EDT: `59 4 * * *` (accounts for daylight saving)
- 11:59 PM PST/PDT: `59 7 * * *`
- 11:59 PM CST/CDT: `59 5 * * *`

## Database Schema

The `news_database.csv` file contains the following columns:

| Column       | Description                                      |
|--------------|--------------------------------------------------|
| `source`     | Name of the news outlet (from RSS feed title)    |
| `title`      | Article headline                                  |
| `link`       | Full URL to the article                          |
| `published`  | Publication date (as provided by the feed)       |
| `captured_at`| Timestamp when the article was scraped (YYYY-MM-DD HH:MM:SS) |

## Features

### Deduplication

The pipeline tracks all previously saved article URLs to prevent duplicates. Only new stories are added to the database on each run.

### Error Handling

- Invalid or malformed feeds are logged as warnings but don't stop the pipeline
- Missing OPML/URL files are handled gracefully
- Network errors are caught and logged

### Logging

The script provides detailed logging output:
- `INFO`: Progress updates (parsing files, fetching feeds)
- `WARNING`: Feed parsing issues
- `ERROR`: Critical failures (no feeds found, file read errors)
- Summary statistics on completion

## Troubleshooting

### "No feed URLs found to process"

**Causes:**
- No OPML files in `feeds/` directory
- No `feeds.opml` or `extra_urls.txt` in repository root
- Empty OPML files

**Solutions:**
1. Verify files exist: `ls -la feeds/`
2. Check OPML content contains `<outline>` elements with `xmlUrl` attributes
3. Add at least one feed source using the methods above

### GitHub Actions Not Running

**Check:**
1. Workflow file is in `.github/workflows/` directory
2. Repository has Actions enabled (Settings → Actions → Allow all actions)
3. Cron syntax is valid (use [crontab.guru](https://crontab.guru) to verify)
4. Check Actions tab for error logs

### Permission Errors in GitHub Actions

The workflow needs `contents: write` permission to commit changes. This is already configured in the workflow file.

## Contributing

To add new features or fix bugs:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally with `python scrape.py`
5. Submit a pull request

## License

[Add your license information here]

## Acknowledgments

This project aggregates content from student journalism outlets across the United States. All articles remain the property of their respective publishers.