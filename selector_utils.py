"""
selector_utils.py – CSS selector building and JSON path helpers.
Pure utility functions with no side-effects and no external dependencies.
"""


def selector_from_config(field_config) -> str:
    """
    Build a CSS selector string from a field config dict.

    Supported formats:
      {"css": "input[type='email']"}       – raw CSS, returned as-is
      {"id": "email"}                      – becomes #email
      {"class": "btn"}                     – becomes .btn
      {"name": "subscribe"}                – becomes [name="subscribe"]
      {"value": "Sign Up"}                 – becomes [value="Sign Up"]
    Multiple attribute keys can be combined (e.g. class + id).
    """
    if not isinstance(field_config, dict):
        return ""

    raw_css = field_config.get("css", "").strip()
    if raw_css:
        return raw_css

    selector = ""
    if field_config.get("class"):
        selector += f'.{field_config["class"]}'
    if field_config.get("id"):
        selector += f'#{field_config["id"]}'
    if field_config.get("name"):
        selector += f'[name="{field_config["name"]}"]'
    if field_config.get("value"):
        selector += f'[value="{field_config["value"]}"]'
    return selector


def parse_css_selector_list(raw_input: str) -> list[dict]:
    """
    Split a comma-separated CSS selector string into a list of {"css": "..."} dicts.
    Blank / whitespace-only selectors are ignored.

    Example:
        "button[type='submit'], input[type='submit']"
        → [{"css": "button[type='submit']"}, {"css": "input[type='submit']"}]
    """
    return [
        {"css": s.strip()}
        for s in raw_input.split(",")
        if s.strip()
    ]


def get_nested_value(data, path: str):
    """
    Traverse a nested dict/list structure using a dot-separated path string.
    List indices are expressed as integers within the path.

    Examples:
        get_nested_value({"a": {"b": 1}}, "a.b")          → 1
        get_nested_value({"r": [{"url": "x"}]}, "r.0.url") → "x"

    Returns None for any missing key, out-of-bounds index, or type mismatch.
    """
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
