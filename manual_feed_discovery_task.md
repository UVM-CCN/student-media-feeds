# Manual RSS Feed Discovery Task

## Background

We maintain a database of stories published by U.S. student journalism outlets. New stories are pulled in automatically each night from each outlet's RSS feed. We have a script that tries to discover RSS feeds automatically by probing common URL patterns. It works for most outlets, but it failed for the 30 outlets listed below.

The failures come in two ways:

- **Discovery failures (29 outlets)** — We don't know where the feed is. These are mostly large, well-known student newspapers that definitely have RSS feeds, but their sites either use non-standard URLs or rate-limit our automated probe. **Your job: find the feed URL.**
- **Fetch failures (1 outlet)** — We already know the feed URL, but the site (Cloudflare or similar bot protection) blocks our scraper from accessing it. The URL probably loads fine when a real person visits it in a browser. **No task to do here.**

Both jobs use the same browser-based approach below. The verify-only outlet is in its own section at the end.

## What to deliver

For each outlet listed in the "Outlets to investigate" section below, fill in:

- **Feed URL** — the working RSS/Atom feed URL you found (or leave blank if none)
- **Status** — one of the codes from the "Status codes" section
- **Notes** — anything relevant (paywall, broken site, multiple feeds available, etc.)

You can edit this file directly, or copy the list into a spreadsheet — whichever is easier for you. Save your work and send the result back when done.

## How to find an RSS feed (in order of effort)

### 1. Look for an RSS link on the site

Visit the homepage. Scroll to the footer. Many sites link to their RSS feed there with a small icon or an "RSS" / "Subscribe" link. Also check the site's "About," "Help," or "Contact" pages.

### 2. View page source and search for "rss" or "atom"

This is the most reliable method. In Chrome/Firefox:

1. Right-click the homepage → **View Page Source** (or `Ctrl+U` / `Cmd+U`)
2. Search the source with `Ctrl+F` / `Cmd+F` for the word `rss`
3. You're looking for a line that looks like this in the page `<head>`:

   ```html
   <link rel="alternate" type="application/rss+xml" title="..." href="https://example.com/feed/" />
   ```

   The URL inside `href="..."` is the feed.

4. If `rss` returns nothing, search for `atom` — Atom is an alternative format that works the same way for our purposes:

   ```html
   <link rel="alternate" type="application/atom+xml" href="https://example.com/atom/" />
   ```

### 3. Try common URL patterns by hand

If view-source doesn't show anything, try appending each of these to the homepage URL in the browser:

- `/feed/`
- `/feed`
- `/rss`
- `/rss.xml`
- `/index.xml`
- `/?feed=rss2`

For sites that look like SNworks/TownNews platforms (often have a distinctive search bar with filters, common at large student dailies), try:

- `/search/?f=rss&t=article&l=50&s=start_time&sd=desc`
- `/search/?f=rss`

A working feed URL will load as XML in your browser (lots of `<item>` or `<entry>` tags). A broken one will be a 404 page or normal HTML.

### 4. Search the web

If nothing else works, try searching: `site:[outlet domain] rss` or `[outlet name] rss feed`. Sometimes the feed is documented on the outlet's own help page, on a third-party feed aggregator, or in old blog posts.

## How to verify a feed URL is real

Once you find a candidate URL, open it in the browser. You should see something like this (XML markup with `<item>` blocks containing article titles and links):

```xml
<rss version="2.0">
  <channel>
    <title>The Daily Example</title>
    <item>
      <title>Some Story Headline</title>
      <link>https://example.com/some-story</link>
      ...
    </item>
    ...
  </channel>
</rss>
```

If you see a 404 page, a login screen, an empty page, or normal HTML, it's **not** a valid feed.

## Status codes

Use exactly one of these for each outlet:

| Code | Meaning |
|---|---|
| `FOUND` | Feed URL located, loads as valid XML in a browser |
| `FOUND_BOT_BLOCKED` | Feed URL loads in a browser, but you see a Cloudflare check, captcha, or similar bot-protection step. The feed is real; the issue is that automated tools may not be able to fetch it. Mention what kind of block you saw in the notes. |
| `NO_FEED` | Site exists but offers no RSS feed at all |
| `PAYWALLED` | Feed exists but requires login or subscription to access |
| `BROKEN_URL` | The homepage URL listed below doesn't load at all |
| `UNCLEAR` | Found something that might be a feed but you're not sure — leave it for review |

## Examples of valid feeds in our existing dataset

To get a feel for what the answer looks like, here are real feeds we already use:

- **WordPress-style** (most common): `https://dailyorange.com/feed/`
- **SNworks/TownNews-style**: `https://www.thedaonline.com/search/?f=rss&t=article&l=50&s=start_time&sd=desc`
- **Custom path**: `https://universe.byu.edu/index.rss`
- **Direct .xml file**: `https://wisconsinwatch.org/feed/`

## Tips and gotchas

- **Skip "comments" feeds**: WordPress sites often expose a `/comments/feed/` URL. This is for blog comments, not articles. We don't want it.
- **Prefer the main feed over category-specific feeds**: If you find feeds like `/news/feed/` and `/sports/feed/`, the broader `/feed/` is usually best. Note the others in the notes column.
- **Don't worry about Atom vs RSS**: Both work for our pipeline. If a site only offers Atom, use that.
- **If you find multiple feeds for one outlet**, list the best one in "Feed URL" and mention the others in "Notes".
- **Time-box yourself**: Most outlets should take under 5 minutes. If you've spent 10+ minutes on one site, mark it `UNCLEAR` and move on.

---

## Outlets to investigate

### Flagship student dailies (26)

#### 1. The Harvard Crimson
- Homepage: https://www.thecrimson.com
- Feed URL: 
- Status: 
- Notes: 

#### 2. The Yale Daily News
- Homepage: https://yaledailynews.com
- Feed URL: 
- Status: 
- Notes: 

#### 3. The Daily Pennsylvanian
- Homepage: https://www.thedp.com
- Feed URL: 
- Status: 
- Notes: 

#### 4. The Cornell Daily Sun
- Homepage: https://cornellsun.com
- Feed URL: 
- Status: 
- Notes: 

#### 5. The Daily Tar Heel (UNC)
- Homepage: https://www.dailytarheel.com
- Feed URL: 
- Status: 
- Notes: 

#### 6. The Independent Florida Alligator (UF)
- Homepage: https://www.alligator.org
- Feed URL: 
- Status: 
- Notes: 

#### 7. The Purdue Exponent
- Homepage: https://www.purdueexponent.org
- Feed URL: 
- Status: 
- Notes: 

#### 8. Daily Bruin (UCLA)
- Homepage: https://dailybruin.com
- Feed URL: 
- Status: 
- Notes: 

#### 9. Indiana Daily Student
- Homepage: https://www.idsnews.com
- Feed URL: 
- Status: 
- Notes: 

#### 10. The Daily Collegian (Penn State)
- Homepage: https://www.collegian.psu.edu
- Feed URL: 
- Status: 
- Notes: 

#### 11. The State News (Michigan State)
- Homepage: https://statenews.com
- Feed URL: 
- Status: 
- Notes: 

#### 12. The Daily Cardinal (Wisconsin)
- Homepage: https://www.dailycardinal.com
- Feed URL: 
- Status: 
- Notes: 

#### 13. The Shorthorn (UT Arlington)
- Homepage: https://www.theshorthorn.com
- Feed URL: 
- Status: 
- Notes: 

#### 14. The Duke Chronicle
- Homepage: https://www.dukechronicle.com
- Feed URL: 
- Status: 
- Notes: 

#### 15. The Johns Hopkins News-Letter
- Homepage: https://www.jhunewsletter.com
- Feed URL: 
- Status: 
- Notes: 

#### 16. The Dartmouth
- Homepage: https://www.thedartmouth.com
- Feed URL: 
- Status: 
- Notes: 

#### 17. The Emory Wheel
- Homepage: https://emorywheel.com
- Feed URL: 
- Status: 
- Notes: 

#### 18. Rice Thresher
- Homepage: https://ricethresher.org
- Feed URL: 
- Status: 
- Notes: 

#### 19. The Ball State Daily News
- Homepage: https://www.ballstatedailynews.com
- Feed URL: 
- Status: 
- Notes: 

#### 20. The Oklahoma Daily
- Homepage: https://oudaily.com
- Feed URL: 
- Status: 
- Notes: 

#### 21. The Daily Gamecock (South Carolina)
- Homepage: https://www.dailygamecock.com
- Feed URL: 
- Status: 
- Notes: 

#### 22. The Daily Kansan
- Homepage: https://www.dailykansan.com
- Feed URL: 
- Status: 
- Notes: 

#### 23. The Daily Nebraskan
- Homepage: https://www.dailynebraskan.com
- Feed URL: 
- Status: 
- Notes: 

#### 24. The Daily O'Collegian (Oklahoma State)
- Homepage: https://www.ocolly.com
- Feed URL: 
- Status: 
- Notes: 

#### 25. The Montana Kaimin
- Homepage: https://www.montanakaimin.com
- Feed URL: 
- Status: 
- Notes: 

#### 26. The FSView & Florida Flambeau (Florida State)
- Homepage: https://www.fsview.com
- Feed URL: 
- Status: 
- Notes: 

### News labs and capstone projects (3)

These are more research/capstone-focused outlets and may genuinely not have RSS feeds. If you confirm there's no feed, mark `NO_FEED` and move on.

#### 27. News21 (Arizona State / Cronkite)
- Homepage: https://news21.com/
- Feed URL: 
- Status: 
- Notes: 

#### 28. Missouri Business Alert (Missouri School of Journalism)
- Homepage: https://www.missouribusinessalert.com/
- Feed URL: 
- Status: 
- Notes: 

#### 29. Buffalo Sports Insider
- Homepage: http://www.buffalosportsinsider.com/
- Feed URL: 
- Status: 
- Notes: 

### Verify-only outlets (1)

For these outlets we already have the feed URL — our scraper just gets blocked when it tries to fetch it. **You don't need to find a new URL.** Open the "Suspected feed URL" in a browser and tell us:

- Does it load valid XML content (lots of `<item>` blocks)? → `FOUND`
- Does it load XML, but only after passing a Cloudflare check / captcha / "verify you are human" step? → `FOUND_BOT_BLOCKED` and describe what you saw in the notes
- Does it not load at all, or load something other than a feed? → `BROKEN_URL` or `NO_FEED`

#### 30. The Minnesota Daily (University of Minnesota)
- Homepage: https://mndaily.com
- Suspected feed URL: https://mndaily.com/feed/
- Status: 
- Notes (what happened when you visited the suspected feed URL?): 
