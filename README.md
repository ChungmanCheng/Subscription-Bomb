# Subscription Bomb 🚀

This Python script automates email subscriptions to various newsletter services using **Selenium (undetected-geckodriver)**, allowing you to test email registration flows. It reads email addresses from a `.env` file and subscription URLs from a JSON file, then submits them to subscription forms automatically.

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
pip install selenium undetected-geckodriver python-dotenv
```

### 2. Configure `.env`

Copy `.env.sample` to `.env` and fill in your values:

```bash
cp .env.sample .env
```

```dotenv
# One or more target emails (comma-separated)
EMAILS=you@example.com,another@example.com

# --- Optional: Search API (for finding subscription URLs automatically) ---
SEARCH_API_URL=https://api.example.com/search
SEARCH_API_KEY=your-api-key
SEARCH_API_KEY_HEADER=X-API-Key
SEARCH_API_QUERY_PARAM=q
SEARCH_API_RESULTS_PATH=results
SEARCH_API_URL_FIELD=url

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
        ├── 1. Add Subscription URL
        ├── 2. Modify Email Subscription List
        ├── 3. Verify Mode
        ├── 4. Attack Mode
        └── 5. Exit
```

---

## 📖 Usage

### 1 · Add Subscription URL

Adds a new subscription form URL to `email_subscription.json`.

1. Choose the URL source:
   - **[1] Manual** – paste the URL directly
   - **[2] Search API** – enter a search query; pick from results
2. Enter CSS selectors for the form fields:
   | Prompt | Default |
   |---|---|
   | Email field | `input[type='email']` |
   | Submit button | `button[type='submit'], input[type='submit']` |
   | Checkboxes | *(optional)* |
   | Radio buttons | *(optional)* |
   | Wait after submit (s) | `0` |
3. Enter optional **IMAP hints** to help identify the confirmation email:
   - **Sender hint** – substring of the sender address (e.g. `noreply@example.com`)
   - **Subject hint** – substring of the subject line (e.g. `confirm`, `welcome`)

The entry is saved as `"verified": false` until Verify Mode confirms it.

---

### 2 · Modify Email Subscription List

Lists all entries with their verification status (✔ / ❌).

| Key | Action |
|---|---|
| `t` | Toggle verified / unverified |
| `d` | Delete the entry |
| `q` | Quit |

---

### 3 · Verify Mode

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

### 4 · Attack Mode

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
