# Improvements to make

*below generated with Claude on June 16 after feeding it methodology from Local Journalism Index 2026 report. no action has been taken yet*

1. Biggest change: classify clusters, not individual stories
This is the single most important technique to borrow. Their workflow is:

Run topic modeling first → get a few hundred clusters of similar stories
For each cluster, send Claude the top keywords + a sample of headlines → assign one CIN + IPTC label to the whole cluster
Propagate the cluster's label down to every story in it
You already have BERTopic running. Your current pipeline produces ~30 clusters per nightly run. The intern plan I drafted earlier had Intern A making ~3,000 individual API calls for classification — that's the wrong approach. Instead:

Run BERTopic on the full corpus to produce stable clusters
Make ~30–100 API calls (one per cluster) to label them
Each story inherits its cluster's CIN category
Why this matters: cheaper, faster, and more consistent — Muck Rack's argument is that classifying related articles together produces fewer disagreements than classifying each in isolation. Worth quoting directly in your methods section.

For Intern A, this changes the work significantly. Instead of "build a classifier and validate on 200 hand-coded stories," it becomes "run BERTopic, build a cluster-labeling pipeline, validate cluster assignments against hand-coded ground truth." Lighter implementation lift, more sophisticated analytical thinking.

2. Add IPTC as a second classification framework
You're planning CIN-only. Muck Rack uses CIN and IPTC topic codes (the wire-service standard: politics, sport, crime, health, etc.) and explicitly explains why: they answer different questions. CIN asks "what does the community need to know?" IPTC asks "what's this story about?"

Why add it:

Your results become directly comparable to Muck Rack's 4.2M-article baseline. That's an enormous comparative dataset for "are student journalists covering the same things commercial local journalists are?"
IPTC has a documented hierarchy you can lift wholesale — no codebook work required
The classification pass is the same cluster-level pipeline; you're just asking Claude for two labels per cluster instead of one
Add IPTC to Intern A's deliverable. Their codebook then has two sections, one per framework.

3. Use the first 200 words, not the full article
This is counterintuitive given you just built the full-text extractor, but it's the right call. Muck Rack explicitly chose 200 words because:

It standardizes input length across very short and very long articles
The lede + nut graf is where geographic and topical signal is densest
It controls API costs (rough math: 3,000 stories × full text ≈ a lot more tokens than 3,000 × 200 words)
Longer text adds noise (later paragraphs often drift into tangents and background)
You don't need to change the extraction layer — fetch_full_text.py should keep storing the whole article. But the classifier input should be the first ~200 words, with the rest reserved for future analyses that need the full text (sentiment over the arc of the article, quote extraction, etc.).

This is a one-line change in the classification script: text = body.split()[:200] before sending to Claude.

4. Two-method locality test instead of single-method scope classification
I'd previously suggested replacing your local/state/national binary with "geographic relevancy." Muck Rack goes further — they use two independent locality tests and only count an article as "strong local signal" if both agree:

NER-based: extract place names from the headline, check if they resolve to the outlet's home county/state
Orientation-based: classify the article's overall geographic orientation (local/state/national/international) based on the mix of place references throughout
This is conservative — only 4.3% of their 4.2M articles passed both tests. For student journalism your pass rate will be much higher (most stories are inherently campus-local), but the structure is still useful:

You can distinguish strong local (both tests agree) from weak local (only one method flags it) in your data
Articles that don't pass either are clearly not local journalism — they're aggregated/national content
You can report both numbers, like Muck Rack does
This makes Intern B's outlet registry work load-bearing for a specific methodological purpose: it's what the NER test resolves against.

5. Filter wire/syndicated content before analysis
Muck Rack removes AP/Reuters content before running the locality test. For student journalism this is probably a smaller fraction than commercial local news, but worth doing:

Look for bylines containing "Associated Press", "Reuters", "AP", "via [wire service]"
Look for stories where the source/byline doesn't match the publication name
Add a is_syndicated boolean column
For your research framing — "are student journalists covering local issues?" — wire content directly undermines the answer. Strip it.

6. Confidence scores on every classification
This is a standard practice they explicitly mention: each cluster-level classification comes with a confidence rating from Claude. Add a classification_confidence column. This lets the interns:

Filter analyses to high-confidence subset for the headline findings
Report low-confidence cases as a known limitation
Identify clusters where the LLM struggled — often a signal that the cluster is heterogeneous and BERTopic should be re-tuned
Simple prompt pattern: ask Claude to return { "category": "...", "confidence": "high|medium|low", "reasoning": "..." }.

7. Keyword fallback layer for low-confidence cases
This is the third stage of their pipeline. For any cluster Claude couldn't confidently classify, check it against a curated keyword list per category. Example:


CIN_KEYWORDS = {
    "transportation": ["transit", "bus", "road", "highway", "commute", "traffic", ...],
    "education": ["school", "teacher", "curriculum", "school board", ...],
    ...
}
You probably already have something like this in scrape.py for the simple keyword extraction. Repurpose those term lists.

This is also a good Intern A task — building the keyword lists per category requires reading the codebook and understanding what each CIN actually covers.

8. Frame results as "floors, not ceilings"
Lift their language directly. In any writeup:

"All topical shares should be read as floors rather than ceilings: the true share of any named category might be higher than reported. We treat the distributions as indicators of structural patterns rather than precise measurements."

This is the right epistemological posture for automated content analysis and protects you from overclaiming.

What this means for the intern plan
The revised division of work:

Intern A: Content Classifier

Build cluster-level classifier (not story-level)
Two frameworks: CIN + IPTC
Confidence ratings + keyword fallback
Validate on 200 hand-coded stories at the story level (since clusters get propagated)
Input is first 200 words of full text
Intern B: Data Analyst + Locality

Build the outlet registry (county, state, FIPS)
Build the NER-based locality test (using spaCy en_core_web_sm for place extraction)
Filter syndicated content
Cross-tabulate CIN/IPTC × locality × news desert status
Produce the publication-level vector analysis your colleague wants
These two pieces compose cleanly: Intern A produces a cin_category + iptc_category + confidence per story, Intern B produces a locality_strong boolean and outlet geography, and the joint analysis is the research deliverable.

One adaptation for student journalism specifically
Muck Rack's locality test treats "town in this county" as local and everything else as not. For student journalism, the geography has finer structure:

Campus: events within the university (clubs, sports, internal policy)
Town/host community: city where the campus lives (Burlington for UVM)
County/region: broader community served
State: state-level policy/politics
National: federal politics, national trends
A pure two-method county-level test would collapse "campus" and "town" together as "local," which loses an important distinction for your research question. Your locality classifier should ideally distinguish at least campus from off-campus local. That's a small extension to Muck Rack's approach but matters for the news desert framing — if 90% of a student paper's "local" stories are actually about campus dining hall renovations, that doesn't fill a community information need.

Worth adding to the codebook before Intern A starts.

*Below suggesrtions from Claude on Aug 18, 2026 after comparing benchmark results from Mizzou News Crawler answering question "should i switch to Mizzou Crawler code instead of writing my own?*

Should you switch? No — but don't ignore it either.
Against adopting it wholesale:

Its design center is the cloud deployment. GKE, Cloud SQL, Argo, Artifact Registry, Firestore, BigQuery, and a paid proxy provider. There's a SQLite/docker-compose local mode, but it's a dev convenience, not the supported path. That's a monthly bill and an ops load for a one-person project.
AGPL-3.0-or-later. Fine if you stay open, but if you ever serve your map or an API from a fork, §13 obliges you to offer source to network users — and you can't vendor pieces into a permissively licensed repo.
The data model is wrong for you. It's source-centric around a curated commercial-publisher list. Remapping to student media is real work, and you'd be throwing away assets — feed lists, outlet directory, corpus, map — that it has no equivalent for.
What I'd actually do, in priority order:

Adopt the CIN taxonomy to replace theme and the BEATS lexicon — ideally their fine-tuned model. Cheapest large win, and it makes your data comparable to theirs and to the published literature.
Archive raw HTML now. Every day you don't is a day that's permanently un-re-extractable. Local gzipped files, no GCS needed.
Extend sitemap discovery to all sources, not just the hard-outlet list. This is what lifts the RSS-window ceiling.
Add the cascade + per-host selector registry, and start capturing byline and a parsed publish date.
Move news_database.csv to SQLite with a status column; keep the CSV as an export. You're committing 5.8MB of churn nightly and rewriting the whole file each run — that's what breaks first.
Cheap wire detection: headline-duplication within your own corpus, no API required. It directly threatens any claim about student-produced coverage.
Talk to them. Your benchmark/README.md reads like a head-to-head is already in motion. They're multi-dataset by design, AGPL, with CITATION.cff and CONTRIBUTING.md — contributing your student-media source list as a dataset to their system may beat both forking and going it alone, and would get you their extraction and wire-detection stack for free on your outlets.

## Comparison with Mizzou News Crawler

*chat with Claude on Aug 12, 2026*

I cloned it and read through both. Here's the comparison.

What they are, in one line
MizzouNewsCrawler is a production cloud system for the local-news-desert research question (University of Missouri / LocalNewsImpact, AGPL-3.0): 657 Python files, Postgres + 52 Alembic migrations, 6 Docker images, GKE + Argo CronWorkflows, BigQuery via Datastream CDC, FastAPI + React frontend, 142 test directories, 16 CI workflows. Yours is a single-machine research pipeline: 8 scripts, CSV storage, one nightly GitHub Action, whole corpus committed to git. Those are different categories of thing, which matters for the "should I switch" question.

Features they have that you don't
1. Discovery that isn't RSS-bound. src/crawler/discovery.py is 4,300 lines: RSS, sitemaps, homepage feed sniffing, section-URL discovery, section inference from article URLs, newspaper4k link harvesting, and StorySniffer (a trained skops classifier) to decide whether a discovered URL is even an article. You do sitemap + WordPress API only in fetch_hard_outlets.py, for a hand-curated list where 14 outlets are marked "cascade failed 2026-06-22". This is the single biggest functional gap: your own benchmark/README.md notes 15,074 stories took 143 days of nightly runs because RSS exposes ~10 items per site. Sitemaps break that ceiling and let you backfill history you currently can't reach.

2. A candidate_links → articles state machine. Status lifecycle: discovered → verified → extracted → cleaned → labeled → entities, each stage a resumable queue. You have one CSV row per article and an extraction_status column.

3. An extraction cascade with a per-host selector registry. extractors.py: schema.org JSON-LD → per-host CSS selectors (src/lookups/site_specs.csv, parser_config.json) → newspaper4k → generic selectors → text fallback, with trafilatura/goose3/readability/boilerpy3 all available and a router that picks per domain. You call trafilatura.extract(favor_recall=True) once in fetch_full_text.py:180 and give up on failure.

4. Structured fields you don't capture at all. Byline (with telemetry recording whether it came from JSON-LD, page metadata, or body text), publish date parsed via htmldate/dateparser, lead image, language via py3langid. Your schema is source,title,link,published,... — no author, and published is whatever string the feed handed you.

5. Serious anti-bot infrastructure. cloudscraper, undetected-chromedriver, selenium-stealth, tls-client, browser fingerprint profiles, Decodo residential proxies plus two Squid fallbacks, and a Firestore-backed per-(proxy, domain) health router with exponential backoff shared across services. You have curl_cffi. Your 283 extraction failures "dominated by HTTP 403 and 429" are precisely what this exists to solve.

6. Automatic site health management. Per-host HTTP error breakdown, field-level extraction success by method, and auto-pause of sites above an ~80% error rate with a documented resume path. You have a 963KB log file.

7. Content cleaning as its own stage, with telemetry. You flagged that 1.2% of your documents carry surviving cookie-consent text — that's the missing stage. (Caveat: they have twelve content_cleaner_*.py variants. Take the idea, not the implementation.)

8. A real classifier on a published taxonomy. Fine-tuned BERT on Critical Information Needs — Civic Life, Civic Information, Emergencies & Public Safety, Health, Transportation, Sports, Environment & Planning, Education, Political Life, Economic Development. That is the FCC/Waldman framework the local-news literature uses. Your theme field is 42.9% Unclassified and clusters on institution names (you document this yourself), and your map's BEATS lexicon is a hand-rolled 10-topic keyword heuristic that happens to be almost the same shape as their label set.

9. Wire-service detection — src/services/wire_detection/. Two methods: MediaCloud API headline-duplication (does this headline appear across many outlets?) and geographic filtering (does the body mention places in the publisher's coverage area?). You have nothing here, and your corpus almost certainly counts syndicated AP/wire content as student-produced reporting.

10. Story-level geography, not newsroom-level. spaCy NER + rapidfuzz against an OSM-derived gazetteer, geocode cache, county reports — and sources/publinks.csv ships precomputed per-publisher gazetteers of schools, government, healthcare, businesses, landmarks. Your scripts/geocode_publications.py places the newsroom on the map; theirs places what the story is about. For a coverage map, theirs is the stronger claim.

11. Raw HTML archived at fetch time (raw_html_archive.py), so extractors can be compared on identical bytes and articles re-extracted without re-crawling. You'd have to re-fetch, which for bot-protected sites measures your proxy stack rather than your extractor.

12. Per-dataset isolation — Lehigh throttled 90–180s, Mizzou 5–15s, CAPTCHA backoff scoped per dataset. Multi-corpus by design (Mizzou, Lehigh, Minnesota WARC import, VTCNI).

13. LLM summarization pipeline with pluggable providers and vector stores. 14. Packaged as a citable research artifact (CITATION.cff, CONTRIBUTING.md, SECURITY.md, CoC).

What you have that they don't
The student-media domain itself. ~900 national student outlets, 1,660 monitored feeds, an outlet directory with coordinates, a corpus at 98.1% extraction success. Their source model is built around commercial local publishers with city/county/owner/frequency fields. Nothing in their repo covers your subject.
Zero infrastructure. Clone and run. No cloud bill, no kubectl, no SRE burden, and the corpus + HF dataset publishing ship in the repo.
A finished public-facing map. Topic × weighting modes, rescaling legend, comparable popup charts, and a headless test harness. Their web tier is internal review/telemetry UIs.
Better documentation hygiene, honestly. docs/PIPELINE.md has a "Two fields not to trust" section naming its own bad data. Their README is 80KB with dated "Recent Maintenance" sections, a START_HERE.md frozen on Oct 15 2025, and 142 committed .old files.
Should you switch? No — but don't ignore it either.
Against adopting it wholesale:

Its design center is the cloud deployment. GKE, Cloud SQL, Argo, Artifact Registry, Firestore, BigQuery, and a paid proxy provider. There's a SQLite/docker-compose local mode, but it's a dev convenience, not the supported path. That's a monthly bill and an ops load for a one-person project.
AGPL-3.0-or-later. Fine if you stay open, but if you ever serve your map or an API from a fork, §13 obliges you to offer source to network users — and you can't vendor pieces into a permissively licensed repo.
The data model is wrong for you. It's source-centric around a curated commercial-publisher list. Remapping to student media is real work, and you'd be throwing away assets — feed lists, outlet directory, corpus, map — that it has no equivalent for.
What I'd actually do, in priority order:

Adopt the CIN taxonomy to replace theme and the BEATS lexicon — ideally their fine-tuned model. Cheapest large win, and it makes your data comparable to theirs and to the published literature.
Archive raw HTML now. Every day you don't is a day that's permanently un-re-extractable. Local gzipped files, no GCS needed.
Extend sitemap discovery to all sources, not just the hard-outlet list. This is what lifts the RSS-window ceiling.
Add the cascade + per-host selector registry, and start capturing byline and a parsed publish date.
Move news_database.csv to SQLite with a status column; keep the CSV as an export. You're committing 5.8MB of churn nightly and rewriting the whole file each run — that's what breaks first.
Cheap wire detection: headline-duplication within your own corpus, no API required. It directly threatens any claim about student-produced coverage.
Talk to them. Your benchmark/README.md reads like a head-to-head is already in motion. They're multi-dataset by design, AGPL, with CITATION.cff and CONTRIBUTING.md — contributing your student-media source list as a dataset to their system may beat both forking and going it alone, and would get you their extraction and wire-detection stack for free on your outlets.