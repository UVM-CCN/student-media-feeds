# Coverage map

Interactive Leaflet heatmap of where topics are reported across US student
newsrooms. Open `map/index.html` directly in a browser — no server needed.

## Regenerating

```bash
python scripts/geocode_publications.py   # -> data/publication_locations.csv
python scripts/build_map_data.py         # -> map/map_data.js + map_data.json
```

Run both after the database grows. The first resolves coordinates, the second
classifies stories by topic and writes what the page reads. `map_data.js` is the
file the page loads — browsers block `fetch()` of local JSON over `file://`, so
the data ships as a script tag.

## Outlets are keyed by domain, not by name

Student papers reuse titles heavily. "The Observer" publishes at Fordham, Notre
Dame/Saint Mary's, Case Western, Illinois-Springfield, and Central Washington;
"The Echo" appears at six schools. 42 titles in the corpus span multiple
campuses, covering 1,584 stories.

Keying on the `source` name would collapse those onto a single point and place
the combined total at whichever campus matched first. Everything here — the
locations table, the map points, the popups — is therefore keyed by domain. The
popup shows the domain alongside the institution for the same reason.

## Where coordinates come from

Resolved in priority order, recorded per row in `data/publication_locations.csv`
under `match`:

| Method | Outlets | Source |
|---|---|---|
| `domain` | 837 | Outlet URL matched to `data/student-media-outlets.csv` or `ccn_nap_master.csv` |
| `override-institution` | 38 | `data/publication_institution_overrides.csv` names a host institution, whose coordinates come from the files above |
| `override-coords` | 9 | Explicit coordinates, for newsrooms with no host campus and for source-data corrections |
| `name` | 9 | Outlet name matched where the domain did not — only for titles unique within the corpus |
| `unresolved` | 10 | Left off the map |

Coverage: **893 of 903 outlets (98.9%)**, accounting for **14,972 of 15,073
stories (99.3%)**.

Overrides are applied *before* domain matching, because several exist to correct
bad coordinates in the source files rather than to fill gaps.

Coordinates are campus-level, not newsroom-level — an outlet sits at its host
institution. For a national thematic map that is the right granularity, but don't
present it as a street address.

## Source-data corrections

`data/student-media-outlets.csv` contains geocoding errors that put outlets in
the wrong state. The geocoder now detects this class automatically: after
resolving, it warns when one coordinate is shared by institutions in different
states, which is the signature of a geocoder returning a centroid on failure.

Found and corrected:

- **`(38.7946, -106.5348)`** — the geographic centre of Colorado, carrying four
  institutions from CA, TX, and PA. A failed-geocode fallback.
- **`(40.7607, -111.8939)`** — Salt Lake City, shared by Southern Utah University
  and a row labelled "University of Texas". The Daily Texan was plotting in Utah.
- **`(42.2392, -71.8080)`** — Worcester MA, correct for College of the Holy Cross
  but also attached to Holy Cross College in Indiana, so Notre Dame/Saint Mary's
  *Observer* plotted in Massachusetts.
- **`(41.1199, -80.3323)`** — New Wilmington PA, correct for Westminster College
  PA but also attached to Westminster College in Missouri.

Eight outlets and 130 stories were mislocated. Corrections live in
`data/publication_institution_overrides.csv` with a note on each row. The
underlying rows in `student-media-outlets.csv` are still wrong — worth fixing at
source if that file is shared with anyone else.

### Still unresolved

`canalsidechronicles.com`, `news7newslinc.net`, `citynewsroomcjs.com`,
`communitywire.miami`, `massnewsservice.org`, `fulcrumnewspaper.wpcomstaging.com`,
`pioneerpress.online`, `indearizona.com`, `pubgen-form-builder.vercel.app`, and
`alcivia.com` — 91 stories total. Each needs a host institution identified by
hand; add a row to `data/publication_institution_overrides.csv` and re-run.

Two of those are not student media at all: `alcivia.com` is an agricultural
cooperative and `pubgen-form-builder.vercel.app` is a form builder. Both should
probably be dropped from the feed lists rather than geocoded.

## Reading the map

**Story count** weights each point by how many stories it published on the topic.
This partly maps newsroom size — a heat blob over Syracuse mostly means The
NewsHouse is large (381 stories).

**Share of output** weights by what fraction of a newsroom's own coverage the
topic represents, damped by output size so a newsroom with 2 stories can't
outrank one with 200. Use this to find where a subject is *unusually central*.
The two modes answer different questions; the share view is the more defensible
one behind a claim like "immigration coverage concentrates here."

Topic assignment is a keyword-lexicon heuristic over article body text, the same
one used in the dataset summary. Each story is counted once under its strongest
beat; 13,931 of 14,190 placed stories cleared the signal threshold. It is not a
trained classifier — describe it as a lexicon heuristic in any writeup.

Remember the collection caveat from the summary: per-outlet story counts track
RSS feed window size, not editorial output. The map shows where *collected*
coverage sits, which is not the same as where coverage is produced.
