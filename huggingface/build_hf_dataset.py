"""
Build Hugging Face dataset files from current pipeline state.

Reads news_database.csv + full_text/ + publication_corpora/ + bag_of_words.csv
and emits a clean, queryable bundle in huggingface/dataset_build/ that's ready
to push to the Hub.

Output structure (huggingface/dataset_build/):
    stories.parquet               — one row per story, columns include full_text
    publication_corpora/*.txt     — per-publication concatenated text (vector use)
    publication_corpora_manifest.csv
    publication_story_index.csv
    bag_of_words.csv
    README.md                     — Dataset Card (auto-generated, edit before push)

The stories.parquet schema mirrors news_database.csv but adds a `full_text`
column containing the cleaned article body (header stripped). This is the
primary research artifact — researchers can filter/query in pandas/polars
without dealing with thousands of small .txt files.

Usage:
    python huggingface/build_hf_dataset.py

Requires:
    pip install pandas pyarrow
"""
import csv
import os
import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_CSV = PROJECT_ROOT / "news_database.csv"
FULL_TEXT_DIR = PROJECT_ROOT / "full_text"
PUB_CORPORA_DIR = PROJECT_ROOT / "publication_corpora"
PUB_MANIFEST = PROJECT_ROOT / "publication_corpora_manifest.csv"
PUB_STORY_INDEX = PROJECT_ROOT / "publication_story_index.csv"
BAG_OF_WORDS = PROJECT_ROOT / "bag_of_words.csv"

BUILD_DIR = Path(__file__).resolve().parent / "dataset_build"
HEADER_END_MARKER = "# ---"


def strip_header(text: str) -> str:
    idx = text.find(HEADER_END_MARKER)
    if idx == -1:
        return text
    newline = text.find("\n", idx)
    return text[newline + 1:] if newline != -1 else ""


def load_full_text(path_str: str) -> str:
    """Read a full_text file and return just the article body."""
    if not path_str:
        return ""
    path = PROJECT_ROOT / path_str
    if not path.exists():
        return ""
    try:
        return strip_header(path.read_text(encoding="utf-8")).strip()
    except Exception:
        return ""


def build_stories_parquet():
    """Convert news_database.csv + full_text/ into a single Parquet file."""
    print(f"Reading {SOURCE_CSV}...")
    df = pd.read_csv(SOURCE_CSV, dtype=str).fillna("")
    print(f"  {len(df)} story rows")

    print("Joining full text bodies...")
    df["full_text"] = df["full_text_path"].apply(load_full_text)

    has_text = (df["full_text"].str.len() > 0).sum()
    print(f"  {has_text} stories have full text attached")

    out = BUILD_DIR / "stories.parquet"
    df.to_parquet(out, index=False, compression="snappy")
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"  Wrote {out.name} ({size_mb:.1f} MB)")
    return len(df), has_text


def copy_artifact(src: Path, dst_name: str | None = None):
    """Copy a single file into the build dir, returning size in MB."""
    if not src.exists():
        print(f"  SKIP {src.name} (not found)")
        return 0.0
    dst = BUILD_DIR / (dst_name or src.name)
    shutil.copy2(src, dst)
    return dst.stat().st_size / 1024 / 1024


def copy_publication_corpora():
    """Copy the per-publication .txt corpora into the build dir."""
    if not PUB_CORPORA_DIR.is_dir():
        print("  SKIP publication_corpora (not found)")
        return 0
    dst = BUILD_DIR / "publication_corpora"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(PUB_CORPORA_DIR, dst)
    count = len(list(dst.glob("*.txt")))
    size_mb = sum(p.stat().st_size for p in dst.glob("*.txt")) / 1024 / 1024
    print(f"  Copied publication_corpora/ ({count} files, {size_mb:.1f} MB)")
    return count


def published_date_range() -> str:
    """Actual min/max of the `published` column, for the dataset card."""
    import csv as _csv
    import re as _re
    lo = hi = None
    with open(SOURCE_CSV, newline="", encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            m = _re.match(r"(\d{4}-\d{2}-\d{2})", (row.get("published") or "").strip())
            if not m:
                continue
            d = m.group(1)
            lo = d if lo is None or d < lo else lo
            hi = d if hi is None or d > hi else hi
    return f"{lo} to {hi}" if lo else "unknown"


def write_readme(story_count: int, with_text_count: int, pub_count: int):
    date_range = published_date_range()
    """Generate a Dataset Card README.md from a template."""
    readme = f"""---
license: cc-by-4.0
language:
  - en
tags:
  - journalism
  - news-deserts
  - student-media
  - content-analysis
  - local-news
size_categories:
  - 1K<n<10K
task_categories:
  - text-classification
  - text-generation
  - feature-extraction
---

# Student Journalism News Deserts Dataset

A growing corpus of stories from U.S. student journalism outlets, supporting
research on whether student journalists help fill local news gaps in counties
classified as "news deserts" (counties with zero local news outlets).

## Dataset summary

- **Stories**: {story_count:,} ({with_text_count:,} with full article text)
- **Publications**: {pub_count} per-publication corpora available for vector analysis
- **Publication dates**: {date_range}
- **Languages**: English
- **Updates**: Refreshed by the `daily-scrape` GitHub Action in the source
  repository, which pushes here after each run. The schedule is currently
  paused pending verification of the rewritten pipeline, so treat the build
  date above as the real currency of the data rather than assuming it is a day
  old.

## Topic labels

Each story carries `topic_id` (0-9), `topic_confidence`, and
`topic_model_version`. Topics come from a **frozen** model: embeddings are
clustered once, the centroids are persisted, and new stories are assigned to
the nearest centroid rather than by refitting. Assignments are therefore
comparable across time, which matters for any longitudinal use.

`topic_confidence` is the cosine similarity to the assigned centroid. Low
values mean the story sits between topics; filter on it rather than treating
every assignment as equally firm. `topic_model_version` records which model
produced the assignment, so a future retrain leaves a visible seam instead of
silently splicing two schemes into one series.

Human-readable labels for each `topic_id` live in `data/topic_labels.json` in
the source repository, deliberately not baked into the rows.

The older `theme` column is **deprecated** and no longer written. It was
produced by refitting BERTopic on each night's headlines, so its labels are not
comparable between runs.

## How to use

### Load the structured story dataset
```python
import pandas as pd
df = pd.read_parquet("stories.parquet")

# Filter to a specific publication
stanford = df[df["source"] == "The Stanford Daily"]

# Get all stories with full text
with_text = df[df["full_text"].str.len() > 0]
```

### Load via 🤗 datasets library
```python
from datasets import load_dataset
ds = load_dataset("YOUR_HF_HANDLE/student-journalism-news-deserts")
```

### Per-publication corpora (for vector-space analysis)
Each publication's stories are concatenated into a single text file at
`publication_corpora/<slug>.txt`. Drop directly into sklearn:

```python
from sklearn.feature_extraction.text import TfidfVectorizer
import os, glob
paths = sorted(glob.glob("publication_corpora/*.txt"))
labels = [os.path.splitext(os.path.basename(p))[0] for p in paths]
docs = [open(p, encoding="utf-8").read() for p in paths]
vectorizer = TfidfVectorizer(stop_words="english", min_df=2)
X = vectorizer.fit_transform(docs)  # shape: (n_publications, vocab_size)
```

## File structure

| File | Description |
|---|---|
| `stories.parquet` | Primary dataset. One row per story with title, source, link, published date, theme, sentiment, keywords, and full article text. |
| `publication_corpora/*.txt` | Per-publication concatenated article text, designed for vector-space analysis. One file per outlet. |
| `publication_corpora_manifest.csv` | Per-publication summary: name, story count, total words, date range. |
| `publication_story_index.csv` | Per-story lookup: which publication each story belongs to, with metadata. |
| `bag_of_words.csv` | Corpus-wide word frequencies. Columns: rank, word, count, document_frequency. |

## Column reference (stories.parquet)

| Column | Description |
|---|---|
| `source` | Outlet name as published in the RSS feed |
| `title` | Article headline |
| `link` | Original article URL |
| `published` | Publication date (ISO 8601 where parseable, raw feed string otherwise) |
| `captured_at` | UTC timestamp when our scraper ingested the story |
| `theme` | BERTopic-derived theme label (or "Unclassified") |
| `keywords` | Pipe-delimited keywords extracted from title + summary |
| `sentiment_label` | One of `positive`, `neutral`, `negative` |
| `sentiment_score` | Lexicon-based sentiment score in `[-1, 1]` |
| `extraction_status` | `ok` if full text was successfully extracted; otherwise an error code |
| `full_text_path` | Path to the original .txt file in the source repo (provenance only) |
| `full_text` | The cleaned article body (header stripped). Empty when extraction failed. |

## Collection methodology

Stories are pulled nightly from a curated list of ~900 student journalism RSS
feeds plus a "hard outlets" cascade scraper for publications that block standard
RSS. Full article text is extracted with [trafilatura](https://trafilatura.readthedocs.io/).
See the [source repository](https://github.com/UVM-CCN/student-media-feeds)
for the full collection pipeline.

## Limitations

- **Extraction noise**: ~3–5% of stories have empty `full_text` due to paywalls,
  JS-rendered pages, or sites that block our scraper.
- **Source naming**: A small number of SNworks-platform feeds produce non-human
  source names like `"www.dailycal.org - RSS Results"` rather than `"The Daily
  Californian"`. Normalization is ongoing.
- **Geographic coverage**: Outlet selection biases toward programs with
  discoverable RSS feeds, which skews to digital-native and well-resourced
  programs. Smaller print-only papers are underrepresented.
- **Story-level metadata only**: This dataset captures what was published, not
  what was *read* or *shared*. Engagement data is not included.

## Citation

If you use this dataset in research, please cite:
```
@dataset{{student_journalism_news_deserts_2026,
  author = {{Cooley, Ben and contributors}},
  title = {{Student Journalism News Deserts Dataset}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/YOUR_HF_HANDLE/student-journalism-news-deserts}}
}}
```

## License

CC-BY 4.0. Free to use for research and commercial purposes with attribution.
Individual articles remain the copyright of their respective publishers.

## Maintainer

Maintained by the University of Vermont Center for Community News.
Source code and pipeline: https://github.com/UVM-CCN/student-media-feeds
"""

    (BUILD_DIR / "README.md").write_text(readme, encoding="utf-8")
    print(f"  Wrote README.md ({len(readme):,} chars)")


def main():
    print(f"Building Hugging Face dataset in {BUILD_DIR}...")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    print()

    total_stories, with_text = build_stories_parquet()
    print()

    print("Copying supplementary files...")
    copy_artifact(PUB_MANIFEST)
    copy_artifact(PUB_STORY_INDEX)
    copy_artifact(BAG_OF_WORDS)
    pub_count = copy_publication_corpora()
    print()

    print("Generating Dataset Card...")
    write_readme(total_stories, with_text, pub_count)
    print()

    total_size = sum(p.stat().st_size for p in BUILD_DIR.rglob("*") if p.is_file()) / 1024 / 1024
    file_count = sum(1 for p in BUILD_DIR.rglob("*") if p.is_file())
    print(f"Build complete. {file_count} files, {total_size:.1f} MB total.")
    print(f"Ready to push from: {BUILD_DIR}")


if __name__ == "__main__":
    main()
