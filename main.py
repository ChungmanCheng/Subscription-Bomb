import os
import json
import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.firefox.options import Options
from undetected_geckodriver import Firefox
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Read emails from .env (comma-separated values)
EMAILS = os.getenv("EMAILS", "").split(",")

# JSON file to store subscription URLs with verification status
URL_JSON = "email_subscription.json"

# User-Agent string to spoof
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Function to initialize Selenium WebDriver with Firefox
def get_driver():
    options = Options()
    options.add_argument("--headless")  # Enable headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = Firefox(options=options)
    return driver

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
            checkbox_selector = ''
            if 'class' in checkbox:
                checkbox_selector += f'.{checkbox["class"]}'
            if 'id' in checkbox:
                checkbox_selector += f'#{checkbox["id"]}'
            if 'name' in checkbox:
                checkbox_selector += f'[name="{checkbox["name"]}"]'
            if 'value' in checkbox:
                checkbox_selector += f'[value="{checkbox["value"]}"]'
            
            if checkbox_selector:
                checkbox_button = driver.find_element(By.CSS_SELECTOR, checkbox_selector)
                if checkbox_button:
                    driver.execute_script("arguments[0].click();", checkbox_button)

        # Fill email in all possible email fields
        for email_field in input_fields.get("email", []):
            email_selector = ''
            if 'class' in email_field:
                email_selector += f'.{email_field["class"]}'
            if 'id' in email_field:
                email_selector += f'#{email_field["id"]}'
            if 'name' in email_field:
                email_selector += f'[name="{email_field["name"]}"]'
            if 'value' in email_field:
                email_selector += f'[value="{email_field["value"]}"]'

            email_input = driver.find_element(By.CSS_SELECTOR, email_selector)
            if email_input:
                type_with_delay(email_input, email, delay=random.uniform(0.03, 0.05))
                print(f"Filled email in field: {email_field}")

        # Select radio buttons if specified in the input fields
        for radio in input_fields.get("radios", []):
            radio_selector = ''
            if 'class' in radio:
                radio_selector += f'.{radio["class"]}'
            if 'id' in radio:
                radio_selector += f'#{radio["id"]}'
            if 'name' in radio:
                radio_selector += f'[name="{radio["name"]}"]'
            if 'value' in radio:
                radio_selector += f'[value="{radio["value"]}"]'

            if radio_selector:
                radio_button = driver.find_element(By.CSS_SELECTOR, radio_selector)
                if radio_button:
                    driver.execute_script("arguments[0].click();", radio_button)

        # Click submit button using multiple possible attributes from JSON
        for submit_field in input_fields.get("submit", []):
            submit_selector = ''
            if 'class' in submit_field:
                submit_selector += f'.{submit_field["class"]}'
            if 'id' in submit_field:
                submit_selector += f'#{submit_field["id"]}'
            if 'name' in submit_field:
                submit_selector += f'[name="{submit_field["name"]}"]'
            if 'value' in submit_field:
                submit_selector += f'[value="{submit_field["value"]}"]'

            submit_button = driver.find_element(By.CSS_SELECTOR, submit_selector)
            if submit_button:
                driver.execute_script("arguments[0].click();", submit_button)
                print(f"Clicked submit button: {submit_field}")
                wait_time = input_fields.get("wait", 0)
                if wait_time:
                    print(f"Waiting for {wait_time} seconds...")
                    time.sleep(wait_time) 
                print("Page navigation complete!")
                return True  # Assume success if clicked submit button

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
    data = load_subscription_urls()
    data.append({"url": url, "verified": False})
    save_subscription_urls(data)
    print("URL added successfully as unverified!")

# Modify subscription file (manual verification)
def modify_subscription_file():
    data = load_subscription_urls()
    for index, entry in enumerate(data):
        status = "✔ Verified" if entry["verified"] else "❌ Unverified"
        print(f"{index + 1}. {entry['url']} - {status}")

    choice = input("Enter the number to toggle verification status, or 'q' to quit: ").strip()
    if choice.lower() == 'q':
        return
    try:
        idx = int(choice) - 1
        data[idx]["verified"] = not data[idx]["verified"]
        save_subscription_urls(data)
        print("Verification status updated.")
    except (ValueError, IndexError):
        print("Invalid selection.")

# Verify mode: test unverified URLs and mark them verified if successful
def verify_mode():
    unverified_urls = load_subscription_urls(unverified_only=True)
    if not unverified_urls:
        print("No unverified URLs found.")
        return

    driver = get_driver()
    for entry in unverified_urls:
        url = entry["url"]
        for email in EMAILS:
            success = subscribe_email(email.strip(), url.strip(), entry.get("input_fields", {}), driver)
            if success:
                entry["verified"] = True
                print(f"URL verified: {url}")
                save_subscription_urls(load_subscription_urls())  # Save updated data
            else:
                print(f"URL failed verification: {url}")

    driver.quit()
    print("Verification process completed.")

# Attack mode: run subscriptions only on verified URLs
def attack_mode():
    verified_urls = load_subscription_urls(verified_only=True)
    if not verified_urls:
        print("No verified URLs found.")
        return

    driver = get_driver()

    for email in EMAILS:
        for entry in verified_urls:
            url = entry["url"]
            input_fields = entry.get("input_fields", {"email": ["email"]})  # Default to email field
            subscribe_email(email.strip(), url.strip(), input_fields, driver)

    driver.quit()

# Main menu
def main():
    while True:
        print("\n=== Subscription Bot ===")
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
