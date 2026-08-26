"""
Discover the topics once, freeze their centroids, and never fit again.

Why centroids rather than a topic model's own inference:

    scrape.py used to refit BERTopic on each night's new headlines, so every
    night was a different model. The same story could carry different themes in
    two copies of the database, and a "coverage over time" chart built on that
    column would have measured model drift rather than editorial change.

    Refitting is the obvious bug, but a frozen topic model is not much better:
    BERTopic's transform() runs UMAP then HDBSCAN approximate_predict, which is
    not deterministic near cluster boundaries and drops uncertain documents into
    an outlier class. LDA is deterministic but bag-of-words, and on this corpus
    it grouped by *register* rather than subject — it put Spider-Man reviews
    and primary-election coverage in one topic because both are written in an
    evaluative first-person voice.

    So: embeddings for semantics, but assignment by nearest frozen centroid.
    A centroid is a fixed vector. Cosine similarity to a fixed vector is
    deterministic forever, gives a usable confidence score, and costs one
    forward pass per new story.

Clustering is spherical k-means — k-means over L2-normalized embeddings, which
makes Euclidean distance monotonic in cosine distance. Fixed seed, so the same
corpus yields the same topics.

Topic descriptions come from c-TF-IDF over the cluster assignments: terms that
are frequent inside a cluster and rare outside it. Publication and institution
names are suppressed there, or the descriptions read as "Wvu | Mountaineers |
Syracuse" instead of naming a subject.

Outputs:
    models/topic_model.joblib   frozen centroids + metadata
    data/topic_labels.json      skeleton for you to fill in human labels
    (stdout)                    top terms and representative headlines per topic

Usage:
    python scripts/train_topic_model.py
    python scripts/train_topic_model.py --k 12
"""
import os
# Quiet the model-loading progress bars before the libraries are imported.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone

try:
    import joblib
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS
    from sentence_transformers import SentenceTransformer
except ImportError as e:
    sys.exit(f"ERROR: missing dependency ({e}).\n"
             "Install with: pip install sentence-transformers scikit-learn joblib")

from text_quality import load_story_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_CSV = os.path.join(ROOT, "news_database.csv")
LOCATIONS_CSV = os.path.join(ROOT, "data", "publication_locations.csv")
MODEL_PATH = os.path.join(ROOT, "models", "topic_model.joblib")
LABELS_PATH = os.path.join(ROOT, "data", "topic_labels.json")
HEADER_END_MARKER = "# ---"
EMBED_MODEL = "all-MiniLM-L6-v2"

BOILERPLATE = {
    "said", "says", "say", "told", "according", "asked", "added", "stated",
    "photo", "photos", "courtesy", "image", "images", "caption", "credit",
    "editor", "editors", "reporter", "reporters", "staff", "writer", "writers",
    "correspondent", "contributed", "reporting", "newsroom",
    "story", "stories", "article", "articles", "read", "reads", "click",
    "comment", "comments", "share", "email", "follow", "subscribe", "newsletter",
    "advertisement", "sponsored", "copyright", "reserved", "rights",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "just", "like", "really", "going", "know", "think", "want", "way", "time",
    "year", "years", "day", "days", "week", "new", "did", "didn", "don", "got",
}


def tokenize_name(name: str) -> set[str]:
    return {t for t in re.split(r"[^A-Za-z]+", (name or "").lower()) if len(t) > 2}


def build_stopwords(sources: set[str]) -> set[str]:
    """English + boilerplate + every token in a publication or institution name."""
    stop = set(ENGLISH_STOP_WORDS) | BOILERPLATE
    names: set[str] = set()
    for s in sources:
        names |= tokenize_name(s)
    if os.path.exists(LOCATIONS_CSV):
        with open(LOCATIONS_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                names |= tokenize_name(row.get("institution", ""))
                names |= tokenize_name(row.get("publication", ""))
                names |= tokenize_name(row.get("state", ""))
    print(f"  suppressing {len(names):,} publication/institution tokens "
          f"from topic descriptions")
    return stop | names


def load_documents(limit_words: int):
    """
    Every extracted story that survives the non-story filter, truncated to the
    first `limit_words` tokens. See scripts/text_quality.py for what gets
    dropped and why.
    """
    docs, meta = [], []
    dropped = 0
    with open(SOURCE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if (row.get("extraction_status") or "").strip() != "ok":
            continue
        path = (row.get("full_text_path") or "").strip()
        if not path:
            continue
        full = os.path.join(ROOT, path)
        if not os.path.exists(full):
            continue
        text = load_story_text(full, row.get("title", ""), row.get("link", ""),
                               limit_words)
        if text is None:
            dropped += 1
            continue
        docs.append(text)
        meta.append({"link": row.get("link", ""), "source": row.get("source", ""),
                     "title": row.get("title", "")})
    if dropped:
        print(f"  filtered out {dropped:,} items that are not stories "
              f"(image pages, CMS stubs, too short)")
    return docs, meta


def ctfidf_terms(docs, labels, k, stopwords, top_n=18):
    """
    Class-based TF-IDF: terms frequent within a cluster and rare across others.
    Gives readable topic descriptions without the centroids themselves being
    involved — the centroids live in embedding space and are not interpretable.
    """
    vec = CountVectorizer(stop_words=sorted(stopwords), min_df=10, max_df=0.5,
                          token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]{2,}\b")
    X = vec.fit_transform(docs)
    vocab = vec.get_feature_names_out()
    per_class = np.zeros((k, X.shape[1]))
    for t in range(k):
        mask = labels == t
        if mask.any():
            per_class[t] = np.asarray(X[mask].sum(axis=0)).ravel()
    tf = per_class / np.maximum(per_class.sum(axis=1, keepdims=True), 1)
    total = np.maximum(per_class.sum(axis=0), 1)
    idf = np.log(1 + (per_class.sum() / k) / total)
    scores = tf * idf
    return [[vocab[i] for i in scores[t].argsort()[::-1][:top_n]] for t in range(k)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--words", type=int, default=200,
                    help="tokens of each body to embed (default 200)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--batch-size", type=int, default=64)
    args = ap.parse_args()

    print("Loading documents...")
    docs, meta = load_documents(args.words)
    print(f"  {len(docs):,} documents with usable bodies")
    if len(docs) < 500:
        print("ERROR: too few documents to fit stable topics.", file=sys.stderr)
        return 1

    print(f"\nEmbedding with {EMBED_MODEL} (this is the slow step)...")
    model = SentenceTransformer(EMBED_MODEL)
    emb = model.encode(docs, batch_size=args.batch_size, show_progress_bar=False,
                       normalize_embeddings=True, convert_to_numpy=True)
    print(f"  {emb.shape[0]:,} x {emb.shape[1]} embeddings")

    print(f"\nSpherical k-means (k={args.k}, seed={args.seed})...")
    km = KMeans(n_clusters=args.k, random_state=args.seed, n_init=10)
    labels = km.fit_predict(emb)
    # Re-normalize centroids: the mean of unit vectors is not itself unit-length,
    # and assignment is by cosine similarity.
    centroids = km.cluster_centers_
    centroids = centroids / np.linalg.norm(centroids, axis=1, keepdims=True)

    # Re-assign by cosine against the normalized centroids, which is exactly
    # what apply_topics.py does nightly. k-means assigned by Euclidean distance
    # to the unnormalized means, and those two partitions differ slightly at the
    # margins. Reporting the k-means partition would describe topics the running
    # pipeline never actually produces.
    sims = emb @ centroids.T
    labels = sims.argmax(axis=1)
    conf = sims.max(axis=1)
    print(f"  mean cosine similarity to assigned centroid: {conf.mean():.3f}")
    print(f"  stories below 0.30 similarity: {(conf < 0.30).sum():,}")

    sources = {m["source"] for m in meta if m["source"]}
    stopwords = build_stopwords(sources)
    print("\nDeriving topic descriptions (c-TF-IDF)...")
    terms = ctfidf_terms(docs, labels, args.k, stopwords)

    version = f"emb-k{args.k}-{datetime.now(timezone.utc):%Y%m%d}"
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump({
        "centroids": centroids,
        "embed_model": EMBED_MODEL,
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_docs": len(docs),
        "terms": terms,
        "params": {"k": args.k, "words": args.words, "seed": args.seed},
    }, MODEL_PATH)
    print(f"Saved {os.path.relpath(MODEL_PATH, ROOT)} (version {version})")

    print("\n" + "=" * 72)
    print("TOPICS — write a label for each in data/topic_labels.json")
    print("=" * 72)
    out = {"model_version": version, "topics": {}}
    for t in range(args.k):
        mask = labels == t
        n = int(mask.sum())
        # Representative = closest to the centroid, i.e. most typical of the topic
        idx = np.where(mask)[0]
        best = idx[np.argsort(sims[idx, t])[::-1][:6]]
        print(f"\nTopic {t}  —  {n:,} stories ({n/len(docs):.1%})  "
              f"mean similarity {sims[mask, t].mean():.3f}")
        print(f"  terms: {', '.join(terms[t])}")
        print("  most typical headlines:")
        for i in best:
            print(f"    - {meta[i]['title'][:95]}")
        out["topics"][str(t)] = {
            "label": "",
            "terms": terms[t],
            "story_share": round(n / len(docs), 4),
            "mean_similarity": round(float(sims[mask, t].mean()), 4),
            "examples": [meta[i]["title"] for i in best[:4]],
        }

    with open(LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {os.path.relpath(LABELS_PATH, ROOT)} — fill in each \"label\".")
    print("Then run: python scripts/apply_topics.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
