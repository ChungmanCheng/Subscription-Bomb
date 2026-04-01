"""
search_api.py – Search API integration and URL selection.

Supports both GET (query-string) and POST (JSON body) APIs via .env config.
"""
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import (
    SEARCH_API_URL,
    SEARCH_API_KEY,
    SEARCH_API_METHOD,
    SEARCH_API_KEY_HEADER,
    SEARCH_API_KEY_BODY_FIELD,
    SEARCH_API_QUERY_PARAM,
    SEARCH_API_RESULTS_PATH,
    SEARCH_API_URL_FIELD,
    USER_AGENT,
)
from selector_utils import get_nested_value


def search_subscription_urls(query: str, limit: int = 5) -> list[str]:
    """
    Query the configured search API for newsletter subscription page URLs.

    Supports GET (appends query string) and POST (sends JSON body) APIs.
    Returns up to *limit* URL strings, or an empty list on any error.
    """
    if not SEARCH_API_URL:
        print("Search API is not configured. Set SEARCH_API_URL in .env first.")
        return []

    headers = {"User-Agent": USER_AGENT}

    if SEARCH_API_METHOD == "POST":
        body = {SEARCH_API_QUERY_PARAM: query}
        if SEARCH_API_KEY and SEARCH_API_KEY_BODY_FIELD:
            body[SEARCH_API_KEY_BODY_FIELD] = SEARCH_API_KEY
        elif SEARCH_API_KEY:
            headers[SEARCH_API_KEY_HEADER] = SEARCH_API_KEY
        headers["Content-Type"] = "application/json"
        request = Request(
            SEARCH_API_URL,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
    else:
        params = {SEARCH_API_QUERY_PARAM: query}
        request_url = f"{SEARCH_API_URL}?{urlencode(params)}"
        if SEARCH_API_KEY:
            headers[SEARCH_API_KEY_HEADER] = SEARCH_API_KEY
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
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        result_url = get_nested_value(item, SEARCH_API_URL_FIELD)
        if isinstance(result_url, str) and result_url.strip():
            urls.append(result_url.strip())
        if len(urls) >= limit:
            break

    return urls


def choose_subscription_url() -> str | None:
    """
    Interactively ask the user for a subscription URL.

    Mode 1 – Manual: user pastes a URL directly.
    Mode 2 – Search API: user enters a query, results are listed for selection.

    Returns the selected URL string, or None if the user cancels.
    """
    mode = input("Choose URL source: [1] Manual URL, [2] Search API: ").strip() or "1"

    if mode == "2":
        query = input("Enter search query: ").strip()
        if not query:
            print("Search query cannot be empty.")
            return None

        results = search_subscription_urls(query)
        if not results:
            print("No URLs returned from search API.")
            return None

        print("Search results:")
        for index, result_url in enumerate(results, start=1):
            print(f"{index}. {result_url}")

        selected = input("Choose a result number, or press Enter to cancel: ").strip()
        if not selected:
            return None

        try:
            return results[int(selected) - 1]
        except (ValueError, IndexError):
            print("Invalid selection.")
            return None

    return input("Enter the subscription URL: ").strip()
