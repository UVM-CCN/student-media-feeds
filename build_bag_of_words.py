"""
Build a single bag-of-words frequency file from the full_text/ corpus.

Walks every .txt file under full_text/, strips the metadata header, tokenizes
the article body, filters stopwords and short tokens, and writes the global
word frequencies to bag_of_words.csv.

Output columns:
    rank                — 1 = most common word
    word                — the token (lowercased, alphabetic + hyphens/apostrophes)
    count               — total occurrences across the entire corpus
    document_frequency  — number of distinct stories the word appears in

This is the simplest bag-of-words representation: order is discarded, frequency
is preserved. The `count` and `document_frequency` columns together let you
compute TF-IDF, identify corpus-wide vs niche vocabulary, build word clouds,
or filter to terms that appear in many documents.

Usage:
    python build_bag_of_words.py

Re-run any time after the full_text/ corpus grows — output is overwritten.
"""

import csv
import logging
import re
import sys
from collections import Counter
from pathlib import Path

CORPUS_DIR = "full_text"
OUTPUT_FILE = "bag_of_words.csv"
HEADER_END_MARKER = "# ---"
MIN_WORD_LENGTH = 3

# Tokenizer: words starting with a letter, optionally containing hyphens or
# apostrophes (so "don't" and "first-year" survive). Numbers are excluded.
WORD_RE = re.compile(r"[a-z][a-z\-']+")

# Standard English stopwords plus a few corpus-specific terms that dominate
# news writing without carrying topical meaning. Add to this set if you see
# noise terms crowding out useful signal in the output.
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am",
    "an", "and", "any", "are", "aren", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can", "could",
    "did", "do", "does", "doing", "don", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "if", "in", "into", "is",
    "isn", "it", "its", "itself", "just", "me", "might", "more", "most", "must",
    "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once", "one",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own",
    "said", "same", "say", "says", "she", "should", "shouldn", "so", "some",
    "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "wasn", "we", "were", "weren",
    "what", "when", "where", "which", "while", "who", "whom", "why", "will",
    "with", "would", "you", "your", "yours", "yourself", "yourselves",
    # contractions remnants after apostrophe split
    "ll", "re", "ve",
    # generic news / time terms
    "year", "years", "day", "days", "week", "weeks", "month", "months", "time",
    "first", "last", "new", "old",
}


def strip_header(text: str) -> str:
    """
    Remove the metadata header (everything up to and including the # --- line).
    Returns the article body only.
    """
    idx = text.find(HEADER_END_MARKER)
    if idx == -1:
        return text
    newline = text.find("\n", idx)
    if newline == -1:
        return ""
    return text[newline + 1:]


def tokenize(text: str) -> list[str]:
    """Lowercase, regex-tokenize, drop short tokens and stopwords."""
    return [
        t for t in WORD_RE.findall(text.lower())
        if len(t) >= MIN_WORD_LENGTH and t not in STOPWORDS
    ]


def build_bag_of_words(corpus_dir: str = CORPUS_DIR, output_file: str = OUTPUT_FILE) -> dict:
    """
    Walk corpus_dir, count word frequencies, write CSV.
    Returns a summary dict for logging.
    """
    corpus_path = Path(corpus_dir)
    if not corpus_path.is_dir():
        raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")

    word_counts: Counter = Counter()
    doc_frequency: Counter = Counter()
    total_docs = 0
    total_tokens = 0

    for txt_path in sorted(corpus_path.rglob("*.txt")):
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                body = strip_header(f.read())
        except OSError as e:
            logging.warning("Could not read %s: %s", txt_path, e)
            continue

        tokens = tokenize(body)
        if not tokens:
            continue

        word_counts.update(tokens)
        doc_frequency.update(set(tokens))
        total_docs += 1
        total_tokens += len(tokens)

        if total_docs % 500 == 0:
            logging.info("Processed %d documents", total_docs)

    sorted_words = word_counts.most_common()

    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "word", "count", "document_frequency"])
        for rank, (word, count) in enumerate(sorted_words, 1):
            writer.writerow([rank, word, count, doc_frequency[word]])

    summary = {
        "documents": total_docs,
        "total_tokens": total_tokens,
        "unique_words": len(sorted_words),
        "output_file": output_file,
    }
    logging.info(
        "Wrote %d unique words (%d total tokens) from %d documents to %s",
        summary["unique_words"], summary["total_tokens"],
        summary["documents"], summary["output_file"],
    )
    return summary


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    build_bag_of_words()


if __name__ == "__main__":
    main()
