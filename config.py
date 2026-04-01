"""
config.py – centralised environment variable loading and application constants.
All other modules import from here; nothing in this file imports from the project.
"""
import os
from dotenv import load_dotenv

load_dotenv()

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
SEARCH_API_KEY_BODY_FIELD: str = os.getenv("SEARCH_API_KEY_BODY_FIELD", "").strip()
SEARCH_API_QUERY_PARAM: str  = os.getenv("SEARCH_API_QUERY_PARAM", "q").strip() or "q"
SEARCH_API_RESULTS_PATH: str = os.getenv("SEARCH_API_RESULTS_PATH", "results").strip() or "results"
SEARCH_API_URL_FIELD: str    = os.getenv("SEARCH_API_URL_FIELD", "url").strip() or "url"

# ---------------------------------------------------------------------------
# IMAP inbox verification
# ---------------------------------------------------------------------------
IMAP_HOST: str    = os.getenv("IMAP_HOST", "").strip()
IMAP_PORT: int    = int(os.getenv("IMAP_PORT", "993").strip() or "993")
IMAP_USER: str    = os.getenv("IMAP_USER", "").strip()
IMAP_PASS: str    = os.getenv("IMAP_PASS", "").strip()
IMAP_FOLDER: str  = os.getenv("IMAP_FOLDER", "INBOX").strip() or "INBOX"
IMAP_TIMEOUT: int = int(os.getenv("IMAP_TIMEOUT", "60").strip() or "60")
