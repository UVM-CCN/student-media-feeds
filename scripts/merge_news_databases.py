"""
Reconcile two divergent copies of news_database.csv into one.

Background: the nightly GitHub Action scraped a narrow feed list and committed
only news_database.csv + analytics/, discarding the full text it extracted.
Meanwhile local runs used the full 785-outlet feed list. The two copies drifted:
neither is a superset of the other, and the committed copy is full of rows
marked extraction_status="ok" whose full_text file was never committed.

This script unions both copies on `link` and repairs the extraction bookkeeping
against what is actually on disk, so fetch_full_text.py can backfill the gaps.

Merge rules
  - Union on `link` (the pipeline's own dedup key).
  - Where a link appears in both, the base row is the one from --primary.
  - `captured_at` takes the EARLIER of the two (first-seen semantics).
  - `theme` / `keywords` / sentiment: the primary's value wins unless it is
    empty, in which case the other side fills it in.
  - `full_text_path` is always RECOMPUTED from the link, never trusted. The
    path scheme is deterministic (sha1(url)[:2]/sha1(url).txt), so a recorded
    path that disagrees with the recomputed one is a bug, not a variant.
  - `extraction_status` is re-derived against the filesystem:
      file present            -> "ok"
      terminal failure recorded -> kept as-is (don't re-hammer dead URLs)
      anything else           -> cleared, so it lands in the backfill queue

Usage
    python scripts/merge_news_databases.py \
        --primary news_database.csv \
        --secondary /path/to/other_news_database.csv \
        --out news_database.merged.csv

    # inspect without writing:
    python scripts/merge_news_databases.py ... --dry-run
"""
import argparse
import csv
import hashlib
import os
import sys
from collections import Counter

FULL_TEXT_DIR = "full_text"

# Mirrors fetch_full_text.TERMINAL_STATUSES, minus "ok" — "ok" is only
# trustworthy when the file backing it actually exists, which we verify.
TERMINAL_FAILURES = {"empty", "http_404", "http_403", "http_410"}

FIELDS = [
    "source", "title", "link", "published", "captured_at", "theme",
    "keywords", "sentiment_label", "sentiment_score", "extraction_status",
    "full_text_path",
]


def text_path_for(url: str) -> str:
    """Same scheme as fetch_full_text.url_to_path — keep these in sync."""
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return os.path.join(FULL_TEXT_DIR, h[:2], f"{h}.txt")


def load(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def blank(value) -> bool:
    return (value or "").strip() in ("", "nan", "NaN", "None")


def pick(primary, secondary, field):
    """Primary wins unless it is blank."""
    p = (primary.get(field) or "").strip() if primary else ""
    if not blank(p):
        return p
    return (secondary.get(field) or "").strip() if secondary else ""


def earlier(a: str, b: str) -> str:
    vals = [v for v in ((a or "").strip(), (b or "").strip()) if v]
    return min(vals) if vals else ""


def merge_row(primary, secondary, on_disk) -> tuple[dict, str]:
    """Returns (merged_row, disposition) where disposition explains the status."""
    base = primary or secondary
    other = secondary if primary else None

    row = {f: pick(primary, secondary, f) for f in FIELDS}
    row["link"] = base["link"]
    if primary and secondary:
        row["captured_at"] = earlier(primary.get("captured_at"),
                                     secondary.get("captured_at"))

    # Never trust the recorded path — recompute it.
    path = text_path_for(row["link"])
    recorded = (base.get("full_text_path") or "").strip()

    if path in on_disk:
        row["full_text_path"] = path
        row["extraction_status"] = "ok"
        disposition = "ok_file_present"
        if recorded and recorded != path:
            disposition = "ok_path_repaired"
    else:
        row["full_text_path"] = ""
        prior = (base.get("extraction_status") or "").strip()
        prior_other = (other.get("extraction_status") or "").strip() if other else ""
        terminal = ({prior, prior_other} & TERMINAL_FAILURES)
        if terminal:
            # A recorded hard failure (404/403/410/empty) still stands.
            row["extraction_status"] = sorted(terminal)[0]
            disposition = f"kept_terminal:{sorted(terminal)[0]}"
        else:
            # Includes rows marked "ok" whose text was discarded by CI.
            row["extraction_status"] = ""
            disposition = "queued_for_backfill" if prior == "ok" else "queued_new"
    return row, disposition


def main():
    global FULL_TEXT_DIR

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--primary", required=True,
                    help="CSV whose field values win on conflict")
    ap.add_argument("--secondary", required=True)
    ap.add_argument("--out", help="destination CSV (required unless --dry-run)")
    ap.add_argument("--full-text-dir", default=FULL_TEXT_DIR)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen, write nothing")
    args = ap.parse_args()

    if not args.dry_run and not args.out:
        ap.error("--out is required unless --dry-run is given")

    FULL_TEXT_DIR = args.full_text_dir

    on_disk = set()
    for d, _, files in os.walk(FULL_TEXT_DIR):
        for name in files:
            on_disk.add(os.path.join(d, name))
    print(f"full_text files on disk: {len(on_disk):,}")

    P, S = load(args.primary), load(args.secondary)
    print(f"primary   {args.primary}: {len(P):,} rows")
    print(f"secondary {args.secondary}: {len(S):,} rows")

    Pi = {r["link"]: r for r in P if (r.get("link") or "").strip()}
    Si = {r["link"]: r for r in S if (r.get("link") or "").strip()}
    if len(Pi) != len(P) or len(Si) != len(S):
        print(f"  note: dropped {len(P)-len(Pi):,} primary / {len(S)-len(Si):,} "
              f"secondary rows with blank or duplicate links")

    merged, dispositions = [], Counter()
    for link in sorted(set(Pi) | set(Si)):
        row, disp = merge_row(Pi.get(link), Si.get(link), on_disk)
        merged.append(row)
        dispositions[disp] += 1

    # Stable, useful ordering for a file that gets diffed nightly.
    merged.sort(key=lambda r: ((r.get("captured_at") or ""), r["link"]))

    print(f"\nmerged rows: {len(merged):,}")
    print("  (primary only / secondary only / both): "
          f"{len(set(Pi)-set(Si)):,} / {len(set(Si)-set(Pi)):,} / {len(set(Pi)&set(Si)):,}")
    print("\ndisposition:")
    for k, v in dispositions.most_common():
        print(f"  {v:>7,}  {k}")

    queued = sum(v for k, v in dispositions.items() if k.startswith("queued"))
    print(f"\n{queued:,} rows will be picked up by fetch_full_text.process_pending_stories()")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return

    tmp = args.out + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(merged)
    os.replace(tmp, args.out)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    sys.exit(main())
