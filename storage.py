"""
storage.py – JSON persistence for the subscription URL list.
"""
import json
import os

from config import URL_JSON


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
    if not os.path.exists(URL_JSON):
        return []
    with open(URL_JSON, "r") as f:
        data = json.load(f)
    if verified_only:
        return [e for e in data if e.get("verified")]
    if unverified_only:
        return [e for e in data if not e.get("verified")]
    return data


def save_subscription_urls(data: list[dict]) -> None:
    """Persist *data* to *URL_JSON* with 4-space indentation."""
    with open(URL_JSON, "w") as f:
        json.dump(data, f, indent=4)
