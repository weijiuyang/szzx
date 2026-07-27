import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from szzx_local.database import Database
from szzx_local.dingtalk_config import bot_credentials, dingtalk_config_path
from szzx_local.dingtalk_daily_bot import DingTalkDailyBot


class DingTalkConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(path=Path(self.temp_dir.name) / "szzx_server.json")

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_first_read_creates_persistent_config_beside_database(self):
        credentials = bot_credentials(self.db, "daily_report_bot")

        self.assertEqual(credentials["app_key"], "")
        self.assertTrue(dingtalk_config_path(self.db).exists())

    def test_file_credentials_take_precedence_over_environment(self):
        dingtalk_config_path(self.db).write_text(json.dumps({
            "daily_report_bot": {
                "app_key": "file-key",
                "app_secret": "file-secret",
                "robot_code": "file-robot",
            },
        }), encoding="utf-8")
        with patch.dict(os.environ, {
            "DINGTALK_DAILY_CLIENT_ID": "env-key",
            "DINGTALK_DAILY_CLIENT_SECRET": "env-secret",
        }):
            bot = DingTalkDailyBot.from_config(self.db)

        self.assertIsNotNone(bot)
        self.assertEqual(bot.client_id, "file-key")
        self.assertEqual(bot.client_secret, "file-secret")
        self.assertEqual(bot.robot_code, "file-robot")

    def test_existing_environment_credentials_are_migrated_to_file(self):
        with patch.dict(os.environ, {
            "DINGTALK_CLIENT_ID": "requirement-key",
            "DINGTALK_CLIENT_SECRET": "requirement-secret",
            "DINGTALK_DAILY_CLIENT_ID": "daily-key",
            "DINGTALK_DAILY_CLIENT_SECRET": "daily-secret",
        }):
            bot_credentials(self.db, "daily_report_bot")

        saved = json.loads(dingtalk_config_path(self.db).read_text(encoding="utf-8"))
        self.assertEqual(saved["requirement_bot"]["app_key"], "requirement-key")
        self.assertEqual(saved["requirement_bot"]["app_secret"], "requirement-secret")
        self.assertEqual(saved["daily_report_bot"]["app_key"], "daily-key")
        self.assertEqual(saved["daily_report_bot"]["app_secret"], "daily-secret")


if __name__ == "__main__":
    unittest.main()
