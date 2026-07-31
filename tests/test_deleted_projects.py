import tempfile
import unittest
from pathlib import Path

from szzx_local.database import Database


class DeletedProjectVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(path=Path(self.temp_dir.name) / "client.json")

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_deleted_projects_are_retained_but_hidden_from_client_lists(self):
        project = self.db.add_project("隐藏项目", "测试用户", "说明")

        self.assertIsNotNone(self.db.update_project_status(project.id, "已删除"))
        self.assertEqual(self.db.list_projects(), [])

        retained = self.db.list_projects(include_deleted=True)
        self.assertEqual([item.id for item in retained], [project.id])
        self.assertEqual(retained[0].status, "已删除")

    def test_deleted_projects_are_hidden_from_member_profile(self):
        project = self.db.add_project("个人项目", "朱世缘", "说明")
        self.assertEqual(
            [item["project_id"] for item in self.db.projects_for_member("朱世缘")],
            [project.id],
        )

        self.assertIsNotNone(self.db.update_project_status(project.id, "已删除"))

        self.assertEqual(self.db.projects_for_member("朱世缘"), [])


class ColleagueStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(path=Path(self.temp_dir.name) / "client.json")

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_only_admin_can_mark_colleague_departed(self):
        self.assertFalse(self.db.set_colleague_departed("测试同事", True))
        self.db.set_display_name("尉久洋")

        self.assertTrue(self.db.set_colleague_departed("测试同事", True))
        self.assertTrue(self.db.is_departed_colleague(" 测试同事 "))
        self.assertIn("测试同事", self.db.departed_colleague_names())

        self.assertTrue(self.db.set_colleague_departed("测试同事", False))
        self.assertFalse(self.db.is_departed_colleague("测试同事"))


if __name__ == "__main__":
    unittest.main()
