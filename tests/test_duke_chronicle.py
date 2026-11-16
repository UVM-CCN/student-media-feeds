import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import http_compat
from scrape import NewsPipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import train_topic_model


FEED_URL = "https://www.dukechronicle.com/xml/feed/firehose.xml"
STORY_URL = "https://dukechronicle.com/article/example"
FEED = f"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Recent stories from the Duke Chronicle</title>
<item><title>A story</title><link>{STORY_URL}</link>
<pubDate>Mon, 16 Nov 2026 10:00:00 GMT</pubDate></item>
</channel></rss>""".encode()


class ChronicleTests(unittest.TestCase):
    def test_feed_capture_and_deduplication(self):
        response = Mock(content=FEED)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "news.csv"
            pipeline = NewsPipeline(str(path))
            with patch("scrape.requests.get", return_value=response) as get, \
                    patch("scrape.throttle_host") as throttle:
                pipeline.fetch_stories([FEED_URL])
                pipeline.fetch_stories([FEED_URL])
            with path.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["link"], STORY_URL)
        self.assertEqual(rows[0]["extraction_status"], "")
        self.assertEqual(get.call_args.kwargs["headers"]["User-Agent"],
                         http_compat.BROWSER_USER_AGENT)
        self.assertEqual(throttle.call_count, 2)

    def test_feed_and_article_share_crawl_delay(self):
        http_compat._last_request_by_host.clear()
        self.addCleanup(http_compat._last_request_by_host.clear)
        with patch("http_compat.time.monotonic", side_effect=[100, 102, 110]), \
                patch("http_compat.time.sleep") as sleep:
            http_compat.throttle_host(FEED_URL)
            http_compat.throttle_host(STORY_URL)
        sleep.assert_called_once_with(8)

    def test_excludes_chronicle_from_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "body.txt").write_text("story body", encoding="utf-8")
            source = root / "news.csv"
            with source.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["link", "source", "title", "extraction_status", "full_text_path"]
                )
                writer.writeheader()
                for url in (STORY_URL, "https://www.dukechronicle.com/article/other",
                            "https://other.example/article/one"):
                    writer.writerow({"link": url, "source": "paper", "title": "headline",
                                     "extraction_status": "ok", "full_text_path": "body.txt"})
            with patch.object(train_topic_model, "ROOT", str(root)), \
                    patch.object(train_topic_model, "SOURCE_CSV", str(source)), \
                    patch.object(train_topic_model, "load_story_text", return_value="usable text") as load:
                docs, meta = train_topic_model.load_documents(200)
        self.assertEqual(docs, ["usable text"])
        self.assertEqual(meta[0]["link"], "https://other.example/article/one")
        self.assertEqual(load.call_count, 1)


if __name__ == "__main__":
    unittest.main()
