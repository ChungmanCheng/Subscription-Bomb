import os
import json
import time
import random
import imaplib
import email
from email.header import decode_header
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from undetected_geckodriver import Firefox
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Read emails from .env (comma-separated values)
EMAILS = [email.strip() for email in os.getenv("EMAILS", "").split(",") if email.strip()]

# JSON file to store subscription URLs with verification status
URL_JSON = "email_subscription.json"

# User-Agent string to spoof
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

SEARCH_API_URL = os.getenv("SEARCH_API_URL", "").strip()
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY", "").strip()
SEARCH_API_METHOD = os.getenv("SEARCH_API_METHOD", "GET").strip().upper() or "GET"
SEARCH_API_KEY_HEADER = os.getenv("SEARCH_API_KEY_HEADER", "X-API-Key").strip() or "X-API-Key"
SEARCH_API_KEY_BODY_FIELD = os.getenv("SEARCH_API_KEY_BODY_FIELD", "").strip()
SEARCH_API_QUERY_PARAM = os.getenv("SEARCH_API_QUERY_PARAM", "q").strip() or "q"
SEARCH_API_RESULTS_PATH = os.getenv("SEARCH_API_RESULTS_PATH", "results").strip() or "results"
SEARCH_API_URL_FIELD = os.getenv("SEARCH_API_URL_FIELD", "url").strip() or "url"

# IMAP configuration for inbox verification
IMAP_HOST = os.getenv("IMAP_HOST", "").strip()
IMAP_PORT = int(os.getenv("IMAP_PORT", "993").strip() or "993")
IMAP_USER = os.getenv("IMAP_USER", "").strip()
IMAP_PASS = os.getenv("IMAP_PASS", "").strip()
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX").strip() or "INBOX"
IMAP_TIMEOUT = int(os.getenv("IMAP_TIMEOUT", "60").strip() or "60")

def get_inbox_uids():
    """
    Connect to the configured IMAP server and return the current set of
    message sequence numbers as a set of bytes.  Returns None if IMAP is
    not configured or the connection fails.
    """
    if not all([IMAP_HOST, IMAP_USER, IMAP_PASS]):
        return None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select(IMAP_FOLDER, readonly=True)
        _, data = mail.search(None, "ALL")
        mail.logout()
        return set(data[0].split()) if data and data[0] else set()
    except Exception as exc:
        print(f"[IMAP] Snapshot failed: {exc}")
        return None


def check_inbox_for_new_email(known_uids, sender_hint="", subject_hint="",
                               timeout=None, poll_interval=10):
    """
    Poll the IMAP inbox until a new email appears that was not present in
    *known_uids*.  Optionally filters messages by *sender_hint* (substring
    matched against the From header) and *subject_hint* (substring matched
    against the decoded Subject header).

    Returns True if a qualifying new email is found before *timeout* seconds
    elapse, False otherwise.  If IMAP is not configured, returns False and
    prints a warning so the caller can decide what to do.
    """
    if not all([IMAP_HOST, IMAP_USER, IMAP_PASS]):
        print("[IMAP] Not configured – skipping inbox check.")
        return False
    if known_uids is None:
        print("[IMAP] No snapshot available – skipping inbox check.")
        return False

    effective_timeout = timeout if timeout is not None else IMAP_TIMEOUT
    deadline = time.time() + effective_timeout

    while time.time() < deadline:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            mail.login(IMAP_USER, IMAP_PASS)
            mail.select(IMAP_FOLDER, readonly=True)
            _, data = mail.search(None, "ALL")
            current_uids = set(data[0].split()) if data and data[0] else set()
            new_uids = current_uids - known_uids

            for uid in new_uids:
                _, msg_data = mail.fetch(uid, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                from_header = msg.get("From", "")

                # Decode subject properly
                raw_subject = msg.get("Subject", "")
                subject_parts = decode_header(raw_subject)
                subject = ""
                for part, enc in subject_parts:
                    if isinstance(part, bytes):
                        subject += part.decode(enc or "utf-8", errors="replace")
                    else:
                        subject += part

                # Apply optional hints as substring filters
                if sender_hint and sender_hint.lower() not in from_header.lower():
                    continue
                if subject_hint and subject_hint.lower() not in subject.lower():
                    continue

                print(f"[IMAP] Confirmation email received!")
                print(f"       From: {from_header}")
                print(f"       Subject: {subject}")
                mail.logout()
                return True

            mail.logout()
        except Exception as exc:
            print(f"[IMAP] Polling error: {exc}")

        remaining = deadline - time.time()
        if remaining > 0:
            wait = min(poll_interval, remaining)
            print(f"[IMAP] No new email yet – checking again in {wait:.0f}s "
                  f"({remaining:.0f}s remaining)...")
            time.sleep(wait)

    print("[IMAP] Timed out waiting for confirmation email.")
    return False


def selector_from_config(field_config):
    """
    Build CSS selector from a field config.
    Supports:
    1) {"css": "..."} raw CSS selector
    2) attribute-based keys: class/id/name/value
    """
    if not isinstance(field_config, dict):
        return ""

    raw_css = field_config.get("css", "").strip()
    if raw_css:
        return raw_css

    selector = ""
    if "class" in field_config and field_config["class"]:
        selector += f'.{field_config["class"]}'
    if "id" in field_config and field_config["id"]:
        selector += f'#{field_config["id"]}'
    if "name" in field_config and field_config["name"]:
        selector += f'[name="{field_config["name"]}"]'
    if "value" in field_config and field_config["value"]:
        selector += f'[value="{field_config["value"]}"]'
    return selector

def parse_css_selector_list(raw_input):
    return [{"css": selector.strip()} for selector in raw_input.split(",") if selector.strip()]

def get_nested_value(data, path):
    current = data
    for part in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None

        if current is None:
            return None
    return current

def search_subscription_urls(query, limit=5):
    if not SEARCH_API_URL:
        print("Search API is not configured. Set SEARCH_API_URL in .env first.")
        return []

    headers = {"User-Agent": USER_AGENT}

    if SEARCH_API_METHOD == "POST":
        # POST with JSON body (e.g. Tavily)
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
        # GET with query string (default)
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

def choose_subscription_url():
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

def create_driver(headless=False):
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return Firefox(options=options)

def type_with_delay(element, text, delay=0.05):
    """
    Types the given text into the input element with a delay between each character.
    :param element: The input element where the text will be typed.
    :param text: The text to type into the input field.
    :param delay: Delay (in seconds) between typing each character.
    """
    for char in text:
        element.send_keys(char)
        time.sleep(delay)

# Function to subscribe email using Selenium
def subscribe_email(email, url, input_fields, driver):
    try:
        driver.get(url)

        # Select checkboxes if specified in the input fields
        for checkbox in input_fields.get("checkboxes", []):
            checkbox_selector = selector_from_config(checkbox)
            if not checkbox_selector:
                continue
            try:
                checkbox_button = driver.find_element(By.CSS_SELECTOR, checkbox_selector)
                driver.execute_script("arguments[0].click();", checkbox_button)
            except Exception as ex:
                print(f"Checkbox not found/skipped ({checkbox_selector}): {ex}")

        # Fill email in all possible email fields
        for email_field in input_fields.get("email", []):
            email_selector = selector_from_config(email_field)
            if not email_selector:
                continue
            try:
                email_input = driver.find_element(By.CSS_SELECTOR, email_selector)
                type_with_delay(email_input, email, delay=random.uniform(0.03, 0.05))
                print(f"Filled email in field: {email_field}")
            except Exception as ex:
                print(f"Email field not found/skipped ({email_selector}): {ex}")

        # Select radio buttons if specified in the input fields
        for radio in input_fields.get("radios", []):
            radio_selector = selector_from_config(radio)
            if not radio_selector:
                continue
            try:
                radio_button = driver.find_element(By.CSS_SELECTOR, radio_selector)
                driver.execute_script("arguments[0].click();", radio_button)
            except Exception as ex:
                print(f"Radio not found/skipped ({radio_selector}): {ex}")

        # Click submit button using multiple possible attributes from JSON
        for submit_field in input_fields.get("submit", []):
            submit_selector = selector_from_config(submit_field)
            if not submit_selector:
                continue
            try:
                submit_button = driver.find_element(By.CSS_SELECTOR, submit_selector)
                driver.execute_script("arguments[0].click();", submit_button)
                print(f"Clicked submit button: {submit_field}")
                wait_time = input_fields.get("wait", 0)
                if wait_time:
                    print(f"Waiting for {wait_time} seconds...")
                    time.sleep(wait_time)
                print("Page navigation complete!")
                return True
            except Exception as ex:
                print(f"Submit selector not found/skipped ({submit_selector}): {ex}")

        print(f"Submit button not found for {url}")
        return False
    except Exception as e:
        print(f"Failed to subscribe {email} to {url}: {e}")
        return False

# Function to load subscription URLs from JSON file
def load_subscription_urls(verified_only=False, unverified_only=False):
    if not os.path.exists(URL_JSON):
        return []
    with open(URL_JSON, "r") as file:
        data = json.load(file)
        if verified_only:
            return [entry for entry in data if entry["verified"]]
        elif unverified_only:
            return [entry for entry in data if not entry["verified"]]
        return data

# Function to save subscription URLs to JSON file
def save_subscription_urls(data):
    with open(URL_JSON, "w") as file:
        json.dump(data, file, indent=4)


def fetch_form_elements(url, driver):
    """
    Navigate to *url*, wait for JS to settle, then collect every interactive
    form element (input, select, textarea, button).  Hidden inputs are skipped.
    Returns a list of descriptor dicts with keys:
        tag, type, id, name, class, placeholder, value, text, selector
    """
    try:
        driver.get(url)
        time.sleep(2)
    except Exception as exc:
        print(f"Failed to load {url}: {exc}")
        return []

    elements = []
    for tag in ("input", "select", "textarea", "button"):
        try:
            found = driver.find_elements(By.TAG_NAME, tag)
        except Exception:
            continue
        for el in found:
            try:
                el_type        = (el.get_attribute("type") or tag).lower()
                el_id          = el.get_attribute("id") or ""
                el_name        = el.get_attribute("name") or ""
                el_class       = (el.get_attribute("class") or "").strip()
                el_placeholder = el.get_attribute("placeholder") or ""
                el_value       = el.get_attribute("value") or ""
                el_text        = (el.text or "").strip()[:50]

                if el_type == "hidden":
                    continue

                # Build the most specific CSS selector available
                if el_id:
                    css = f"#{el_id}"
                elif el_name:
                    css = f'{tag}[name="{el_name}"]'
                elif el_class:
                    first_cls = el_class.split()[0]
                    css = f"{tag}.{first_cls}"
                else:
                    css = tag

                elements.append({
                    "tag":         tag,
                    "type":        el_type,
                    "id":          el_id,
                    "name":        el_name,
                    "class":       el_class,
                    "placeholder": el_placeholder,
                    "value":       el_value,
                    "text":        el_text,
                    "selector":    css,
                })
            except Exception:
                continue
    return elements


def print_elements_table(elements):
    """Print a numbered table of discovered form elements."""
    print(f"\n  {'#':<4} {'TAG / TYPE':<24} {'ID':<22} {'NAME':<22} HINT")
    print("  " + "-" * 92)
    for i, el in enumerate(elements, start=1):
        tag_type = f"{el['tag']}[{el['type']}]" if el["type"] not in ("", el["tag"]) else el["tag"]
        hint     = el["placeholder"] or el["text"] or el["value"]
        print(f"  {i:<4} {tag_type:<24} {el['id']:<22} {el['name']:<22} {hint[:28]}")
    print()


def pick_selectors_interactively(elements, prompt, fallback_default=""):
    """
    Ask the user to pick form elements by number(s) or type raw CSS.
    - Numbers: "1" or "1,3,5"  → maps to elements[n-1]["selector"]
    - Anything else             → treated as raw comma-separated CSS
    - Blank                     → uses fallback_default (if given)
    Returns a list of {"css": "..."} dicts.
    """
    if elements:
        print_elements_table(elements)

    hint = f" [default: {fallback_default}]" if fallback_default else " (optional)"
    raw = input(f"  {prompt}{hint}\n  > ").strip()

    if not raw:
        return parse_css_selector_list(fallback_default) if fallback_default else []

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if all(p.isdigit() for p in parts):
        result = []
        for p in parts:
            idx = int(p) - 1
            if 0 <= idx < len(elements):
                result.append({"css": elements[idx]["selector"]})
                print(f"    ✔ Selected: {elements[idx]['selector']}")
            else:
                print(f"    ⚠ Index {p} out of range, skipped.")
        return result

    # Raw CSS fallback
    return parse_css_selector_list(raw)


# Add new subscription URLs to JSON file
def add_subscription_url():
    url = choose_subscription_url()
    if not url:
        print("URL cannot be empty.")
        return

    data = load_subscription_urls()
    if any(entry.get("url", "").strip() == url for entry in data):
        print("URL already exists in list.")
        return

    # --- Open browser and scrape all form elements ---
    print("\nOpening browser to inspect form elements…")
    driver = create_driver(headless=False)
    elements = fetch_form_elements(url, driver)
    driver.quit()

    if not elements:
        print("No form elements detected – falling back to manual CSS entry.")

    # Categorise for focused sub-lists
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
        }
    })
    save_subscription_urls(data)
    print("URL added successfully as unverified!")


# Modify subscription file (manual verification)
def modify_subscription_file():
    data = load_subscription_urls()
    if not data:
        print("No subscription URLs found.")
        return

    for index, entry in enumerate(data):
        status = "✔ Verified" if entry["verified"] else "❌ Unverified"
        print(f"{index + 1}. {entry['url']} - {status}")

    print("Actions: t=toggle verified, d=delete, q=quit")
    action = input("Choose action: ").strip().lower()
    if action == "q":
        return

    choice = input("Enter the number to modify: ").strip()
    if choice.lower() == 'q':
        return
    try:
        idx = int(choice) - 1
        if action == "t":
            data[idx]["verified"] = not data[idx]["verified"]
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

# Verify mode: test unverified URLs and mark them verified if successful
def verify_mode():
    if not EMAILS:
        print("No EMAILS found in .env. Please set EMAILS=email1,email2 first.")
        return

    data = load_subscription_urls()
    if not data:
        print("No URLs found.")
        return

    unverified_urls = load_subscription_urls(unverified_only=True)
    if not unverified_urls:
        print("No unverified URLs found.")
        return

    imap_enabled = all([IMAP_HOST, IMAP_USER, IMAP_PASS])
    if imap_enabled:
        print(f"[IMAP] Inbox verification enabled (host={IMAP_HOST}, folder={IMAP_FOLDER}, "
              f"timeout={IMAP_TIMEOUT}s).")
    else:
        print("[IMAP] IMAP not configured – verification will rely on form-submit success only.")

    driver = create_driver(headless=False)

    any_changed = False
    for entry in unverified_urls:
        url = entry["url"]
        verification = entry.get("verification", {})
        sender_hint = verification.get("sender_hint", "")
        subject_hint = verification.get("subject_hint", "")
        verified_now = False

        for email_addr in EMAILS:
            # ── Snapshot the inbox BEFORE submitting the form ──────────────
            known_uids = get_inbox_uids() if imap_enabled else None

            success = subscribe_email(email_addr, url.strip(), entry.get("input_fields", {}), driver)

            if success:
                if imap_enabled:
                    print(f"[IMAP] Form submitted for {url} – polling inbox for confirmation…")
                    inbox_confirmed = check_inbox_for_new_email(
                        known_uids,
                        sender_hint=sender_hint,
                        subject_hint=subject_hint,
                    )
                    if inbox_confirmed:
                        verified_now = True
                        print(f"[IMAP] URL verified via inbox: {url}")
                    else:
                        print(f"[IMAP] No confirmation email received for {url}")
                else:
                    # Fallback: treat a successful form submission as verified
                    verified_now = True
                    print(f"URL verified (form submit): {url}")

            if verified_now:
                break

        if verified_now:
            for saved_entry in data:
                if saved_entry.get("url", "").strip() == url.strip():
                    saved_entry["verified"] = True
                    any_changed = True
                    break
        else:
            print(f"URL failed verification: {url}")

    if any_changed:
        save_subscription_urls(data)
        print("Verification updates saved.")

    driver.quit()
    print("Verification process completed.")

# Attack mode: run subscriptions only on verified URLs
def attack_mode():
    if not EMAILS:
        print("No EMAILS found in .env. Please set EMAILS=email1,email2 first.")
        return

    verified_urls = load_subscription_urls(verified_only=True)
    if not verified_urls:
        print("No verified URLs found.")
        return

    driver = create_driver(headless=True)
    success_count = 0
    fail_count = 0

    for email in EMAILS:
        for entry in verified_urls:
            url = entry["url"]
            input_fields = entry.get("input_fields", {"email": [{"css": "input[type='email']"}]})
            if subscribe_email(email, url.strip(), input_fields, driver):
                success_count += 1
            else:
                fail_count += 1

    driver.quit()
    print(f"Attack mode completed. Success: {success_count}, Failed: {fail_count}")

# Main menu
def main():

    verified_urls = load_subscription_urls(verified_only=True)
    unverified_urls = load_subscription_urls(unverified_only=True)

    print(f"Current verified URLs: {len(verified_urls)}")
    print(f"Current unverified URLs: {len(unverified_urls)}")

    while True:
        print("=== Subscription Bot ===")
        print("1. Add Subscription URL")
        print("2. Modify Email Subscription List")
        print("3. Verify Mode (Test Unverified URLs)")
        print("4. Attack Mode (Use Verified URLs)")
        print("5. Exit")
        
        choice = input("Choose an option: ").strip()
        if choice == '1':
            add_subscription_url()
        elif choice == '2':
            modify_subscription_file()
        elif choice == '3':
            verify_mode()
        elif choice == '4':
            attack_mode()
        elif choice == '5':
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
