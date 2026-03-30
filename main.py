import os
import json
import time
import random
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

# Add new subscription URLs to JSON file
def add_subscription_url():
    url = input("Enter the subscription URL: ").strip()
    if not url:
        print("URL cannot be empty.")
        return

    data = load_subscription_urls()
    if any(entry.get("url", "").strip() == url for entry in data):
        print("URL already exists in list.")
        return

    print("Enter CSS selectors separated by commas.")
    print("Example: input[type='email'], #email")

    email_selectors = input("Email field selector(s) [default: input[type='email']]: ").strip()
    submit_selectors = input("Submit selector(s) [default: button[type='submit'], input[type='submit']]: ").strip()
    checkbox_selectors = input("Checkbox selector(s) (optional): ").strip()
    radio_selectors = input("Radio selector(s) (optional): ").strip()
    wait_seconds_raw = input("Wait seconds after submit [default 0]: ").strip()

    if not email_selectors:
        email_selectors = "input[type='email']"
    if not submit_selectors:
        submit_selectors = "button[type='submit'], input[type='submit']"

    try:
        wait_seconds = int(wait_seconds_raw) if wait_seconds_raw else 0
    except ValueError:
        wait_seconds = 0

    data.append(
        {
            "url": url, 
            "verified": False,
            "input_fields": {
                "email": parse_css_selector_list(email_selectors),
                "username": [],
                "phone": [],
                "submit": parse_css_selector_list(submit_selectors),
                "radios": parse_css_selector_list(radio_selectors),
                "checkboxes": parse_css_selector_list(checkbox_selectors),
                "selections":[

                ],
                "wait": wait_seconds
            }
        }
    )
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

    driver = create_driver(headless=False)

    any_changed = False
    for entry in unverified_urls:
        url = entry["url"]
        verified_now = False
        for email in EMAILS:
            success = subscribe_email(email, url.strip(), entry.get("input_fields", {}), driver)
            if success:
                verified_now = True
                print(f"URL verified: {url}")
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
