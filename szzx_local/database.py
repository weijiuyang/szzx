from __future__ import annotations

import getpass
import json
import os
import socket
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import DailyReport, Project, ProjectDeck, ProjectMember, ProjectWeeklyReport, WeeklyReport
from .pin import DEFAULT_PIN, hash_pin, verify_pin


def _default_app_dir() -> Path:
    override = os.environ.get("SZZX_LOCAL_DATA_DIR")
    if override:
        return Path(override)

    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            return Path(base) / "SZZXLocalDesk"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "SZZXLocalDesk"
        return Path.home() / ".local" / "share" / "SZZXLocalDesk"

    return Path.cwd() / "local_data"


APP_DIR = _default_app_dir()
DB_PATH = APP_DIR / "szzx.json"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


class Database:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        self._migrate()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_data()
        try:
            with self.path.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
        except (OSError, json.JSONDecodeError):
            return self._empty_data()
        if not isinstance(loaded, dict):
            return self._empty_data()
        return loaded

    def _empty_data(self) -> dict[str, Any]:
        return {
            "settings": {},
            "weekly_reports": [],
            "projects": [],
            "project_members": [],
            "daily_reports": [],
            "project_weekly_reports": [],
            "project_decks": [],
            "counters": {},
        }

    def _migrate(self) -> None:
        empty = self._empty_data()
        for key, value in empty.items():
            self.data.setdefault(key, value.copy() if isinstance(value, dict) else list(value))

        if self.get_setting("pin_hash") is None:
            self.set_setting("pin_hash", hash_pin(DEFAULT_PIN), save=False)
        if self.get_setting("device_id") is None:
            self.set_setting("device_id", uuid.uuid4().hex, save=False)
        if self.get_setting("display_name") is None:
            self.set_setting("display_name", self._default_display_name(), save=False)
        self._seed_project_workspace()
        self._save()

    def _save(self) -> None:
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
        tmp_path.replace(self.path)

    def _next_id(self, table: str) -> int:
        counters = self.data.setdefault("counters", {})
        current = int(counters.get(table, 0)) + 1
        counters[table] = current
        return current

    def get_setting(self, key: str) -> str | None:
        value = self.data.get("settings", {}).get(key)
        return None if value is None else str(value)

    def set_setting(self, key: str, value: str, save: bool = True) -> None:
        self.data.setdefault("settings", {})[key] = value
        if save:
            self._save()

    def verify_pin(self, pin: str) -> bool:
        stored = self.get_setting("pin_hash")
        return stored is not None and verify_pin(pin, stored)

    def change_pin(self, new_pin: str) -> None:
        self.set_setting("pin_hash", hash_pin(new_pin))

    def device_id(self) -> str:
        value = self.get_setting("device_id")
        if value:
            return value
        value = uuid.uuid4().hex
        self.set_setting("device_id", value)
        return value

    def display_name(self) -> str:
        return self.get_setting("display_name") or self._default_display_name()

    def set_display_name(self, name: str) -> None:
        self.set_setting("display_name", name.strip())

    def pet_kind(self) -> str:
        return self.get_setting("pet_kind") or "penguin"

    def set_pet_kind(self, kind: str) -> None:
        self.set_setting("pet_kind", kind.strip() or "penguin")

    def _default_display_name(self) -> str:
        user = getpass.getuser() or "同事"
        host = socket.gethostname().split(".", 1)[0]
        if host:
            return f"{user}@{host}"
        return user

    def _seed_project_workspace(self) -> None:
        if self.data["projects"]:
            return
        created_at = datetime.now().isoformat(timespec="seconds")
        project_id = self._next_id("projects")
        self.data["projects"].append(
            {
                "id": project_id,
                "name": "GEO文库",
                "owner": self.display_name(),
                "description": "面向 GEO 内容沉淀、检索和复用的项目工作台。",
                "status": "推进中",
                "created_at": created_at,
            }
        )
        for name, role in (
            (self.display_name(), "产品经理"),
            ("前端开发", "前端开发"),
            ("后端开发", "后端开发"),
            ("测试同学", "测试"),
        ):
            self.data["project_members"].append(
                {
                    "id": self._next_id("project_members"),
                    "project_id": project_id,
                    "name": name,
                    "role": role,
                    "created_at": created_at,
                }
            )

    def add_project(self, name: str, owner: str, description: str, status: str = "推进中") -> Project:
        created_at = datetime.now()
        row = {
            "id": self._next_id("projects"),
            "name": name.strip(),
            "owner": owner.strip(),
            "description": description.strip(),
            "status": status.strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
        }
        self.data["projects"].append(row)
        self._save()
        return self._project_from_row(row)

    def list_projects(self) -> list[Project]:
        rows = sorted(self.data["projects"], key=lambda row: int(row["id"]), reverse=True)
        return [self._project_from_row(row) for row in rows]

    def get_project(self, project_id: int) -> Project | None:
        for row in self.data["projects"]:
            if int(row["id"]) == project_id:
                return self._project_from_row(row)
        return None

    def _project_from_row(self, row: dict[str, Any]) -> Project:
        return Project(
            id=int(row["id"]),
            name=str(row["name"]),
            owner=str(row["owner"]),
            description=str(row["description"]),
            status=str(row["status"]),
            created_at=_parse_time(str(row["created_at"])),
        )

    def add_project_member(self, project_id: int, name: str, role: str) -> ProjectMember:
        created_at = datetime.now()
        row = {
            "id": self._next_id("project_members"),
            "project_id": project_id,
            "name": name.strip(),
            "role": role.strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
        }
        self.data["project_members"].append(row)
        self._save()
        return self._member_from_row(row)

    def list_project_members(self, project_id: int) -> list[ProjectMember]:
        rows = [row for row in self.data["project_members"] if int(row["project_id"]) == project_id]
        rows.sort(key=lambda row: int(row["id"]))
        return [self._member_from_row(row) for row in rows]

    def _member_from_row(self, row: dict[str, Any]) -> ProjectMember:
        return ProjectMember(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            name=str(row["name"]),
            role=str(row["role"]),
            created_at=_parse_time(str(row["created_at"])),
        )

    def add_daily_report(self, project_id: int, member_name: str, role: str, content: str) -> DailyReport:
        created_at = datetime.now()
        row = {
            "id": self._next_id("daily_reports"),
            "project_id": project_id,
            "member_name": member_name.strip(),
            "role": role.strip(),
            "content": content.strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
        }
        self.data["daily_reports"].append(row)
        self._save()
        return self._daily_from_row(row)

    def list_daily_reports(self, project_id: int, limit: int = 50) -> list[DailyReport]:
        rows = [row for row in self.data["daily_reports"] if int(row["project_id"]) == project_id]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        return [self._daily_from_row(row) for row in rows[:limit]]

    def _daily_from_row(self, row: dict[str, Any]) -> DailyReport:
        return DailyReport(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            member_name=str(row["member_name"]),
            role=str(row["role"]),
            content=str(row["content"]),
            created_at=_parse_time(str(row["created_at"])),
        )

    def add_project_weekly_report(self, project_id: int, author: str, content: str) -> ProjectWeeklyReport:
        created_at = datetime.now()
        row = {
            "id": self._next_id("project_weekly_reports"),
            "project_id": project_id,
            "author": author.strip(),
            "content": content.strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
        }
        self.data["project_weekly_reports"].append(row)
        self._save()
        return self._project_weekly_from_row(row)

    def list_project_weekly_reports(self, project_id: int, limit: int = 20) -> list[ProjectWeeklyReport]:
        rows = [row for row in self.data["project_weekly_reports"] if int(row["project_id"]) == project_id]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        return [self._project_weekly_from_row(row) for row in rows[:limit]]

    def _project_weekly_from_row(self, row: dict[str, Any]) -> ProjectWeeklyReport:
        return ProjectWeeklyReport(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            author=str(row["author"]),
            content=str(row["content"]),
            created_at=_parse_time(str(row["created_at"])),
        )

    def add_project_deck(self, project_id: int, title: str, file_path: str) -> ProjectDeck:
        created_at = datetime.now()
        row = {
            "id": self._next_id("project_decks"),
            "project_id": project_id,
            "title": title.strip(),
            "file_path": file_path,
            "created_at": created_at.isoformat(timespec="seconds"),
        }
        self.data["project_decks"].append(row)
        self._save()
        return self._deck_from_row(row)

    def list_project_decks(self, project_id: int, limit: int = 20) -> list[ProjectDeck]:
        rows = [row for row in self.data["project_decks"] if int(row["project_id"]) == project_id]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        return [self._deck_from_row(row) for row in rows[:limit]]

    def get_project_deck(self, deck_id: int) -> ProjectDeck | None:
        for row in self.data["project_decks"]:
            if int(row["id"]) == deck_id:
                return self._deck_from_row(row)
        return None

    def _deck_from_row(self, row: dict[str, Any]) -> ProjectDeck:
        return ProjectDeck(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            title=str(row["title"]),
            file_path=str(row["file_path"]),
            created_at=_parse_time(str(row["created_at"])),
        )

    def add_weekly_report(self, content: str, summary: str, mood: str) -> WeeklyReport:
        created_at = datetime.now()
        row = {
            "id": self._next_id("weekly_reports"),
            "content": content,
            "summary": summary,
            "mood": mood,
            "created_at": created_at.isoformat(timespec="seconds"),
        }
        self.data["weekly_reports"].append(row)
        self._save()
        return self._weekly_from_row(row)

    def list_weekly_reports(self, limit: int = 20) -> list[WeeklyReport]:
        rows = sorted(self.data["weekly_reports"], key=lambda row: int(row["id"]), reverse=True)
        return [self._weekly_from_row(row) for row in rows[:limit]]

    def _weekly_from_row(self, row: dict[str, Any]) -> WeeklyReport:
        return WeeklyReport(
            id=int(row["id"]),
            content=str(row["content"]),
            summary=str(row["summary"]),
            mood=str(row["mood"]),
            created_at=_parse_time(str(row["created_at"])),
        )

    def close(self) -> None:
        self._save()
