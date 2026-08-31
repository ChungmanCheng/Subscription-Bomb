"""
modes.py – The operational modes of the bot:

  add_subscription_url   – fully automatic newsletter discovery
  add_subscription_url_interactive – register a specific URL manually
  modify_subscription_file – list / toggle verified / delete entries
  verify_mode            – test unverified URLs and confirm via IMAP
  attack_mode            – run subscriptions against all verified URLs
"""
import time
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from config import EMAILS, IMAP_HOST, IMAP_USER, IMAP_PASS, IMAP_FOLDER, IMAP_TIMEOUT
from config import (
    AUTO_SEARCH_QUERIES,
    AUTO_RESULTS_PER_QUERY,
    AUTO_TARGET_ADDITIONS,
    AUTO_MAX_CANDIDATES,
    AUTO_EXPAND_SEARCH_QUERIES,
    AUTO_MIN_SEARCH_SCORE,
    AUTO_FOLLOW_LINKS,
    AUTO_LINKS_PER_PAGE,
    AUTO_RESPECT_ROBOTS,
    AUTO_ROBOTS_USER_AGENT,
    AUTO_REQUEST_DELAY,
)
from storage import load_subscription_urls, save_subscription_urls
from browser import (
    create_driver,
    subscribe_email,
    fetch_form_elements,
    find_subscription_links,
    infer_subscription_fields,
    reveal_subscription_form,
    detect_automation_block,
    validate_subscription_mapping,
    pick_selectors_interactively,
)
from search_api import (
    choose_subscription_urls,
    newsletter_search_query,
    normalize_subscription_url,
    search_subscription_urls,
)
from imap_utils import get_inbox_uids, check_inbox_for_new_email
from selector_utils import parse_css_selector_list


# ---------------------------------------------------------------------------
# 1. Add URL
# ---------------------------------------------------------------------------

def _subscription_entry(url: str, input_fields: dict,
                        sender_hint: str = "", subject_hint: str = "") -> dict:
    """Build a new unverified subscription entry."""
    return {
        "url": url,
        "verified": False,
        "verification": {
            "sender_hint": sender_hint,
            "subject_hint": subject_hint,
        },
        "input_fields": input_fields,
    }


def _robots_allowed(url: str, cache: dict[str, RobotFileParser | None]) -> bool:
    """Return whether robots.txt permits automated discovery of *url*."""
    parts = urlsplit(url)
    origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    if origin not in cache:
        parser = RobotFileParser(f"{origin}/robots.txt")
        try:
            parser.read()
            cache[origin] = parser
        except Exception as exc:
            cache[origin] = None
            print(f"  Skipped: robots.txt was unreachable ({exc}).")
    parser = cache[origin]
    return bool(parser and parser.can_fetch(AUTO_ROBOTS_USER_AGENT, url))


def _inspect_newsletter_page(url: str, driver) -> dict | None:
    """Return inferred fields when *url* contains a coherent newsletter form."""
    elements = fetch_form_elements(url, driver)
    current_url = normalize_subscription_url(driver.current_url) or url
    current_path = urlsplit(current_url).path.lower()
    if any(part in current_path for part in (
        "/login", "/log-in", "/signin", "/sign-in", "/account/login",
        "/register",
    )):
        return None
    fields = infer_subscription_fields(elements)
    if fields["email"] and fields["submit"]:
        return fields
    return reveal_subscription_form(driver)


def auto_add_subscription_urls(
    urls: list[str],
    *,
    follow_links: bool = AUTO_FOLLOW_LINKS,
    respect_robots: bool = AUTO_RESPECT_ROBOTS,
    request_delay: float = AUTO_REQUEST_DELAY,
    max_additions: int | None = None,
) -> dict[str, int]:
    """Inspect and add every valid newsletter URL without further prompts.

    Existing and duplicate URLs are skipped. A page is stored only when both
    an email field and a submit control can be inferred. No form is submitted
    by this discovery workflow.
    """
    data = load_subscription_urls()
    existing = {
        normalized
        for entry in data
        if (normalized := normalize_subscription_url(entry.get("url", "")))
    }
    candidates = []
    seen = set()
    stats = {
        "added": 0,
        "existing": 0,
        "invalid": 0,
        "unrecognized": 0,
        "robots": 0,
        "blocked": 0,
    }

    for raw_url in urls:
        url = normalize_subscription_url(raw_url)
        if not url:
            stats["invalid"] += 1
        elif url in existing or url in seen:
            stats["existing"] += 1
        else:
            candidates.append(url)
            seen.add(url)

    if not candidates:
        return stats

    print(f"\nAutomatically inspecting {len(candidates)} URL(s)…")
    driver = create_driver(headless=True, discovery=True)
    robots_cache: dict[str, RobotFileParser | None] = {}
    pages_inspected = 0
    try:
        for index, url in enumerate(candidates, start=1):
            if max_additions is not None and stats["added"] >= max_additions:
                break
            print(f"[{index}/{len(candidates)}] {url}")
            if respect_robots and not _robots_allowed(url, robots_cache):
                stats["robots"] += 1
                print("  Skipped: disallowed by robots.txt.")
                continue

            if pages_inspected and request_delay:
                time.sleep(request_delay)
            try:
                input_fields = _inspect_newsletter_page(url, driver)
                inspection_failed = False
            except Exception as exc:
                print(f"  Skipped: page inspection failed ({exc}).")
                input_fields = None
                inspection_failed = True
            pages_inspected += 1

            resolved_url = normalize_subscription_url(driver.current_url) or url
            block_reason = detect_automation_block(driver) if not input_fields else ""
            if block_reason:
                stats["blocked"] += 1
                print(f"  Skipped: site blocked browser inspection ({block_reason}).")
                continue
            if not input_fields and follow_links and not inspection_failed:
                links = find_subscription_links(
                    url, driver, limit=AUTO_LINKS_PER_PAGE
                )
                for link in links:
                    normalized_link = normalize_subscription_url(link)
                    if not normalized_link or normalized_link in existing:
                        continue
                    if respect_robots and not _robots_allowed(
                        normalized_link, robots_cache
                    ):
                        stats["robots"] += 1
                        continue
                    if request_delay:
                        time.sleep(request_delay)
                    try:
                        input_fields = _inspect_newsletter_page(
                            normalized_link, driver
                        )
                        pages_inspected += 1
                    except Exception as exc:
                        print(
                            f"  Linked-page inspection failed for "
                            f"{normalized_link} ({exc})."
                        )
                        input_fields = None
                    if input_fields:
                        resolved_url = normalized_link
                        break

            if not input_fields:
                stats["unrecognized"] += 1
                print("  Skipped: newsletter email and submit controls not found.")
                continue

            if resolved_url in existing:
                stats["existing"] += 1
                continue
            if not validate_subscription_mapping(
                resolved_url, input_fields, driver
            ):
                stats["unrecognized"] += 1
                print("  Skipped: inferred selectors failed a fresh-load replay.")
                continue
            data.append(_subscription_entry(resolved_url, input_fields))
            existing.add(resolved_url)
            stats["added"] += 1
            # Checkpoint every success. A 50-source discovery can run for a
            # long time, and an interruption must not discard earlier finds.
            save_subscription_urls(data)
            print(
                f"  Added {resolved_url}: {input_fields['email'][0]['css']} -> "
                f"{input_fields['submit'][0]['css']}"
            )
    finally:
        try:
            driver.quit()
        except Exception as exc:
            print(f"Browser cleanup warning: {exc}")

    return stats


_AUTO_DISCOVERY_TOPICS = (
    "technology", "business", "finance", "science", "health",
    "food", "travel", "sports", "culture", "books", "education",
    "climate", "nonprofit", "marketing", "design", "startups",
    "software development", "cybersecurity", "artificial intelligence",
    "gaming", "photography", "music", "film", "local news",
    "world news", "parenting", "careers", "personal productivity",
)


def _automatic_query_plan(configured_queries: list[str]) -> list[str]:
    """Build a diverse, deterministic query plan for target backfilling."""
    queries = [newsletter_search_query(query) for query in configured_queries]
    if AUTO_EXPAND_SEARCH_QUERIES:
        queries.extend(
            newsletter_search_query(topic) for topic in _AUTO_DISCOVERY_TOPICS
        )
        queries.extend((
            "site:substack.com newsletter subscribe email",
            "site:beehiiv.com newsletter subscribe email",
            "site:buttondown.email newsletter subscribe email",
        ))
    return list(dict.fromkeys(queries))


def _empty_discovery_stats() -> dict[str, int]:
    return {
        "added": 0,
        "existing": 0,
        "invalid": 0,
        "unrecognized": 0,
        "robots": 0,
        "blocked": 0,
    }


def add_subscription_url() -> None:
    """Fully automatic, configuration-driven newsletter discovery (Mode 1)."""
    if not AUTO_SEARCH_QUERIES:
        print("No AUTO_SEARCH_QUERIES configured in .env.")
        return

    queries = _automatic_query_plan(AUTO_SEARCH_QUERIES)
    seen = set()
    stats = _empty_discovery_stats()
    candidates_inspected = 0
    print(
        f"Automatic target: {AUTO_TARGET_ADDITIONS} new source(s); "
        f"candidate budget: {AUTO_MAX_CANDIDATES}."
    )

    for index, query in enumerate(queries, start=1):
        if stats["added"] >= AUTO_TARGET_ADDITIONS:
            break
        if candidates_inspected >= AUTO_MAX_CANDIDATES:
            break

        print(f"[Search {index}/{len(queries)}] {query}")
        results = search_subscription_urls(
            query,
            limit=AUTO_RESULTS_PER_QUERY,
            min_score=AUTO_MIN_SEARCH_SCORE,
        )
        fresh = [url for url in results if url not in seen]
        for url in fresh:
            seen.add(url)
        remaining_budget = AUTO_MAX_CANDIDATES - candidates_inspected
        fresh = fresh[:remaining_budget]
        if not fresh:
            print("  No new candidates from this query.")
            continue

        print(f"  Inspecting {len(fresh)} new candidate(s) from this query.")
        remaining_target = AUTO_TARGET_ADDITIONS - stats["added"]
        batch_stats = auto_add_subscription_urls(
            fresh,
            max_additions=remaining_target,
        )
        candidates_inspected += len(fresh)
        for key in stats:
            stats[key] += batch_stats[key]
        print(
            f"  Progress: {stats['added']}/{AUTO_TARGET_ADDITIONS} added "
            f"after {candidates_inspected} candidate(s)."
        )

    if not seen:
        print("Automatic discovery found no candidate URLs.")
        return

    print(
        "\nFully automatic discovery complete. "
        f"Target: {AUTO_TARGET_ADDITIONS}, "
        f"Added: {stats['added']}, Existing/duplicate: {stats['existing']}, "
        f"Invalid: {stats['invalid']}, Robots denied: {stats['robots']}, "
        f"Browser blocked: {stats['blocked']}, "
        f"No form detected: {stats['unrecognized']}"
    )


def add_subscription_url_interactive() -> None:
    """
    Manual/single-result wizard:
      1. Choose one URL, or all results from the Search API
      2. Open browser → scrape all form elements
      3. Automatically infer form fields, with manual mapping as a fallback
      4. Optionally collect IMAP verification hints in manual setup
      5. Save as unverified entry in the JSON list
    """
    urls, auto_add = choose_subscription_urls()
    if not urls:
        return

    if auto_add:
        stats = auto_add_subscription_urls(urls)
        print(
            "\nAutomatic URL import complete. "
            f"Added: {stats['added']}, Existing/duplicate: {stats['existing']}, "
            f"Invalid: {stats['invalid']}, Robots denied: {stats['robots']}, "
            f"Browser blocked: {stats['blocked']}, "
            f"No form detected: {stats['unrecognized']}"
        )
        return

    url = urls[0]

    data = load_subscription_urls()
    if any(
        normalize_subscription_url(entry.get("url", "")) == url
        for entry in data
    ):
        print("URL already exists in list.")
        return

    print("\nOpening browser to inspect form elements…")
    driver = create_driver(headless=False)
    try:
        elements = fetch_form_elements(url, driver)
    finally:
        driver.quit()

    if not elements:
        print("No form elements detected – falling back to manual CSS entry.")

    setup_mode = input(
        "Choose form setup: [1] Automatic (recommended), [2] Manual: "
    ).strip() or "1"
    input_fields = infer_subscription_fields(elements) if setup_mode != "2" else None

    if input_fields and input_fields["email"] and input_fields["submit"]:
        print("\nAutomatic form setup complete:")
        print(f"  Email:  {input_fields['email'][0]['css']}")
        print(f"  Submit: {input_fields['submit'][0]['css']}")
        if input_fields["checkboxes"]:
            print(f"  Required checkbox(es): {len(input_fields['checkboxes'])}")
        sender_hint = ""
        subject_hint = ""
    else:
        if setup_mode != "2":
            print("Automatic setup could not confidently identify both fields; using manual setup.")

        email_els    = [e for e in elements if e["type"] in ("email", "text", "textarea")]
        submit_els   = [e for e in elements if e["type"] in ("submit", "button") or e["tag"] == "button"]
        checkbox_els = [e for e in elements if e["type"] == "checkbox"]
        radio_els    = [e for e in elements if e["type"] == "radio"]

        print("\n=== Assign form fields for this URL ===")
        print("Enter element number(s) from the table, raw CSS, or press Enter for the default.\n")

        email_fields    = pick_selectors_interactively(
            email_els,    "EMAIL input field(s)",   "input[type='email']")
        submit_fields   = pick_selectors_interactively(
            submit_els,   "SUBMIT button(s)",       "button[type='submit'], input[type='submit']")
        checkbox_fields = pick_selectors_interactively(
            checkbox_els, "CHECKBOX(es) to tick")
        radio_fields    = pick_selectors_interactively(
            radio_els,    "RADIO button(s) to select")

        wait_seconds_raw = input("\n  Wait seconds after submit [default 0]: ").strip()
        try:
            wait_seconds = max(0, int(wait_seconds_raw)) if wait_seconds_raw else 0
        except ValueError:
            wait_seconds = 0

        input_fields = {
            "email": email_fields,
            "username": [],
            "phone": [],
            "submit": submit_fields,
            "radios": radio_fields,
            "checkboxes": checkbox_fields,
            "selections": [],
            "wait": wait_seconds,
        }

        print("\n--- IMAP Inbox Verification Hints (optional) ---")
        print("These help narrow down which email counts as a confirmation.")
        sender_hint  = input("Sender hint (e.g. noreply@example.com): ").strip()
        subject_hint = input("Subject hint (e.g. confirm, verify, welcome): ").strip()

    data.append(_subscription_entry(
        url, input_fields, sender_hint=sender_hint, subject_hint=subject_hint
    ))
    save_subscription_urls(data)
    print("URL added successfully as unverified!")


# ---------------------------------------------------------------------------
# 2. Modify list
# ---------------------------------------------------------------------------

def modify_subscription_file() -> None:
    """
    Display all subscription entries with their verification status and
    allow the user to toggle verified/unverified, delete, or quit.
    """
    data = load_subscription_urls()
    if not data:
        print("No subscription URLs found.")
        return

    for index, entry in enumerate(data):
        status = "✔ Verified" if entry.get("verified") else "❌ Unverified"
        print(f"{index + 1}. {entry['url']} - {status}")

    print("Actions: t=toggle verified, d=delete, q=quit")
    action = input("Choose action: ").strip().lower()
    if action == "q":
        return

    choice = input("Enter the number to modify: ").strip()
    if choice.lower() == "q":
        return

    try:
        idx = int(choice) - 1
        if action == "t":
            data[idx]["verified"] = not data[idx].get("verified", False)
            save_subscription_urls(data)
            print("Verification status updated.")
        elif action == "d":
            removed = data.pop(idx)
            save_subscription_urls(data)
            print(f"Deleted: {removed.get('url', 'unknown')}")
        else:
            print("Invalid action.")
    except (ValueError, IndexError):
        print("Invalid selection.")


# ---------------------------------------------------------------------------
# 3. Verify mode
# ---------------------------------------------------------------------------

def verify_mode() -> None:
    """
    For each unverified URL:
      1. Snapshot the inbox (IMAP) before form submit
      2. Submit the form via Selenium
      3. If IMAP configured → poll inbox for a confirmation email
         Otherwise         → treat form-submit success as verified

    Saves updated verification status to the JSON file.
    """
    if not EMAILS:
        print("No EMAILS found in .env. Please set EMAILS=email1,email2 first.")
        return

    data = load_subscription_urls()
    if not data:
        print("No URLs found.")
        return

    unverified = load_subscription_urls(unverified_only=True)
    if not unverified:
        print("No unverified URLs found.")
        return

    imap_enabled = all([IMAP_HOST, IMAP_USER, IMAP_PASS])
    if imap_enabled:
        print(f"[IMAP] Inbox verification enabled "
              f"(host={IMAP_HOST}, folder={IMAP_FOLDER}, timeout={IMAP_TIMEOUT}s).")
    else:
        print("[IMAP] IMAP not configured – verification will rely on form-submit success only.")

    driver = create_driver(headless=False)
    any_changed = False

    for entry in unverified:
        url = entry["url"]
        verification = entry.get("verification", {})
        sender_hint  = verification.get("sender_hint", "")
        subject_hint = verification.get("subject_hint", "")
        verified_now = False

        for email_addr in EMAILS:
            known_uids = get_inbox_uids() if imap_enabled else None
            success = subscribe_email(email_addr, url.strip(),
                                      entry.get("input_fields", {}), driver)

            if success:
                if imap_enabled:
                    print(f"[IMAP] Form submitted for {url} – polling inbox for confirmation…")
                    if check_inbox_for_new_email(known_uids, sender_hint, subject_hint):
                        verified_now = True
                        print(f"[IMAP] URL verified via inbox: {url}")
                    else:
                        print(f"[IMAP] No confirmation email received for {url}")
                else:
                    verified_now = True
                    print(f"URL verified (form submit): {url}")

            if verified_now:
                break

        if verified_now:
            for saved in data:
                if saved.get("url", "").strip() == url.strip():
                    saved["verified"] = True
                    any_changed = True
                    break
        else:
            print(f"URL failed verification: {url}")

    if any_changed:
        save_subscription_urls(data)
        print("Verification updates saved.")

    driver.quit()
    print("Verification process completed.")


# ---------------------------------------------------------------------------
# 4. Attack mode
# ---------------------------------------------------------------------------

def attack_mode() -> None:
    """
    Submit the subscription form for every (email, verified URL) combination
    using a headless browser.  Prints a final success/fail count.
    """
    if not EMAILS:
        print("No EMAILS found in .env. Please set EMAILS=email1,email2 first.")
        return

    verified = load_subscription_urls(verified_only=True)
    if not verified:
        print("No verified URLs found.")
        return

    driver = create_driver(headless=True)
    success_count = 0
    fail_count = 0

    for email_addr in EMAILS:
        for entry in verified:
            url = entry["url"]
            fields = entry.get("input_fields", {"email": [{"css": "input[type='email']"}]})
            if subscribe_email(email_addr, url.strip(), fields, driver):
                success_count += 1
            else:
                fail_count += 1

    driver.quit()
    print(f"Attack mode completed. Success: {success_count}, Failed: {fail_count}")
