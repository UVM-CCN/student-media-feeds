import csv
import json
import os
import datetime
import logging
import email.utils
from collections import Counter, defaultdict
from typing import Dict, List, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class AnalyticsEngine:
    def __init__(self, csv_path: str = "news_database.csv", output_dir: str = "analytics"):
        self.csv_path = csv_path
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def load_stories(self) -> List[Dict[str, str]]:
        """Load all stories from the CSV."""
        stories = []
        if not os.path.exists(self.csv_path):
            return stories
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            stories = list(reader)
        return stories

    def extract_date(self, timestamp_str: str) -> Optional[str]:
        """Extract YYYY-MM-DD from various timestamp formats."""
        if not timestamp_str:
            return None
        
        timestamp_str = timestamp_str.strip()

        # First try robust RFC 2822 parsing used by many RSS feeds,
        # e.g. "Mon, 24 Jun 2019 17:48:00 -0500".
        try:
            dt = email.utils.parsedate_to_datetime(timestamp_str)
            if dt is not None:
                return dt.strftime("%Y-%m-%d")
        except (TypeError, ValueError, IndexError):
            pass
        
        # Try formats in order of likelihood
        formats = [
            "%Y-%m-%d %H:%M:%S",           # 2026-02-03 11:52:48
            "%Y-%m-%dT%H:%M:%S",          # 2026-02-03T11:52:48
            "%Y-%m-%dT%H:%M:%S%z",        # 2026-02-03T11:52:48+0000
            "%a, %d %b %Y %H:%M:%S %z",   # Mon, 24 Jun 2019 17:48:00 -0500
            "%a, %d %b %Y %H:%M:%S",      # Mon, 24 Jun 2019 17:48:00
            "%d %b %Y %H:%M:%S %z",       # 19 Dec 2025 19:19:34 +0000
            "%d %b %Y %H:%M:%S",          # 19 Dec 2025 19:19:34
        ]
        
        for fmt in formats:
            try:
                dt = datetime.datetime.strptime(timestamp_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        # Fall back to ISO format with replacement
        try:
            dt = datetime.datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return None

    def aggregate_by_theme(self, stories: List[Dict]) -> Dict[str, int]:
        """Count articles by theme."""
        counter = Counter()
        for story in stories:
            theme = (story.get("theme") or "").strip()
            if theme and theme.lower() != "unclassified":
                counter[theme] += 1
        return dict(counter.most_common(20))

    def aggregate_by_sentiment(self, stories: List[Dict]) -> Dict[str, int]:
        """Count articles by sentiment label."""
        counter = Counter()
        for story in stories:
            label = (story.get("sentiment_label") or "").strip().lower()
            if label in {"positive", "neutral", "negative"}:
                counter[label] += 1
        return dict(counter)

    def aggregate_keywords_global(self, stories: List[Dict], top_n: int = 30) -> Dict[str, int]:
        """Extract and rank keywords globally across all stories."""
        keyword_counter = Counter()
        for story in stories:
            keywords_str = (story.get("keywords") or "").strip()
            if keywords_str:
                tokens = [k.strip() for k in keywords_str.split("|")]
                keyword_counter.update(tokens)
        return dict(keyword_counter.most_common(top_n))

    def aggregate_by_source(self, stories: List[Dict]) -> Dict[str, int]:
        """Count articles by source."""
        counter = Counter()
        for story in stories:
            source = (story.get("source") or "").strip()
            if source:
                counter[source] += 1
        return dict(counter.most_common(15))

    def aggregate_timeseries(self, stories: List[Dict]) -> Dict[str, Any]:
        """Build time-series data for trend charts using published dates."""
        by_date = defaultdict(lambda: {
            "total": 0,
            "themes": Counter(),
            "sentiment": Counter(),
            "keywords": Counter(),
            "sources": Counter(),
        })

        for story in stories:
            # Use published date instead of captured_at for richer timeline
            date = self.extract_date(story.get("published", ""))
            if not date:
                continue

            by_date[date]["total"] += 1

            theme = (story.get("theme") or "").strip()
            if theme and theme.lower() != "unclassified":
                by_date[date]["themes"][theme] += 1

            sentiment = (story.get("sentiment_label") or "").strip().lower()
            if sentiment in {"positive", "neutral", "negative"}:
                by_date[date]["sentiment"][sentiment] += 1

            keywords_str = (story.get("keywords") or "").strip()
            if keywords_str:
                tokens = [k.strip() for k in keywords_str.split("|")]
                by_date[date]["keywords"].update(tokens)

            source = (story.get("source") or "").strip()
            if source:
                by_date[date]["sources"][source] += 1

        result = {}
        for date in sorted(by_date.keys()):
            result[date] = {
                "total": by_date[date]["total"],
                "themes": dict(by_date[date]["themes"].most_common(10)),
                "sentiment": dict(by_date[date]["sentiment"]),
                "keywords": dict(by_date[date]["keywords"].most_common(10)),
                "sources": dict(by_date[date]["sources"].most_common()),
            }
        return result

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive analytics report."""
        stories = self.load_stories()
        if not stories:
            logging.warning("No stories found in %s", self.csv_path)
            return {}

        logging.info("Generating analytics report for %d stories...", len(stories))

        report = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_stories": len(stories),
            "themes": self.aggregate_by_theme(stories),
            "sentiment": self.aggregate_by_sentiment(stories),
            "keywords": self.aggregate_keywords_global(stories),
            "sources": self.aggregate_by_source(stories),
            "timeseries": self.aggregate_timeseries(stories),
        }

        return report

    def save_report(self, report: Dict[str, Any], filename: str = "analytics.json") -> str:
        """Save analytics report to JSON file."""
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logging.info("Saved analytics report to %s", filepath)
        return filepath

    def run(self) -> str:
        """Generate and save analytics report."""
        report = self.generate_report()
        if report:
            return self.save_report(report)
        return None


def main():
    engine = AnalyticsEngine()
    engine.run()


if __name__ == "__main__":
    main()
