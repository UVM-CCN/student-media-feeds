"""
Rehydrate full_text/ from the Hugging Face dataset.

full_text/ is no longer stored in git — the Hub is its canonical home. But the
nightly pipeline still needs it on disk: build_publication_corpora.py and
build_bag_of_words.py read every article body to regenerate the corpus. Without
this step a CI run would rebuild the corpora from only that night's handful of
new stories and then push that truncated corpus back to the Hub, destroying it.

So this step is FAIL-CLOSED. If it cannot restore what news_database.csv says
should exist, it exits non-zero and the workflow stops before anything is
rebuilt or pushed.

Bodies are read from stories.parquet, which is one file rather than ~23,000, so
the nightly download stays cheap. Parquet holds the body with its metadata
header stripped; the header is reconstructed here from news_database.csv, whose
columns are its original source.

Configuration:
    HF_REPO_ID — required, e.g. "center-for-community-news/student-media-feeds"
    HF_TOKEN   — required only if the dataset is private

Usage:
    python huggingface/restore_full_text.py
    python huggingface/restore_full_text.py --tolerance 0.02
"""
import argparse
import csv
import hashlib
import os
import sys
from pathlib import Path

try:
    import pandas as pd
    from huggingface_hub import hf_hub_download
except ImportError:
    print("ERROR: requires huggingface_hub, pandas and pyarrow.\n"
          "Install with: pip install huggingface_hub pandas pyarrow", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FULL_TEXT_DIR = PROJECT_ROOT / "full_text"
SOURCE_CSV = PROJECT_ROOT / "news_database.csv"
HEADER_END_MARKER = "# ---"


def url_to_path(url: str) -> Path:
    """Same scheme as fetch_full_text.url_to_path — keep these in sync."""
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return FULL_TEXT_DIR / h[:2] / f"{h}.txt"


def build_header(row) -> str:
    """Reconstruct the metadata header that fetch_full_text.py writes."""
    def g(k):
        v = row.get(k, "")
        return "" if v is None else str(v).replace("\n", " ").strip()
    return (
        f"# Title: {g('title')}\n"
        f"# URL: {g('link')}\n"
        f"# Source: {g('source')}\n"
        f"# Published: {g('published')}\n"
        f"# Restored: from Hugging Face stories.parquet\n"
        f"{HEADER_END_MARKER}\n\n"
    )


def expected_ok_count() -> int:
    """How many rows news_database.csv claims have an extracted body."""
    if not SOURCE_CSV.exists():
        return 0
    with open(SOURCE_CSV, newline="", encoding="utf-8") as f:
        return sum(1 for r in csv.DictReader(f)
                   if (r.get("extraction_status") or "").strip() == "ok")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-id", default=os.environ.get("HF_REPO_ID"))
    ap.add_argument("--tolerance", type=float, default=0.01,
                    help="fraction of expected bodies allowed to be missing "
                         "before this fails the run (default 1%%)")
    ap.add_argument("--allow-empty", action="store_true",
                    help="permit an empty restore; only for bootstrapping a "
                         "dataset that has no stories.parquet yet")
    args = ap.parse_args()

    if not args.repo_id:
        print("ERROR: HF_REPO_ID is not set.", file=sys.stderr)
        return 1

    expected = expected_ok_count()
    print(f"news_database.csv expects {expected:,} extracted bodies")

    print(f"Downloading stories.parquet from {args.repo_id}...")
    try:
        parquet_path = hf_hub_download(
            repo_id=args.repo_id,
            repo_type="dataset",
            filename="stories.parquet",
            token=os.environ.get("HF_TOKEN"),
        )
    except Exception as e:
        if args.allow_empty:
            print(f"WARNING: could not download stories.parquet ({e}); "
                  f"continuing because --allow-empty was given.")
            return 0
        print(f"ERROR: could not download stories.parquet: {e}", file=sys.stderr)
        return 1

    df = pd.read_parquet(parquet_path)
    if "full_text" not in df.columns:
        print("ERROR: stories.parquet has no full_text column.", file=sys.stderr)
        return 1
    df = df.fillna("")
    print(f"  {len(df):,} rows in parquet")

    written = skipped = 0
    for row in df.to_dict("records"):
        body = (row.get("full_text") or "").strip()
        link = (row.get("link") or "").strip()
        if not body or not link:
            continue
        path = url_to_path(link)
        if path.exists():
            skipped += 1          # already on disk; leave it alone
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_header(row) + body + "\n", encoding="utf-8")
        written += 1

    on_disk = sum(1 for _ in FULL_TEXT_DIR.rglob("*.txt")) if FULL_TEXT_DIR.exists() else 0
    print(f"  wrote {written:,}, already present {skipped:,}")
    print(f"  full_text/ now holds {on_disk:,} files")

    # Fail-closed guard: refuse to let the pipeline continue on a partial corpus,
    # because the next steps would rebuild and publish it over the good one.
    if expected:
        shortfall = (expected - on_disk) / expected
        if shortfall > args.tolerance:
            print(f"\nERROR: restored corpus is {shortfall:.1%} short of the "
                  f"{expected:,} bodies news_database.csv expects "
                  f"(tolerance {args.tolerance:.1%}).\n"
                  f"Refusing to continue — rebuilding corpora now would publish "
                  f"a truncated corpus over the good one on the Hub.",
                  file=sys.stderr)
            return 1
        print(f"  OK: within tolerance ({shortfall:.2%} short of expected)")
    elif not args.allow_empty:
        print("ERROR: news_database.csv reports no extracted bodies.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
