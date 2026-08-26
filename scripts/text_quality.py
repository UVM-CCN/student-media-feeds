"""
Shared text cleaning and non-story detection for the topic pipeline.

The extractor (trafilatura) is good but not perfect. Two classes of junk survive
into full_text/ and they damage topic quality out of all proportion to their
count:

  * CMS template leakage. Many student papers run on SNO (School Newspapers
    Online), whose navigation markup sometimes survives extraction as bare CSS
    class names — "sno-hac-hamburger-menu-tablet-" and friends. Only ~40 files
    are affected, but one of them repeats a single token 48 times, which is
    enough to dominate class-based TF-IDF and hand an entire topic a
    description made of stylesheet fragments rather than subject words.

  * Non-stories ingested as stories. Image pages (`/image_...`), bare photo
    filenames as headlines ("IMG_0191.jpg"), and newscast stubs. These have no
    topical content, so they land in whichever cluster is loosest and inflate
    a catch-all topic.

Both are filtered here rather than in the extractor, because re-extracting the
corpus would mean re-fetching 22,000 URLs — and the source pages for the older
ones are already rotting. This keeps the raw archive faithful to what was
actually published while keeping analysis clean.

Legitimate short items (police blotter briefs, event notices) are deliberately
NOT filtered: the floor stays at 50 words, matching the rest of the pipeline.
Raising it to 80 would drop ~1,000 real briefs, and brief local coverage is
exactly what this research is about.
"""
import re

HEADER_END_MARKER = "# ---"

# Bare CSS class names from the SNO/HAC theme that survived extraction.
CMS_ARTIFACT = re.compile(r"\b(?:sno|hac)-[a-z0-9-]+", re.IGNORECASE)

# Inline stylesheet declarations that survived alongside the class names. The
# worst affected file is 38.6% CSS by character count -- 401 declarations --
# which is more than enough to steer a topic. Matched against a whitelist of
# real CSS properties rather than a generic "word: value;" pattern, because
# that generic form also matches ordinary prose ("The verdict: guilty;").
_CSS_PROPERTIES = (
    "background|background-color|background-image|background-position|"
    "background-repeat|background-size|border|border-top|border-right|"
    "border-bottom|border-left|border-radius|border-color|border-width|"
    "border-style|box-shadow|box-sizing|clear|color|content|cursor|display|"
    "flex|flex-direction|float|font|font-family|font-size|font-style|"
    "font-weight|height|left|letter-spacing|line-height|margin|margin-top|"
    "margin-right|margin-bottom|margin-left|max-height|max-width|min-height|"
    "min-width|opacity|overflow|overflow-x|overflow-y|padding|padding-top|"
    "padding-right|padding-bottom|padding-left|position|right|text-align|"
    "text-decoration|text-transform|top|transform|transition|vertical-align|"
    "visibility|white-space|width|word-wrap|z-index"
)
CSS_DECLARATION = re.compile(
    rf"\b(?:{_CSS_PROPERTIES})\s*:\s*[^;{{}}\n]{{1,60}}\s*;?",
    re.IGNORECASE,
)

# Leftover selector/at-rule fragments and bare unit values.
CSS_FRAGMENT = re.compile(
    r"(@media[^{{]*|!important|[{}]|#[0-9a-fA-F]{3,8}\b|\b\d+(?:px|em|rem|vh|vw|pt)\b)"
)

# Headline is just a camera/CMS filename rather than a title.
IMAGE_FILENAME_TITLE = re.compile(
    r"(?i)^\s*(?:img|dsc|dscn|pxl|screenshot|photo|image)[\s_-]*\d*\s*\.?(?:jpe?g|png|gif|webp)?\s*$"
)

# A numbered photo-series title such as "The Chicks 06".
NUMBERED_SERIES_TITLE = re.compile(r"^[A-Za-z][A-Za-z' ]{1,28}\s\d{1,3}$")

# URL points at an image/gallery page, not an article.
IMAGE_URL = re.compile(r"/(?:image|photo|gallery)[_-]", re.IGNORECASE)

# Broadcast rundown stubs that carry only a date.
NEWSCAST_TITLE = re.compile(r"(?i)\b(?:ditv|newscast|rundown)\b")

MIN_STORY_WORDS = 50


def strip_header(text: str) -> str:
    """full_text files carry a metadata header; return only the body."""
    idx = text.find(HEADER_END_MARKER)
    if idx == -1:
        return text
    newline = text.find("\n", idx)
    return text[newline + 1:] if newline != -1 else ""


def clean_body(text: str) -> str:
    """Remove template artifacts and stylesheet leakage, normalize whitespace."""
    text = CMS_ARTIFACT.sub(" ", text)
    text = CSS_DECLARATION.sub(" ", text)
    text = CSS_FRAGMENT.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_probable_story(title: str, link: str, body: str,
                      min_words: int = MIN_STORY_WORDS) -> bool:
    """
    False for items that are not articles at all. Conservative by design —
    when in doubt this returns True, because dropping real coverage biases the
    analysis more than admitting a little noise.
    """
    title = (title or "").strip()
    link = (link or "").strip()

    if len(body.split()) < min_words:
        return False
    if IMAGE_FILENAME_TITLE.match(title):
        return False
    if NUMBERED_SERIES_TITLE.match(title):
        return False
    if IMAGE_URL.search(link):
        return False
    if NEWSCAST_TITLE.search(title):
        return False
    return True


def load_story_text(path: str, title: str, link: str, limit_words: int):
    """
    Read a full_text file and return cleaned, truncated body text, or None if
    the item does not look like a story. Truncation to the first `limit_words`
    standardizes across articles ranging from 50 to several thousand words and
    keeps the lede, where topical signal is densest.
    """
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return None
    body = clean_body(strip_header(raw))
    if not is_probable_story(title, link, body):
        return None
    return " ".join(body.split()[:limit_words])
