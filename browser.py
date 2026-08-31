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
from urllib.parse import urljoin, urlsplit, urlunsplit

from selenium.webdriver import Firefox
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from config import AUTO_PAGE_WAIT, AUTO_ROBOTS_USER_AGENT
from selector_utils import selector_from_config, parse_css_selector_list


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def create_driver(headless: bool = False, discovery: bool = False) -> Firefox:
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if discovery:
        options.set_preference(
            "general.useragent.override",
            f"Mozilla/5.0 (compatible; {AUTO_ROBOTS_USER_AGENT}/1.0)",
        )
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


def _find_configured_element(driver, field: dict):
    """Locate a configured element, entering its iframe when necessary."""
    driver.switch_to.default_content()
    frame_index = field.get("frame_index")
    if isinstance(frame_index, int):
        frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
        driver.switch_to.frame(frames[frame_index])
    return driver.find_element(By.CSS_SELECTOR, selector_from_config(field))


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
                el = _find_configured_element(driver, checkbox)
                driver.execute_script("arguments[0].click();", el)
            except Exception as ex:
                print(f"Checkbox not found/skipped ({css}): {ex}")
            finally:
                driver.switch_to.default_content()

        # Email field(s)
        for email_field in input_fields.get("email", []):
            css = selector_from_config(email_field)
            if not css:
                continue
            try:
                el = _find_configured_element(driver, email_field)
                type_with_delay(el, email, delay=random.uniform(0.03, 0.05))
                print(f"Filled email in field: {email_field}")
            except Exception as ex:
                print(f"Email field not found/skipped ({css}): {ex}")
            finally:
                driver.switch_to.default_content()

        # Radio buttons
        for radio in input_fields.get("radios", []):
            css = selector_from_config(radio)
            if not css:
                continue
            try:
                el = _find_configured_element(driver, radio)
                driver.execute_script("arguments[0].click();", el)
            except Exception as ex:
                print(f"Radio not found/skipped ({css}): {ex}")
            finally:
                driver.switch_to.default_content()

        # Submit button
        for submit_field in input_fields.get("submit", []):
            css = selector_from_config(submit_field)
            if not css:
                continue
            try:
                el = _find_configured_element(driver, submit_field)
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
            finally:
                driver.switch_to.default_content()

        print(f"Submit button not found for {url}")
        return False
    except Exception as e:
        print(f"Failed to subscribe {email} to {url}: {e}")
        return False


# ---------------------------------------------------------------------------
# Form inspection
# ---------------------------------------------------------------------------

def _collect_form_elements(driver, frame_index: int | None = None) -> list[dict]:
    """Collect form controls from the driver's current browsing context."""
    elements = []
    for tag in ("input", "select", "textarea", "button"):
        try:
            found = driver.find_elements(By.TAG_NAME, tag)
        except Exception:
            continue
        for el in found:
            try:
                if el.is_displayed() is False:
                    continue
                el_type        = (el.get_attribute("type") or tag).lower()
                el_id          = el.get_attribute("id") or ""
                el_name        = el.get_attribute("name") or ""
                el_class       = (el.get_attribute("class") or "").strip()
                el_placeholder = el.get_attribute("placeholder") or ""
                el_autocomplete = el.get_attribute("autocomplete") or ""
                el_aria_label  = el.get_attribute("aria-label") or ""
                required_attr  = el.get_attribute("required")
                el_required    = (
                    bool(required_attr)
                    and str(required_attr).lower() != "false"
                )
                el_value       = el.get_attribute("value") or ""
                el_text        = (el.text or "").strip()[:100]
                form_index = driver.execute_script(
                    "return arguments[0].form ? "
                    "Array.from(document.forms).indexOf(arguments[0].form) : -1;",
                    el,
                )
                if not isinstance(form_index, int):
                    form_index = -1

                if el_type == "hidden":
                    continue

                if el_id:
                    css = f"#{el_id}"
                elif el_name:
                    css = f'{tag}[name="{el_name}"]'
                elif el_class:
                    css = f"{tag}.{el_class.split()[0]}"
                elif tag == "input" and el_type not in ("input", "text"):
                    css = f'input[type="{el_type}"]'
                elif tag == "button" and el_type == "submit":
                    css = 'button[type="submit"]'
                else:
                    css = tag

                elements.append({
                    "tag":          tag,
                    "type":         el_type,
                    "id":           el_id,
                    "name":         el_name,
                    "class":        el_class,
                    "placeholder":  el_placeholder,
                    "autocomplete": el_autocomplete,
                    "aria_label":   el_aria_label,
                    "required":     el_required,
                    "value":        el_value,
                    "text":         el_text,
                    "selector":     css,
                    "frame_index":  frame_index,
                    "form_index":   form_index,
                })
            except Exception:
                continue
    return elements


def fetch_form_elements(url: str, driver) -> list[dict]:
    """
    Navigate to *url*, wait for JS to settle, then collect every interactive
    form element (input, select, textarea, button).  Hidden inputs are skipped.

    Each element is described as a dict with keys:
        tag, type, id, name, class, placeholder, autocomplete, aria_label,
        required, value, text, selector, frame_index, form_index
    The *selector* is the most specific CSS selector derivable from the element.
    """
    try:
        driver.get(url)
        try:
            WebDriverWait(driver, AUTO_PAGE_WAIT).until(
                lambda current: current.execute_script(
                    "return document.readyState"
                ) in ("interactive", "complete")
            )
        except Exception:
            pass
    except Exception as exc:
        print(f"Failed to load {url}: {exc}")
        return []

    driver.switch_to.default_content()
    elements = _collect_form_elements(driver)
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
    except Exception:
        frames = []
    for frame_index, frame in enumerate(frames):
        try:
            driver.switch_to.frame(frame)
            elements.extend(_collect_form_elements(driver, frame_index))
        except Exception:
            continue
        finally:
            driver.switch_to.default_content()
    return elements


def find_subscription_links(base_url: str, driver, limit: int = 3) -> list[str]:
    """Rank same-site links that are likely to lead to a newsletter form."""
    if limit <= 0:
        return []
    try:
        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href]")
    except Exception:
        return []

    base = urlsplit(base_url)
    ranked = []
    seen = set()
    positive_terms = (
        "newsletter", "subscribe", "subscription", "sign-up", "signup",
        "email-updates", "email updates", "mailing-list", "mailing list",
    )
    for index, anchor in enumerate(anchors):
        try:
            href = anchor.get_attribute("href") or ""
            absolute = urlsplit(urljoin(base_url, href))
            if (
                absolute.scheme not in ("http", "https")
                or absolute.hostname != base.hostname
            ):
                continue
            url = urlunsplit((
                absolute.scheme.lower(), absolute.netloc.lower(),
                absolute.path or "/", absolute.query, "",
            ))
            if url == base_url or url in seen:
                continue
            text = " ".join((
                absolute.path, absolute.query, anchor.text or "",
                anchor.get_attribute("title") or "",
                anchor.get_attribute("aria-label") or "",
            )).lower()
            if "unsubscribe" in text:
                continue
            score = sum(1 for term in positive_terms if term in text)
            if score:
                ranked.append((score, -index, url))
                seen.add(url)
        except Exception:
            continue
    ranked.sort(reverse=True)
    return [item[2] for item in ranked[:limit]]


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
            "aria_label", "value", "text",
        )
        return " ".join(str(element.get(key, "")) for key in keys).lower()

    def selector_for(element: dict) -> list[dict]:
        selector = str(element.get("selector", "")).strip()
        if not selector:
            return []
        configured = {"css": selector}
        frame_index = element.get("frame_index")
        if isinstance(frame_index, int):
            configured["frame_index"] = frame_index
        return [configured]

    email_candidates = []
    submit_candidates = []

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

    pairs = []
    for email_score, email_order, email_element in email_candidates:
        for submit_score, submit_order, submit_element in submit_candidates:
            if email_element.get("frame_index") != submit_element.get("frame_index"):
                continue
            email_form = email_element.get("form_index", -1)
            submit_form = submit_element.get("form_index", -1)
            if email_form != submit_form and (
                email_form >= 0 or submit_form >= 0
            ):
                continue
            same_form_bonus = 100 if email_form >= 0 and email_form == submit_form else 0
            pairs.append((
                email_score + submit_score + same_form_bonus,
                email_order + submit_order,
                email_element,
                submit_element,
            ))

    pairs.sort(reverse=True, key=lambda item: (item[0], item[1]))
    if pairs:
        _, _, selected_email, selected_submit = pairs[0]
        selected_frame = selected_email.get("frame_index")
        selected_form = selected_email.get("form_index", -1)
        consent_checkboxes = []
        for element in elements:
            if (
                str(element.get("type", "")).lower() == "checkbox"
                and element.get("required")
                and element.get("frame_index") == selected_frame
                and (
                    selected_form < 0
                    or element.get("form_index", -1) == selected_form
                )
            ):
                consent_checkboxes.extend(selector_for(element))
    else:
        selected_email = None
        selected_submit = None
        consent_checkboxes = []

    return {
        "email": selector_for(selected_email) if selected_email else [],
        "username": [],
        "phone": [],
        "submit": selector_for(selected_submit) if selected_submit else [],
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
