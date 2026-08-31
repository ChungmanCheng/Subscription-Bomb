# Subscription Bomb 🚀

This Python script uses **Selenium with standard Firefox WebDriver** to discover and test newsletter registration flows. It reads email addresses from a `.env` file and subscription URLs from a JSON file, then submits them only in the explicit verification or subscription modes.

## ⚠️ Disclaimer

**This script is intended for educational and ethical purposes only.**  
Do **not** use it for spam or malicious purposes. Misuse of this script may violate privacy laws and terms of service. The author is not responsible for any misuse.

---

## 📂 Project Structure

```
Subscription-Bomb/
├── main.py                   # Main script
├── email_subscription.json   # Subscription URL list (auto-created)
├── .env                      # Your configuration (see setup)
├── .env.sample               # Example configuration file
└── README.md
```

---

## ⚙️ Setup

### 1. Install dependencies

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure `.env`

Copy `.env.sample` to `.env` and fill in your values:

```bash
cp .env.sample .env
```

```dotenv
# One or more target emails (comma-separated)
EMAILS=you@example.com,another@example.com

# --- Search API used by fully automatic Mode 1 (Tavily example) ---
SEARCH_API_URL=https://api.tavily.com/search
SEARCH_API_KEY=your-api-key
SEARCH_API_METHOD=POST
SEARCH_API_KEY_HEADER=Authorization
SEARCH_API_KEY_PREFIX=Bearer
SEARCH_API_QUERY_PARAM=query
SEARCH_API_MAX_RESULTS_FIELD=max_results
SEARCH_API_RESULTS_PATH=results
SEARCH_API_URL_FIELD=url
SEARCH_API_SCORE_FIELD=score

# Topics searched automatically after choosing Mode 1
AUTO_SEARCH_QUERIES=technology,finance,health,science
AUTO_RESULTS_PER_QUERY=10
AUTO_MAX_URLS=50
AUTO_MIN_SEARCH_SCORE=0.5
AUTO_FOLLOW_LINKS=true
AUTO_LINKS_PER_PAGE=3
AUTO_RESPECT_ROBOTS=true
AUTO_ROBOTS_USER_AGENT=SubscriptionBot
AUTO_REQUEST_DELAY=1.0
AUTO_PAGE_WAIT=5.0

# --- Optional: IMAP inbox verification ---
IMAP_HOST=imap.example.com
IMAP_PORT=993
IMAP_USER=you@example.com
IMAP_PASS=your-imap-password
IMAP_FOLDER=INBOX
IMAP_TIMEOUT=60
```

> **IMAP is optional.** If left blank, Verify Mode falls back to treating a successful form submission as verified.

### 3. Run

```bash
python3 main.py
```

---

## 🗺️ Workflow

```
Startup
  └── Show verified / unverified URL counts
  └── Main menu
        ├── 1. Fully Automatic Newsletter Discovery
        ├── 2. Add Subscription URL Manually
        ├── 3. Modify Email Subscription List
        ├── 4. Verify Mode
        ├── 5. Attack Mode
        └── 6. Exit
```

---

## 📖 Usage

### 1 · Fully Automatic Newsletter Discovery

Mode 1 has no prompts after it starts. It reads every setting from `.env`:

1. Expands each `AUTO_SEARCH_QUERIES` topic into a newsletter-focused query.
2. Requests `AUTO_RESULTS_PER_QUERY` results from the Search API and filters
   low relevance scores.
3. Normalizes URLs, removes duplicates, rejects non-HTTP URLs, and caps the
   run at `AUTO_MAX_URLS` candidates.
4. Checks `robots.txt`, applies `AUTO_REQUEST_DELAY`, and opens candidates in
   one headless Firefox session.
5. Uses explicit page-readiness waits and inspects the top document plus
   first-level iframes.
6. Selects an email field and submit control from the same form and frame.
7. If the result has no form, follows a limited number of promising same-site
   newsletter/subscribe links and inspects those automatically.
8. Saves every recognized form as unverified and prints a final summary.

Discovery never fills or submits a form. Verification and actual subscriptions
remain separate modes.

Implementation choices follow the official documentation for
[Tavily Search parameters](https://docs.tavily.com/documentation/api-reference/endpoint/search),
[Selenium waiting strategies](https://www.selenium.dev/documentation/webdriver/waits/),
[Selenium iframe handling](https://www.selenium.dev/documentation/webdriver/interactions/frames/),
and the [Robots Exclusion Protocol](https://www.rfc-editor.org/rfc/rfc9309.html).

### 2 · Add Subscription URL Manually

Use this mode for a specific URL or a one-off Search API query. Automatic form
mapping remains the default, with interactive CSS selection as its fallback.

In manual setup, configure these fields:

   | Prompt | Default |
   |---|---|
   | Email field | `input[type='email']` |
   | Submit button | `button[type='submit'], input[type='submit']` |
   | Checkboxes | *(optional)* |
   | Radio buttons | *(optional)* |
   | Wait after submit (s) | `0` |

Enter optional **IMAP hints** to help identify the confirmation email:

   - **Sender hint** – substring of the sender address (e.g. `noreply@example.com`)
   - **Subject hint** – substring of the subject line (e.g. `confirm`, `welcome`)

The entry is saved as `"verified": false` until Verify Mode confirms it.

---

### 3 · Modify Email Subscription List

Lists all entries with their verification status (✔ / ❌).

| Key | Action |
|---|---|
| `t` | Toggle verified / unverified |
| `d` | Delete the entry |
| `q` | Quit |

---

### 4 · Verify Mode

Tests every **unverified** URL and marks it verified if the confirmation flow succeeds.

**Flow per URL:**

```
For each unverified URL:
  For each email in EMAILS:
    1. Snapshot current inbox UIDs via IMAP (if configured)
    2. Selenium fills and submits the form
    3. If form submit succeeded:
         IMAP configured?
           Yes → Poll inbox every 10 s up to IMAP_TIMEOUT
                   Filter by sender_hint / subject_hint (if set)
                   ✔ Email found  → mark verified
                   ✗ Timed out   → mark failed
           No  → mark verified (form-submit fallback)
    4. Break to next URL once verified
```

Results are saved back to `email_subscription.json`.

> Inbox polling is **differential**: a snapshot is taken *before* form submit, so pre-existing emails never cause false positives.

---

### 5 · Attack Mode

Runs subscriptions against all **verified** URLs in headless mode.

- Iterates every email × every verified URL
- Uses the CSS selectors stored in the JSON entry
- Prints a final `Success / Failed` count

---

## 🗄️ email_subscription.json format

```json
[
  {
    "url": "https://example.com/newsletter",
    "verified": false,
    "verification": {
      "sender_hint": "noreply@example.com",
      "subject_hint": "confirm"
    },
    "input_fields": {
      "email":       [{"css": "input[type='email']"}],
      "username":    [],
      "phone":       [],
      "submit":      [{"css": "button[type='submit']"}],
      "radios":      [],
      "checkboxes":  [],
      "selections":  [],
      "wait":        3
    }
  }
]
```

CSS selectors can also be expressed as attribute objects instead of raw CSS:

```json
{"id": "email-input"}
{"class": "submit-btn"}
{"name": "subscribe"}
{"value": "Sign Up"}
```
