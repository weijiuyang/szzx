import json
import unittest
from unittest.mock import patch

from szzx_local.central_sync import CentralDataSync


class _Database:
    def __init__(self):
        self.settings = {
            "data_server_url": "http://server.test:45456",
            "data_server_auth_tokens": json.dumps({"http://server.test:45456": "saved-token"}),
            "display_name": "stale name",
        }
        self.saved = 0

    def get_setting(self, key):
        return self.settings.get(key, "")

    def set_setting(self, key, value, save=True):
        self.settings[key] = value

    def display_name(self):
        return self.settings.get("display_name", "")

    def save_local_settings(self):
        self.saved += 1

    def add_after_save_callback(self, callback):
        pass


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return json.dumps({"ok": True, "username": "actual account"}).encode()


class CentralSyncAuthTests(unittest.TestCase):
    def test_saved_session_refreshes_local_account_name(self):
        db = _Database()
        sync = CentralDataSync(db)
        with patch("szzx_local.central_sync.urlopen", return_value=_Response()):
            self.assertTrue(sync.validate_saved_session())
        self.assertEqual(db.display_name(), "actual account")
        self.assertEqual(db.saved, 1)

    def test_logout_removes_only_current_server_token(self):
        db = _Database()
        db.settings["data_server_auth_tokens"] = json.dumps({
            "http://server.test:45456": "saved-token",
            "http://other.test:45456": "other-token",
        })
        sync = CentralDataSync(db)
        sync.logout()
        self.assertEqual(sync.auth_token, "")
        self.assertEqual(
            json.loads(db.settings["data_server_auth_tokens"]),
            {"http://other.test:45456": "other-token"},
        )


if __name__ == "__main__":
    unittest.main()
