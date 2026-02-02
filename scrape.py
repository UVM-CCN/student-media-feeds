import csv
import os
import datetime
import logging
from typing import List, Set

# You may need to install these: pip install feedparser listparser
import feedparser
import listparser

# Configure logging to track the pipeline progress
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class NewsPipeline:
    def __init__(self, output_file: str = "news_stories.csv"):
        self.output_file = output_file
        self.headers = ["source", "title", "link", "published", "captured_at"]
        self._setup_csv()

    def _setup_csv(self):
        """Initializes the CSV file with headers if it doesn't exist."""
        if not os.path.exists(self.output_file):
            with open(self.output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.headers)
                writer.writeheader()
            logging.info(f"Created new database file: {self.output_file}")

    def get_existing_links(self) -> Set[str]:
        """Reads the CSV to get a set of already saved links to avoid duplicates."""
        links = set()
        if os.path.exists(self.output_file):
            with open(self.output_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    links.add(row['link'])
        return links

    def parse_opml(self, opml_path: str) -> List[str]:
        """Extracts RSS URLs from an OPML file."""
        logging.info(f"Parsing OPML file: {opml_path}")
        try:
            # listparser.parse expects OPML content; read the file first
            with open(opml_path, 'r', encoding='utf-8') as f:
                content = f.read()
            result = listparser.parse(content)
            return [feed.url for feed in result.feeds if feed.url]
        except Exception as e:
            logging.error(f"Error parsing OPML: {e}")
            return []

    def parse_url_list(self, txt_path: str) -> List[str]:
        """Reads a simple text file where each line is a URL."""
        logging.info(f"Reading URL list: {txt_path}")
        try:
            with open(txt_path, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        except Exception as e:
            logging.error(f"Error reading URL list: {e}")
            return []

    def fetch_stories(self, feed_urls: List[str]):
        """Fetches stories from a list of RSS feeds and saves new ones."""
        existing_links = self.get_existing_links()
        captured_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_stories_count = 0

        with open(self.output_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.headers)

            for url in feed_urls:
                logging.info(f"Fetching: {url}")
                feed = feedparser.parse(url)
                
                # Check if the feed is valid
                if feed.bozo:
                    logging.warning(f"Possible issue with feed {url}: {feed.bozo_exception}")

                for entry in feed.entries:
                    link = getattr(entry, 'link', '')
                    
                    # Skip if we already have this story
                    if not link or link in existing_links:
                        continue

                    story = {
                        "source": feed.feed.get('title', url),
                        "title": getattr(entry, 'title', 'No Title'),
                        "link": link,
                        "published": getattr(entry, 'published', 'No Date'),
                        "captured_at": captured_at
                    }
                    
                    writer.writerow(story)
                    existing_links.add(link)
                    new_stories_count += 1
        
        logging.info(f"Pipeline complete. Added {new_stories_count} new stories.")

def run_daily_update():
    # Configuration
    DATABASE = "news_database.csv"

    pipeline = NewsPipeline(DATABASE)

    # Gather all feed URLs
    all_feeds = []

    # 1) Look for any .opml files inside the `feeds` directory (common export location)
    feeds_dir = "feeds"
    if os.path.isdir(feeds_dir):
        for fname in os.listdir(feeds_dir):
            if fname.lower().endswith('.opml'):
                opml_path = os.path.join(feeds_dir, fname)
                all_feeds.extend(pipeline.parse_opml(opml_path))

    # 2) Also keep backward-compatible single-file names in the repo root
    OPML_FILE = "feeds.opml"
    if os.path.exists(OPML_FILE):
        all_feeds.extend(pipeline.parse_opml(OPML_FILE))

    TEXT_FILE = "discovered_feeds.txt"
    if os.path.exists(TEXT_FILE):
        all_feeds.extend(pipeline.parse_url_list(TEXT_FILE))

    # Remove duplicates from the feed list itself
    unique_feeds = list(set(all_feeds))

    if unique_feeds:
        pipeline.fetch_stories(unique_feeds)
    else:
        logging.error("No feed URLs found to process.")

if __name__ == "__main__":
    run_daily_update()