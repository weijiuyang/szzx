import json
import tempfile
import unittest
from pathlib import Path

from szzx_local.database import Database


class ProjectTodoTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(path=Path(self.temp_dir.name) / "client.json")
        self.project = self.db.add_project("转交测试", "产品甲", "")

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_current_recipient_can_transfer_assigned_todo(self):
        todo = self.db.add_project_todo(
            self.project.id,
            "整理接口文档",
            "产品甲",
            scope="assigned",
            assignee="开发乙",
            assigned_by="产品甲",
        )

        transferred = self.db.transfer_project_todo(todo.id, "开发乙", "开发丙")

        self.assertIsNotNone(transferred)
        assert transferred is not None
        self.assertEqual(transferred.assigned_by, "产品甲")
        self.assertEqual(transferred.assignee, "开发乙")
        self.assertEqual(transferred.current_handler, "开发丙")
        history = json.loads(transferred.flow_history)
        self.assertEqual(history[-1]["actor"], "开发乙")
        self.assertEqual(history[-1]["action"], "转交任务")
        self.assertEqual(history[-1]["handler"], "开发丙")

    def test_only_current_recipient_can_transfer(self):
        todo = self.db.add_project_todo(
            self.project.id,
            "整理接口文档",
            "产品甲",
            scope="assigned",
            assignee="开发乙",
            assigned_by="产品甲",
        )

        self.assertIsNone(self.db.transfer_project_todo(todo.id, "产品甲", "开发丙"))
        unchanged = self.db.get_project_todo(todo.id)
        self.assertIsNotNone(unchanged)
        assert unchanged is not None
        self.assertEqual(unchanged.current_handler, "开发乙")

    def test_workflow_transfer_updates_current_stage_owner(self):
        todo = self.db.add_project_todo(
            self.project.id,
            "开发登录功能",
            "产品甲",
            scope="assigned",
            assignee="开发乙",
            assigned_by="产品甲",
            workflow="dev_test_accept",
            developer="开发乙",
            tester="测试甲",
            acceptor="产品甲",
        )

        transferred = self.db.transfer_project_todo(todo.id, "开发乙", "开发丙")

        self.assertIsNotNone(transferred)
        assert transferred is not None
        self.assertEqual(transferred.status, "dev_todo")
        self.assertEqual(transferred.developer, "开发丙")
        self.assertEqual(transferred.current_handler, "开发丙")


if __name__ == "__main__":
    unittest.main()
