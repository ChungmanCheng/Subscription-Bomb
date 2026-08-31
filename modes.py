"""
modes.py – The four operational modes of the bot:

  add_subscription_url   – interactive wizard to register a new URL
  modify_subscription_file – list / toggle verified / delete entries
  verify_mode            – test unverified URLs and confirm via IMAP
  attack_mode            – run subscriptions against all verified URLs
"""
from config import EMAILS, IMAP_HOST, IMAP_USER, IMAP_PASS, IMAP_FOLDER, IMAP_TIMEOUT
from storage import load_subscription_urls, save_subscription_urls
from browser import (
    create_driver,
    subscribe_email,
    fetch_form_elements,
    infer_subscription_fields,
    pick_selectors_interactively,
)
from search_api import choose_subscription_urls, normalize_subscription_url
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


def auto_add_subscription_urls(urls: list[str]) -> dict[str, int]:
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
    stats = {"added": 0, "existing": 0, "invalid": 0, "unrecognized": 0}

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
    driver = create_driver(headless=True)
    try:
        for index, url in enumerate(candidates, start=1):
            print(f"[{index}/{len(candidates)}] {url}")
            try:
                elements = fetch_form_elements(url, driver)
                input_fields = infer_subscription_fields(elements)
            except Exception as exc:
                stats["unrecognized"] += 1
                print(f"  Skipped: page inspection failed ({exc}).")
                continue
            if not input_fields["email"] or not input_fields["submit"]:
                stats["unrecognized"] += 1
                print("  Skipped: newsletter email and submit controls not found.")
                continue

            data.append(_subscription_entry(url, input_fields))
            existing.add(url)
            stats["added"] += 1
            print(
                f"  Added: {input_fields['email'][0]['css']} -> "
                f"{input_fields['submit'][0]['css']}"
            )
    finally:
        try:
            driver.quit()
        except Exception as exc:
            print(f"Browser cleanup warning: {exc}")

    if stats["added"]:
        save_subscription_urls(data)
    return stats


def add_subscription_url() -> None:
    """
    Interactive wizard:
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
            f"Invalid: {stats['invalid']}, No form detected: {stats['unrecognized']}"
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
