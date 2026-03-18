import csv
import os
import datetime
import logging
import json
import math
import time
import random
import html
import re
from collections import Counter
from typing import List, Set, Any, Optional

import feedparser
import listparser
import requests
from bs4 import BeautifulSoup

from bertopic import BERTopic
from bertopic.representation import KeyBERTInspired
import pandas as pd

# Configure logging to track the pipeline progress
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he", "in", "is", "it", "its",
    "of", "on", "that", "the", "to", "was", "were", "will", "with", "this", "their", "they", "you", "your",
    "about", "after", "all", "also", "but", "can", "into", "more", "new", "not", "one", "or", "our", "out",
    "over", "said", "than", "them", "these", "those", "through", "up", "we", "what", "when", "who", "why", "how"
}

POSITIVE_WORDS = {
    "achievement", "achieve", "award", "benefit", "breakthrough", "celebrate", "growth", "improve", "improved",
    "improvement", "innovation", "lead", "leading", "opportunity", "progress", "recovery", "record", "support",
    "success", "successful", "win", "wins", "positive", "strong", "resilient"
}

NEGATIVE_WORDS = {
    "abuse", "accident", "crisis", "decline", "deficit", "delay", "dispute", "failure", "harm", "injury", "lawsuit",
    "loss", "negative", "protest", "risk", "scandal", "shortage", "shooting", "strike", "threat", "violence", "warning"
}

class NewsPipeline:
    def __init__(self, output_file: str = "news_database.csv"):
        self.output_file = output_file
        # Standardized headers
        self.headers = [
            "source",
            "title",
            "link",
            "published",
            "captured_at",
            "theme",
            "keywords",
            "sentiment_label",
            "sentiment_score",
        ]
        self._setup_csv()

    def _setup_csv(self):
        """Initializes or migrates the CSV file schema."""
        if not os.path.exists(self.output_file):
            with open(self.output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.headers)
                writer.writeheader()
            logging.info(f"Created new database file: {self.output_file}")
            return

        with open(self.output_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            existing_headers = reader.fieldnames or []
            rows = list(reader)

        if existing_headers == self.headers:
            return

        missing_headers = [h for h in self.headers if h not in existing_headers]
        if not missing_headers:
            return

        logging.info(
            "Migrating CSV schema for %s. Adding missing columns: %s",
            self.output_file,
            ", ".join(missing_headers),
        )
        with open(self.output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.headers)
            writer.writeheader()
            for row in rows:
                migrated_row = {h: row.get(h, "") for h in self.headers}
                writer.writerow(migrated_row)

    def _clean_text(self, value: Any, fallback: str = "") -> str:
        """Normalizes feed text values and strips embedded HTML."""
        if value is None:
            return fallback
        raw = str(value).strip()
        if not raw:
            return fallback
        unescaped = html.unescape(raw)
        cleaned = BeautifulSoup(unescaped, "html.parser").get_text(" ", strip=True)
        return cleaned or fallback

    def _normalize_published(self, entry: Any) -> str:
        """Returns an ISO 8601 timestamp where possible for easier time-series analysis."""
        parsed = getattr(entry, 'published_parsed', None)
        if parsed:
            try:
                dt = datetime.datetime(*parsed[:6], tzinfo=datetime.timezone.utc)
                return dt.isoformat()
            except Exception:
                pass

        updated_parsed = getattr(entry, 'updated_parsed', None)
        if updated_parsed:
            try:
                dt = datetime.datetime(*updated_parsed[:6], tzinfo=datetime.timezone.utc)
                return dt.isoformat()
            except Exception:
                pass

        raw_published = self._clean_text(getattr(entry, 'published', ''), fallback='')
        if raw_published:
            try:
                normalized = datetime.datetime.fromisoformat(raw_published.replace('Z', '+00:00'))
                return normalized.isoformat()
            except ValueError:
                return raw_published

        return "No Date"

    def _fetch_feed_with_retries(self, url: str, max_retries: int = 4, timeout_seconds: int = 15) -> Optional[Any]:
        """Fetches a feed with retry/backoff to tolerate transient failures."""
        headers = {
            "User-Agent": "StudentMediaFeedsBot/1.0 (+https://github.com/)"
        }

        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=timeout_seconds, headers=headers)
                response.raise_for_status()
                return feedparser.parse(response.content)
            except requests.exceptions.RequestException as e:
                wait_time = (2 ** attempt) + (random.randint(0, 500) / 1000)
                last_try = attempt == max_retries - 1
                if last_try:
                    logging.error("Failed to fetch %s after %s attempts: %s", url, max_retries, e)
                    return None
                logging.warning(
                    "Feed fetch failed for %s (attempt %s/%s): %s. Retrying in %.2fs",
                    url,
                    attempt + 1,
                    max_retries,
                    e,
                    wait_time,
                )
                time.sleep(wait_time)
        return None

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[A-Za-z][A-Za-z\-']+", text.lower())

    def _extract_keywords(self, text: str, max_keywords: int = 5) -> str:
        """Extracts lightweight keywords for dashboard filters and quick trend analysis."""
        tokens = self._tokenize(text)
        candidates = [t for t in tokens if len(t) >= 4 and t not in STOPWORDS]
        if not candidates:
            return ""
        counts = Counter(candidates)
        ranked = [word for word, _ in counts.most_common(max_keywords)]
        return " | ".join(ranked)

    def _score_sentiment(self, text: str) -> tuple[str, float]:
        """Returns a simple lexicon-based sentiment label and score in [-1, 1]."""
        tokens = self._tokenize(text)
        if not tokens:
            return "neutral", 0.0

        positive_hits = sum(1 for t in tokens if t in POSITIVE_WORDS)
        negative_hits = sum(1 for t in tokens if t in NEGATIVE_WORDS)
        raw_score = (positive_hits - negative_hits) / max(1, len(tokens))
        score = max(-1.0, min(1.0, round(raw_score, 4)))

        if score > 0.05:
            return "positive", score
        if score < -0.05:
            return "negative", score
        return "neutral", score

    def _enrich_story_metadata(self, title: str, summary: str = "") -> dict:
        """Builds keyword and sentiment metadata used by analytics and UI filters."""
        combined_text = " ".join([title.strip(), summary.strip()]).strip()
        sentiment_label, sentiment_score = self._score_sentiment(combined_text)
        return {
            "keywords": self._extract_keywords(combined_text),
            "sentiment_label": sentiment_label,
            "sentiment_score": f"{sentiment_score:.4f}",
        }

    def enrich_missing_metadata(self) -> None:
        """Backfills keyword/sentiment metadata for rows that are missing analytics fields."""
        if not os.path.exists(self.output_file):
            return

        with open(self.output_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        updated = 0
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for row in rows:
            row_changed = False

            title = self._clean_text(row.get("title", ""), fallback="")
            if not title:
                row["title"] = "No Title"
                title = "No Title"
                row_changed = True

            captured_at = (row.get("captured_at") or "").strip()
            if not captured_at:
                row["captured_at"] = now_utc
                row_changed = True

            keywords = (row.get("keywords") or "").strip()
            sentiment_label = (row.get("sentiment_label") or "").strip().lower()
            sentiment_score = (row.get("sentiment_score") or "").strip()
            if not (keywords and sentiment_label in {"positive", "neutral", "negative"} and sentiment_score):
                enrichment = self._enrich_story_metadata(title)
                row.update(enrichment)
                row_changed = True

            if row_changed:
                updated += 1

        if updated > 0:
            normalized_rows = [{h: row.get(h, "") for h in self.headers} for row in rows]
            self._write_rows_atomic(normalized_rows)
            logging.info("Backfilled analytics metadata for %s existing stories.", updated)

    def _write_rows_atomic(self, rows: List[dict]) -> None:
        """Writes the full dataset using a temp file then atomically replaces the target."""
        temp_path = f"{self.output_file}.tmp"
        with open(temp_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.headers)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_path, self.output_file)

    def _append_rows_atomic(self, rows_to_append: List[dict]) -> None:
        """Appends rows by rebuilding and atomically replacing the CSV file."""
        if not rows_to_append:
            return

        existing_rows: List[dict] = []
        if os.path.exists(self.output_file):
            with open(self.output_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_rows.append({h: row.get(h, "") for h in self.headers})

        combined = existing_rows + [{h: row.get(h, "") for h in self.headers} for row in rows_to_append]
        self._write_rows_atomic(combined)

    def get_existing_links(self) -> Set[str]:
        """Reads the CSV to get a set of already saved links to avoid duplicates."""
        links = set()
        if os.path.exists(self.output_file):
            with open(self.output_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    link = row.get('link', '').strip()
                    if link:
                        links.add(link)
        return links

    def parse_opml(self, opml_path: str) -> List[str]:
        """Extracts RSS URLs from an OPML file."""
        logging.info(f"Parsing OPML file: {opml_path}")
        try:
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

    def tag_stories_with_bertopic(self):
        """
        Uses BERTopic to cluster headlines into themes locally.
        This follows the 'Quick Start' pattern: fit_transform then map back to CSV.
        """
        if not os.path.exists(self.output_file):
            return

        # Load data into Pandas for easier manipulation
        df = pd.read_csv(self.output_file)
        
        # Ensure 'theme' column exists
        if 'theme' not in df.columns:
            df['theme'] = ""

        # Use all titles for training the model
        # Ensure no NaN/float values are passed to the embedding model
        df['title'] = df['title'].fillna("").astype(str)
        valid_mask = df['title'].str.strip().astype(bool)
        docs = df.loc[valid_mask, 'title'].tolist()
        
        logging.info(f"Starting local BERTopic analysis on {len(docs)} headlines...")
        
        try:
            # Initialize BERTopic with KeyBERTInspired representation for better topic labels
            topic_model = BERTopic(
                language="english",
                calculate_probabilities=False,
                representation_model=KeyBERTInspired()
            )
            
            # Fit the model and extract topics
            topics, probs = topic_model.fit_transform(docs)
            
            # Create a mapping of Topic ID to a readable label
            topic_labels = {}
            def is_valid_topic_id(t):
                if t is None:
                    return False
                if isinstance(t, float) and math.isnan(t):
                    return False
                return True

            topic_ids = sorted(set([t for t in topics if is_valid_topic_id(t)]))
            for topic_id in topic_ids:
                if topic_id == -1:
                    topic_labels[topic_id] = "Unclassified"
                else:
                    try:
                        topic_words = topic_model.get_topic(topic_id)
                        words = []
                        if topic_words:
                            for w in topic_words[:5]:
                                if isinstance(w, (list, tuple)) and len(w) > 0:
                                    word_str = str(w[0]).strip()
                                else:
                                    word_str = str(w).strip()

                                if word_str and not word_str.replace('.', '', 1).isdigit():
                                    words.append(word_str)
                        if words:
                            label = " | ".join([str(w) for w in words])
                            topic_labels[topic_id] = label.title()
                        else:
                            topic_labels[topic_id] = f"Topic {topic_id}"
                    except Exception as label_error:
                        logging.warning(f"Could not create label for topic {topic_id}: {label_error}")
                        topic_labels[topic_id] = f"Topic {topic_id}"

            # Print all possible topics
            possible_topics = sorted(set(topic_labels.values()))
            print("Possible topics:", possible_topics)

            # Map the results back to the dataframe
            df.loc[valid_mask, 'theme'] = [topic_labels.get(t, "Unclassified") for t in topics]
            
            # Save back to CSV
            df.to_csv(self.output_file, index=False)
            num_themes = len([t for t in topic_labels.keys() if t != -1])
            logging.info(f"Local tagging complete. Identified {num_themes} themes.")
            
        except Exception as e:
            logging.exception(f"BERTopic tagging failed: {e}")

    def tag_stories_with_ai(self, api_key: str):
        """
        Reads the CSV, finds untagged stories, uses Gemini to categorize them,
        and saves the updated data back to the CSV incrementally.
        """
        if not os.path.exists(self.output_file) or not api_key:
            return

        rows = []
        with open(self.output_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        untagged = [r for r in rows if not r.get('theme')]
        if not untagged:
            logging.info("All stories already have themes.")
            return

        logging.info(f"Found {len(untagged)} untagged stories out of {len(rows)} total.")
        
        # --- Diverse Sampling Logic ---
        sample_size = 300
        step = max(1, len(rows) // sample_size)
        sampled_rows = rows[::step][:sample_size]
        sample_text = "\n".join([r['title'] for r in sampled_rows])
        
        # Determine Themes
        theme_prompt = f"Identify 8-10 broad news themes for these headlines. Return ONLY JSON: {{\"themes\": [\"Tech\", \"Politics\", \"Health\", \"Finance\", ...]}}. Headlines:\n{sample_text}"
        
        try:
            def call_gemini(prompt, max_retries=5):
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={api_key}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                
                for attempt in range(max_retries):
                    try:
                        res = requests.post(url, json=payload, timeout=30)
                        res.raise_for_status()
                        res_json = res.json()
                        text = res_json['candidates'][0]['content']['parts'][0]['text']
                        clean_text = text.replace('```json', '').replace('```', '').strip()
                        return json.loads(clean_text)
                    except requests.exceptions.HTTPError as e:
                        status_code = e.response.status_code
                        if status_code in [429, 500, 503]:
                            wait_time = (2 ** attempt) + (random.randint(0, 1000) / 1000)
                            logging.warning(f"API Error {status_code}. Retrying in {wait_time:.2f}s... (Attempt {attempt+1}/{max_retries})")
                            time.sleep(wait_time)
                        else:
                            raise e
                    except (json.JSONDecodeError, KeyError) as e:
                        logging.error(f"Failed to parse AI response: {e}")
                        if attempt == max_retries - 1: raise e
                        time.sleep(2)
                return None

            themes_json = call_gemini(theme_prompt)
            if not themes_json: return
            
            theme_labels = ", ".join(themes_json['themes'])
            logging.info(f"Target Themes: {theme_labels}")

            batch_size = 25
            total_batches = (len(untagged) + batch_size - 1) // batch_size
            
            for i in range(0, len(untagged), batch_size):
                batch = untagged[i:i+batch_size]
                batch_text = "\n".join([f"{idx}: {r['title']}" for idx, r in enumerate(batch)])
                cat_prompt = f"Categorize these headlines into one of these themes: {theme_labels}. Return ONLY JSON: {{\"mapping\": [{{ \"id\": 0, \"theme\": \"Label\" }}, ...]}}. Headlines:\n{batch_text}"
                
                try:
                    mapping_json = call_gemini(cat_prompt)
                    if mapping_json and 'mapping' in mapping_json:
                        for item in mapping_json['mapping']:
                            try:
                                idx = int(item['id'])
                                if idx < len(batch):
                                    batch[idx]['theme'] = item['theme']
                            except (ValueError, KeyError, TypeError):
                                continue

                    normalized_rows = [{h: row.get(h, "") for h in self.headers} for row in rows]
                    self._write_rows_atomic(normalized_rows)
                    
                    logging.info(f"Successfully processed batch {i // batch_size + 1}/{total_batches}")
                    time.sleep(2)
                    
                except Exception as batch_error:
                    logging.error(f"Error in batch {i // batch_size + 1}: {batch_error}")
                    time.sleep(5)

            logging.info("AI Tagging process finished.")

        except Exception as e:
            logging.error(f"Thematic analysis failed: {e}")

    def fetch_stories(self, feed_urls: List[str]):
        """Fetches stories from RSS feeds and saves new ones."""
        existing_links = self.get_existing_links()
        captured_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        new_stories = []
        processed_feeds = 0
        failed_feeds = 0

        for url in feed_urls:
            start = time.time()
            logging.info("Fetching: %s", url)
            try:
                feed = self._fetch_feed_with_retries(url)
                if feed is None:
                    failed_feeds += 1
                    continue

                processed_feeds += 1
                feed_story_count = 0
                for entry in feed.entries:
                    link = getattr(entry, 'link', '')
                    if not link or link in existing_links:
                        continue

                    cleaned_title = self._clean_text(getattr(entry, 'title', 'No Title'), fallback='No Title')
                    cleaned_summary = self._clean_text(
                        getattr(entry, 'summary', getattr(entry, 'description', '')),
                        fallback='',
                    )
                    enrichment = self._enrich_story_metadata(cleaned_title, cleaned_summary)
                    
                    new_stories.append({
                        "source": self._clean_text(feed.feed.get('title', url), fallback=url),
                        "title": cleaned_title,
                        "link": link,
                        "published": self._normalize_published(entry),
                        "captured_at": captured_at,
                        "theme": "",
                        "keywords": enrichment["keywords"],
                        "sentiment_label": enrichment["sentiment_label"],
                        "sentiment_score": enrichment["sentiment_score"],
                    })
                    existing_links.add(link)
                    feed_story_count += 1

                duration = time.time() - start
                logging.info(
                    "Feed complete: %s | new_entries=%s | total_entries=%s | duration=%.2fs",
                    url,
                    feed_story_count,
                    len(getattr(feed, 'entries', [])),
                    duration,
                )

                if getattr(feed, 'bozo', 0):
                    logging.warning("Feed parser reported bozo feed for %s: %s", url, getattr(feed, 'bozo_exception', 'unknown parse issue'))
            except Exception as e:
                failed_feeds += 1
                logging.error("Failed to process %s: %s", url, e)

        if new_stories:
            self._append_rows_atomic(new_stories)
            logging.info("Added %s new stories.", len(new_stories))

        logging.info(
            "Feed run summary | total_feeds=%s | successful_feeds=%s | failed_feeds=%s | new_stories=%s",
            len(feed_urls),
            processed_feeds,
            failed_feeds,
            len(new_stories),
        )

def run_daily_update():
    DATABASE = "news_database.csv"
    pipeline = NewsPipeline(DATABASE)

    all_feeds = []
    
    # Check OPML files
    if os.path.exists("feeds.opml"):
        all_feeds.extend(pipeline.parse_opml("feeds.opml"))
    
    # Check text list
    if os.path.exists("discovered_feeds.txt"):
        all_feeds.extend(pipeline.parse_url_list("discovered_feeds.txt"))

    unique_feeds = list(set(all_feeds))

    if unique_feeds:
        pipeline.fetch_stories(unique_feeds)
        pipeline.enrich_missing_metadata()
        
        # Using BERTopic for local, rate-limit-free thematic analysis
        pipeline.tag_stories_with_bertopic()
        
        # Commented out AI tagging to avoid rate limits
        # api_key = os.environ.get("GEMINI_API_KEY")
        # if api_key:
        #     pipeline.tag_stories_with_ai(api_key)
    else:
        logging.error("No feeds found to process.")

    # Generate analytics report for dashboard
    try:
        from analytics import AnalyticsEngine
        analytics = AnalyticsEngine(DATABASE)
        analytics.run()
        logging.info("Analytics report generated successfully.")
    except Exception as e:
        logging.error("Failed to generate analytics report: %s", e)

if __name__ == "__main__":
    run_daily_update()