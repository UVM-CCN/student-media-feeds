"""User-Agent selection for hosts that block the identifying bot UA.

Most outlets are fetched with the project's identifying User-Agent. A few
sit behind Cloudflare's browser-integrity check (usually a 403 with a short
118-byte body) and serve the same URL normally to a browser UA. Keep the
override list small and specific: prefer a working feed first, and only add a
domain here after confirming the bot UA is the reason for the block.
"""

from urllib.parse import urlparse

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Hosts that reject the bot UA on feeds and article pages. Entries are keyed by
# bare host (no leading "www.").
BROWSER_UA_HOSTS = {
    "thenewpolitical.com",  # Cloudflare 403/1010 on feeds and articles
}


def host_key(url: str) -> str:
    """Return a lowercase bare hostname, or an empty string for bad input."""
    try:
        netloc = urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return ""
    return netloc[4:] if netloc.startswith("www.") else netloc


def user_agent_for(url: str, default: str) -> str:
    """Choose the browser UA only for hosts on the override list."""
    return BROWSER_USER_AGENT if host_key(url) in BROWSER_UA_HOSTS else default
