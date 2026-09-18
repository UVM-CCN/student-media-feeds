import csv
import os
import sys

# The full schema, not just the columns scrape.py populates.
#
# This list is the guard against a silent schema regression. Every rewrite in
# scrape.py used to flatten news_database.csv onto its own hardcoded column
# list, which deleted the three topic_* columns on every capture run -- the
# whole corpus lost its topic assignments three times a day. That shipped
# unnoticed for months precisely because this list stopped at sentiment_score,
# so a CSV that had just lost every topic assignment still validated green.
#
# Anything a pipeline stage is expected to leave behind belongs here.
REQUIRED_HEADERS = [
    # written by scrape.py
    "source",
    "title",
    "link",
    "published",
    "captured_at",
    "theme",
    "keywords",
    "sentiment_label",
    "sentiment_score",
    # written by fetch_full_text.py
    "extraction_status",
    "full_text_path",
    # written by scripts/apply_topics.py
    "topic_id",
    "topic_confidence",
    "topic_model_version",
]
VALID_SENTIMENT_LABELS = {"positive", "neutral", "negative"}


def fail(message: str) -> None:
    print(f"VALIDATION_ERROR: {message}")
    sys.exit(1)


def validate_csv(path: str) -> None:
    if not os.path.exists(path):
        fail(f"File not found: {path}")

    if os.path.getsize(path) == 0:
        fail(f"File is empty: {path}")

    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        missing = [h for h in REQUIRED_HEADERS if h not in headers]
        if missing:
            fail(f"Missing required columns: {', '.join(missing)}")

        seen_links = set()
        row_count = 0
        for row_count, row in enumerate(reader, start=1):
            link = (row.get("link") or "").strip()
            title = (row.get("title") or "").strip()
            captured_at = (row.get("captured_at") or "").strip()
            sentiment_label = (row.get("sentiment_label") or "").strip().lower()
            sentiment_score = (row.get("sentiment_score") or "").strip()

            if not link:
                fail(f"Row {row_count}: missing link")
            if not title:
                fail(f"Row {row_count}: missing title")
            if not captured_at:
                fail(f"Row {row_count}: missing captured_at")
            if sentiment_label not in VALID_SENTIMENT_LABELS:
                fail(f"Row {row_count}: invalid sentiment_label '{sentiment_label}'")

            try:
                score = float(sentiment_score)
            except ValueError:
                fail(f"Row {row_count}: non-numeric sentiment_score '{sentiment_score}'")

            if score < -1.0 or score > 1.0:
                fail(f"Row {row_count}: sentiment_score out of range [-1, 1]: {score}")

            if link in seen_links:
                fail(f"Row {row_count}: duplicate link detected: {link}")
            seen_links.add(link)

        print(f"Validation passed for {path}. Rows checked: {row_count}")


def main() -> None:
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "news_database.csv"
    validate_csv(csv_path)


if __name__ == "__main__":
    main()
