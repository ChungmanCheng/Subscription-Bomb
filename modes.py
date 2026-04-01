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
    pick_selectors_interactively,
)
from search_api import choose_subscription_url
from imap_utils import get_inbox_uids, check_inbox_for_new_email
from selector_utils import parse_css_selector_list


# ---------------------------------------------------------------------------
# 1. Add URL
# ---------------------------------------------------------------------------

def add_subscription_url() -> None:
    """
    Interactive wizard:
      1. Choose URL (manual or Search API)
      2. Open browser → scrape all form elements
      3. User picks email / submit / checkbox / radio fields by number or CSS
      4. Collect IMAP verification hints
      5. Save as unverified entry in the JSON list
    """
    url = choose_subscription_url()
    if not url:
        print("URL cannot be empty.")
        return

    data = load_subscription_urls()
    if any(entry.get("url", "").strip() == url for entry in data):
        print("URL already exists in list.")
        return

    print("\nOpening browser to inspect form elements…")
    driver = create_driver(headless=False)
    elements = fetch_form_elements(url, driver)
    driver.quit()

    if not elements:
        print("No form elements detected – falling back to manual CSS entry.")

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
        wait_seconds = int(wait_seconds_raw) if wait_seconds_raw else 0
    except ValueError:
        wait_seconds = 0

    print("\n--- IMAP Inbox Verification Hints (optional) ---")
    print("These help narrow down which email counts as a confirmation.")
    sender_hint  = input("Sender hint (e.g. noreply@example.com): ").strip()
    subject_hint = input("Subject hint (e.g. confirm, verify, welcome): ").strip()

    data.append({
        "url": url,
        "verified": False,
        "verification": {
            "sender_hint":  sender_hint,
            "subject_hint": subject_hint,
        },
        "input_fields": {
            "email":      email_fields,
            "username":   [],
            "phone":      [],
            "submit":     submit_fields,
            "radios":     radio_fields,
            "checkboxes": checkbox_fields,
            "selections": [],
            "wait":       wait_seconds,
        },
    })
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
