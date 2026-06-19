from __future__ import annotations

import getpass
import base64
import json
import os
import socket
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import DailyReport, Project, ProjectDocument, ProjectMember, ProjectWeeklyReport, WeeklyReport
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
SHARED_TABLES = (
    "weekly_reports",
    "projects",
    "project_members",
    "daily_reports",
    "project_weekly_reports",
    "project_decks",
    "project_documents",
    "counters",
)


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
            "project_documents": [],
            "counters": {},
            "sync": {},
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
        self._migrate_project_decks()
        self._ensure_sync_state()
        self._save(bump_sync=False)

    def _save(self, bump_sync: bool = True) -> None:
        if bump_sync:
            self._bump_sync_revision()
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
        tmp_path.replace(self.path)

    def _bump_sync_revision(self) -> None:
        sync = self.data.setdefault("sync", {})
        sync["revision"] = int(sync.get("revision", 0)) + 1
        sync["updated_at"] = datetime.now().isoformat(timespec="microseconds")
        sync["origin"] = self.device_id()

    def _ensure_sync_state(self) -> None:
        sync = self.data.setdefault("sync", {})
        if sync.get("updated_at"):
            return
        sync["revision"] = int(sync.get("revision", 0)) or 1
        sync["updated_at"] = datetime.now().isoformat(timespec="microseconds")
        sync["origin"] = self.device_id()

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
            self._save(bump_sync=False)

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
        previous = self.display_name()
        next_name = name.strip()
        if previous and previous != next_name:
            aliases = self.display_name_aliases()
            if previous not in aliases:
                aliases.append(previous)
                self.set_setting("display_name_aliases", json.dumps(aliases, ensure_ascii=False), save=False)
        self.set_setting("display_name", next_name)

    def display_name_aliases(self) -> list[str]:
        raw = self.get_setting("display_name_aliases")
        if not raw:
            return []
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(loaded, list):
            return []
        return [str(item) for item in loaded if str(item).strip()]

    def current_user_names(self) -> set[str]:
        names = {self.display_name(), self._default_display_name(), *self.display_name_aliases()}
        return {name for name in names if name}

    def is_current_user_name(self, name: str) -> bool:
        return name in self.current_user_names()

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

    def _migrate_project_decks(self) -> None:
        documents = self.data.setdefault("project_documents", [])
        existing_deck_ids = {
            int(row.get("legacy_deck_id", 0))
            for row in documents
            if isinstance(row, dict) and row.get("legacy_deck_id") is not None
        }
        for deck in self.data.get("project_decks", []):
            deck_id = int(deck["id"])
            if deck_id in existing_deck_ids:
                continue
            documents.append(
                {
                    "id": self._next_id("project_documents"),
                    "legacy_deck_id": deck_id,
                    "project_id": int(deck["project_id"]),
                    "title": str(deck["title"]),
                    "doc_type": "项目汇报PPT",
                    "visibility": "team",
                    "uploader": self.display_name(),
                    "file_path": str(deck["file_path"]),
                    "created_at": str(deck["created_at"]),
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

    def delete_project(self, project_id: int) -> bool:
        before = len(self.data["projects"])
        self.data["projects"] = [row for row in self.data["projects"] if int(row["id"]) != project_id]
        if len(self.data["projects"]) == before:
            return False
        for table in (
            "project_members",
            "daily_reports",
            "project_weekly_reports",
            "project_decks",
            "project_documents",
        ):
            self.data[table] = [row for row in self.data[table] if int(row["project_id"]) != project_id]
        self._save()
        return True

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

    def add_project_document(
        self,
        project_id: int,
        title: str,
        doc_type: str,
        visibility: str,
        uploader: str,
        file_path: str,
    ) -> ProjectDocument:
        created_at = datetime.now()
        row = {
            "id": self._next_id("project_documents"),
            "project_id": project_id,
            "title": title.strip(),
            "doc_type": doc_type.strip(),
            "visibility": visibility.strip(),
            "uploader": uploader.strip(),
            "file_path": file_path,
            "created_at": created_at.isoformat(timespec="seconds"),
        }
        self.data["project_documents"].append(row)
        self._save()
        return self._document_from_row(row)

    def list_project_documents(
        self,
        project_id: int | None = None,
        visibility: str | None = None,
        doc_type: str | None = None,
        uploader: str | None = None,
        limit: int = 100,
    ) -> list[ProjectDocument]:
        rows = list(self.data["project_documents"])
        if project_id is not None:
            rows = [row for row in rows if int(row["project_id"]) == project_id]
        if visibility:
            rows = [row for row in rows if str(row.get("visibility", "team")) == visibility]
        if doc_type:
            rows = [row for row in rows if str(row.get("doc_type", "")) == doc_type]
        if uploader:
            rows = [row for row in rows if str(row.get("uploader", "")) == uploader]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        return [self._document_from_row(row) for row in rows[:limit]]

    def list_visible_project_documents(
        self,
        viewer: str,
        project_id: int | None = None,
        scope: str = "all",
        doc_type: str | None = None,
        limit: int = 100,
    ) -> list[ProjectDocument]:
        rows = self.list_project_documents(project_id=project_id, doc_type=doc_type, limit=1000)
        if scope == "mine":
            rows = [row for row in rows if row.uploader == viewer]
        elif scope == "team":
            rows = [row for row in rows if row.visibility == "team"]
        else:
            rows = [row for row in rows if row.visibility == "team" or row.uploader == viewer]
        return rows[:limit]

    def get_project_document(self, document_id: int) -> ProjectDocument | None:
        for row in self.data["project_documents"]:
            if int(row["id"]) == document_id:
                return self._document_from_row(row)
        return None

    def _document_from_row(self, row: dict[str, Any]) -> ProjectDocument:
        return ProjectDocument(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            title=str(row["title"]),
            doc_type=str(row.get("doc_type", "项目文档")),
            visibility=str(row.get("visibility", "team")),
            uploader=str(row.get("uploader", "")),
            file_path=str(row["file_path"]),
            created_at=_parse_time(str(row["created_at"])),
        )

    def add_project_deck(self, project_id: int, title: str, file_path: str) -> ProjectDocument:
        return self.add_project_document(
            project_id,
            title,
            "项目汇报PPT",
            "team",
            self.display_name(),
            file_path,
        )

    def list_project_decks(self, project_id: int, limit: int = 20) -> list[ProjectDocument]:
        return self.list_project_documents(project_id=project_id, doc_type="项目汇报PPT", limit=limit)

    def get_project_deck(self, deck_id: int) -> ProjectDocument | None:
        return self.get_project_document(deck_id)

    def _deck_from_row(self, row: dict[str, Any]) -> ProjectDocument:
        return self._document_from_row(row)

    def sync_state(self) -> dict[str, Any]:
        sync = self.data.setdefault("sync", {})
        return {
            "revision": int(sync.get("revision", 0)),
            "updated_at": str(sync.get("updated_at", "")),
            "origin": str(sync.get("origin", "")),
        }

    def _document_file_payloads(self, documents: Any) -> dict[str, dict[str, str]]:
        if not isinstance(documents, list):
            return {}
        files: dict[str, dict[str, str]] = {}
        for row in documents:
            if not isinstance(row, dict):
                continue
            document_id = str(row.get("id", ""))
            source = Path(str(row.get("file_path", "")))
            if not document_id or not source.is_file():
                continue
            try:
                files[document_id] = {
                    "name": source.name,
                    "content": base64.b64encode(source.read_bytes()).decode("ascii"),
                }
            except OSError:
                continue
        return files

    def shared_snapshot(self, include_files: bool = False) -> dict[str, Any]:
        tables = {
            table: self.data.get(table, {}).copy() if isinstance(self.data.get(table), dict) else list(self.data.get(table, []))
            for table in SHARED_TABLES
        }
        snapshot = {
            "sync": self.sync_state(),
            "tables": tables,
        }
        if include_files:
            snapshot["files"] = self._document_file_payloads(tables.get("project_documents", []))
        return snapshot

    def remote_sync_is_newer(self, sync: dict[str, Any]) -> bool:
        return self._remote_sync_key(sync) > self._local_sync_key()

    def apply_shared_snapshot(self, snapshot: dict[str, Any]) -> bool:
        if not self._is_remote_snapshot_newer(snapshot):
            return False
        tables = snapshot.get("tables")
        sync = snapshot.get("sync")
        if not isinstance(tables, dict) or not isinstance(sync, dict):
            return False
        for table in SHARED_TABLES:
            if table not in tables:
                return False
        files = snapshot.get("files")
        if isinstance(files, dict):
            self._restore_document_files(tables, files)
        for table in SHARED_TABLES:
            value = tables[table]
            if isinstance(self._empty_data()[table], dict):
                self.data[table] = dict(value) if isinstance(value, dict) else {}
            else:
                self.data[table] = list(value) if isinstance(value, list) else []
        self.data["sync"] = {
            "revision": int(sync.get("revision", 0)),
            "updated_at": str(sync.get("updated_at", "")),
            "origin": str(sync.get("origin", "")),
        }
        self._save(bump_sync=False)
        return True

    def _restore_document_files(self, tables: dict[str, Any], files: dict[str, Any]) -> None:
        documents = tables.get("project_documents")
        if not isinstance(documents, list):
            return
        for row in documents:
            if not isinstance(row, dict):
                continue
            document_id = str(row.get("id", ""))
            payload = files.get(document_id)
            if not isinstance(payload, dict):
                continue
            try:
                content = base64.b64decode(str(payload.get("content", "")))
            except ValueError:
                continue
            project_id = int(row.get("project_id", 0))
            filename = Path(str(payload.get("name") or row.get("title") or f"document-{document_id}")).name
            target_dir = self.path.parent / "documents" / str(project_id)
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            if target.exists():
                stem = target.stem or "document"
                suffix = target.suffix
                target = target_dir / f"{stem}-{document_id}{suffix}"
            try:
                target.write_bytes(content)
            except OSError:
                continue
            row["file_path"] = str(target)

    def _is_remote_snapshot_newer(self, snapshot: dict[str, Any]) -> bool:
        remote = snapshot.get("sync")
        if not isinstance(remote, dict):
            return False
        return self.remote_sync_is_newer(remote)

    def _remote_sync_key(self, sync: dict[str, Any]) -> tuple[int, str, str]:
        return (
            int(sync.get("revision", 0)),
            str(sync.get("updated_at", "")),
            str(sync.get("origin", "")),
        )

    def _local_sync_key(self) -> tuple[int, str, str]:
        local = self.sync_state()
        return self._remote_sync_key(local)

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
        self._save(bump_sync=False)
