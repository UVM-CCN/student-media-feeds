import logging
import urllib.parse
import requests
import feedparser
import os
import pandas as pd
from bs4 import BeautifulSoup
from typing import List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def is_valid_feed(url: str) -> bool:
    """Checks if a URL is a direct, valid RSS/Atom feed."""
    try:
        feed = feedparser.parse(url)
        return len(feed.entries) > 0
    except:
        return False

def discover_feeds_from_url(url: str) -> List[str]:
    """
    Scans a website's HTML head for RSS/Atom feed links.
    """
    discovered = []
    headers = {'User-Agent': 'Mozilla/5.0 (NewsPipeline Discoverer)'}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        feed_types = [
            'application/rss+xml', 
            'application/atom+xml', 
            'application/rdf+xml', 
            'text/xml'
        ]
        
        # Search for <link rel="alternate"> tags
        links = soup.find_all('link', rel='alternate')
        for link in links:
            if link.get('type') in feed_types:
                href = link.get('href')
                if href:
                    full_url = urllib.parse.urljoin(url, href)
                    discovered.append(full_url)
        
    except Exception as e:
        logging.error(f"Discovery failed for {url}: {e}")
        
    return list(set(discovered)) # Return unique discovered feeds

def update_static_feed_list_from_csv(csv_path: str, url_column: str, storage_path: str):
    """
    Reads a CSV using pandas, extracts URLs from a specific column, 
    finds their feeds, and appends unique new feeds to a static text file.
    """
    if not os.path.exists(csv_path):
        logging.error(f"CSV file not found: {csv_path}")
        return

    try:
        df = pd.read_csv(csv_path)
        if url_column not in df.columns:
            logging.error(f"Column '{url_column}' not found in {csv_path}")
            return
        
        # Get list of URLs, dropping any empty values
        source_urls = df[url_column].dropna().unique().tolist()
        logging.info(f"Loaded {len(source_urls)} unique URLs from {csv_path}")
        
    except Exception as e:
        logging.error(f"Error reading CSV with pandas: {e}")
        return

    existing_feeds = set()
    if os.path.exists(storage_path):
        with open(storage_path, 'r') as f:
            existing_feeds = {line.strip() for line in f if line.strip()}

    newly_found = []
    for url in source_urls:
        # Ensure url is a string
        url = str(url).strip()
        if not url.startswith('http'):
            continue

        logging.info(f"Checking {url}...")
        
        # If it's already a feed, use it
        if is_valid_feed(url):
            if url not in existing_feeds:
                newly_found.append(url)
        else:
            # Otherwise, try to discover feeds on the page
            feeds = discover_feeds_from_url(url)
            for f in feeds:
                if f not in existing_feeds:
                    newly_found.append(f)
    
    if newly_found:
        with open(storage_path, 'a') as f:
            for feed in newly_found:
                f.write(f"{feed}\n")
        logging.info(f"Added {len(newly_found)} new feeds to {storage_path}")
    else:
        logging.info("No new feeds discovered.")

if __name__ == "__main__":
    import sys
    # Example usage: python feed_discoverer.py my_data.csv url_col_name
    # python feed_discoverer.py ccn_nap_master.csv URL
    if len(sys.argv) > 2:
        csv_file = sys.argv[1]
        col_name = sys.argv[2]
        update_static_feed_list_from_csv(csv_file, col_name, "discovered_feeds.txt")
    elif len(sys.argv) == 2:
        target_url = sys.argv[1]
        print(f"Discovering feeds for: {target_url}")
        print(discover_feeds_from_url(target_url))