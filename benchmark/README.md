# Scraper comparison lists

Website URLs for benchmarking this repo's collection pipeline against another
scraper. Derived from the monitored feed lists and from the domains that actually
appear in `news_database.csv` at the 2026-06-26 snapshot.

## What to send

| File | Rows | Use |
|---|---|---|
| `sites_productive.txt` | 903 | **Send this one for a head-to-head run.** Sites we have confirmed produce stories, so any miss is the scraper's, not a dead site. |
| `sites_all.txt` | 1,003 | The full monitored set, including sites that never returned anything. Use to compare *discovery* — how many dead or hard sites each tool can still pull from. |
| `sites_productive.csv` | 903 | Same as the `.txt` plus publication name and our story count per site. This is the scorecard; keep it on our side rather than sending it, so his run isn't anchored to our numbers. |

These are **site URLs** (`https://dailyorange.com`), not the RSS feed URLs this
repo consumes internally. If his tool discovers its own feeds, site URLs are the
correct input. If it wants feeds directly, send the raw `feeds_*.txt` lists
instead — but then the comparison only covers extraction, not feed discovery.

## Making the comparison fair

Our 15,074 stories were accumulated over 143 days of nightly runs (2026-02-03 to
2026-06-26). A single run of his scraper against these URLs will collect roughly
what one RSS window exposes — about 10 items per site. Comparing his one-shot
total against our cumulative total measures elapsed collection time, not scraper
quality.

Compare on rates instead:

- **Site reach** — of 903 known-good sites, how many yield at least one story?
- **Extraction success** — of stories found, what share have usable body text?
  Ours is 98.1% (283 failures out of 15,074), dominated by HTTP 403 and 429.
- **Text quality per story** — median words extracted for the same URL. Our
  median is 596 words. Boilerplate contamination is the thing to check: 1.2% of
  our documents carry cookie-consent text that survived extraction.
- **Cost per story** — wall-clock and requests per successfully extracted story.

The cleanest single test: pick 100 sites at random from `sites_productive.txt`,
run both tools on the same day, and compare stories found and median extracted
word count on the URLs both tools reached.

## Regenerating

These lists are a snapshot. Rebuild with the script that produced them
(`build_url_lists.py`, kept with the analysis scratch files) after the feed lists
or database change.
