"""
search_api.py – Search API integration and URL selection.

Supports both GET (query-string) and POST (JSON body) APIs via .env config.
"""
import json
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from config import (
    SEARCH_API_URL,
    SEARCH_API_KEY,
    SEARCH_API_METHOD,
    SEARCH_API_KEY_HEADER,
    SEARCH_API_KEY_PREFIX,
    SEARCH_API_KEY_BODY_FIELD,
    SEARCH_API_QUERY_PARAM,
    SEARCH_API_RESULTS_PATH,
    SEARCH_API_URL_FIELD,
    SEARCH_API_SCORE_FIELD,
    SEARCH_API_MAX_RESULTS_FIELD,
    USER_AGENT,
)
from selector_utils import get_nested_value


def normalize_subscription_url(url: str) -> str | None:
    """Return a canonical HTTP(S) URL suitable for storage and deduplication."""
    if not isinstance(url, str):
        return None

    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None

    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    if scheme not in ("http", "https") or not hostname:
        return None

    try:
        port = parts.port
    except ValueError:
        return None

    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if parts.username or parts.password:
        return None
    if port and not default_port:
        netloc = f"{netloc}:{port}"

    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def newsletter_search_query(topic: str) -> str:
    """Turn a topic into a query aimed at actual subscription pages."""
    query = " ".join(topic.split())
    lowered = query.lower()
    if not any(term in lowered for term in ("newsletter", "subscribe", "sign up")):
        query = f"{query} newsletter subscribe email signup"
    return query


def search_subscription_urls(query: str, limit: int = 5,
                             min_score: float | None = None) -> list[str]:
    """
    Query the configured search API for newsletter subscription page URLs.

    Supports GET (appends query string) and POST (sends JSON body) APIs.
    Returns up to *limit* URL strings, or an empty list on any error.
    """
    if not SEARCH_API_URL:
        print("Search API is not configured. Set SEARCH_API_URL in .env first.")
        return []

    limit = max(1, min(20, limit))
    headers = {"User-Agent": USER_AGENT}
    api_key_header_value = (
        f"{SEARCH_API_KEY_PREFIX} {SEARCH_API_KEY}"
        if SEARCH_API_KEY_PREFIX
        else SEARCH_API_KEY
    )

    if SEARCH_API_METHOD == "POST":
        body = {SEARCH_API_QUERY_PARAM: query}
        if SEARCH_API_KEY and SEARCH_API_KEY_BODY_FIELD:
            body[SEARCH_API_KEY_BODY_FIELD] = SEARCH_API_KEY
        elif SEARCH_API_KEY:
            headers[SEARCH_API_KEY_HEADER] = api_key_header_value
        headers["Content-Type"] = "application/json"
        if SEARCH_API_MAX_RESULTS_FIELD:
            body[SEARCH_API_MAX_RESULTS_FIELD] = limit
        request = Request(
            SEARCH_API_URL,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
    else:
        params = {SEARCH_API_QUERY_PARAM: query}
        if SEARCH_API_MAX_RESULTS_FIELD:
            params[SEARCH_API_MAX_RESULTS_FIELD] = limit
        request_url = f"{SEARCH_API_URL}?{urlencode(params)}"
        if SEARCH_API_KEY:
            headers[SEARCH_API_KEY_HEADER] = api_key_header_value
        request = Request(request_url, headers=headers)

    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"Search API request failed: {exc}")
        return []

    raw_results = get_nested_value(payload, SEARCH_API_RESULTS_PATH)
    if not isinstance(raw_results, list):
        print("Search API response did not contain a result list.")
        return []

    urls = []
    seen = set()
    for item in raw_results:
        result_url = (
            get_nested_value(item, SEARCH_API_URL_FIELD)
            if isinstance(item, dict)
            else item
        )
        score = (
            get_nested_value(item, SEARCH_API_SCORE_FIELD)
            if isinstance(item, dict)
            else None
        )
        if (
            min_score is not None
            and isinstance(score, (int, float))
            and score < min_score
        ):
            continue
        normalized = normalize_subscription_url(result_url)
        if normalized and normalized not in seen:
            urls.append(normalized)
            seen.add(normalized)
        if len(urls) >= limit:
            break

    return urls


def choose_subscription_urls() -> tuple[list[str], bool]:
    """
    Interactively choose one or more subscription URLs.

    Mode 1 – Manual: user pastes a URL directly.
    Mode 2 – Search API: user selects one search result.
    Mode 3 – Auto-add: all valid Search API results are returned for automatic
             inspection and configuration.

    Returns ``(urls, auto_add)``. An empty list means the user cancelled or the
    search failed.
    """
    mode = input(
        "Choose URL source: [1] Manual URL, [2] Choose Search API result, "
        "[3] Auto-add all Search API results: "
    ).strip() or "1"

    if mode in ("2", "3"):
        query = input("Enter search query: ").strip()
        if not query:
            print("Search query cannot be empty.")
            return [], mode == "3"

        results = search_subscription_urls(query, limit=20 if mode == "3" else 5)
        if not results:
            print("No URLs returned from search API.")
            return [], mode == "3"

        if mode == "3":
            print(f"Found {len(results)} unique URL(s) for automatic inspection.")
            return results, True

        print("Search results:")
        for index, result_url in enumerate(results, start=1):
            print(f"{index}. {result_url}")

        selected = input("Choose a result number, or press Enter to cancel: ").strip()
        if not selected:
            return [], False

        try:
            return [results[int(selected) - 1]], False
        except (ValueError, IndexError):
            print("Invalid selection.")
            return [], False

    manual_url = normalize_subscription_url(
        input("Enter the subscription URL: ").strip()
    )
    if not manual_url:
        print("Enter a valid http:// or https:// URL.")
        return [], False
    return [manual_url], False


def choose_subscription_url() -> str | None:
    """Backward-compatible single-URL wrapper around URL selection."""
    urls, _ = choose_subscription_urls()
    return urls[0] if urls else None
