"""
config.py – centralised environment variable loading and application constants.
All other modules import from here; nothing in this file imports from the project.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Read a bounded integer without making a bad .env value fatal."""
    try:
        value = int(os.getenv(name, str(default)).strip())
    except (AttributeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float,
               maximum: float) -> float:
    """Read a bounded float without making a bad .env value fatal."""
    try:
        value = float(os.getenv(name, str(default)).strip())
    except (AttributeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_bool(name: str, default: bool) -> bool:
    """Read a conventional boolean value from the environment."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")

# ---------------------------------------------------------------------------
# Email targets
# ---------------------------------------------------------------------------
EMAILS: list[str] = [
    e.strip()
    for e in os.getenv("EMAILS", "").split(",")
    if e.strip()
]

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
URL_JSON: str = "email_subscription.json"

# ---------------------------------------------------------------------------
# HTTP spoofing
# ---------------------------------------------------------------------------
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.124 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Search API
# ---------------------------------------------------------------------------
SEARCH_API_URL: str          = os.getenv("SEARCH_API_URL", "").strip()
SEARCH_API_KEY: str          = os.getenv("SEARCH_API_KEY", "").strip()
SEARCH_API_METHOD: str       = os.getenv("SEARCH_API_METHOD", "GET").strip().upper() or "GET"
SEARCH_API_KEY_HEADER: str   = os.getenv("SEARCH_API_KEY_HEADER", "X-API-Key").strip() or "X-API-Key"
SEARCH_API_KEY_PREFIX: str   = os.getenv("SEARCH_API_KEY_PREFIX", "").strip()
SEARCH_API_KEY_BODY_FIELD: str = os.getenv("SEARCH_API_KEY_BODY_FIELD", "").strip()
SEARCH_API_QUERY_PARAM: str  = os.getenv("SEARCH_API_QUERY_PARAM", "q").strip() or "q"
SEARCH_API_RESULTS_PATH: str = os.getenv("SEARCH_API_RESULTS_PATH", "results").strip() or "results"
SEARCH_API_URL_FIELD: str    = os.getenv("SEARCH_API_URL_FIELD", "url").strip() or "url"
SEARCH_API_SCORE_FIELD: str  = os.getenv("SEARCH_API_SCORE_FIELD", "score").strip() or "score"
SEARCH_API_MAX_RESULTS_FIELD: str = os.getenv(
    "SEARCH_API_MAX_RESULTS_FIELD",
    "max_results" if "tavily.com" in SEARCH_API_URL.lower() else "",
).strip()

# ---------------------------------------------------------------------------
# Fully automatic URL discovery (Mode 1)
# ---------------------------------------------------------------------------
AUTO_SEARCH_QUERIES: list[str] = [
    query.strip()
    for query in os.getenv("AUTO_SEARCH_QUERIES", "newsletter subscribe").split(",")
    if query.strip()
]
AUTO_RESULTS_PER_QUERY: int = _env_int("AUTO_RESULTS_PER_QUERY", 10, 1, 20)
AUTO_MAX_URLS: int = _env_int("AUTO_MAX_URLS", 50, 1, 500)
AUTO_MIN_SEARCH_SCORE: float = _env_float("AUTO_MIN_SEARCH_SCORE", 0.5, 0.0, 1.0)
AUTO_FOLLOW_LINKS: bool = _env_bool("AUTO_FOLLOW_LINKS", True)
AUTO_LINKS_PER_PAGE: int = _env_int("AUTO_LINKS_PER_PAGE", 3, 0, 20)
AUTO_RESPECT_ROBOTS: bool = _env_bool("AUTO_RESPECT_ROBOTS", True)
AUTO_ROBOTS_USER_AGENT: str = os.getenv(
    "AUTO_ROBOTS_USER_AGENT", "SubscriptionBot"
).strip() or "SubscriptionBot"
AUTO_REQUEST_DELAY: float = _env_float("AUTO_REQUEST_DELAY", 1.0, 0.0, 60.0)
AUTO_PAGE_WAIT: float = _env_float("AUTO_PAGE_WAIT", 5.0, 0.5, 60.0)

# ---------------------------------------------------------------------------
# IMAP inbox verification
# ---------------------------------------------------------------------------
IMAP_HOST: str    = os.getenv("IMAP_HOST", "").strip()
IMAP_PORT: int    = int(os.getenv("IMAP_PORT", "993").strip() or "993")
IMAP_USER: str    = os.getenv("IMAP_USER", "").strip()
IMAP_PASS: str    = os.getenv("IMAP_PASS", "").strip()
IMAP_FOLDER: str  = os.getenv("IMAP_FOLDER", "INBOX").strip() or "INBOX"
IMAP_TIMEOUT: int = int(os.getenv("IMAP_TIMEOUT", "60").strip() or "60")
