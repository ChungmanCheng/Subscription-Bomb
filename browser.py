"""
browser.py – Selenium/geckodriver helpers.

Responsibilities:
  - Driver lifecycle  (create_driver)
  - Human-like typing (type_with_delay)
  - Form submission   (subscribe_email)
  - Form inspection   (fetch_form_elements, print_elements_table,
                       pick_selectors_interactively)
"""
import time
import random
import os

from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from undetected_geckodriver import Firefox

from selector_utils import selector_from_config, parse_css_selector_list


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def create_driver(headless: bool = False) -> Firefox:
    options = Options()
    accept_insecure = os.getenv("SUBSCRIPTION_BOMB_ACCEPT_INSECURE_ALERTS", "").lower() == "true"
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.set_capability("unhandledPromptBehavior", "accept" if accept_insecure else "dismiss")
    if accept_insecure:
        options.set_preference("security.warn_submit_secure_to_insecure", False)
    return Firefox(options=options)


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def type_with_delay(element, text: str, delay: float = 0.05) -> None:
    """Type *text* into *element* one character at a time with a small delay
    to mimic human keyboard input."""
    for char in text:
        element.send_keys(char)
        time.sleep(delay)


def fill_text_input(driver, element, text: str) -> None:
    """
    Fill a text input using normal keyboard interaction, with a JS fallback for
    inputs Selenium can locate but cannot interact with directly.
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        element.clear()
        type_with_delay(element, text, delay=random.uniform(0.03, 0.05))
    except Exception:
        driver.execute_script(
            """
            const el = arguments[0];
            const value = arguments[1];
            el.focus();
            el.value = value;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            """,
            element,
            text,
        )


def click_element(driver, element) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    driver.execute_script("arguments[0].click();", element)


def is_unstable_value_only_choice(field_config: dict) -> bool:
    if not isinstance(field_config, dict):
        return False
    value = str(field_config.get("value") or "")
    css = str(field_config.get("css") or "")
    has_stable_hint = any(field_config.get(key) for key in ("id", "name", "class", "text"))
    if has_stable_hint or not value:
        return False
    if len(value) > 8 or not value.isalnum():
        return False
    return "[value=" in css or not css


def handle_unexpected_alert(driver) -> bool:
    """
    Handle browser confirmation dialogs. Insecure-form prompts are only accepted
    when explicitly enabled via SUBSCRIPTION_BOMB_ACCEPT_INSECURE_ALERTS=true.
    """
    try:
        alert = driver.switch_to.alert
        text = alert.text or ""
        accept_insecure = os.getenv("SUBSCRIPTION_BOMB_ACCEPT_INSECURE_ALERTS", "").lower() == "true"
        if accept_insecure and "insecure connection" in text.lower():
            alert.accept()
            print("Accepted insecure form confirmation dialog.")
            return True
        alert.dismiss()
        print(f"Dismissed browser confirmation dialog: {text}")
    except Exception as ex:
        print(f"Unable to handle browser confirmation dialog: {ex}")
    return False


def has_unexpected_alert(exc: Exception) -> bool:
    name = type(exc).__name__
    return name in {"UnexpectedAlertPresentException", "UnexpectedAlertOpenError"} or (
        "Unexpected" in name and "Alert" in name
    )


def handle_open_alert_if_present(driver) -> bool | None:
    try:
        alert = driver.switch_to.alert
        if not isinstance(alert.text, str):
            return None
    except Exception:
        return None
    return handle_unexpected_alert(driver)


def wait_after_submit(driver, input_fields: dict) -> bool:
    wait_time = input_fields.get("wait", 0)
    if wait_time:
        print(f"Waiting for {wait_time} seconds...")
        time.sleep(wait_time)
    alert_result = handle_open_alert_if_present(driver)
    if alert_result is not None:
        return alert_result
    print("Page navigation complete!")
    return True


def submit_candidate_label(element) -> str:
    parts = []
    for attr in ("value", "aria-label", "title", "name", "id", "type"):
        try:
            parts.append(element.get_attribute(attr) or "")
        except Exception:
            continue
    try:
        parts.append(element.text or "")
    except Exception:
        pass
    return " ".join(parts).lower()


def looks_like_subscription_submit(element, allow_unlabeled_submit: bool = False) -> bool:
    label = submit_candidate_label(element)
    reject_words = ("search", "comment", "contact", "login", "log in", "sign in")
    if any(word in label for word in reject_words):
        return False

    positive_words = ("subscribe", "sign up", "signup", "join", "newsletter")
    if any(word in label for word in positive_words):
        return True

    try:
        element_type = (element.get_attribute("type") or "").lower()
    except Exception:
        element_type = ""
    return allow_unlabeled_submit and element_type == "submit"


def fallback_submit_buttons(driver, email_elements: list) -> list:
    selectors = "button[type='submit'], input[type='submit'], button, input[type='button'], [role='button']"
    candidates = []
    for email_element in email_elements:
        try:
            candidates.extend(driver.execute_script(
                """
                const input = arguments[0];
                const selector = arguments[1];
                const form = input.closest('form');
                if (!form) return [];
                return Array.from(form.querySelectorAll(selector));
                """,
                email_element,
                selectors,
            ) or [])
        except Exception:
            continue

    form_matches = [
        candidate
        for candidate in candidates
        if looks_like_subscription_submit(candidate, allow_unlabeled_submit=True)
    ]
    if form_matches:
        return form_matches

    try:
        page_candidates = driver.find_elements(By.CSS_SELECTOR, selectors)
    except Exception:
        return []
    return [
        candidate
        for candidate in page_candidates
        if looks_like_subscription_submit(candidate, allow_unlabeled_submit=False)
    ]


# ---------------------------------------------------------------------------
# Form submission
# ---------------------------------------------------------------------------

def subscribe_email(email: str, url: str, input_fields: dict, driver) -> bool:
    """
    Navigate to *url*, fill the email field(s), tick checkboxes / radio
    buttons, and click submit.

    Returns True if a submit button was successfully clicked, False otherwise.
    """
    try:
        driver.get(url)

        # Checkboxes
        for checkbox in input_fields.get("checkboxes", []):
            if is_unstable_value_only_choice(checkbox):
                print(f"Checkbox skipped unstable value-only selector: {checkbox}")
                continue
            css = selector_from_config(checkbox)
            if not css:
                continue
            try:
                el = driver.find_element(By.CSS_SELECTOR, css)
                click_element(driver, el)
            except Exception as ex:
                print(f"Checkbox not found/skipped ({css}): {ex}")

        # Email field(s)
        email_filled = False
        filled_email_elements = []
        for email_field in input_fields.get("email", []):
            css = selector_from_config(email_field)
            if not css:
                continue
            try:
                el = driver.find_element(By.CSS_SELECTOR, css)
                fill_text_input(driver, el, email)
                email_filled = True
                filled_email_elements.append(el)
                print(f"Filled email in field: {email_field}")
            except Exception as ex:
                print(f"Email field not found/skipped ({css}): {ex}")

        if not email_filled:
            print(f"No email field could be filled for {url}; skipping submit.")
            return False

        # Radio buttons
        for radio in input_fields.get("radios", []):
            if is_unstable_value_only_choice(radio):
                print(f"Radio skipped unstable value-only selector: {radio}")
                continue
            css = selector_from_config(radio)
            if not css:
                continue
            try:
                el = driver.find_element(By.CSS_SELECTOR, css)
                click_element(driver, el)
            except Exception as ex:
                print(f"Radio not found/skipped ({css}): {ex}")

        # Submit button
        for submit_field in input_fields.get("submit", []):
            css = selector_from_config(submit_field)
            if not css:
                continue
            try:
                el = driver.find_element(By.CSS_SELECTOR, css)
                click_element(driver, el)
                print(f"Clicked submit button: {submit_field}")
                return wait_after_submit(driver, input_fields)
            except Exception as ex:
                if has_unexpected_alert(ex):
                    return handle_unexpected_alert(driver)
                print(f"Submit selector not found/skipped ({css}): {ex}")

        for fallback in fallback_submit_buttons(driver, filled_email_elements):
            try:
                click_element(driver, fallback)
                print("Clicked fallback submit button.")
                return wait_after_submit(driver, input_fields)
            except Exception as ex:
                if has_unexpected_alert(ex):
                    return handle_unexpected_alert(driver)
                print(f"Fallback submit button skipped: {ex}")

        print(f"Submit button not found for {url}")
        return False
    except Exception as e:
        if has_unexpected_alert(e):
            return handle_unexpected_alert(driver)
        print(f"Failed to subscribe {email} to {url}: {e}")
        return False


# ---------------------------------------------------------------------------
# Form inspection
# ---------------------------------------------------------------------------

def fetch_form_elements(url: str, driver) -> list[dict]:
    """
    Navigate to *url*, wait for JS to settle, then collect every interactive
    form element (input, select, textarea, button).  Hidden inputs are skipped.

    Each element is described as a dict with keys:
        tag, type, id, name, class, placeholder, value, text, selector
    The *selector* is the most specific CSS selector derivable from the element.
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

                if el_id:
                    css = f"#{el_id}"
                elif el_name:
                    css = f'{tag}[name="{el_name}"]'
                elif el_class:
                    css = f"{tag}.{el_class.split()[0]}"
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


def print_elements_table(elements: list[dict]) -> None:
    """Print a numbered table of discovered form elements to stdout."""
    print(f"\n  {'#':<4} {'TAG / TYPE':<24} {'ID':<22} {'NAME':<22} HINT")
    print("  " + "-" * 92)
    for i, el in enumerate(elements, start=1):
        tag_type = (
            f"{el['tag']}[{el['type']}]"
            if el["type"] not in ("", el["tag"])
            else el["tag"]
        )
        hint = el["placeholder"] or el["text"] or el["value"]
        print(f"  {i:<4} {tag_type:<24} {el['id']:<22} {el['name']:<22} {hint[:28]}")
    print()


def pick_selectors_interactively(elements: list[dict], prompt: str,
                                  fallback_default: str = "") -> list[dict]:
    """
    Prompt the user to assign selectors for a specific field category.

    Input options:
      - Number(s): "1" or "1,3"  → maps to elements[n-1]["selector"]
      - Raw CSS  : any other text → split on commas and used directly
      - Blank    : uses *fallback_default* if provided, otherwise returns []

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

    return parse_css_selector_list(raw)
