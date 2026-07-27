import unittest
from datetime import date, datetime
from types import SimpleNamespace

from szzx_local.dingtalk_daily_bot import DingTalkDailyBot


class _SettingsDatabase:
    def __init__(self):
        self.settings = {}

    def get_setting(self, key):
        return self.settings.get(key)

    def set_setting(self, key, value):
        self.settings[key] = value

    def dingtalk_id_for_name(self, name):
        return {"李四": "lisi01"}.get(name, "")

    def dingtalk_staff_id_for_name(self, name):
        return {"李四": "staff-lisi"}.get(name, "")

    def list_rest_days(self, mine_only=True):
        return []

    def remember_dingtalk_staff_id(self, name, staff_id):
        return None


class DailyReportBotTests(unittest.TestCase):
    def test_markdown_contains_all_report_identity_fields(self):
        bot = DingTalkDailyBot(_SettingsDatabase(), "client", "secret")
        messages = bot._markdown_messages(
            date(2026, 7, 23),
            [{
                "created_at": datetime(2026, 7, 23, 18, 5),
                "project_name": "订单退款",
                "member_name": "张三",
                "role": "后端开发",
                "content": "完成退款接口联调",
            }],
        )

        self.assertEqual(len(messages), 1)
        self.assertIn("## ✅ 已写日报（1 人）", messages[0])
        self.assertIn("# 张三（1 篇）", messages[0])
        self.assertIn("### 订单退款 · 后端开发 · 18:05", messages[0])
        self.assertIn("完成退款接口联调", messages[0])

    def test_reports_are_grouped_by_member(self):
        bot = DingTalkDailyBot(_SettingsDatabase(), "client", "secret")
        messages = bot._markdown_messages(
            date(2026, 7, 23),
            [
                {
                    "created_at": datetime(2026, 7, 23, 10, 0),
                    "project_name": "项目甲",
                    "member_name": "王欢",
                    "role": "产品经理",
                    "content": "第一篇",
                },
                {
                    "created_at": datetime(2026, 7, 23, 11, 0),
                    "project_name": "项目乙",
                    "member_name": "张三",
                    "role": "开发",
                    "content": "第二篇",
                },
                {
                    "created_at": datetime(2026, 7, 23, 12, 0),
                    "project_name": "项目丙",
                    "member_name": "王欢",
                    "role": "产品经理",
                    "content": "第三篇",
                },
            ],
        )

        self.assertEqual(messages[0].count("# 王欢（2 篇）"), 1)
        self.assertEqual(messages[0].count("# 张三（1 篇）"), 1)
        self.assertLess(messages[0].index("第一篇"), messages[0].index("第三篇"))

    def test_missing_members_are_listed_with_their_projects(self):
        bot = DingTalkDailyBot(_SettingsDatabase(), "client", "secret")
        messages = bot._markdown_messages(
            date(2026, 7, 23),
            [{
                "created_at": datetime(2026, 7, 23, 18, 5),
                "project_name": "项目甲",
                "member_name": "张三",
                "role": "开发",
                "content": "已提交",
            }],
            {
                "张三": {"name": "张三", "projects": ["项目甲"]},
                "李四": {"name": "李四", "projects": ["项目乙", "项目丙"]},
            },
        )

        markdown = "\n".join(messages)
        self.assertIn("## ⚠️ 未写日报（1 人）", markdown)
        self.assertIn("# 李四", markdown)
        self.assertNotIn("### 项目乙", markdown)
        self.assertNotIn("### 项目丙", markdown)
        self.assertEqual(markdown.count("> 昨日未提交日报。"), 1)
        self.assertNotIn("# 张三\n\n### 项目甲\n\n> 昨日未提交日报。", markdown)

    def test_long_reports_are_split_into_multiple_messages(self):
        bot = DingTalkDailyBot(_SettingsDatabase(), "client", "secret")
        reports = [
            {
                "created_at": datetime(2026, 7, 23, 18, index),
                "project_name": f"项目{index}",
                "member_name": "张三",
                "role": "开发",
                "content": "日报内容" * 2200,
            }
            for index in range(3)
        ]

        messages = bot._markdown_messages(date(2026, 7, 23), reports)

        self.assertGreater(len(messages), 1)
        self.assertTrue(all("全员项目日报" in message for message in messages))

    def test_missing_member_with_dingtalk_id_is_a_real_mention(self):
        db = _SettingsDatabase()
        db.list_projects = lambda: []
        db.daily_reports_between = lambda *args, **kwargs: []
        bot = DingTalkDailyBot(db, "client", "secret")
        sent = []
        bot._send_group_markdown = lambda conversation_id, title, text, mentioned_user_ids=None: sent.append(
            (text, mentioned_user_ids)
        )
        db.set_setting("dingtalk_daily_open_conversation_id", "cid")
        bot._expected_daily_report_members = lambda report_day: {
            "李四": {
                "name": "李四",
                "projects": ["项目乙"],
                "dingtalk_id": "lisi01",
            }
        }

        bot.send_daily_reports(date(2026, 7, 23))

        self.assertIn("# @lisi01（李四）", sent[0][0])
        self.assertEqual(sent[0][1], ["lisi01"])

    def test_group_markdown_adds_at_metadata(self):
        db = _SettingsDatabase()
        db.set_setting("dingtalk_daily_session_webhook", "https://example.test/session")
        db.set_setting("dingtalk_daily_session_webhook_expires_at", "4102444800000")
        bot = DingTalkDailyBot(db, "client", "secret")
        requests = []
        bot._get_access_token = lambda: "token"
        bot._request_json = lambda url, payload, headers=None: requests.append((url, payload)) or {}

        bot._send_group_markdown("cid", "标题", "# @lisi01（李四）", ["lisi01", "lisi01"])

        self.assertEqual(
            requests[0][1]["at"],
            {"atUserIds": ["lisi01"], "isAtAll": False},
        )
        self.assertEqual(requests[0][0], "https://example.test/session")

    def test_resting_member_is_not_expected_to_submit(self):
        db = _SettingsDatabase()
        db.list_rest_days = lambda mine_only=True: [
            SimpleNamespace(author=" 李四 ", day=date(2026, 7, 23))
        ]
        project = SimpleNamespace(id=1, name="项目乙", owner="李四", status="进行中")
        db.list_projects = lambda: [project]
        db.list_project_members = lambda project_id: [
            SimpleNamespace(name="王五")
        ]
        bot = DingTalkDailyBot(db, "client", "secret")

        members = bot._expected_daily_report_members(date(2026, 7, 23))

        self.assertNotIn("李四", members)
        self.assertIn("王五", members)

    def test_rest_on_another_day_does_not_exclude_member(self):
        db = _SettingsDatabase()
        db.list_rest_days = lambda mine_only=True: [
            SimpleNamespace(author="李四", day=date(2026, 7, 24))
        ]
        project = SimpleNamespace(id=1, name="项目乙", owner="李四", status="进行中")
        db.list_projects = lambda: [project]
        db.list_project_members = lambda project_id: []
        bot = DingTalkDailyBot(db, "client", "secret")

        members = bot._expected_daily_report_members(date(2026, 7, 23))

        self.assertIn("李四", members)


if __name__ == "__main__":
    unittest.main()
