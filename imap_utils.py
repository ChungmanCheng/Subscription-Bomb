"""
imap_utils.py – IMAP inbox snapshot and polling helpers.
Used by verify_mode() to confirm a confirmation email arrived after form submit.
"""
import imaplib
import email
import time
from email.header import decode_header

from config import IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_PASS, IMAP_FOLDER, IMAP_TIMEOUT


def get_inbox_uids():
    """
    Connect to the configured IMAP server and return the current set of
    message sequence numbers as a set of bytes.
    Returns None if IMAP is not configured or the connection fails.
    """
    if not all([IMAP_HOST, IMAP_USER, IMAP_PASS]):
        return None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select(IMAP_FOLDER, readonly=True)
        _, data = mail.search(None, "ALL")
        mail.logout()
        return set(data[0].split()) if data and data[0] else set()
    except Exception as exc:
        print(f"[IMAP] Snapshot failed: {exc}")
        return None


def check_inbox_for_new_email(known_uids, sender_hint="", subject_hint="",
                               timeout=None, poll_interval=10):
    """
    Poll the IMAP inbox until a new email appears that was not in *known_uids*.

    Optionally filters messages by:
      - sender_hint  : substring matched against the From header
      - subject_hint : substring matched against the decoded Subject header

    Returns True if a qualifying email arrives before *timeout* seconds.
    Returns False if IMAP is unconfigured, no snapshot exists, or time runs out.
    """
    if not all([IMAP_HOST, IMAP_USER, IMAP_PASS]):
        print("[IMAP] Not configured – skipping inbox check.")
        return False
    if known_uids is None:
        print("[IMAP] No snapshot available – skipping inbox check.")
        return False

    effective_timeout = timeout if timeout is not None else IMAP_TIMEOUT
    deadline = time.time() + effective_timeout

    while time.time() < deadline:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            mail.login(IMAP_USER, IMAP_PASS)
            mail.select(IMAP_FOLDER, readonly=True)
            _, data = mail.search(None, "ALL")
            current_uids = set(data[0].split()) if data and data[0] else set()
            new_uids = current_uids - known_uids

            for uid in new_uids:
                _, msg_data = mail.fetch(uid, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                from_header = msg.get("From", "")

                raw_subject = msg.get("Subject", "")
                subject_parts = decode_header(raw_subject)
                subject = ""
                for part, enc in subject_parts:
                    if isinstance(part, bytes):
                        subject += part.decode(enc or "utf-8", errors="replace")
                    else:
                        subject += part

                if sender_hint and sender_hint.lower() not in from_header.lower():
                    continue
                if subject_hint and subject_hint.lower() not in subject.lower():
                    continue

                print(f"[IMAP] Confirmation email received!")
                print(f"       From: {from_header}")
                print(f"       Subject: {subject}")
                mail.logout()
                return True

            mail.logout()
        except Exception as exc:
            print(f"[IMAP] Polling error: {exc}")

        remaining = deadline - time.time()
        if remaining > 0:
            wait = min(poll_interval, remaining)
            print(f"[IMAP] No new email yet – checking again in {wait:.0f}s "
                  f"({remaining:.0f}s remaining)...")
            time.sleep(wait)

    print("[IMAP] Timed out waiting for confirmation email.")
    return False
