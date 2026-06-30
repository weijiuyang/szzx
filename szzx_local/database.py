from __future__ import annotations

import base64
import getpass
import hashlib
import json
import os
import socket
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import DailyReport, Project, ProjectDocument, ProjectMember, ProjectTodo, ProjectWeeklyReport, RestDay, WeeklyReport
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
LEGACY_DEMO_PROJECT_NAME = "GEO文库"
LEGACY_DEMO_PROJECT_DESCRIPTION = "面向 GEO 内容沉淀、检索和复用的项目工作台。"
PROJECT_ID_TIMESTAMP_FLOOR = 20000101000000000
SHARED_TABLES = (
    "weekly_reports",
    "projects",
    "project_members",
    "daily_reports",
    "project_weekly_reports",
    "project_decks",
    "project_documents",
    "project_todos",
    "rest_days",
    "name_claims",
    "deleted_projects",
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
            "project_todos": [],
            "rest_days": [],
            "name_claims": [],
            "deleted_projects": [],
            "counters": {},
            "sync": {},
        }

    def _migrate(self) -> None:
        empty = self._empty_data()
        for key, value in empty.items():
            self.data.setdefault(key, value.copy() if isinstance(value, dict) else list(value))

        if self.get_setting("pin_hash") is None:
            self.set_setting("pin_hash", hash_pin(DEFAULT_PIN), save=False)
        if self.get_setting("mac_address") is None:
            self.set_setting("mac_address", self._mac_address(), save=False)
        if self.get_setting("device_id") is None:
            self.set_setting("device_id", self._stable_device_id(), save=False)
        if self.get_setting("display_name") is None:
            self.set_setting("display_name", self._default_display_name(), save=False)
        if self.get_setting("display_name_locked") is None:
            locked = "true" if self.display_name_aliases() else "false"
            self.set_setting("display_name_locked", locked, save=False)
        if self.get_setting("autostart_enabled") is None:
            self.set_setting("autostart_enabled", "true", save=False)
        self._remove_legacy_demo_project()
        self._migrate_project_decks()
        self._migrate_project_ids_to_timestamps()
        self._migrate_weekly_report_owners()
        self._migrate_weekly_ids_to_timestamps()
        self._claim_display_name(self.display_name(), save=False)
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
        sync["actor"] = self.display_name()

    def _ensure_sync_state(self) -> None:
        sync = self.data.setdefault("sync", {})
        if sync.get("updated_at"):
            return
        sync["revision"] = int(sync.get("revision", 0))
        sync["updated_at"] = ""
        sync["origin"] = ""
        sync["actor"] = ""

    def _next_id(self, table: str) -> int:
        counters = self.data.setdefault("counters", {})
        current = int(counters.get(table, 0)) + 1
        counters[table] = current
        return current

    def _next_project_id(self, created_at: datetime) -> int:
        base = int(created_at.strftime("%Y%m%d%H%M%S")) * 1000 + created_at.microsecond // 1000
        existing_ids = {
            int(row.get("id", 0) or 0)
            for row in self.data.get("projects", [])
            if isinstance(row, dict)
        }
        project_id = base
        while project_id in existing_ids:
            project_id += 1
        counters = self.data.setdefault("counters", {})
        counters["projects"] = max(int(counters.get("projects", 0) or 0), project_id)
        return project_id

    def _next_timestamp_id(self, table: str, created_at: datetime) -> int:
        base = int(created_at.strftime("%Y%m%d%H%M%S")) * 1000 + created_at.microsecond // 1000
        existing_ids = {
            int(row.get("id", 0) or 0)
            for row in self.data.get(table, [])
            if isinstance(row, dict)
        }
        next_id = base
        while next_id in existing_ids:
            next_id += 1
        counters = self.data.setdefault("counters", {})
        counters[table] = max(int(counters.get(table, 0) or 0), next_id)
        return next_id

    def _is_timestamp_project_id(self, value: Any) -> bool:
        try:
            return int(value) >= PROJECT_ID_TIMESTAMP_FLOOR
        except (TypeError, ValueError):
            return False

    def _with_operator(self, row: dict[str, Any]) -> dict[str, Any]:
        row["operator"] = self.display_name()
        row["operator_device_id"] = self.device_id()
        return row

    def get_setting(self, key: str) -> str | None:
        value = self.data.get("settings", {}).get(key)
        return None if value is None else str(value)

    def set_setting(self, key: str, value: str, save: bool = True) -> None:
        self.data.setdefault("settings", {})[key] = value
        if save:
            self._save(bump_sync=False)

    def save_local_settings(self) -> None:
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
        value = self._stable_device_id()
        self.set_setting("device_id", value)
        return value

    def mac_address(self) -> str:
        value = self.get_setting("mac_address")
        if value:
            return value
        value = self._mac_address()
        self.set_setting("mac_address", value)
        return value

    def display_name(self) -> str:
        return self.get_setting("display_name") or self._default_display_name()

    def display_name_locked(self) -> bool:
        return self.get_setting("display_name_locked") == "true"

    def display_name_claim_owner(self, name: str) -> str | None:
        target = self._normalize_display_name(name)
        if not target:
            return None
        for row in self.data.get("name_claims", []):
            if not isinstance(row, dict):
                continue
            if self._normalize_display_name(str(row.get("name", ""))) != target:
                continue
            device_id = str(row.get("device_id", ""))
            mac_address = str(row.get("mac_address", ""))
            if device_id == self.device_id() or mac_address == self.mac_address():
                continue
            return device_id or mac_address or "unknown"
        return None

    def set_display_name(self, name: str) -> None:
        previous = self.display_name()
        next_name = name.strip()
        if self.display_name_locked() and next_name != previous:
            raise ValueError("名字已经锁定，不能再次修改。")
        if self.display_name_claim_owner(next_name) is not None:
            raise ValueError("这个名字已经被别人使用。")
        if previous and previous != next_name:
            aliases = self.display_name_aliases()
            if previous not in aliases:
                aliases.append(previous)
                self.set_setting("display_name_aliases", json.dumps(aliases, ensure_ascii=False), save=False)
            self.set_setting("display_name", next_name, save=False)
            self.set_setting("display_name_locked", "true", save=False)
            self._claim_display_name(next_name, save=False)
            self._save()
            return
        self._claim_display_name(next_name)

    def release_display_name(self) -> None:
        previous = self.display_name()
        aliases = self.display_name_aliases()
        if previous and previous not in aliases:
            aliases.append(previous)
            self.set_setting("display_name_aliases", json.dumps(aliases, ensure_ascii=False), save=False)
        self._remove_own_display_name_claim(previous)
        self.set_setting("display_name", self._default_display_name(), save=False)
        self.set_setting("display_name_locked", "false", save=False)
        self._save()

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

    def known_display_names(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for name in (self.display_name(), *self.display_name_aliases()):
            normalized = self._normalize_display_name(name)
            if normalized and normalized not in seen:
                names.append(name)
                seen.add(normalized)
        for row in self.data.get("name_claims", []):
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "")).strip()
            normalized = self._normalize_display_name(name)
            if normalized and normalized not in seen:
                names.append(name)
                seen.add(normalized)
        for row in self.data.get("rest_days", []):
            if not isinstance(row, dict):
                continue
            name = str(row.get("operator", "")).strip()
            normalized = self._normalize_display_name(name)
            if normalized and normalized not in seen:
                names.append(name)
                seen.add(normalized)
        return names

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

    def _mac_address(self) -> str:
        node = uuid.getnode()
        return ":".join(f"{(node >> shift) & 0xff:02x}" for shift in range(40, -1, -8))

    def _stable_device_id(self) -> str:
        digest = hashlib.sha256(self._mac_address().encode("utf-8")).hexdigest()
        return f"mac-{digest[:32]}"

    def _normalize_display_name(self, name: str) -> str:
        return " ".join(name.strip().split()).casefold()

    def _claim_display_name(self, name: str, save: bool = True) -> None:
        normalized = self._normalize_display_name(name)
        if not normalized:
            return
        claims = self.data.setdefault("name_claims", [])
        device_id = self.device_id()
        mac_address = self.mac_address()
        claims[:] = [
            row
            for row in claims
            if not isinstance(row, dict)
            or (
                self._normalize_display_name(str(row.get("name", ""))) != normalized
                and str(row.get("device_id", "")) != device_id
                and str(row.get("mac_address", "")) != mac_address
            )
        ]
        claims.append(
            {
                "name": name.strip(),
                "normalized_name": normalized,
                "device_id": device_id,
                "mac_address": mac_address,
                "claimed_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        if save:
            self._save()

    def _remove_own_display_name_claim(self, name: str) -> None:
        normalized = self._normalize_display_name(name)
        device_id = self.device_id()
        mac_address = self.mac_address()
        claims = self.data.setdefault("name_claims", [])
        claims[:] = [
            row
            for row in claims
            if not isinstance(row, dict)
            or self._normalize_display_name(str(row.get("name", ""))) != normalized
            or (
                str(row.get("device_id", "")) != device_id
                and str(row.get("mac_address", "")) != mac_address
            )
        ]

    def _remove_legacy_demo_project(self) -> None:
        legacy_project_ids = [
            int(row["id"])
            for row in self.data["projects"]
            if str(row.get("name", "")) == LEGACY_DEMO_PROJECT_NAME
            and str(row.get("description", "")) == LEGACY_DEMO_PROJECT_DESCRIPTION
        ]
        if not legacy_project_ids:
            return

        removable_ids = set()
        content_tables = ("daily_reports", "project_weekly_reports", "project_decks", "project_documents")
        for project_id in legacy_project_ids:
            has_content = any(
                int(row.get("project_id", 0)) == project_id
                for table in content_tables
                for row in self.data.get(table, [])
            )
            if not has_content:
                removable_ids.add(project_id)

        if not removable_ids:
            return

        self.data["projects"] = [row for row in self.data["projects"] if int(row["id"]) not in removable_ids]
        self.data["project_members"] = [
            row for row in self.data["project_members"] if int(row["project_id"]) not in removable_ids
        ]

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

    def _migrate_project_ids_to_timestamps(self) -> None:
        projects = self.data.get("projects", [])
        if not isinstance(projects, list):
            return
        id_map: dict[int, int] = {}
        for row in projects:
            if not isinstance(row, dict):
                continue
            try:
                old_id = int(row.get("id", 0) or 0)
            except (TypeError, ValueError):
                continue
            if self._is_timestamp_project_id(old_id):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                created_at = datetime.now()
            new_id = self._next_project_id(created_at)
            if new_id == old_id:
                continue
            row["id"] = new_id
            row.setdefault("legacy_project_id", old_id)
            row.setdefault("source_device_id", str(row.get("operator_device_id") or self.device_id()))
            row.setdefault("source_id", str(old_id))
            id_map[old_id] = new_id

        if not id_map:
            self._sync_counters_to_rows()
            return

        for table in (
            "project_members",
            "daily_reports",
            "project_weekly_reports",
            "project_decks",
            "project_documents",
            "project_todos",
        ):
            rows = self.data.get(table, [])
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    old_project_id = int(row.get("project_id", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if old_project_id in id_map:
                    row["project_id"] = id_map[old_project_id]
        self._sync_counters_to_rows()

    def _migrate_weekly_report_owners(self) -> None:
        for row in self.data.get("weekly_reports", []):
            if not isinstance(row, dict):
                continue
            row.setdefault("operator", self.display_name())
            row.setdefault("operator_device_id", self.device_id())

    def _migrate_weekly_ids_to_timestamps(self) -> None:
        for table in ("weekly_reports", "project_weekly_reports"):
            rows = self.data.get(table, [])
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    old_id = int(row.get("id", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if self._is_timestamp_project_id(old_id):
                    continue
                try:
                    created_at = _parse_time(str(row.get("created_at", "")))
                except ValueError:
                    created_at = datetime.now()
                new_id = self._next_timestamp_id(table, created_at)
                if new_id == old_id:
                    continue
                row["id"] = new_id
                row.setdefault("legacy_id", old_id)
        self._sync_counters_to_rows()

    def add_project(self, name: str, owner: str, description: str, status: str = "推进中") -> Project:
        created_at = datetime.now()
        row = self._with_operator({
            "id": self._next_project_id(created_at),
            "name": name.strip(),
            "owner": owner.strip(),
            "description": description.strip(),
            "status": status.strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
        })
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
        project_row = self._project_row(project_id)
        if project_row is None:
            return False
        self._remember_deleted_project(project_row)
        self._remove_project_rows(project_id)
        self._save()
        return True

    def _project_row(self, project_id: int) -> dict[str, Any] | None:
        for row in self.data["projects"]:
            if isinstance(row, dict) and int(row.get("id", 0) or 0) == project_id:
                return row
        return None

    def _remove_project_rows(self, project_id: int) -> None:
        self.data["projects"] = [
            row
            for row in self.data["projects"]
            if not isinstance(row, dict) or int(row.get("id", 0) or 0) != project_id
        ]
        for table in (
            "project_members",
            "daily_reports",
            "project_weekly_reports",
            "project_decks",
            "project_documents",
            "project_todos",
        ):
            self.data[table] = [
                row
                for row in self.data[table]
                if not isinstance(row, dict) or int(row.get("project_id", 0) or 0) != project_id
            ]

    def _remember_deleted_project(self, project_row: dict[str, Any]) -> None:
        source = self._row_source_key(project_row)
        if source is None:
            source = (self.device_id(), str(project_row.get("id", "")))
        source_device, source_id = source
        tombstones = self.data.setdefault("deleted_projects", [])
        tombstone = {
            "source_device_id": source_device,
            "source_id": source_id,
            "project_id": int(project_row.get("id", 0) or 0),
            "name": str(project_row.get("name", "")),
            "deleted_by": self.display_name(),
            "deleted_by_device_id": self.device_id(),
            "deleted_at": datetime.now().isoformat(timespec="microseconds"),
        }
        for index, row in enumerate(tombstones):
            if not isinstance(row, dict):
                continue
            if self._deleted_project_key(row) == (source_device, source_id):
                tombstones[index] = tombstone
                return
        tombstones.append(tombstone)

    def update_project_description(self, project_id: int, description: str) -> Project | None:
        for row in self.data["projects"]:
            if int(row["id"]) != project_id:
                continue
            row["description"] = description.strip()
            self._save()
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
        row = self._with_operator({
            "id": self._next_id("project_members"),
            "project_id": project_id,
            "name": name.strip(),
            "role": role.strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
        })
        self.data["project_members"].append(row)
        self._save()
        return self._member_from_row(row)

    def list_project_members(self, project_id: int) -> list[ProjectMember]:
        rows = [row for row in self.data["project_members"] if int(row["project_id"]) == project_id]
        rows.sort(key=lambda row: int(row["id"]))
        return [self._member_from_row(row) for row in rows]

    def delete_project_member(self, member_id: int) -> bool:
        rows = self.data["project_members"]
        for index, row in enumerate(rows):
            if int(row["id"]) != member_id:
                continue
            del rows[index]
            self._save()
            return True
        return False

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
        row = self._with_operator({
            "id": self._next_id("daily_reports"),
            "project_id": project_id,
            "member_name": member_name.strip(),
            "role": role.strip(),
            "content": content.strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
        })
        self.data["daily_reports"].append(row)
        self._save()
        return self._daily_from_row(row)

    def list_daily_reports(self, project_id: int, limit: int = 50) -> list[DailyReport]:
        rows = [row for row in self.data["daily_reports"] if int(row["project_id"]) == project_id]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        return [self._daily_from_row(row) for row in rows[:limit]]

    def daily_report_counts_by_day(self, mine_only: bool = True) -> dict[date, int]:
        counts: dict[date, int] = {}
        for row in self.data["daily_reports"]:
            if not isinstance(row, dict):
                continue
            if mine_only and not self.is_current_user_name(str(row.get("member_name", ""))):
                continue
            try:
                day = _parse_time(str(row.get("created_at", ""))).date()
            except ValueError:
                continue
            counts[day] = counts.get(day, 0) + 1
        return counts

    def daily_reports_on_day(self, day: date, mine_only: bool = True) -> list[dict[str, Any]]:
        project_names = {
            int(row["id"]): str(row.get("name", "未知项目"))
            for row in self.data["projects"]
            if isinstance(row, dict)
        }
        reports: list[dict[str, Any]] = []
        for row in self.data["daily_reports"]:
            if not isinstance(row, dict):
                continue
            if mine_only and not self.is_current_user_name(str(row.get("member_name", ""))):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            if created_at.date() != day:
                continue
            try:
                project_id = int(row.get("project_id", 0) or 0)
            except (TypeError, ValueError):
                project_id = 0
            reports.append(
                {
                    "report": self._daily_from_row(row),
                    "project_id": project_id,
                    "project_name": project_names.get(project_id, "未知项目"),
                    "member_name": str(row.get("member_name", "")),
                    "role": str(row.get("role", "")),
                    "content": str(row.get("content", "")),
                    "created_at": created_at,
                }
            )
        reports.sort(key=lambda item: item["created_at"], reverse=True)
        return reports

    def daily_reports_between(self, start_day: date, end_day: date, mine_only: bool = True) -> list[dict[str, Any]]:
        reports: list[dict[str, Any]] = []
        current = start_day
        while current <= end_day:
            reports.extend(self.daily_reports_on_day(current, mine_only=mine_only))
            current += timedelta(days=1)
        reports.sort(key=lambda item: item["created_at"])
        return reports

    def today_project_logs(self, member_name: str | None = None) -> list[dict[str, Any]]:
        today = date.today()
        logs = self.project_logs_for_member(member_name)
        return [log for log in logs if _parse_time(str(log["created_at"])).date() == today]

    def project_logs_for_member(self, member_name: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        target = self._normalize_display_name(member_name or self.display_name())
        project_names = {
            int(row["id"]): str(row.get("name", "未知项目"))
            for row in self.data["projects"]
            if isinstance(row, dict)
        }
        logs: list[dict[str, Any]] = []
        for row in self.data["daily_reports"]:
            if not isinstance(row, dict):
                continue
            name = str(row.get("member_name", "")).strip()
            if target and self._normalize_display_name(name) != target:
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            try:
                project_id = int(row.get("project_id", 0) or 0)
            except (TypeError, ValueError):
                project_id = 0
            logs.append(
                {
                    "project_id": project_id,
                    "project_name": project_names.get(project_id, "未知项目"),
                    "member_name": name,
                    "role": str(row.get("role", "")),
                    "content": str(row.get("content", "")),
                    "created_at": created_at.isoformat(timespec="seconds"),
                }
            )
        logs.sort(key=lambda item: str(item["created_at"]), reverse=True)
        return logs if limit is None else logs[:limit]

    def delete_daily_report(self, report_id: int, mine_only: bool = True) -> bool:
        rows = self.data["daily_reports"]
        for index, row in enumerate(rows):
            if int(row["id"]) != report_id:
                continue
            if mine_only and not self.is_current_user_name(str(row.get("member_name", ""))):
                return False
            del rows[index]
            self._save()
            return True
        return False

    def _daily_from_row(self, row: dict[str, Any]) -> DailyReport:
        return DailyReport(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            member_name=str(row["member_name"]),
            role=str(row["role"]),
            content=str(row["content"]),
            created_at=_parse_time(str(row["created_at"])),
        )

    def add_project_todo(
        self,
        project_id: int,
        title: str,
        creator: str,
        scope: str = "personal",
        assignee: str = "",
        assigned_by: str = "",
    ) -> ProjectTodo:
        created_at = datetime.now()
        todo_scope = scope if scope in {"personal", "project", "assigned"} else "personal"
        row = self._with_operator({
            "id": self._next_id("project_todos"),
            "project_id": project_id,
            "title": title.strip(),
            "creator": creator.strip(),
            "scope": todo_scope,
            "assignee": assignee.strip(),
            "assigned_by": assigned_by.strip(),
            "status": "todo",
            "completed_by": "",
            "created_at": created_at.isoformat(timespec="seconds"),
            "completed_at": "",
        })
        self.data["project_todos"].append(row)
        self._save()
        return self._todo_from_row(row)

    def list_project_todos(
        self,
        project_id: int,
        include_completed: bool = False,
        scope: str | None = None,
    ) -> list[ProjectTodo]:
        rows = [row for row in self.data["project_todos"] if int(row["project_id"]) == project_id]
        if scope in {"personal", "project", "assigned"}:
            rows = [row for row in rows if str(row.get("scope", "personal")) == scope]
        if not include_completed:
            rows = [row for row in rows if str(row.get("status", "todo")) != "done"]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        return [self._todo_from_row(row) for row in rows]

    def list_all_project_todos(
        self,
        include_completed: bool = False,
        scope: str | None = None,
    ) -> list[ProjectTodo]:
        rows = list(self.data["project_todos"])
        if scope in {"personal", "project", "assigned"}:
            rows = [row for row in rows if str(row.get("scope", "personal")) == scope]
        if not include_completed:
            rows = [row for row in rows if str(row.get("status", "todo")) != "done"]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        return [self._todo_from_row(row) for row in rows]

    def delete_project_todo(self, todo_id: int) -> bool:
        rows = self.data["project_todos"]
        for index, row in enumerate(rows):
            if int(row["id"]) != todo_id:
                continue
            del rows[index]
            self._save()
            return True
        return False

    def complete_project_todo(
        self,
        todo_id: int,
        member_name: str,
        role: str,
        progress_prefix: str = "完成待办",
    ) -> DailyReport | ProjectTodo | None:
        for row in self.data["project_todos"]:
            if int(row["id"]) != todo_id:
                continue
            if str(row.get("status", "todo")) == "done":
                return None
            completed_at = datetime.now()
            row["status"] = "done"
            row["completed_by"] = member_name.strip()
            row["completed_at"] = completed_at.isoformat(timespec="seconds")
            if str(row.get("scope", "personal")) == "project":
                self._save()
                return self._todo_from_row(row)
            report = self.add_daily_report(
                int(row["project_id"]),
                member_name,
                role,
                f"{progress_prefix}：{str(row.get('title', '')).strip()}",
            )
            return report
        return None

    def _todo_from_row(self, row: dict[str, Any]) -> ProjectTodo:
        completed_at = str(row.get("completed_at", "")).strip()
        return ProjectTodo(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            title=str(row["title"]),
            creator=str(row.get("creator", "")),
            scope=str(row.get("scope", "personal")),
            assignee=str(row.get("assignee", "")),
            assigned_by=str(row.get("assigned_by", "")),
            status=str(row.get("status", "todo")),
            completed_by=str(row.get("completed_by", "")),
            created_at=_parse_time(str(row["created_at"])),
            completed_at=_parse_time(completed_at) if completed_at else None,
        )

    def add_project_weekly_report(self, project_id: int, author: str, content: str) -> ProjectWeeklyReport:
        created_at = datetime.now()
        row = self._with_operator({
            "id": self._next_timestamp_id("project_weekly_reports", created_at),
            "project_id": project_id,
            "author": author.strip(),
            "content": content.strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
        })
        self.data["project_weekly_reports"].append(row)
        self._save()
        return self._project_weekly_from_row(row)

    def list_project_weekly_reports(self, project_id: int, limit: int = 20) -> list[ProjectWeeklyReport]:
        rows = [row for row in self.data["project_weekly_reports"] if int(row["project_id"]) == project_id]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        return [self._project_weekly_from_row(row) for row in rows[:limit]]

    def delete_project_weekly_report(self, report_id: int) -> bool:
        rows = self.data["project_weekly_reports"]
        for index, row in enumerate(rows):
            if int(row["id"]) != report_id:
                continue
            del rows[index]
            self._save()
            return True
        return False

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
        row = self._with_operator({
            "id": self._next_id("project_documents"),
            "project_id": project_id,
            "title": title.strip(),
            "doc_type": doc_type.strip(),
            "visibility": visibility.strip(),
            "uploader": uploader.strip(),
            "file_path": file_path,
            "created_at": created_at.isoformat(timespec="seconds"),
        })
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

    def delete_project_document(self, document_id: int, uploader: str | None = None) -> bool:
        rows = self.data["project_documents"]
        for index, row in enumerate(rows):
            if int(row["id"]) != document_id:
                continue
            if uploader is not None:
                row_uploader = self._normalize_display_name(str(row.get("uploader", "")))
                expected_uploader = self._normalize_display_name(uploader)
                if row_uploader != expected_uploader:
                    return False
            del rows[index]
            self._save()
            return True
        return False

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
            "actor": str(sync.get("actor", "")),
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

    def apply_shared_snapshot(self, snapshot: dict[str, Any], force: bool = False) -> bool:
        if not force and not self._is_remote_snapshot_newer(snapshot):
            return False
        tables = snapshot.get("tables")
        sync = snapshot.get("sync")
        if not isinstance(tables, dict) or not isinstance(sync, dict):
            return False
        for table in SHARED_TABLES:
            if table not in tables:
                if table in ("name_claims", "project_todos", "deleted_projects"):
                    tables[table] = list(self.data.get(table, [])) if table == "deleted_projects" else []
                else:
                    return False
        local_has_missing_rows = self._snapshot_missing_local_shared_rows(tables)
        self._backup_before_sync()
        files = snapshot.get("files")
        changed = False
        if self._merge_deleted_projects(tables.get("deleted_projects")):
            changed = True
        if self._apply_deleted_projects():
            changed = True
        project_id_map, projects_changed = self._merge_remote_projects(tables.get("projects"))
        changed = changed or projects_changed
        for table in SHARED_TABLES:
            if table in {"projects", "deleted_projects", "counters"}:
                continue
            if self._merge_remote_table(table, tables.get(table), project_id_map):
                changed = True
        if self._apply_deleted_projects():
            changed = True
        if isinstance(files, dict) and changed:
            self._restore_document_files(self.data, files)
        self._sync_counters_to_rows()
        self.data["sync"] = {
            "revision": int(sync.get("revision", 0)),
            "updated_at": str(sync.get("updated_at", "")),
            "origin": str(sync.get("origin", "")),
            "actor": str(sync.get("actor", "")),
        }
        self._claim_display_name(self.display_name(), save=False)
        self._save(bump_sync=local_has_missing_rows)
        return True

    def merge_missing_shared_snapshot(self, snapshot: dict[str, Any]) -> bool:
        tables = snapshot.get("tables")
        if not isinstance(tables, dict):
            return False
        changed = False
        if self._merge_deleted_projects(tables.get("deleted_projects")):
            changed = True
        if self._apply_deleted_projects():
            changed = True
        project_id_map, projects_changed = self._merge_remote_projects(tables.get("projects"))
        changed = changed or projects_changed
        for table in SHARED_TABLES:
            if table in {"projects", "deleted_projects", "counters"}:
                continue
            if self._merge_remote_table(table, tables.get(table), project_id_map):
                changed = True
        if self._apply_deleted_projects():
            changed = True
        if not changed:
            return False
        files = snapshot.get("files")
        if isinstance(files, dict):
            self._restore_document_files(self.data, files)
        self._sync_counters_to_rows()
        self._save()
        return True

    def _merge_remote_projects(self, remote_value: Any) -> tuple[dict[int, int], bool]:
        project_id_map: dict[int, int] = {}
        changed = False
        local_projects = self.data.get("projects")
        if not isinstance(remote_value, list) or not isinstance(local_projects, list):
            return project_id_map, changed
        existing_sources = self._source_index("projects")
        existing_ids = self._id_index("projects")
        deleted_sources = self._deleted_project_keys()
        for row in remote_value:
            if not isinstance(row, dict):
                continue
            try:
                remote_id = int(row.get("id", 0) or 0)
            except (TypeError, ValueError):
                continue
            source = self._row_source_key(row)
            if source and source in deleted_sources:
                continue
            if source and source in existing_sources:
                project_id_map[remote_id] = int(existing_sources[source].get("id", remote_id))
                continue
            existing = existing_ids.get(remote_id)
            if existing is not None and self._rows_match(existing, row):
                self._remember_row_source(existing, row)
                project_id_map[remote_id] = remote_id
                continue
            next_row = dict(row)
            self._remember_row_source(next_row, row)
            if existing is not None:
                try:
                    next_created_at = _parse_time(str(next_row.get("created_at", "")))
                except ValueError:
                    next_created_at = datetime.now()
                next_row["id"] = self._next_project_id(next_created_at)
            local_projects.append(next_row)
            project_id_map[remote_id] = int(next_row["id"])
            changed = True
        return project_id_map, changed

    def _merge_remote_table(self, table: str, remote_value: Any, project_id_map: dict[int, int]) -> bool:
        local_value = self.data.get(table)
        if isinstance(self._empty_data()[table], dict):
            if not isinstance(remote_value, dict) or not isinstance(local_value, dict):
                return False
            changed = False
            for key, value in remote_value.items():
                try:
                    remote_int = int(value)
                except (TypeError, ValueError):
                    continue
                local_int = int(local_value.get(key, 0) or 0)
                if remote_int > local_int:
                    local_value[key] = remote_int
                    changed = True
            return changed
        if not isinstance(remote_value, list) or not isinstance(local_value, list):
            return False
        existing_sources = self._source_index(table)
        existing_ids = self._id_index(table)
        changed = False
        for row in remote_value:
            if not isinstance(row, dict):
                continue
            source = self._row_source_key(row)
            if source and source in existing_sources:
                continue
            next_row = dict(row)
            if "project_id" in next_row:
                try:
                    remote_project_id = int(next_row.get("project_id", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if remote_project_id not in project_id_map:
                    continue
                next_row["project_id"] = project_id_map[remote_project_id]
            key = self._shared_row_key(table, next_row)
            if table == "name_claims":
                existing = next(
                    (
                        item
                        for item in local_value
                        if isinstance(item, dict) and self._shared_row_key(table, item) == key
                    ),
                    None,
                )
                if existing is not None:
                    same_device = (
                        str(next_row.get("device_id", "")) == str(existing.get("device_id", ""))
                        and str(next_row.get("mac_address", "")) == str(existing.get("mac_address", ""))
                    )
                    if (
                        not same_device
                        and str(next_row.get("claimed_at", "")) >= str(existing.get("claimed_at", ""))
                    ) or str(next_row.get("claimed_at", "")) > str(existing.get("claimed_at", "")):
                        existing.update(next_row)
                        changed = True
                    continue
                local_value.append(next_row)
                changed = True
                continue
            try:
                row_id = int(next_row.get("id", 0) or 0)
            except (TypeError, ValueError):
                continue
            existing = existing_ids.get(row_id)
            if existing is not None and self._rows_match(existing, next_row):
                self._remember_row_source(existing, row)
                continue
            self._remember_row_source(next_row, row)
            if existing is not None:
                next_row["id"] = self._next_id(table)
            local_value.append(next_row)
            changed = True
        return changed

    def _merge_deleted_projects(self, remote_value: Any) -> bool:
        if not isinstance(remote_value, list):
            return False
        tombstones = self.data.setdefault("deleted_projects", [])
        existing = {
            key: row
            for row in tombstones
            if isinstance(row, dict) and (key := self._deleted_project_key(row)) is not None
        }
        changed = False
        for row in remote_value:
            if not isinstance(row, dict):
                continue
            key = self._deleted_project_key(row)
            if key is None:
                continue
            current = existing.get(key)
            if current is not None:
                if str(row.get("deleted_at", "")) > str(current.get("deleted_at", "")):
                    current.update(dict(row))
                    changed = True
                continue
            next_row = dict(row)
            tombstones.append(next_row)
            existing[key] = next_row
            changed = True
        return changed

    def _snapshot_missing_local_shared_rows(self, tables: dict[str, Any]) -> bool:
        for table in SHARED_TABLES:
            if table == "counters" or isinstance(self._empty_data()[table], dict):
                continue
            remote_value = tables.get(table)
            local_value = self.data.get(table)
            if not isinstance(remote_value, list) or not isinstance(local_value, list):
                continue
            remote_keys: set[tuple[str, ...]] = set()
            for row in remote_value:
                if not isinstance(row, dict):
                    continue
                source = self._row_source_key(row)
                if source is not None:
                    remote_keys.add((table, "source", source[0], source[1]))
                remote_keys.add(self._shared_row_key(table, row))
            for row in local_value:
                if not isinstance(row, dict):
                    continue
                source = self._row_source_key(row)
                if source is not None and (table, "source", source[0], source[1]) in remote_keys:
                    continue
                if self._shared_row_key(table, row) in remote_keys:
                    continue
                return True
        return False

    def _apply_deleted_projects(self) -> bool:
        deleted_sources = self._deleted_project_keys()
        if not deleted_sources:
            return False
        changed = False
        for row in list(self.data.get("projects", [])):
            if not isinstance(row, dict):
                continue
            source = self._row_source_key(row)
            if source is None or source not in deleted_sources:
                continue
            try:
                project_id = int(row.get("id", 0) or 0)
            except (TypeError, ValueError):
                continue
            self._remove_project_rows(project_id)
            changed = True
        return changed

    def _deleted_project_keys(self) -> set[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        for row in self.data.get("deleted_projects", []):
            if not isinstance(row, dict):
                continue
            key = self._deleted_project_key(row)
            if key is not None:
                keys.add(key)
        return keys

    def _deleted_project_key(self, row: dict[str, Any]) -> tuple[str, str] | None:
        source_device = str(row.get("source_device_id") or row.get("deleted_by_device_id") or "").strip()
        source_id = str(row.get("source_id") or row.get("project_id") or "").strip()
        if not source_device or not source_id:
            return None
        return source_device, source_id

    def _id_index(self, table: str) -> dict[int, dict[str, Any]]:
        rows = self.data.get(table)
        if not isinstance(rows, list):
            return {}
        index: dict[int, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                index[int(row.get("id", 0) or 0)] = row
            except (TypeError, ValueError):
                continue
        return index

    def _source_index(self, table: str) -> dict[tuple[str, str], dict[str, Any]]:
        rows = self.data.get(table)
        if not isinstance(rows, list):
            return {}
        index: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            source = self._row_source_key(row)
            if source:
                index[source] = row
        return index

    def _row_source_key(self, row: dict[str, Any]) -> tuple[str, str] | None:
        source_device = str(row.get("source_device_id") or row.get("operator_device_id") or "").strip()
        source_id = str(row.get("source_id") or row.get("id") or "").strip()
        if not source_device or not source_id:
            return None
        return source_device, source_id

    def _remember_row_source(self, target: dict[str, Any], source: dict[str, Any]) -> None:
        source_device = str(source.get("source_device_id") or source.get("operator_device_id") or "").strip()
        source_id = str(source.get("source_id") or source.get("id") or "").strip()
        if source_device and source_id:
            target.setdefault("source_device_id", source_device)
            target.setdefault("source_id", source_id)

    def _rows_match(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        ignored = {"source_device_id", "source_id"}
        left_clean = {key: value for key, value in left.items() if key not in ignored}
        right_clean = {key: value for key, value in right.items() if key not in ignored}
        return left_clean == right_clean

    def _sync_counters_to_rows(self) -> None:
        counters = self.data.setdefault("counters", {})
        for table in SHARED_TABLES:
            rows = self.data.get(table)
            if not isinstance(rows, list):
                continue
            max_id = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    max_id = max(max_id, int(row.get("id", 0) or 0))
                except (TypeError, ValueError):
                    continue
            if max_id:
                counters[table] = max(int(counters.get(table, 0) or 0), max_id)

    def _shared_row_key(self, table: str, row: dict[str, Any]) -> tuple[str, ...]:
        if table == "name_claims":
            return (
                table,
                self._normalize_display_name(str(row.get("name", ""))),
            )
        if table == "deleted_projects":
            key = self._deleted_project_key(row)
            if key is not None:
                return (table, key[0], key[1])
        if "id" in row:
            return (table, str(row.get("id", "")))
        return (table, json.dumps(row, ensure_ascii=False, sort_keys=True))

    def _backup_before_sync(self) -> None:
        backup_dir = self.path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"szzx-before-sync-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        try:
            with backup_path.open("w", encoding="utf-8") as file:
                json.dump(self.data, file, ensure_ascii=False, indent=2)
        except OSError:
            return

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
        row = self._with_operator({
            "id": self._next_timestamp_id("weekly_reports", created_at),
            "content": content,
            "summary": summary,
            "mood": mood,
            "created_at": created_at.isoformat(timespec="seconds"),
        })
        self.data["weekly_reports"].append(row)
        self._save()
        return self._weekly_from_row(row)

    def _is_current_user_row(self, row: dict[str, Any]) -> bool:
        operator = str(row.get("operator", "")).strip()
        device_id = str(row.get("operator_device_id", "")).strip()
        if operator and self.is_current_user_name(operator):
            return True
        if device_id and device_id == self.device_id():
            return True
        return False

    def list_weekly_reports(self, limit: int = 20, mine_only: bool = True) -> list[WeeklyReport]:
        rows = list(self.data["weekly_reports"])
        if mine_only:
            rows = [row for row in rows if self._is_current_user_row(row)]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        return [self._weekly_from_row(row) for row in rows[:limit]]

    def delete_weekly_report(self, report_id: int, mine_only: bool = True) -> bool:
        rows = self.data["weekly_reports"]
        for index, row in enumerate(rows):
            if int(row["id"]) != report_id:
                continue
            if mine_only and not self._is_current_user_row(row):
                return False
            del rows[index]
            self._save()
            return True
        return False

    def _weekly_from_row(self, row: dict[str, Any]) -> WeeklyReport:
        return WeeklyReport(
            id=int(row["id"]),
            author=str(row.get("operator", "")),
            content=str(row["content"]),
            summary=str(row["summary"]),
            mood=str(row["mood"]),
            created_at=_parse_time(str(row["created_at"])),
        )

    def list_rest_days(self, mine_only: bool = True) -> list[RestDay]:
        rows = list(self.data["rest_days"])
        if mine_only:
            rows = [row for row in rows if self._is_current_user_row(row)]
        rows.sort(key=lambda row: str(row["day"]))
        return [self._rest_day_from_row(row) for row in rows]

    def set_rest_day(self, day: date, note: str = "") -> RestDay:
        day_text = day.isoformat()
        for row in self.data["rest_days"]:
            if str(row.get("day")) == day_text and self._is_current_user_row(row):
                row["note"] = note.strip()
                self._save()
                return self._rest_day_from_row(row)

        row = self._with_operator({
            "id": self._next_id("rest_days"),
            "day": day_text,
            "note": note.strip(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })
        self.data["rest_days"].append(row)
        self._save()
        return self._rest_day_from_row(row)

    def delete_rest_day(self, day: date, mine_only: bool = True) -> bool:
        day_text = day.isoformat()
        rows = self.data["rest_days"]
        for index, row in enumerate(rows):
            if str(row.get("day")) != day_text:
                continue
            if mine_only and not self._is_current_user_row(row):
                continue
            del rows[index]
            self._save()
            return True
        return False

    def _rest_day_from_row(self, row: dict[str, Any]) -> RestDay:
        return RestDay(
            id=int(row["id"]),
            author=str(row.get("operator", "")),
            day=date.fromisoformat(str(row["day"])),
            note=str(row.get("note", "")),
            created_at=_parse_time(str(row["created_at"])),
        )

    def close(self) -> None:
        self._save(bump_sync=False)
