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
modes.py         – Automatic discovery, manual add, modify, verify, attack
main.py          – CLI menu (this file)
"""
from storage import load_subscription_urls
from modes import (
    add_subscription_url,
    add_subscription_url_interactive,
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
        print("1. Fully Automatic Newsletter Discovery")
        print("2. Add Subscription URL Manually")
        print("3. Modify Email Subscription List")
        print("4. Verify Mode (Test Unverified URLs)")
        print("5. Attack Mode (Use Verified URLs)")
        print("6. Exit")

        choice = input("Choose an option: ").strip()
        if choice == "1":
            add_subscription_url()
        elif choice == "2":
            add_subscription_url_interactive()
        elif choice == "3":
            modify_subscription_file()
        elif choice == "4":
            verify_mode()
        elif choice == "5":
            attack_mode()
        elif choice == "6":
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
