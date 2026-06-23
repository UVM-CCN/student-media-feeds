"""
Build per-publication text corpora for vector-space analysis.

Reads news_database.csv, groups every successfully-extracted story by its
`source` (publication name), and writes one concatenated text file per
publication. Designed for workflows that vectorize each publication's entire
body of work as a single "document" (CountVectorizer, TfidfVectorizer, doc2vec).

Outputs:

  publication_corpora/<slug>.txt
      One file per publication. Article bodies are concatenated with blank-line
      separators only — no metadata headers, story numbers, or markers that
      would pollute the vocabulary during vectorization. Use these files as
      direct input to sklearn / gensim / spaCy.

  publication_corpora_manifest.csv
      One row per publication: name, slug, corpus file path, story count,
      total words, date range. Quick summary stats.

  publication_story_index.csv
      One row per story: which publication it belongs to, title, URL, published
      date, word count, and path to the original .txt. This is the lookup table
      to "find every story under a given publication" — load it in pandas and
      filter by publication.

Usage:
    python build_publication_corpora.py

Re-run any time after full_text/ grows. Output is overwritten.

Downstream example (your colleague's vectorization workflow):
    from sklearn.feature_extraction.text import TfidfVectorizer
    import os, glob
    paths = sorted(glob.glob("publication_corpora/*.txt"))
    labels = [os.path.splitext(os.path.basename(p))[0] for p in paths]
    docs = [open(p, encoding="utf-8").read() for p in paths]
    vectorizer = TfidfVectorizer(stop_words="english", min_df=2)
    X = vectorizer.fit_transform(docs)  # shape: (n_publications, vocab_size)
"""

import csv
import logging
import os
import re
import sys
from collections import defaultdict
from typing import Optional

CSV_PATH = "news_database.csv"
OUTPUT_DIR = "publication_corpora"
MANIFEST_FILE = "publication_corpora_manifest.csv"
STORY_INDEX_FILE = "publication_story_index.csv"
HEADER_END_MARKER = "# ---"
STORY_SEPARATOR = "\n\n"


def slugify(name: str) -> str:
    """Convert a publication name to a filesystem-safe slug."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "unknown"


def disambiguate_slug(slug: str, used: set[str]) -> str:
    """Append a numeric suffix if the slug collides with an existing one."""
    if slug not in used:
        return slug
    for n in range(2, 1000):
        candidate = f"{slug}-{n}"
        if candidate not in used:
            return candidate
    raise RuntimeError(f"Could not disambiguate slug: {slug}")


def strip_header(text: str) -> str:
    """Remove the metadata header inserted by fetch_full_text.py."""
    idx = text.find(HEADER_END_MARKER)
    if idx == -1:
        return text
    newline = text.find("\n", idx)
    if newline == -1:
        return ""
    return text[newline + 1:]


def read_story_body(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return strip_header(f.read()).strip()
    except OSError as e:
        logging.warning("Could not read %s: %s", path, e)
        return None


def build_corpora(
    csv_path: str = CSV_PATH,
    output_dir: str = OUTPUT_DIR,
    manifest_file: str = MANIFEST_FILE,
    story_index_file: str = STORY_INDEX_FILE,
) -> dict:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    os.makedirs(output_dir, exist_ok=True)

    by_publication: dict[str, list[dict]] = defaultdict(list)
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("extraction_status") or "").strip() != "ok":
                continue
            path = (row.get("full_text_path") or "").strip()
            if not path or not os.path.exists(path):
                continue
            pub = (row.get("source") or "").strip() or "Unknown Publication"
            by_publication[pub].append(row)

    if not by_publication:
        logging.warning("No extractable stories found in %s.", csv_path)
        return {"publications": 0, "stories": 0}

    manifest_rows = []
    story_index_rows = []
    used_slugs: set[str] = set()

    for pub in sorted(by_publication.keys()):
        stories = by_publication[pub]
        stories.sort(key=lambda r: r.get("published") or "")

        slug = disambiguate_slug(slugify(pub), used_slugs)
        used_slugs.add(slug)
        corpus_path = os.path.join(output_dir, f"{slug}.txt")

        total_words = 0
        bodies = []
        for story in stories:
            body = read_story_body(story["full_text_path"])
            if not body:
                continue
            word_count = len(body.split())
            total_words += word_count
            bodies.append(body)
            story_index_rows.append({
                "publication": pub,
                "slug": slug,
                "title": story.get("title", ""),
                "url": story.get("link", ""),
                "published": story.get("published", ""),
                "word_count": word_count,
                "full_text_path": story["full_text_path"],
            })

        if not bodies:
            logging.info("%s: no readable bodies, skipping corpus file", pub)
            continue

        with open(corpus_path, "w", encoding="utf-8") as out:
            out.write(STORY_SEPARATOR.join(bodies))
            out.write("\n")

        dates = [s.get("published") for s in stories if s.get("published")]
        manifest_rows.append({
            "publication": pub,
            "slug": slug,
            "corpus_file": corpus_path,
            "story_count": len(bodies),
            "total_words": total_words,
            "earliest_story": min(dates) if dates else "",
            "latest_story": max(dates) if dates else "",
        })

        logging.info(
            "%s → %s (%d stories, %d words)",
            pub, corpus_path, len(bodies), total_words,
        )

    manifest_rows.sort(key=lambda r: r["story_count"], reverse=True)
    with open(manifest_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "publication", "slug", "corpus_file", "story_count",
            "total_words", "earliest_story", "latest_story",
        ])
        writer.writeheader()
        writer.writerows(manifest_rows)

    with open(story_index_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "publication", "slug", "title", "url", "published",
            "word_count", "full_text_path",
        ])
        writer.writeheader()
        writer.writerows(story_index_rows)

    total_stories = sum(r["story_count"] for r in manifest_rows)
    logging.info(
        "Done. %d publications, %d stories. Corpora → %s/, manifest → %s, story index → %s",
        len(manifest_rows), total_stories, output_dir, manifest_file, story_index_file,
    )
    return {
        "publications": len(manifest_rows),
        "stories": total_stories,
        "output_dir": output_dir,
        "manifest_file": manifest_file,
        "story_index_file": story_index_file,
    }


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    build_corpora()


if __name__ == "__main__":
    main()
