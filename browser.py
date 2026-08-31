"""
browser.py – Selenium/geckodriver helpers.

Responsibilities:
  - Driver lifecycle  (create_driver)
  - Human-like typing (type_with_delay)
  - Form submission   (subscribe_email)
  - Form inspection   (fetch_form_elements, print_elements_table,
                       infer_subscription_fields,
                       pick_selectors_interactively)
"""
import time
import random

from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from undetected_geckodriver import Firefox

from selector_utils import selector_from_config, parse_css_selector_list


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def create_driver(headless: bool = False) -> Firefox:
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
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
            css = selector_from_config(checkbox)
            if not css:
                continue
            try:
                el = driver.find_element(By.CSS_SELECTOR, css)
                driver.execute_script("arguments[0].click();", el)
            except Exception as ex:
                print(f"Checkbox not found/skipped ({css}): {ex}")

        # Email field(s)
        for email_field in input_fields.get("email", []):
            css = selector_from_config(email_field)
            if not css:
                continue
            try:
                el = driver.find_element(By.CSS_SELECTOR, css)
                type_with_delay(el, email, delay=random.uniform(0.03, 0.05))
                print(f"Filled email in field: {email_field}")
            except Exception as ex:
                print(f"Email field not found/skipped ({css}): {ex}")

        # Radio buttons
        for radio in input_fields.get("radios", []):
            css = selector_from_config(radio)
            if not css:
                continue
            try:
                el = driver.find_element(By.CSS_SELECTOR, css)
                driver.execute_script("arguments[0].click();", el)
            except Exception as ex:
                print(f"Radio not found/skipped ({css}): {ex}")

        # Submit button
        for submit_field in input_fields.get("submit", []):
            css = selector_from_config(submit_field)
            if not css:
                continue
            try:
                el = driver.find_element(By.CSS_SELECTOR, css)
                driver.execute_script("arguments[0].click();", el)
                print(f"Clicked submit button: {submit_field}")
                wait_time = input_fields.get("wait", 0)
                if wait_time:
                    print(f"Waiting for {wait_time} seconds...")
                    time.sleep(wait_time)
                print("Page navigation complete!")
                return True
            except Exception as ex:
                print(f"Submit selector not found/skipped ({css}): {ex}")

        print(f"Submit button not found for {url}")
        return False
    except Exception as e:
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
        tag, type, id, name, class, placeholder, autocomplete, required,
        value, text, selector
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
                el_autocomplete = el.get_attribute("autocomplete") or ""
                required_attr   = el.get_attribute("required")
                el_required     = bool(required_attr) and str(required_attr).lower() != "false"
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
                    "autocomplete": el_autocomplete,
                    "required":    el_required,
                    "value":       el_value,
                    "text":        el_text,
                    "selector":    css,
                })
            except Exception:
                continue
    return elements


def infer_subscription_fields(elements: list[dict]) -> dict:
    """Infer a newsletter form configuration from scraped elements.

    The highest-confidence email and submit controls are selected. Required
    consent checkboxes are included, while radio buttons are deliberately left
    for manual configuration because choosing an arbitrary option is unsafe.

    An empty ``email`` or ``submit`` list means automatic setup was not
    confident enough and the caller should fall back to manual selection.
    """
    def text_for(element: dict) -> str:
        keys = (
            "id", "name", "class", "placeholder", "autocomplete",
            "value", "text",
        )
        return " ".join(str(element.get(key, "")) for key in keys).lower()

    def selector_for(element: dict) -> list[dict]:
        selector = str(element.get("selector", "")).strip()
        return [{"css": selector}] if selector else []

    email_candidates = []
    submit_candidates = []
    consent_checkboxes = []

    for index, element in enumerate(elements):
        tag = str(element.get("tag", "")).lower()
        field_type = str(element.get("type", "")).lower()
        text = text_for(element)

        if field_type in ("email", "text") or tag == "textarea":
            email_score = 0
            if field_type == "email":
                email_score += 100
            if element.get("autocomplete", "").lower() == "email":
                email_score += 80
            if "email" in text or "e-mail" in text:
                email_score += 60
            if "newsletter" in text or "subscribe" in text:
                email_score += 20
            if email_score:
                email_candidates.append((email_score, -index, element))

        if field_type != "reset" and (tag in ("button", "input")):
            submit_score = 0
            if field_type == "submit":
                submit_score += 100
            if any(term in text for term in (
                "subscribe", "sign up", "signup", "join", "newsletter",
                "register", "get updates",
            )):
                submit_score += 60
            if tag == "button":
                submit_score += 10
            if submit_score >= 60:
                submit_candidates.append((submit_score, -index, element))

        if field_type == "checkbox" and element.get("required"):
            consent_checkboxes.extend(selector_for(element))

    email_candidates.sort(reverse=True, key=lambda item: (item[0], item[1]))
    submit_candidates.sort(reverse=True, key=lambda item: (item[0], item[1]))

    return {
        "email": selector_for(email_candidates[0][2]) if email_candidates else [],
        "username": [],
        "phone": [],
        "submit": selector_for(submit_candidates[0][2]) if submit_candidates else [],
        "radios": [],
        "checkboxes": consent_checkboxes,
        "selections": [],
        "wait": 0,
    }


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
