"""
main.py – Entry point for the Subscription Bot.

Module layout
-------------
config.py        – environment variables and constants
imap_utils.py    – IMAP inbox snapshot & polling
selector_utils.py – CSS selector building and JSON path helpers
browser.py       – Selenium driver, form scraping, form submission
search_api.py    – Search API integration and URL selection
storage.py       – JSON persistence (load / save subscription list)
modes.py         – Four bot modes: add / modify / verify / attack
main.py          – CLI menu (this file)
"""
from storage import load_subscription_urls
from modes import (
    add_subscription_url,
    modify_subscription_file,
    verify_mode,
    attack_mode,
)


def main() -> None:
    verified   = load_subscription_urls(verified_only=True)
    unverified = load_subscription_urls(unverified_only=True)
    print(f"Current verified URLs  : {len(verified)}")
    print(f"Current unverified URLs: {len(unverified)}")

    while True:
        print("\n=== Subscription Bot ===")
        print("1. Add Subscription URL")
        print("2. Modify Email Subscription List")
        print("3. Verify Mode (Test Unverified URLs)")
        print("4. Attack Mode (Use Verified URLs)")
        print("5. Exit")

        choice = input("Choose an option: ").strip()
        if choice == "1":
            add_subscription_url()
        elif choice == "2":
            modify_subscription_file()
        elif choice == "3":
            verify_mode()
        elif choice == "4":
            attack_mode()
        elif choice == "5":
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
