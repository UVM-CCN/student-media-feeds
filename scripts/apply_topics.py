"""
Assign topics to stories by nearest frozen centroid.

This is the nightly half of the topic pipeline. It fits nothing. It embeds each
new story and assigns it to whichever of the frozen centroids from
train_topic_model.py it is closest to by cosine similarity.

Because the centroids are fixed vectors, a story classified tonight is directly
comparable to one classified a year ago — which is the entire point, since the
dashboard charts coverage change over time and that is only meaningful if the
topic definitions hold still.

Only rows needing work are touched: no topic yet, or a topic_model_version that
does not match the current model. Re-running is cheap and idempotent.

Columns written to news_database.csv:
    topic_id             index of the nearest centroid, stable per model version
    topic_confidence     cosine similarity to that centroid (0-1). Low values
                         mean the story sits between topics; the dashboard can
                         filter on this rather than pretending every assignment
                         is equally good.
    topic_model_version  which model produced the assignment, so a future
                         retrain leaves a visible seam instead of silently
                         breaking the time series

Labels are deliberately NOT written here. They live in data/topic_labels.json
and are resolved when dashboard data is built, so renaming a topic never
requires reprocessing the corpus.

Usage:
    python scripts/apply_topics.py
    python scripts/apply_topics.py --reassign-all    # after retraining
"""
import os
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import argparse
import collections
import csv
import sys

try:
    import joblib
    import numpy as np
    from sentence_transformers import SentenceTransformer
except ImportError as e:
    sys.exit(f"ERROR: missing dependency ({e}).\n"
             "Install with: pip install sentence-transformers joblib")

from text_quality import load_story_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_CSV = os.path.join(ROOT, "news_database.csv")
MODEL_PATH = os.path.join(ROOT, "models", "topic_model.joblib")
HEADER_END_MARKER = "# ---"
TOPIC_COLUMNS = ("topic_id", "topic_confidence", "topic_model_version")


def body_for(row: dict, limit_words: int) -> str:
    """Cleaned, truncated body, or "" if this is not a story (see text_quality)."""
    path = (row.get("full_text_path") or "").strip()
    if not path:
        return ""
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return ""
    text = load_story_text(full, row.get("title", ""), row.get("link", ""),
                           limit_words)
    return text or ""


def write_csv_atomic(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({fn: r.get(fn, "") for fn in fieldnames})
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reassign-all", action="store_true")
    ap.add_argument("--csv", default=SOURCE_CSV)
    ap.add_argument("--model", default=MODEL_PATH)
    ap.add_argument("--batch-size", type=int, default=64)
    args = ap.parse_args()

    if not os.path.exists(args.model):
        print(f"ERROR: no model at {args.model}.\n"
              "Run scripts/train_topic_model.py first.", file=sys.stderr)
        return 1

    bundle = joblib.load(args.model)
    centroids = bundle["centroids"]
    version = bundle["version"]
    limit_words = bundle["params"]["words"]
    k = bundle["params"]["k"]
    print(f"Model {version}: {k} frozen centroids, "
          f"{bundle['embed_model']}, first {limit_words} words")

    with open(args.csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    for col in TOPIC_COLUMNS:
        if col not in fieldnames:
            fieldnames.append(col)
    for r in rows:
        for col in TOPIC_COLUMNS:
            r.setdefault(col, "")

    def needs_work(r: dict) -> bool:
        if (r.get("extraction_status") or "").strip() != "ok":
            return False
        if args.reassign_all:
            return True
        return (not (r.get("topic_id") or "").strip()
                or (r.get("topic_model_version") or "").strip() != version)

    targets = [i for i, r in enumerate(rows) if needs_work(r)]
    print(f"  {len(targets):,} of {len(rows):,} rows need assignment")
    if not targets:
        print("  nothing to do")
        return 0

    usable, docs = [], []
    for i in targets:
        text = body_for(rows[i], limit_words)
        if text:
            usable.append(i)
            docs.append(text)
    skipped = len(targets) - len(usable)
    print(f"  {len(usable):,} with usable text"
          + (f", {skipped:,} skipped (missing or under 50 words)" if skipped else ""))
    if not usable:
        return 0

    print("Embedding and assigning...")
    model = SentenceTransformer(bundle["embed_model"])
    emb = model.encode(docs, batch_size=args.batch_size, show_progress_bar=False,
                       normalize_embeddings=True, convert_to_numpy=True)
    sims = emb @ centroids.T
    assigned = sims.argmax(axis=1)
    conf = sims.max(axis=1)

    for n, i in enumerate(usable):
        rows[i]["topic_id"] = str(int(assigned[n]))
        rows[i]["topic_confidence"] = f"{float(conf[n]):.4f}"
        rows[i]["topic_model_version"] = version

    write_csv_atomic(args.csv, fieldnames, rows)

    dist = collections.Counter(r["topic_id"] for r in rows if (r.get("topic_id") or "").strip())
    total = sum(dist.values())
    print(f"\nAssigned. Corpus now {total:,} classified stories:")
    for t in sorted(dist, key=int):
        print(f"  topic {t:>2}: {dist[t]:>6,}  ({dist[t]/total:5.1%})")
    low = int((conf < 0.30).sum())
    print(f"\n  batch mean similarity {conf.mean():.3f}"
          + (f"; {low:,} below 0.30 (between topics)" if low else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
