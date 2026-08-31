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
import random
import re
import time
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
    selector = selector_from_config(field)
    occurrence = field.get("index", 0)
    if field.get("visible"):
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            if element.is_displayed():
                return element
        raise LookupError(f"No visible element matched {selector}")
    if isinstance(occurrence, int) and occurrence > 0:
        return driver.find_elements(By.CSS_SELECTOR, selector)[occurrence]
    return driver.find_element(By.CSS_SELECTOR, selector)


def _find_configured_element_with_timeout(driver, field: dict):
    """Retry a configured selector while client-side UI finishes rendering."""
    deadline = time.monotonic() + AUTO_PAGE_WAIT
    while True:
        try:
            return _find_configured_element(driver, field)
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)


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

        # Some newsletter hubs require choosing a newsletter before revealing
        # the actual signup form. Discovery stores those safe, non-submit
        # button clicks so the subscription run can reproduce the same state.
        for action in input_fields.get("pre_clicks", []):
            css = selector_from_config(action)
            if not css:
                continue
            try:
                el = _find_configured_element_with_timeout(driver, action)
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", el
                )
                driver.execute_script("arguments[0].click();", el)
            except Exception as ex:
                print(f"Signup reveal action not found/skipped ({css}): {ex}")
            finally:
                driver.switch_to.default_content()

        if input_fields.get("pre_clicks") and input_fields.get("email"):
            deadline = time.monotonic() + AUTO_PAGE_WAIT
            while True:
                try:
                    _find_configured_element(driver, input_fields["email"][0])
                    break
                except Exception:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.2)
                finally:
                    driver.switch_to.default_content()

        # Checkboxes
        for checkbox in input_fields.get("checkboxes", []):
            css = selector_from_config(checkbox)
            if not css:
                continue
            try:
                el = _find_configured_element_with_timeout(driver, checkbox)
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
                el = _find_configured_element_with_timeout(driver, email_field)
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
                el = _find_configured_element_with_timeout(driver, radio)
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
                el = _find_configured_element_with_timeout(driver, submit_field)
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


def validate_subscription_mapping(
    url: str, input_fields: dict, driver
) -> bool:
    """Prove saved selectors work after a fresh load without submitting.

    Discovery can observe ephemeral React IDs or controls that exist only in
    the current DOM state. This reloads the resolved URL, replays safe reveal
    buttons, and requires a visible email field plus a resolvable submit
    control. It never types into or submits the form.
    """
    email_fields = input_fields.get("email", [])
    submit_fields = input_fields.get("submit", [])
    if not email_fields or not submit_fields:
        return False

    try:
        driver.get(url)
        for action in input_fields.get("pre_clicks", []):
            element = _find_configured_element_with_timeout(driver, action)
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
            driver.execute_script("arguments[0].click();", element)
            driver.switch_to.default_content()

        email_element = _find_configured_element_with_timeout(
            driver, email_fields[0]
        )
        if email_element.is_displayed() is False:
            return False
        driver.switch_to.default_content()
        _find_configured_element_with_timeout(driver, submit_fields[0])
        return True
    except Exception as exc:
        print(f"  Fresh-load selector replay failed: {exc}")
        return False
    finally:
        driver.switch_to.default_content()


# ---------------------------------------------------------------------------
# Form inspection
# ---------------------------------------------------------------------------

def _css_string(value: str) -> str:
    """Escape a value for a double-quoted CSS attribute selector."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _safe_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", value))


def _stable_id(value: str) -> bool:
    """Reject syntactically valid IDs that are likely generated per render."""
    if not _safe_id(value):
        return False
    if re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{8,}",
        value,
        re.IGNORECASE,
    ):
        return False
    return re.search(r"\d{5,}", value) is None


def _form_selector(form) -> str:
    """Return a stable selector for a form when one is available."""
    if not form:
        return ""
    try:
        form_id = form.get_attribute("id") or ""
        if _stable_id(form_id):
            return f"#{form_id}"
        aria = form.get_attribute("aria-label") or ""
        if aria:
            return f'form[aria-label="{_css_string(aria)}"]'
        name = form.get_attribute("name") or ""
        if name:
            return f'form[name="{_css_string(name)}"]'
    except Exception:
        pass
    return ""


def _element_selector(el, tag: str, el_type: str, form=None) -> str:
    """Build a repeatable selector, preferring semantic attributes."""
    el_id = el.get_attribute("id") or ""
    el_name = el.get_attribute("name") or ""
    el_class = (el.get_attribute("class") or "").strip()
    parent = _form_selector(form)
    if el_name:
        selector = f'{tag}[name="{_css_string(el_name)}"]'
        return f"{parent} {selector}" if parent else selector

    for attr in (
        "data-zjs-newsletter", "data-list-id", "data-identity-name",
        "data-role", "aria-label", "title",
    ):
        value = el.get_attribute(attr) or ""
        if value:
            return f'{tag}[{attr}="{_css_string(value)}"]'

    if _stable_id(el_id):
        return f"#{el_id}"
    if parent:
        suffix = tag
        if el_type and el_type != tag:
            suffix += f'[type="{_css_string(el_type)}"]'
        if el.get_attribute("required"):
            suffix += "[required]"
        return f"{parent} {suffix}"
    if el_class:
        return f"{tag}.{el_class.split()[0]}"
    if tag == "input" and el_type not in ("input", "text"):
        return f'input[type="{_css_string(el_type)}"]'
    if tag == "button" and el_type == "submit":
        return 'button[type="submit"]'
    return tag


def _collect_form_elements(
    driver,
    frame_index: int | None = None,
    *,
    include_hidden_form_controls: bool = False,
) -> list[dict]:
    """Collect form controls from the driver's current browsing context."""
    elements = []
    for tag in ("input", "select", "textarea", "button"):
        try:
            found = driver.find_elements(By.TAG_NAME, tag)
        except Exception:
            continue
        for el in found:
            try:
                displayed = el.is_displayed()
                form = driver.execute_script("return arguments[0].form;", el)
                if displayed is False:
                    if not include_hidden_form_controls or not form:
                        continue
                    try:
                        if form.is_displayed() is False:
                            continue
                    except Exception:
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

                label_text = driver.execute_script(
                    "return Array.from(arguments[0].labels || [])"
                    ".map(label => label.innerText || label.textContent || '')"
                    ".join(' ');",
                    el,
                )
                if not isinstance(label_text, str):
                    label_text = ""
                form_text = ""
                form_label = ""
                if form:
                    try:
                        raw_form_text = form.text
                        if isinstance(raw_form_text, str):
                            form_text = raw_form_text[:1000]
                        form_label = form.get_attribute("aria-label") or ""
                    except Exception:
                        pass
                css = _element_selector(el, tag, el_type, form)
                selector_index = 0
                try:
                    matches = driver.find_elements(By.CSS_SELECTOR, css)
                    selector_index = matches.index(el)
                except Exception:
                    pass

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
                    "label_text":   label_text.strip()[:300],
                    "form_text":    form_text,
                    "form_label":   form_label,
                    "displayed":    displayed is not False,
                    "selector":     css,
                    "selector_index": selector_index,
                    "frame_index":  frame_index,
                    "form_index":   form_index,
                })
            except Exception:
                continue
    return elements


def _collect_page_form_elements(
    driver, *, include_hidden_form_controls: bool = False
) -> list[dict]:
    """Collect controls from the top document and first-level frames."""
    driver.switch_to.default_content()
    elements = _collect_form_elements(
        driver,
        include_hidden_form_controls=include_hidden_form_controls,
    )
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
    except Exception:
        frames = []
    for frame_index, frame in enumerate(frames):
        try:
            driver.switch_to.frame(frame)
            elements.extend(_collect_form_elements(
                driver,
                frame_index,
                include_hidden_form_controls=include_hidden_form_controls,
            ))
        except Exception:
            continue
        finally:
            driver.switch_to.default_content()
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

    return _collect_page_form_elements(driver)


def _reveal_candidates(driver) -> list[dict]:
    """Find safe non-submit buttons likely to reveal a newsletter form."""
    candidates = []
    driver.switch_to.default_content()
    contexts = [(None, None)]
    try:
        contexts.extend(enumerate(driver.find_elements(
            By.CSS_SELECTOR, "iframe, frame"
        )))
    except Exception:
        pass

    for frame_index, frame in contexts:
        try:
            driver.switch_to.default_content()
            if frame is not None:
                driver.switch_to.frame(frame)
            buttons = driver.find_elements(By.CSS_SELECTOR, 'button[type="button"]')
            for order, button in enumerate(buttons):
                if not button.is_displayed() or not button.is_enabled():
                    continue
                values = {
                    attr: button.get_attribute(attr) or ""
                    for attr in (
                        "aria-label", "title", "data-role", "data-list-id",
                        "data-identity-name", "data-zjs-newsletter",
                    )
                }
                text = " ".join((button.text or "", *values.values())).lower()
                if "remove " in text or not any(term in text for term in (
                    "newsletter", "subscribe", "sign up", "signup",
                    "subscribe list", "data-list-id",
                )) and not (
                    values["data-list-id"]
                    or values["data-identity-name"]
                    or values["data-zjs-newsletter"]
                ):
                    continue
                score = 0
                if values["data-zjs-newsletter"] or values["data-list-id"]:
                    score += 120
                if "newsletter" in text or "subscribe list" in text:
                    score += 80
                if "sign up" in text or "subscribe" in text:
                    score += 60
                selector = _element_selector(button, "button", "button")
                field = {"css": selector}
                try:
                    matches = driver.find_elements(By.CSS_SELECTOR, selector)
                    occurrence = matches.index(button)
                    if occurrence:
                        field["index"] = occurrence
                except Exception:
                    pass
                if isinstance(frame_index, int):
                    field["frame_index"] = frame_index
                candidates.append((score, -order, field))
        except Exception:
            continue
        finally:
            driver.switch_to.default_content()

    candidates.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return [item[2] for item in candidates]


def reveal_subscription_form(driver, max_actions: int = 5) -> dict | None:
    """Safely click a newsletter-choice button and infer the revealed form.

    Only visible ``type=button`` controls are considered, so discovery never
    enters an address or clicks a submit control.
    """
    for action in _reveal_candidates(driver)[:max_actions]:
        try:
            button = _find_configured_element(driver, action)
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", button
            )
            driver.execute_script("arguments[0].click();", button)
        except Exception:
            continue
        finally:
            driver.switch_to.default_content()

        deadline = time.monotonic() + min(AUTO_PAGE_WAIT, 2.0)
        while True:
            fields = infer_subscription_fields(_collect_page_form_elements(
                driver, include_hidden_form_controls=True
            ))
            if fields["email"] and fields["submit"]:
                fields["pre_clicks"] = [action]
                return fields
            if time.monotonic() >= deadline:
                break
            time.sleep(0.2)
    return None


def detect_automation_block(driver) -> str:
    """Describe a strong bot/WAF block signature, or return an empty string."""
    try:
        values = (driver.page_source, driver.title, driver.current_url)
        source, title, current = (
            value.lower() if isinstance(value, str) else ""
            for value in values
        )
    except Exception:
        return ""
    combined = " ".join((source, title, current))
    signatures = (
        ("_incapsula_resource", "Incapsula challenge"),
        ("incapsula incident id", "Incapsula access block"),
        ("cf-chl-", "Cloudflare challenge"),
        ("checking your browser", "browser verification challenge"),
        ("verify you are human", "human-verification challenge"),
    )
    for signature, description in signatures:
        if signature in combined:
            return description
    return ""


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
            if "unsubscribe" in text or any(term in text for term in (
                "/login", "/log-in", "/signin", "/sign-in", "/account",
                "/register", "redirectto=/login",
            )):
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
        # Only use evidence attached to the control itself. Broad form text is
        # shared by every input and previously caused fields such as
        # ``first_name`` to be mistaken for the email address.
        keys = (
            "id", "name", "class", "placeholder", "autocomplete",
            "aria_label", "value", "text", "label_text",
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
        selector_index = element.get("selector_index")
        if (
            isinstance(selector_index, int)
            and selector_index > 0
            and element.get("displayed") is True
        ):
            configured["visible"] = True
        elif isinstance(selector_index, int) and selector_index > 0:
            configured["index"] = selector_index
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
            if email_form >= 0 and any(
                str(other.get("type", "")).lower() == "password"
                and other.get("frame_index") == email_element.get("frame_index")
                and other.get("form_index", -1) == email_form
                for other in elements
            ):
                # Email/password forms are authentication or registration
                # flows, not safe automatic newsletter mappings.
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
        "pre_clicks": [],
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
