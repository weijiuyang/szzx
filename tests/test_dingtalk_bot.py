import unittest

from szzx_local.dingtalk_bot import _recipient


class FakeDatabase:
    def __init__(self, ids=None):
        self.ids = ids or {}

    def dingtalk_id_for_name(self, name):
        return self.ids.get(name, "")


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


if __name__ == "__main__":
    unittest.main()
