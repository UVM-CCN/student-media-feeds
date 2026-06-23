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