"""
Unit tests for main.py
Run with:  pytest test_main.py -v
"""
import json
import os
import sys
import time
import types
import importlib
import email as email_module
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Helpers to import main without triggering Selenium / dotenv side-effects
# ---------------------------------------------------------------------------

def _import_main(env_overrides=None):
    """
    Import (or re-import) main with a controlled environment so tests are
    isolated from the real .env and from Selenium.
    """
    base_env = {
        "EMAILS": "test@example.com",
        "SEARCH_API_URL": "",
        "SEARCH_API_KEY": "",
        "SEARCH_API_METHOD": "GET",
        "SEARCH_API_KEY_HEADER": "X-API-Key",
        "SEARCH_API_KEY_BODY_FIELD": "",
        "SEARCH_API_QUERY_PARAM": "q",
        "SEARCH_API_RESULTS_PATH": "results",
        "SEARCH_API_URL_FIELD": "url",
        "IMAP_HOST": "",
        "IMAP_PORT": "993",
        "IMAP_USER": "",
        "IMAP_PASS": "",
        "IMAP_FOLDER": "INBOX",
        "IMAP_TIMEOUT": "60",
    }
    if env_overrides:
        base_env.update(env_overrides)

    with patch.dict(os.environ, base_env, clear=True):
        # Stub heavy deps so the import doesn't fail in CI / headless env
        for mod in ("selenium", "selenium.webdriver", "selenium.webdriver.common",
                    "selenium.webdriver.common.by", "selenium.webdriver.firefox",
                    "selenium.webdriver.firefox.options", "undetected_geckodriver",
                    "dotenv"):
            if mod not in sys.modules:
                sys.modules[mod] = MagicMock()

        # Stub load_dotenv so it doesn't overwrite our controlled env
        sys.modules["dotenv"].load_dotenv = lambda: None

        # Force fresh import
        if "main" in sys.modules:
            del sys.modules["main"]
        import main as m
        return m


# ===========================================================================
# 1. selector_from_config
# ===========================================================================

class TestSelectorFromConfig:
    def setup_method(self):
        self.m = _import_main()

    def test_raw_css_returned_directly(self):
        assert self.m.selector_from_config({"css": "input[type='email']"}) == "input[type='email']"

    def test_id_selector(self):
        assert self.m.selector_from_config({"id": "email"}) == "#email"

    def test_class_selector(self):
        assert self.m.selector_from_config({"class": "btn-primary"}) == ".btn-primary"

    def test_name_selector(self):
        assert self.m.selector_from_config({"name": "subscribe"}) == '[name="subscribe"]'

    def test_value_selector(self):
        assert self.m.selector_from_config({"value": "Sign Up"}) == '[value="Sign Up"]'

    def test_combined_class_and_id(self):
        result = self.m.selector_from_config({"class": "btn", "id": "submit"})
        assert ".btn" in result
        assert "#submit" in result

    def test_empty_dict_returns_empty_string(self):
        assert self.m.selector_from_config({}) == ""

    def test_non_dict_returns_empty_string(self):
        assert self.m.selector_from_config("not-a-dict") == ""
        assert self.m.selector_from_config(None) == ""


# ===========================================================================
# 2. parse_css_selector_list
# ===========================================================================

class TestParseCssSelectorList:
    def setup_method(self):
        self.m = _import_main()

    def test_single_selector(self):
        result = self.m.parse_css_selector_list("input[type='email']")
        assert result == [{"css": "input[type='email']"}]

    def test_multiple_selectors(self):
        result = self.m.parse_css_selector_list("button[type='submit'], input[type='submit']")
        assert len(result) == 2
        assert {"css": "button[type='submit']"} in result
        assert {"css": "input[type='submit']"} in result

    def test_empty_string_returns_empty_list(self):
        assert self.m.parse_css_selector_list("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert self.m.parse_css_selector_list("   ,  ") == []


# ===========================================================================
# 3. get_nested_value
# ===========================================================================

class TestGetNestedValue:
    def setup_method(self):
        self.m = _import_main()

    def test_simple_key(self):
        assert self.m.get_nested_value({"a": 1}, "a") == 1

    def test_nested_dict(self):
        assert self.m.get_nested_value({"a": {"b": 42}}, "a.b") == 42

    def test_list_index(self):
        assert self.m.get_nested_value({"results": [{"url": "http://x.com"}]}, "results.0.url") == "http://x.com"

    def test_missing_key_returns_none(self):
        assert self.m.get_nested_value({"a": 1}, "b") is None

    def test_out_of_bounds_index_returns_none(self):
        assert self.m.get_nested_value({"items": []}, "items.0") is None

    def test_none_mid_path_returns_none(self):
        assert self.m.get_nested_value({"a": None}, "a.b") is None


# ===========================================================================
# 4. load_subscription_urls / save_subscription_urls
# ===========================================================================

SAMPLE_DATA = [
    {"url": "https://a.com", "verified": True,  "input_fields": {}},
    {"url": "https://b.com", "verified": False, "input_fields": {}},
    {"url": "https://c.com", "verified": False, "input_fields": {}},
]

class TestLoadSaveSubscriptionUrls:
    def setup_method(self, _):
        self.m = _import_main()

    def _make_json(self, tmp_path, data):
        p = tmp_path / "subs.json"
        p.write_text(json.dumps(data))
        self.m.URL_JSON = str(p)
        return p

    def test_load_all(self, tmp_path):
        self._make_json(tmp_path, SAMPLE_DATA)
        result = self.m.load_subscription_urls()
        assert len(result) == 3

    def test_load_verified_only(self, tmp_path):
        self._make_json(tmp_path, SAMPLE_DATA)
        result = self.m.load_subscription_urls(verified_only=True)
        assert all(e["verified"] for e in result)
        assert len(result) == 1

    def test_load_unverified_only(self, tmp_path):
        self._make_json(tmp_path, SAMPLE_DATA)
        result = self.m.load_subscription_urls(unverified_only=True)
        assert all(not e["verified"] for e in result)
        assert len(result) == 2

    def test_load_missing_file_returns_empty(self, tmp_path):
        self.m.URL_JSON = str(tmp_path / "nonexistent.json")
        assert self.m.load_subscription_urls() == []

    def test_save_and_reload(self, tmp_path):
        path = tmp_path / "subs.json"
        self.m.URL_JSON = str(path)
        self.m.save_subscription_urls(SAMPLE_DATA)
        loaded = json.loads(path.read_text())
        assert loaded == SAMPLE_DATA


# ===========================================================================
# 5. search_subscription_urls – GET mode
# ===========================================================================

class TestSearchSubscriptionUrlsGet:
    def setup_method(self):
        self.m = _import_main({"SEARCH_API_URL": "https://api.example.com/search",
                                "SEARCH_API_KEY": "key123",
                                "SEARCH_API_METHOD": "GET",
                                "SEARCH_API_QUERY_PARAM": "q",
                                "SEARCH_API_RESULTS_PATH": "results",
                                "SEARCH_API_URL_FIELD": "url"})

    def _mock_response(self, payload):
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = json.dumps(payload).encode()
        return resp

    def test_returns_urls_from_results(self):
        payload = {"results": [{"url": "https://x.com"}, {"url": "https://y.com"}]}
        with patch("main.urlopen", return_value=self._mock_response(payload)):
            urls = self.m.search_subscription_urls("newsletter")
        assert urls == ["https://x.com", "https://y.com"]

    def test_respects_limit(self):
        payload = {"results": [{"url": f"https://site{i}.com"} for i in range(10)]}
        with patch("main.urlopen", return_value=self._mock_response(payload)):
            urls = self.m.search_subscription_urls("newsletter", limit=3)
        assert len(urls) == 3

    def test_empty_search_api_url_returns_empty(self):
        self.m.SEARCH_API_URL = ""
        assert self.m.search_subscription_urls("newsletter") == []

    def test_network_error_returns_empty(self):
        with patch("main.urlopen", side_effect=Exception("timeout")):
            urls = self.m.search_subscription_urls("newsletter")
        assert urls == []

    def test_non_list_results_returns_empty(self):
        payload = {"results": "not-a-list"}
        with patch("main.urlopen", return_value=self._mock_response(payload)):
            urls = self.m.search_subscription_urls("newsletter")
        assert urls == []


# ===========================================================================
# 6. search_subscription_urls – POST mode (Tavily)
# ===========================================================================

class TestSearchSubscriptionUrlsPost:
    def setup_method(self):
        self.m = _import_main({
            "SEARCH_API_URL": "https://api.tavily.com/search",
            "SEARCH_API_KEY": "tvly-key",
            "SEARCH_API_METHOD": "POST",
            "SEARCH_API_QUERY_PARAM": "query",
            "SEARCH_API_KEY_BODY_FIELD": "api_key",
            "SEARCH_API_RESULTS_PATH": "results",
            "SEARCH_API_URL_FIELD": "url",
        })

    def _mock_response(self, payload):
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = json.dumps(payload).encode()
        return resp

    def test_sends_post_with_json_body(self):
        payload = {"results": [{"url": "https://example.com"}]}
        with patch("main.urlopen", return_value=self._mock_response(payload)) as mock_open:
            self.m.search_subscription_urls("test query")
            req = mock_open.call_args[0][0]
            body = json.loads(req.data.decode())
            assert body["query"] == "test query"
            assert body["api_key"] == "tvly-key"

    def test_returns_urls_from_post_response(self):
        payload = {"results": [{"url": "https://a.com"}, {"url": "https://b.com"}]}
        with patch("main.urlopen", return_value=self._mock_response(payload)):
            urls = self.m.search_subscription_urls("newsletters")
        assert urls == ["https://a.com", "https://b.com"]


# ===========================================================================
# 7. get_inbox_uids
# ===========================================================================

class TestGetInboxUids:
    def setup_method(self):
        self.m = _import_main({
            "IMAP_HOST": "imap.example.com",
            "IMAP_USER": "user@example.com",
            "IMAP_PASS": "pass",
            "IMAP_FOLDER": "INBOX",
        })

    def test_returns_none_when_not_configured(self):
        self.m.IMAP_HOST = ""
        assert self.m.get_inbox_uids() is None

    def test_returns_set_of_uids(self):
        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1 2 3"])
        with patch("imaplib.IMAP4_SSL", return_value=mock_mail):
            uids = self.m.get_inbox_uids()
        assert uids == {b"1", b"2", b"3"}

    def test_returns_empty_set_for_empty_inbox(self):
        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b""])
        with patch("imaplib.IMAP4_SSL", return_value=mock_mail):
            uids = self.m.get_inbox_uids()
        assert uids == set()

    def test_returns_none_on_exception(self):
        with patch("imaplib.IMAP4_SSL", side_effect=Exception("connection refused")):
            assert self.m.get_inbox_uids() is None


# ===========================================================================
# 8. check_inbox_for_new_email
# ===========================================================================

def _make_raw_email(from_addr, subject):
    msg = MIMEText("body")
    msg["From"] = from_addr
    msg["Subject"] = subject
    return msg.as_bytes()


class TestCheckInboxForNewEmail:
    def setup_method(self):
        self.m = _import_main({
            "IMAP_HOST": "imap.example.com",
            "IMAP_USER": "user@example.com",
            "IMAP_PASS": "pass",
            "IMAP_FOLDER": "INBOX",
            "IMAP_TIMEOUT": "30",
        })

    def test_returns_false_when_imap_not_configured(self):
        self.m.IMAP_HOST = ""
        assert self.m.check_inbox_for_new_email({b"1"}, timeout=1) is False

    def test_returns_false_when_known_uids_is_none(self):
        assert self.m.check_inbox_for_new_email(None, timeout=1) is False

    def test_detects_new_email_no_hints(self):
        raw = _make_raw_email("news@site.com", "Welcome!")
        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1 2"])
        mock_mail.fetch.return_value = ("OK", [(None, raw)])
        with patch("imaplib.IMAP4_SSL", return_value=mock_mail):
            result = self.m.check_inbox_for_new_email(
                known_uids={b"1"}, timeout=5, poll_interval=1
            )
        assert result is True

    def test_filters_by_sender_hint(self):
        raw = _make_raw_email("other@site.com", "Hello")
        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1 2"])
        mock_mail.fetch.return_value = ("OK", [(None, raw)])
        with patch("imaplib.IMAP4_SSL", return_value=mock_mail):
            with patch("time.sleep"):
                result = self.m.check_inbox_for_new_email(
                    known_uids={b"1"},
                    sender_hint="newsletter@",
                    timeout=1,
                    poll_interval=1,
                )
        assert result is False

    def test_filters_by_subject_hint(self):
        raw = _make_raw_email("news@site.com", "Your order confirmation")
        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1 2"])
        mock_mail.fetch.return_value = ("OK", [(None, raw)])
        with patch("imaplib.IMAP4_SSL", return_value=mock_mail):
            with patch("time.sleep"):
                result = self.m.check_inbox_for_new_email(
                    known_uids={b"1"},
                    subject_hint="welcome",
                    timeout=1,
                    poll_interval=1,
                )
        assert result is False

    def test_matches_subject_hint_case_insensitive(self):
        raw = _make_raw_email("news@site.com", "WELCOME to our newsletter")
        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1 2"])
        mock_mail.fetch.return_value = ("OK", [(None, raw)])
        with patch("imaplib.IMAP4_SSL", return_value=mock_mail):
            result = self.m.check_inbox_for_new_email(
                known_uids={b"1"},
                subject_hint="welcome",
                timeout=5,
                poll_interval=1,
            )
        assert result is True

    def test_times_out_when_no_new_email(self):
        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])
        with patch("imaplib.IMAP4_SSL", return_value=mock_mail):
            with patch("time.sleep"):
                result = self.m.check_inbox_for_new_email(
                    known_uids={b"1"}, timeout=0, poll_interval=1
                )
        assert result is False

    def test_returns_false_on_imap_exception(self):
        with patch("imaplib.IMAP4_SSL", side_effect=Exception("error")):
            with patch("time.sleep"):
                result = self.m.check_inbox_for_new_email(
                    known_uids={b"1"}, timeout=0, poll_interval=1
                )
        assert result is False


# ===========================================================================
# 9. subscribe_email (Selenium interactions mocked)
# ===========================================================================

class TestSubscribeEmail:
    def setup_method(self):
        self.m = _import_main()

    def _make_driver(self, find_ok=True):
        driver = MagicMock()
        if not find_ok:
            driver.find_element.side_effect = Exception("not found")
        return driver

    def test_returns_true_on_successful_submit(self):
        driver = self._make_driver()
        input_fields = {
            "email": [{"css": "input[type='email']"}],
            "submit": [{"css": "button[type='submit']"}],
            "checkboxes": [],
            "radios": [],
            "wait": 0,
        }
        result = self.m.subscribe_email("a@b.com", "https://example.com", input_fields, driver)
        assert result is True
        driver.get.assert_called_once_with("https://example.com")

    def test_returns_false_when_submit_not_found(self):
        driver = self._make_driver(find_ok=False)
        input_fields = {
            "email": [],
            "submit": [{"css": "button[type='submit']"}],
            "checkboxes": [],
            "radios": [],
            "wait": 0,
        }
        result = self.m.subscribe_email("a@b.com", "https://example.com", input_fields, driver)
        assert result is False

    def test_returns_false_on_driver_get_exception(self):
        driver = MagicMock()
        driver.get.side_effect = Exception("WebDriver error")
        result = self.m.subscribe_email("a@b.com", "https://example.com", {}, driver)
        assert result is False

    def test_clicks_checkbox_before_email(self):
        driver = self._make_driver()
        call_order = []
        orig_find = driver.find_element.side_effect

        def track_find(by, selector):
            call_order.append(selector)
            return MagicMock()

        driver.find_element.side_effect = track_find

        input_fields = {
            "checkboxes": [{"css": "#agree"}],
            "email": [{"css": "input[type='email']"}],
            "submit": [{"css": "button[type='submit']"}],
            "radios": [],
            "wait": 0,
        }
        self.m.subscribe_email("a@b.com", "https://example.com", input_fields, driver)
        assert call_order.index("#agree") < call_order.index("input[type='email']")


# ===========================================================================
# 10. modify_subscription_file – toggle and delete
# ===========================================================================

class TestModifySubscriptionFile:
    def setup_method(self):
        self.m = _import_main()

    def _setup_json(self, tmp_path, data):
        p = tmp_path / "subs.json"
        p.write_text(json.dumps(data))
        self.m.URL_JSON = str(p)

    def test_toggle_verified_status(self, tmp_path):
        data = [{"url": "https://a.com", "verified": False, "input_fields": {}}]
        self._setup_json(tmp_path, data)
        with patch("builtins.input", side_effect=["t", "1"]):
            self.m.modify_subscription_file()
        result = json.loads((tmp_path / "subs.json").read_text())
        assert result[0]["verified"] is True

    def test_delete_entry(self, tmp_path):
        data = [
            {"url": "https://a.com", "verified": True,  "input_fields": {}},
            {"url": "https://b.com", "verified": False, "input_fields": {}},
        ]
        self._setup_json(tmp_path, data)
        with patch("builtins.input", side_effect=["d", "1"]):
            self.m.modify_subscription_file()
        result = json.loads((tmp_path / "subs.json").read_text())
        assert len(result) == 1
        assert result[0]["url"] == "https://b.com"

    def test_quit_action_does_nothing(self, tmp_path):
        data = [{"url": "https://a.com", "verified": False, "input_fields": {}}]
        self._setup_json(tmp_path, data)
        with patch("builtins.input", return_value="q"):
            self.m.modify_subscription_file()
        result = json.loads((tmp_path / "subs.json").read_text())
        assert result[0]["verified"] is False

    def test_invalid_index_does_not_crash(self, tmp_path):
        data = [{"url": "https://a.com", "verified": False, "input_fields": {}}]
        self._setup_json(tmp_path, data)
        with patch("builtins.input", side_effect=["t", "99"]):
            self.m.modify_subscription_file()  # should not raise


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
