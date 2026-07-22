import tempfile
import unittest
from pathlib import Path

from szzx_local.auth import hash_password, verify_password
from szzx_local.database import Database
from szzx_local.server import DataService


class PasswordHashTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verifiable(self):
        first = hash_password("correct horse battery staple")
        second = hash_password("correct horse battery staple")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("correct horse battery staple", first))
        self.assertFalse(verify_password("wrong password", first))


class DataServiceAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(path=Path(self.temp_dir.name) / "server.json")
        self.service = DataService(self.db, "test", 45456)

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_first_login_creates_server_account_and_returns_session(self):
        result = self.service.login("Alice", "1")
        self.assertTrue(result["created"])
        self.assertEqual(self.service.authenticate(result["token"]), "Alice")
        stored = self.service._auth_users()["alice"]
        self.assertNotEqual(stored["password_hash"], "1")

    def test_existing_account_rejects_wrong_password(self):
        self.service.login("Alice", "long-enough-password")
        with self.assertRaises(PermissionError):
            self.service.login("Alice", "not-the-password")

    def test_change_password_requires_current_password(self):
        result = self.service.login("Alice", "long-enough-password")
        with self.assertRaises(PermissionError):
            self.service.change_password(result["token"], "wrong-password", "new-long-password")
        changed = self.service.change_password(result["token"], "long-enough-password", "new-long-password")
        with self.assertRaises(PermissionError):
            self.service.authenticate(result["token"])
        self.assertEqual(self.service.authenticate(changed["token"]), "Alice")
        with self.assertRaises(PermissionError):
            self.service.login("Alice", "long-enough-password")
        self.assertFalse(self.service.login("Alice", "new-long-password")["created"])

    def test_account_name_can_change_without_device_binding(self):
        result = self.service.login("Alice", "1")
        changed = self.service.change_account(result["token"], "1", "Bob")
        self.assertEqual(self.service.authenticate(changed["token"]), "Bob")
        self.assertNotIn("alice", self.service._auth_users())
        self.assertFalse(self.service.login("Bob", "1")["created"])


if __name__ == "__main__":
    unittest.main()
