import csv
import os
import datetime
import logging
import json
import math
import time
import random
from typing import List, Set

import feedparser
import listparser
import requests

# Note: You will need to install these for the new function:
# pip install bertopic pandas
try:
    from bertopic import BERTopic
    import pandas as pd
except ImportError:
    logging.warning("BERTopic or Pandas not installed. Local tagging will not work.")

# Configure logging to track the pipeline progress
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class NewsPipeline:
    def __init__(self, output_file: str = "news_database.csv"):
        self.output_file = output_file
        # Standardized headers
        self.headers = ["source", "title", "link", "published", "captured_at", "theme"]
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
            # Initialize BERTopic
            # 'language="english"' uses a default SBERT model
            # 'calculate_probabilities=False' speeds up processing
            topic_model = BERTopic(language="english", calculate_probabilities=False)
            
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
                    
                    with open(self.output_file, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=self.headers)
                        writer.writeheader()
                        writer.writerows(rows)
                    
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
        captured_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_stories = []

        for url in feed_urls:
            logging.info(f"Fetching: {url}")
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    link = getattr(entry, 'link', '')
                    if not link or link in existing_links:
                        continue
                    
                    new_stories.append({
                        "source": feed.feed.get('title', url),
                        "title": getattr(entry, 'title', 'No Title'),
                        "link": link,
                        "published": getattr(entry, 'published', 'No Date'),
                        "captured_at": captured_at,
                        "theme": ""
                    })
                    existing_links.add(link)
            except Exception as e:
                logging.error(f"Failed to fetch {url}: {e}")

        if new_stories:
            with open(self.output_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.headers)
                writer.writerows(new_stories)
            logging.info(f"Added {len(new_stories)} new stories.")

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
        
        # Using BERTopic for local, rate-limit-free thematic analysis
        pipeline.tag_stories_with_bertopic()
        
        # Commented out AI tagging to avoid rate limits
        # api_key = os.environ.get("GEMINI_API_KEY")
        # if api_key:
        #     pipeline.tag_stories_with_ai(api_key)
    else:
        logging.error("No feeds found to process.")

if __name__ == "__main__":
    run_daily_update()