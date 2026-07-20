import unittest
from types import SimpleNamespace

from szzx_local.dingtalk_bot import _recipient


class FakeDatabase:
    def __init__(self, ids=None, names=None, aliases=None):
        self.ids = ids or {}
        self.names = names or {}
        self.aliases = aliases or {}

    def dingtalk_id_for_name(self, name):
        return self.ids.get(name, "")

    def name_for_dingtalk_id(self, user_id):
        return self.names.get(user_id, "")

    def requirement_recipient_alias(self, user_id):
        return self.aliases.get(user_id, "")


class RecipientParsingTests(unittest.TestCase):
    def test_visible_mention_is_authoritative_when_at_users_are_reversed(self):
        message = {
            "atUsers": [
                {"dingtalkNick": "需求搜集机器人", "staffId": "bot-id"},
                {"dingtalkNick": "", "staffId": "wrong-id"},
            ]
        }
        db = FakeDatabase({"吴晓杰": "wu-id"})

        self.assertEqual(
            _recipient(db, message, "@ 需求搜集机器人 @ 吴晓杰(吴晓杰)", "需求搜集机器人"),
            ("吴晓杰", "wu-id"),
        )

    def test_named_structured_mention_can_supply_id(self):
        message = {"atUsers": [{"dingtalkNick": "吴晓杰", "staffId": "wu-id"}]}

        self.assertEqual(_recipient(FakeDatabase(), message, "@吴晓杰", "需求搜集机器人"), ("吴晓杰", "wu-id"))

    def test_structured_mention_is_used_when_dingtalk_strips_at_text(self):
        message = SimpleNamespace(
            chatbot_user_id="bot-id",
            robot_code="robot-code",
            at_users=[
                SimpleNamespace(dingtalk_id="yu-encrypted-id", staff_id="yu-staff-id"),
                SimpleNamespace(dingtalk_id="bot-id", staff_id="bot-staff-id"),
            ],
        )
        db = FakeDatabase(aliases={"yu-encrypted-id": "尉久洋"})

        self.assertEqual(
            _recipient(db, message, "需求描述：审批流加签", "需求搜集机器人"),
            ("尉久洋", "yu-encrypted-id"),
        )

    def test_historical_staff_id_resolves_recipient_among_two_unknown_mentions(self):
        message = SimpleNamespace(
            chatbot_user_id="unmatched-bot-id",
            robot_code="robot-code",
            at_users=[
                SimpleNamespace(dingtalk_id="yu-changing-id", staff_id="yu-stable-staff-id"),
                SimpleNamespace(dingtalk_id="bot-changing-id", staff_id="bot-staff-id"),
            ],
        )
        db = FakeDatabase(names={"yu-stable-staff-id": "尉久洋"})

        self.assertEqual(
            _recipient(db, message, "需求描述：审批流加签", "需求搜集机器人"),
            ("尉久洋", "yu-stable-staff-id"),
        )

    def test_directory_resolver_recovers_name_from_current_staff_id(self):
        message = SimpleNamespace(
            chatbot_user_id="bot-encrypted-id",
            robot_code="robot-code",
            at_users=[
                SimpleNamespace(dingtalk_id="yu-encrypted-id", staff_id="yu-current-staff-id"),
                SimpleNamespace(dingtalk_id="bot-encrypted-id", staff_id=None),
            ],
        )

        self.assertEqual(
            _recipient(
                FakeDatabase(),
                message,
                "需求描述：审批流加签",
                "需求搜集机器人",
                name_resolver=lambda user_id: "尉久洋" if user_id == "yu-current-staff-id" else "",
            ),
            ("尉久洋", "yu-current-staff-id"),
        )

    def test_placeholder_cache_does_not_block_directory_lookup(self):
        message = SimpleNamespace(
            chatbot_user_id="bot-encrypted-id",
            robot_code="robot-code",
            at_users=[
                SimpleNamespace(dingtalk_id="liu-encrypted-id", staff_id="liu-staff-id"),
                SimpleNamespace(dingtalk_id="bot-encrypted-id", staff_id=None),
            ],
        )
        db = FakeDatabase(names={"liu-staff-id": "待确认承接人"})

        self.assertEqual(
            _recipient(
                db,
                message,
                "需求描述：审批流加签",
                "需求搜集机器人",
                name_resolver=lambda user_id: "刘文博" if user_id == "liu-staff-id" else "",
            ),
            ("刘文博", "liu-staff-id"),
        )


if __name__ == "__main__":
    unittest.main()
