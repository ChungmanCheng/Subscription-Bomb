"""
storage.py – JSON persistence for the subscription URL list.
"""
import json
import os

from config import URL_JSON


def subscription_storage_path() -> str:
    """Return the absolute path used for subscription persistence."""
    return os.path.abspath(URL_JSON)


def load_subscription_urls(verified_only: bool = False,
                            unverified_only: bool = False) -> list[dict]:
    """
    Load the subscription URL list from *URL_JSON*.

    Parameters
    ----------
    verified_only   : return only entries where verified == True
    unverified_only : return only entries where verified == False
    (both False)    : return all entries

    Returns an empty list if the file does not exist.
    """
    path = subscription_storage_path()
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if verified_only:
        return [e for e in data if e.get("verified")]
    if unverified_only:
        return [e for e in data if not e.get("verified")]
    return data


def save_subscription_urls(data: list[dict]) -> None:
    """Persist *data* to *URL_JSON* with 4-space indentation."""
    path = subscription_storage_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        f.write("\n")
    print(f"Saved {len(data)} subscription URL(s) to {path}")
