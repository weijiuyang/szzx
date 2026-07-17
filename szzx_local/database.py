from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import stat
import sys
import threading
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .models import DailyReport, Project, ProjectDocument, ProjectMember, ProjectTodo, ProjectWeeklyReport, Requirement, RestDay, WeeklyReport
from .pin import DEFAULT_PIN, hash_pin, verify_pin
from .version import APP_VERSION


BUNDLED_SEED_ENV = "SZZX_BUNDLED_SEED_PATH"
MAX_DOCUMENT_FILENAME_LENGTH = 120
BEFORE_SYNC_BACKUP_INTERVAL = timedelta(hours=1)
BEFORE_SYNC_BACKUP_LIMIT = 24
DOCUMENT_VAULT_MAGIC = b"SZZXDOC2"
LEGACY_DOCUMENT_VAULT_MAGIC = b"SZZXDOC1"


def _default_app_dir() -> Path:
    override = os.environ.get("SZZX_LOCAL_DATA_DIR")
    if override:
        return Path(override)

    platform_dir = _platform_app_dir()
    if getattr(sys, "frozen", False):
        return platform_dir

    if os.environ.get("SZZX_USE_PROJECT_LOCAL_DATA") == "1":
        return Path.cwd() / "local_data"

    if os.environ.get("SZZX_ALLOW_DEVELOPMENT_SEED") == "1":
        _seed_app_data_from_development(Path.cwd() / "local_data" / "szzx.json", platform_dir / "szzx.json")
    return platform_dir


def _platform_app_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "SZZXLocalDesk"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SZZXLocalDesk"
    return Path.home() / ".local" / "share" / "SZZXLocalDesk"


def _bundled_seed_path() -> Path | None:
    override = os.environ.get(BUNDLED_SEED_ENV, "").strip()
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    frozen_base = getattr(sys, "_MEIPASS", "")
    if frozen_base:
        candidates.append(Path(str(frozen_base)) / "szzx_local" / "seed" / "szzx_seed.json")
    for path in candidates:
        if path.is_file():
            return path
    return None


def _seed_app_data_from_development(dev_db: Path, app_db: Path) -> None:
    if not dev_db.is_file():
        return
    should_copy = not app_db.exists()
    if app_db.exists():
        dev_score = _database_completeness_score(dev_db)
        app_score = _database_completeness_score(app_db)
        should_copy = dev_score > app_score
    if not should_copy:
        return
    app_db.parent.mkdir(parents=True, exist_ok=True)
    if app_db.exists():
        backup = app_db.with_name(f"szzx.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
        try:
            backup.write_bytes(app_db.read_bytes())
        except OSError:
            return
    try:
        app_db.write_bytes(dev_db.read_bytes())
    except OSError:
        return


def _database_completeness_score(path: Path) -> tuple[int, int, int, int, int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (0, 0, 0, 0, 0)
    if not isinstance(data, dict):
        return (0, 0, 0, 0, 0)
    sync = data.get("sync") if isinstance(data.get("sync"), dict) else {}
    revision = int(sync.get("revision", 0) or 0) if isinstance(sync, dict) else 0
    projects = len(data.get("projects", [])) if isinstance(data.get("projects"), list) else 0
    members = len(data.get("project_members", [])) if isinstance(data.get("project_members"), list) else 0
    todos = len(data.get("project_todos", [])) if isinstance(data.get("project_todos"), list) else 0
    reports = len(data.get("daily_reports", [])) if isinstance(data.get("daily_reports"), list) else 0
    return (projects, members + todos + reports, revision, int(path.stat().st_mtime), path.stat().st_size)


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
    "requirements",
    "rest_days",
    "activity_events",
    "name_claims",
    "deleted_projects",
    "deleted_records",
    "counters",
)
ACTIVITY_EVENT_SYNC_DAYS = 0
PROJECT_NOTES_ADMIN_NAMES = {"尉久洋"}
RECORD_TOMBSTONE_TABLES = {
    "project_members",
    "daily_reports",
    "project_weekly_reports",
    "project_decks",
    "project_documents",
    "project_todos",
    "requirements",
    "rest_days",
}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _previous_week_range(today: date | None = None) -> tuple[date, date]:
    current = today or date.today()
    start = current - timedelta(days=current.weekday() + 7)
    return start, start + timedelta(days=6)


def safe_document_filename(name: str, fallback: str = "document", max_length: int = MAX_DOCUMENT_FILENAME_LENGTH) -> str:
    raw = Path(str(name or "")).name.strip() or fallback
    raw = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", raw).strip(" ._") or fallback
    suffix = Path(raw).suffix[:16]
    stem = Path(raw).stem or fallback
    max_stem = max(12, max_length - len(suffix))
    if len(stem) > max_stem:
        stem = stem[:max_stem].rstrip(" ._-") or fallback
    return f"{stem}{suffix}"


def unique_document_path(target_dir: Path, filename: str, unique_id: str = "") -> Path:
    safe_name = safe_document_filename(filename)
    target = target_dir / safe_name
    if not target.exists():
        return target
    path = Path(safe_name)
    suffix = path.suffix
    stem = path.stem or "document"
    tag = str(unique_id or datetime.now().strftime("%Y%m%d%H%M%S%f"))[-16:]
    max_stem = max(12, MAX_DOCUMENT_FILENAME_LENGTH - len(suffix) - len(tag) - 1)
    stem = stem[:max_stem].rstrip(" ._-") or "document"
    return target_dir / f"{stem}-{tag}{suffix}"


class Database:
    def __init__(self, path: Path = DB_PATH, *, enable_before_sync_backup: bool = False) -> None:
        self.path = path
        self.enable_before_sync_backup = enable_before_sync_backup
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._save_lock = threading.RLock()
        self._after_save_callbacks: list[Callable[[bool], None]] = []
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
            "requirements": [],
            "rest_days": [],
            "activity_events": [],
            "name_claims": [],
            "deleted_projects": [],
            "deleted_records": [],
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
        self._migrate_shared_ids_to_timestamps()
        self._migrate_weekly_report_owners()
        self._migrate_weekly_ids_to_timestamps()
        self._migrate_project_todo_scopes()
        self._cleanup_document_open_cache()
        self._migrate_document_vault()
        self._repair_workflow_todo_handlers()
        self._repair_project_todo_completion_duplicates()
        self._repair_daily_report_duplicates()
        self._claim_display_name(self.display_name(), save=False)
        self._apply_deleted_projects(self._active_deleted_project_keys(set()))
        self._apply_deleted_records(self._active_deleted_record_keys_by_table({}))
        self._ensure_sync_state()
        self._save(bump_sync=False)
        if os.environ.get("SZZX_ENABLE_BUNDLED_SEED") == "1":
            self._apply_bundled_seed_snapshot()

    def _apply_bundled_seed_snapshot(self) -> None:
        snapshot = self._load_bundled_seed_snapshot()
        if snapshot is None:
            return
        seed_id = self._seed_snapshot_id(snapshot)
        if seed_id and self.get_setting("bundled_seed_applied") == seed_id:
            return
        changed = self.merge_missing_shared_snapshot(snapshot, honor_deletions=True)
        if seed_id:
            self.set_setting("bundled_seed_applied", seed_id, save=False)
            self._save(bump_sync=False)
        elif changed:
            self._save(bump_sync=False)

    def _load_bundled_seed_snapshot(self) -> dict[str, Any] | None:
        path = _bundled_seed_path()
        if path is None:
            return None
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(loaded, dict):
            return None
        tables = loaded.get("tables")
        if not isinstance(tables, dict):
            return None
        normalized_tables: dict[str, Any] = {}
        has_shared_rows = False
        for table in SHARED_TABLES:
            source_value = tables.get(table)
            empty_value = self._empty_data()[table]
            if isinstance(empty_value, dict):
                normalized_tables[table] = dict(source_value) if isinstance(source_value, dict) else {}
            else:
                normalized_tables[table] = list(source_value) if isinstance(source_value, list) else []
                if table in {"projects", "project_members", "project_todos"} and normalized_tables[table]:
                    has_shared_rows = True
        if not has_shared_rows:
            return None
        sync = loaded.get("sync") if isinstance(loaded.get("sync"), dict) else {}
        owner = loaded.get("owner") if isinstance(loaded.get("owner"), dict) else {}
        return {
            "sync": sync,
            "owner": owner,
            "tables": normalized_tables,
        }

    def _seed_snapshot_id(self, snapshot: dict[str, Any]) -> str:
        tables = snapshot.get("tables") if isinstance(snapshot.get("tables"), dict) else {}
        counts: dict[str, int] = {}
        project_keys: list[str] = []
        for table in SHARED_TABLES:
            value = tables.get(table) if isinstance(tables, dict) else None
            if isinstance(value, list):
                counts[table] = len(value)
                if table == "projects":
                    project_keys = sorted(
                        self._project_fingerprint_key(row)
                        for row in value
                        if isinstance(row, dict) and self._project_fingerprint_key(row)
                    )
            elif isinstance(value, dict):
                counts[table] = len(value)
        payload = {
            "app_version": APP_VERSION,
            "sync": snapshot.get("sync") if isinstance(snapshot.get("sync"), dict) else {},
            "counts": counts,
            "projects": project_keys,
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _save(self, bump_sync: bool = True) -> None:
        with self._save_lock:
            if bump_sync:
                self._bump_sync_revision()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.path.with_name(f"{self.path.stem}.{uuid.uuid4().hex}.tmp")
            try:
                with tmp_path.open("w", encoding="utf-8") as file:
                    json.dump(self.data, file, ensure_ascii=False, indent=2)
                tmp_path.replace(self.path)
            finally:
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except OSError:
                    pass
            callbacks = list(self._after_save_callbacks)
        for callback in callbacks:
            try:
                callback(bump_sync)
            except Exception:
                continue

    def add_after_save_callback(self, callback: Callable[[bool], None]) -> None:
        if callback not in self._after_save_callbacks:
            self._after_save_callbacks.append(callback)

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

    def _next_id(self, table: str, created_at: datetime | None = None) -> int:
        return self._next_timestamp_id(table, created_at or datetime.now())

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

    def _is_timestamp_id(self, value: Any) -> bool:
        return self._is_timestamp_project_id(value)

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
        # The settings themselves stay local, but this save also publishes the
        # current user's shared name claim (including their DingTalk ID).
        self._save(bump_sync=True)

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

    def dingtalk_id(self) -> str:
        return self.get_setting("dingtalk_id") or ""

    def set_dingtalk_id(self, dingtalk_id: str, save: bool = True) -> None:
        self.set_setting("dingtalk_id", dingtalk_id.strip(), save=False)
        self._claim_display_name(self.display_name(), save=False)
        if save:
            self._save()

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
                "dingtalk_id": self.dingtalk_id(),
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
            try:
                created_at = _parse_time(str(deck["created_at"]))
            except ValueError:
                created_at = datetime.now()
            documents.append(
                {
                    "id": self._next_id("project_documents", created_at),
                    "legacy_deck_id": deck_id,
                    "project_id": int(deck["project_id"]),
                    "title": str(deck["title"]),
                    "doc_type": "项目汇报PPT",
                    "visibility": "team",
                    "uploader": self.display_name(),
                    "file_path": str(deck["file_path"]),
                    "created_at": created_at.isoformat(timespec="seconds"),
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

    def _migrate_shared_ids_to_timestamps(self) -> None:
        id_maps: dict[str, dict[int, int]] = {}
        todo_id_map_by_project: dict[tuple[int, int], int] = {}
        for table in (
            "project_members",
            "daily_reports",
            "project_todos",
            "project_decks",
            "project_documents",
            "rest_days",
            "activity_events",
        ):
            rows = self.data.get(table, [])
            if not isinstance(rows, list):
                continue
            id_map: dict[int, int] = {}
            used_ids: set[int] = set()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    old_id = int(row.get("id", 0) or 0)
                except (TypeError, ValueError):
                    old_id = 0
                if old_id and self._is_timestamp_id(old_id) and old_id not in used_ids:
                    used_ids.add(old_id)
                    continue
                try:
                    created_at = _parse_time(str(row.get("created_at", "")))
                except ValueError:
                    created_at = datetime.now()
                new_id = int(created_at.strftime("%Y%m%d%H%M%S")) * 1000 + created_at.microsecond // 1000
                while new_id in used_ids:
                    new_id += 1
                if old_id:
                    row.setdefault("legacy_id", old_id)
                    id_map[old_id] = new_id
                    if table == "project_todos":
                        try:
                            project_id = int(row.get("project_id", 0) or 0)
                        except (TypeError, ValueError):
                            project_id = 0
                        todo_id_map_by_project[(project_id, old_id)] = new_id
                row["id"] = new_id
                used_ids.add(new_id)
            if id_map:
                id_maps[table] = id_map

        todo_id_map = id_maps.get("project_todos", {})
        if todo_id_map:
            for row in self.data.get("daily_reports", []):
                if not isinstance(row, dict):
                    continue
                try:
                    old_todo_id = int(row.get("todo_id", 0) or 0)
                except (TypeError, ValueError):
                    continue
                try:
                    project_id = int(row.get("project_id", 0) or 0)
                except (TypeError, ValueError):
                    project_id = 0
                if (project_id, old_todo_id) in todo_id_map_by_project:
                    row["todo_id"] = todo_id_map_by_project[(project_id, old_todo_id)]
                elif old_todo_id in todo_id_map:
                    row["todo_id"] = todo_id_map[old_todo_id]
        self._sync_counters_to_rows()

    def _migrate_project_todo_scopes(self) -> None:
        rows = self.data.get("project_todos")
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("scope", "")).strip() not in {"personal", "project", "assigned"}:
                row["scope"] = "personal"


    def add_project(
        self,
        name: str,
        owner: str,
        description: str,
        status: str = "推进中",
        project_link: str = "",
        backup_project_link: str = "",
        development_group_link: str = "",
        coordination_group_link: str = "",
        project_notes: str = "",
    ) -> Project:
        created_at = datetime.now()
        row = self._with_operator({
            "id": self._next_project_id(created_at),
            "name": name.strip(),
            "owner": owner.strip(),
            "description": description.strip(),
            "status": status.strip(),
            "project_link": project_link.strip(),
            "backup_project_link": backup_project_link.strip(),
            "development_group_link": development_group_link.strip(),
            "coordination_group_link": coordination_group_link.strip(),
            "project_notes": project_notes.strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
            "updated_at": created_at.isoformat(timespec="seconds"),
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

    def update_project_status(self, project_id: int, status: str) -> Project | None:
        normalized_status = status.strip()
        if normalized_status not in {"推进中", "已暂停", "已完成", "已删除"}:
            return None
        for row in self.data["projects"]:
            if int(row["id"]) != project_id:
                continue
            row["status"] = normalized_status
            row["updated_at"] = datetime.now().isoformat(timespec="microseconds")
            self._save()
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

    def _remember_deleted_project(
        self,
        project_row: dict[str, Any],
        deleted_by: str | None = None,
        deleted_by_device_id: str | None = None,
    ) -> None:
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
            "deleted_by": deleted_by or self.display_name(),
            "deleted_by_device_id": deleted_by_device_id or self.device_id(),
            "deleted_at": datetime.now().isoformat(timespec="microseconds"),
        }
        for index, row in enumerate(tombstones):
            if not isinstance(row, dict):
                continue
            if self._deleted_project_key(row) == (source_device, source_id):
                tombstones[index] = tombstone
                return
        tombstones.append(tombstone)

    def _remember_deleted_record(self, table: str, row: dict[str, Any]) -> None:
        if table not in RECORD_TOMBSTONE_TABLES:
            return
        source = self._row_source_key(row)
        if source is None:
            source = (self.device_id(), str(row.get("id", "")))
        source_device, source_id = source
        tombstones = self.data.setdefault("deleted_records", [])
        tombstone = {
            "table": table,
            "source_device_id": source_device,
            "source_id": source_id,
            "record_id": str(row.get("id", "")),
            "project_id": str(row.get("project_id", "")),
            "title": str(row.get("title") or row.get("content") or row.get("name") or ""),
            "deleted_by": self.display_name(),
            "deleted_by_device_id": self.device_id(),
            "deleted_at": datetime.now().isoformat(timespec="microseconds"),
        }
        if table == "project_todos" and str(row.get("scope", "")) == "assigned":
            tombstone.update({
                "scope": "assigned",
                "assignee": str(row.get("assignee", "")),
                "assigned_by": str(row.get("assigned_by", "")),
                "assigned_by_pet": str(row.get("assigned_by_pet", "penguin")) or "penguin",
            })
        key = self._deleted_record_key(tombstone)
        if key is None:
            return
        for index, existing in enumerate(tombstones):
            if not isinstance(existing, dict):
                continue
            if self._deleted_record_key(existing) == key:
                tombstones[index] = tombstone
                return
        tombstones.append(tombstone)

    def _is_current_user_deleted_rest_record(self, row: dict[str, Any]) -> bool:
        if str(row.get("table", "")) != "rest_days":
            return False
        deleted_by = str(row.get("deleted_by", "")).strip()
        deleted_by_device_id = str(row.get("deleted_by_device_id", "")).strip()
        source_device_id = str(row.get("source_device_id", "")).strip()
        if deleted_by and self.is_current_user_name(deleted_by):
            return True
        if deleted_by_device_id and deleted_by_device_id == self.device_id():
            return True
        if source_device_id and source_device_id == self.device_id():
            return True
        return False

    def _remote_rest_owner_matches(self, row: dict[str, Any], sync: dict[str, Any]) -> bool:
        actor = self._normalize_display_name(str(sync.get("actor", "")).strip())
        origin = str(sync.get("origin", "")).strip()
        row_devices = (
            str(row.get("operator_device_id", "")).strip(),
            str(row.get("source_device_id", "")).strip(),
            str(row.get("deleted_by_device_id", "")).strip(),
        )
        if origin and origin in row_devices:
            return True
        row_names = (
            self._normalize_display_name(str(row.get("operator", "")).strip()),
            self._normalize_display_name(str(row.get("deleted_by", "")).strip()),
        )
        if actor and actor in row_names:
            return True
        return not actor and not origin

    def _personalized_snapshot_tables(self, tables: dict[str, Any]) -> dict[str, Any]:
        personalized = dict(tables)
        rest_days = personalized.get("rest_days")
        if isinstance(rest_days, list):
            personalized["rest_days"] = [
                dict(row)
                for row in rest_days
                if isinstance(row, dict) and self._is_current_user_row(row)
            ]
        deleted_records = personalized.get("deleted_records")
        if isinstance(deleted_records, list):
            personalized["deleted_records"] = [
                dict(row)
                for row in deleted_records
                if isinstance(row, dict)
                and (
                    str(row.get("table", "")) != "rest_days"
                    or self._is_current_user_deleted_rest_record(row)
                )
            ]
        return personalized

    def _personalized_remote_tables(self, tables: dict[str, Any], sync: dict[str, Any]) -> dict[str, Any]:
        if str(sync.get("scope", "")).strip() == "all":
            return tables
        personalized = dict(tables)
        rest_days = personalized.get("rest_days")
        if isinstance(rest_days, list):
            personalized["rest_days"] = [
                dict(row)
                for row in rest_days
                if isinstance(row, dict) and self._remote_rest_owner_matches(row, sync)
            ]
        deleted_records = personalized.get("deleted_records")
        if isinstance(deleted_records, list):
            personalized["deleted_records"] = [
                dict(row)
                for row in deleted_records
                if isinstance(row, dict)
                and (
                    str(row.get("table", "")) != "rest_days"
                    or self._remote_rest_owner_matches(row, sync)
                )
            ]
        return personalized

    def _project_notes_visible_to_actor(self, project_row: dict[str, Any], actor: str) -> bool:
        actor_key = self._normalize_display_name(actor)
        if not actor_key:
            return False
        if actor_key in {self._normalize_display_name(name) for name in PROJECT_NOTES_ADMIN_NAMES}:
            return True
        if self._normalize_display_name(str(project_row.get("owner", ""))) == actor_key:
            return True
        try:
            project_id = int(project_row.get("id", 0) or 0)
        except (TypeError, ValueError):
            return False
        for member in self.data.get("project_members", []):
            if not isinstance(member, dict):
                continue
            try:
                member_project_id = int(member.get("project_id", 0) or 0)
            except (TypeError, ValueError):
                continue
            if member_project_id != project_id:
                continue
            if self._normalize_display_name(str(member.get("name", ""))) == actor_key:
                return True
        return False

    def _redact_project_notes_for_actor(self, tables: dict[str, Any], actor: str) -> dict[str, Any]:
        redacted = dict(tables)
        projects = redacted.get("projects")
        if not isinstance(projects, list):
            return redacted
        next_projects: list[Any] = []
        for row in projects:
            if not isinstance(row, dict):
                next_projects.append(row)
                continue
            next_row = dict(row)
            if "project_notes" in next_row and not self._project_notes_visible_to_actor(next_row, actor):
                next_row.pop("project_notes", None)
            next_projects.append(next_row)
        redacted["projects"] = next_projects
        return redacted

    def update_project_description(self, project_id: int, description: str) -> Project | None:
        for row in self.data["projects"]:
            if int(row["id"]) != project_id:
                continue
            row["description"] = description.strip()
            row["updated_at"] = datetime.now().isoformat(timespec="microseconds")
            self._save()
            return self._project_from_row(row)
        return None

    def update_project_details(
        self,
        project_id: int,
        name: str,
        description: str,
        project_link: str = "",
        backup_project_link: str = "",
        development_group_link: str = "",
        coordination_group_link: str = "",
        project_notes: str = "",
    ) -> Project | None:
        for row in self.data["projects"]:
            if int(row["id"]) != project_id:
                continue
            row["name"] = name.strip()
            row["description"] = description.strip()
            row["project_link"] = project_link.strip()
            row["backup_project_link"] = backup_project_link.strip()
            row["development_group_link"] = development_group_link.strip()
            row["coordination_group_link"] = coordination_group_link.strip()
            row["project_notes"] = project_notes.strip()
            row["updated_at"] = datetime.now().isoformat(timespec="microseconds")
            self._save()
            return self._project_from_row(row)
        return None

    def update_project_owner(self, project_id: int, owner: str) -> Project | None:
        for row in self.data["projects"]:
            if int(row["id"]) != project_id:
                continue
            row["owner"] = owner.strip()
            row["updated_at"] = datetime.now().isoformat(timespec="microseconds")
            self._save()
            return self._project_from_row(row)
        return None

    def _project_from_row(self, row: dict[str, Any]) -> Project:
        return Project(
            id=int(row["id"]),
            name=str(row["name"]),
            owner=str(row["owner"]),
            description=str(row.get("description", "")),
            status=str(row.get("status", "推进中")),
            created_at=_parse_time(str(row["created_at"])),
            project_link=str(row.get("project_link", "")),
            backup_project_link=str(row.get("backup_project_link", "")),
            development_group_link=str(row.get("development_group_link", "")),
            coordination_group_link=str(row.get("coordination_group_link", "")),
            project_notes=str(row.get("project_notes", "")),
        )

    def add_project_member(self, project_id: int, name: str, role: str, dingtalk_id: str = "") -> ProjectMember:
        existing = self._find_project_member_row(project_id, name, role)
        if existing is not None:
            if dingtalk_id.strip() and not str(existing.get("dingtalk_id", "")).strip():
                existing["dingtalk_id"] = dingtalk_id.strip()
                self._save()
            return self._member_from_row(existing)
        created_at = datetime.now()
        row = self._with_operator({
            "id": self._next_id("project_members", created_at),
            "project_id": project_id,
            "name": name.strip(),
            "role": role.strip(),
            "dingtalk_id": dingtalk_id.strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
        })
        self.data["project_members"].append(row)
        self._save()
        return self._member_from_row(row)

    def list_project_members(self, project_id: int) -> list[ProjectMember]:
        rows = [row for row in self.data["project_members"] if int(row["project_id"]) == project_id]
        rows.sort(key=lambda row: int(row["id"]))
        unique_rows: list[dict[str, Any]] = []
        seen: set[tuple[int, str, str]] = set()
        for row in rows:
            key = self._project_member_natural_key(row)
            if key in seen:
                continue
            seen.add(key)
            unique_rows.append(row)
        return [self._member_from_row(row) for row in unique_rows]

    def _find_project_member_row(self, project_id: int, name: str, role: str) -> dict[str, Any] | None:
        target = (
            int(project_id),
            self._normalize_display_name(name),
            self._normalize_display_name(role),
        )
        for row in self.data.get("project_members", []):
            if not isinstance(row, dict):
                continue
            if self._project_member_natural_key(row) == target:
                return row
        return None

    def _project_member_natural_key(self, row: dict[str, Any]) -> tuple[int, str, str]:
        try:
            project_id = int(row.get("project_id", 0) or 0)
        except (TypeError, ValueError):
            project_id = 0
        return (
            project_id,
            self._normalize_display_name(str(row.get("name", ""))),
            self._normalize_display_name(str(row.get("role", ""))),
        )

    def delete_project_member(self, member_id: int) -> bool:
        rows = self.data["project_members"]
        for index, row in enumerate(rows):
            if int(row["id"]) != member_id:
                continue
            self._remember_deleted_record("project_members", row)
            del rows[index]
            self._save()
            return True
        return False

    def update_project_member_dingtalk_id(self, member_id: int, dingtalk_id: str) -> bool:
        for row in self.data["project_members"]:
            if int(row["id"]) != member_id:
                continue
            row["dingtalk_id"] = dingtalk_id.strip()
            self._save()
            return True
        return False

    def dingtalk_id_for_name(self, name: str) -> str:
        target = self._normalize_display_name(name)
        if not target:
            return ""
        for row in reversed(self.data.get("name_claims", [])):
            if not isinstance(row, dict):
                continue
            if self._normalize_display_name(str(row.get("name", ""))) != target:
                continue
            dingtalk_id = str(row.get("dingtalk_id", "")).strip()
            if dingtalk_id:
                return dingtalk_id
        for row in reversed(self.data.get("project_members", [])):
            if not isinstance(row, dict):
                continue
            if self._normalize_display_name(str(row.get("name", ""))) != target:
                continue
            dingtalk_id = str(row.get("dingtalk_id", "")).strip()
            if dingtalk_id:
                return dingtalk_id
        return ""

    def name_for_dingtalk_id(self, dingtalk_id: str) -> str:
        target = dingtalk_id.strip().casefold()
        if not target:
            return ""
        for table in ("name_claims", "project_members"):
            for row in reversed(self.data.get(table, [])):
                if not isinstance(row, dict):
                    continue
                if str(row.get("dingtalk_id", "")).strip().casefold() != target:
                    continue
                name = str(row.get("name", "")).strip()
                if name:
                    return name
        return ""

    def requirement_recipient_alias(self, dingtalk_id: str) -> str:
        target = dingtalk_id.strip()
        if not target:
            return ""
        try:
            aliases = json.loads(self.get_setting("requirement_recipient_aliases") or "{}")
        except json.JSONDecodeError:
            return ""
        value = aliases.get(target) if isinstance(aliases, dict) else None
        if isinstance(value, str):
            return value.strip()
        # 兼容此前保存的 {name, dingtalk_id} 格式，读取时只使用名字。
        return str(value.get("name", "")).strip() if isinstance(value, dict) else ""

    def set_requirement_recipient_alias(self, source_id: str, name: str) -> None:
        try:
            aliases = json.loads(self.get_setting("requirement_recipient_aliases") or "{}")
        except json.JSONDecodeError:
            aliases = {}
        if not isinstance(aliases, dict):
            aliases = {}
        aliases[source_id.strip()] = name.strip()
        self.set_setting("requirement_recipient_aliases", json.dumps(aliases, ensure_ascii=False))

    def update_requirement_recipient(self, requirement_id: int, name: str, dingtalk_id: str) -> bool:
        for row in self.data.get("requirements", []):
            if not isinstance(row, dict) or int(row.get("id", 0) or 0) != requirement_id:
                continue
            row["recipient_name"] = name.strip()
            row["recipient_dingtalk_id"] = dingtalk_id.strip()
            row["updated_at"] = datetime.now().isoformat(timespec="microseconds")
            self._save()
            return True
        return False

    def _member_from_row(self, row: dict[str, Any]) -> ProjectMember:
        return ProjectMember(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            name=str(row["name"]),
            role=str(row["role"]),
            dingtalk_id=str(row.get("dingtalk_id", "")),
            created_at=_parse_time(str(row["created_at"])),
        )

    def add_daily_report(
        self,
        project_id: int,
        member_name: str,
        role: str,
        content: str,
        todo_id: int | None = None,
    ) -> DailyReport:
        created_at = datetime.now()
        row = self._with_operator({
            "id": self._next_id("daily_reports", created_at),
            "project_id": project_id,
            "member_name": member_name.strip(),
            "role": role.strip(),
            "content": content.strip(),
            "todo_id": todo_id or "",
            "created_at": created_at.isoformat(timespec="seconds"),
        })
        self.data["daily_reports"].append(row)
        self._save()
        return self._daily_from_row(row)

    def list_daily_reports(self, project_id: int, limit: int = 50) -> list[DailyReport]:
        rows = [row for row in self.data["daily_reports"] if int(row["project_id"]) == project_id]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        rows = self._unique_daily_report_rows(rows)
        return [self._daily_from_row(row) for row in rows[:limit]]

    def list_member_daily_reports(self, project_id: int, member_name: str) -> list[DailyReport]:
        target = self._normalize_display_name(member_name)
        rows = [
            row
            for row in self.data["daily_reports"]
            if int(row["project_id"]) == project_id
            and self._normalize_display_name(str(row.get("member_name", ""))) == target
        ]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        rows = self._unique_daily_report_rows(rows)
        return [self._daily_from_row(row) for row in rows]

    def list_daily_reports_for_todo(self, todo_id: int, limit: int = 10) -> list[DailyReport]:
        rows = [
            row
            for row in self.data["daily_reports"]
            if str(row.get("todo_id", "")).strip() == str(todo_id)
        ]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        rows = self._unique_daily_report_rows(rows)
        return [self._daily_from_row(row) for row in rows[:limit]]

    def _unique_daily_report_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = self._daily_report_duplicate_key(row)
            if key is None:
                unique.append(row)
                continue
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

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

    def starry_night_badge(self, days: int = 7) -> dict[str, Any] | None:
        start_day, end_day = _previous_week_range()
        latest_by_day: dict[date, tuple[datetime, str, str]] = {}

        def remember(day: date, created_at: datetime, name: str, kind: str) -> None:
            if day < start_day or day > end_day or not name.strip():
                return
            current = latest_by_day.get(day)
            if current is None or created_at > current[0]:
                latest_by_day[day] = (created_at, name.strip(), kind)

        for row in self.data.get("daily_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            remember(created_at.date(), created_at, str(row.get("member_name", "")), "日报")

        for row in self.data.get("project_weekly_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            remember(created_at.date(), created_at, str(row.get("author", "")), "项目周报")

        for row in self.data.get("weekly_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            remember(created_at.date(), created_at, str(row.get("operator", "")), "个人周报")

        if not latest_by_day:
            return None

        counts: dict[str, int] = {}
        last_win: dict[str, tuple[date, datetime, str]] = {}
        for day, (created_at, name, kind) in latest_by_day.items():
            counts[name] = counts.get(name, 0) + 1
            previous = last_win.get(name)
            if previous is None or created_at > previous[1]:
                last_win[name] = (day, created_at, kind)

        winner = max(counts, key=lambda name: (counts[name], last_win[name][1], name))
        win_day, win_time, win_kind = last_win[winner]
        return {
            "name": winner,
            "count": counts[winner],
            "days": len(latest_by_day),
            "last_day": win_day,
            "last_time": win_time,
            "last_kind": win_kind,
        }

    def record_activity(self, kind: str, actor: str | None = None) -> None:
        created_at = datetime.now()
        row = self._with_operator({
            "id": self._next_timestamp_id("activity_events", created_at),
            "kind": kind.strip() or "操作",
            "actor": (actor or self.display_name()).strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
        })
        self.data["activity_events"].append(row)
        self._save()

    def dawn_badge(self, days: int = 7) -> dict[str, Any] | None:
        start_day, end_day = _previous_week_range()
        morning_start = time(7, 0)
        morning_end = time(8, 30)
        earliest_by_day: dict[date, tuple[datetime, str, str]] = {}

        def remember(created_at: datetime, name: str, kind: str) -> None:
            day = created_at.date()
            if day < start_day or day > end_day or not name.strip():
                return
            if not (morning_start <= created_at.time() <= morning_end):
                return
            current = earliest_by_day.get(day)
            if current is None or created_at < current[0]:
                earliest_by_day[day] = (created_at, name.strip(), kind)

        for row in self.data.get("activity_events", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            remember(created_at, str(row.get("actor") or row.get("operator", "")), str(row.get("kind", "操作")))

        for row in self.data.get("daily_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            remember(created_at, str(row.get("member_name", "")), "日报")

        for row in self.data.get("project_weekly_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            remember(created_at, str(row.get("author", "")), "项目周报")

        for row in self.data.get("weekly_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            remember(created_at, str(row.get("operator", "")), "个人周报")

        for row in self.data.get("project_todos", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            remember(created_at, str(row.get("creator", "")), "代办")
            completed_at = str(row.get("completed_at", "")).strip()
            if completed_at:
                try:
                    completed_time = _parse_time(completed_at)
                except ValueError:
                    continue
                remember(completed_time, str(row.get("completed_by", "")), "完成代办")

        if not earliest_by_day:
            return None

        counts: dict[str, int] = {}
        last_win: dict[str, tuple[date, datetime, str]] = {}
        for day, (created_at, name, kind) in earliest_by_day.items():
            counts[name] = counts.get(name, 0) + 1
            previous = last_win.get(name)
            if previous is None or created_at > previous[1]:
                last_win[name] = (day, created_at, kind)

        winner = max(counts, key=lambda name: (counts[name], last_win[name][1], name))
        win_day, win_time, win_kind = last_win[winner]
        return {
            "name": winner,
            "count": counts[winner],
            "days": len(earliest_by_day),
            "last_day": win_day,
            "last_time": win_time,
            "last_kind": win_kind,
        }

    def log_badge(self, days: int = 7) -> dict[str, Any] | None:
        start_day, end_day = _previous_week_range()
        expected_days = (end_day - start_day).days + 1
        stats: dict[str, dict[str, Any]] = {}

        def word_count(content: str) -> int:
            return len("".join(content.split()))

        def remember(created_at: datetime, name: str, content: str, kind: str) -> None:
            day = created_at.date()
            name = name.strip()
            if day < start_day or day > end_day or not name:
                return
            stat = stats.setdefault(
                name,
                {
                    "days": set(),
                    "count": 0,
                    "words": 0,
                    "last_time": created_at,
                    "last_kind": kind,
                },
            )
            stat["days"].add(day)
            stat["count"] += 1
            stat["words"] += word_count(content)
            if created_at > stat["last_time"]:
                stat["last_time"] = created_at
                stat["last_kind"] = kind

        for row in self.data.get("daily_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            remember(created_at, str(row.get("member_name", "")), str(row.get("content", "")), "日报")

        for row in self.data.get("project_weekly_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            remember(created_at, str(row.get("author", "")), str(row.get("content", "")), "项目周报")

        for row in self.data.get("weekly_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            remember(created_at, str(row.get("operator", "")), str(row.get("content", "")), "个人周报")

        if not stats:
            return None

        winner = max(
            stats,
            key=lambda name: (
                len(stats[name]["days"]) == expected_days,
                stats[name]["count"],
                stats[name]["words"],
                stats[name]["last_time"],
                name,
            ),
        )
        winner_stat = stats[winner]
        return {
            "name": winner,
            "days": len(winner_stat["days"]),
            "count": int(winner_stat["count"]),
            "words": int(winner_stat["words"]),
            "last_time": winner_stat["last_time"],
            "last_kind": str(winner_stat["last_kind"]),
        }

    def todo_badge(self, days: int = 7) -> dict[str, Any] | None:
        start_day, end_day = _previous_week_range()
        stats: dict[str, dict[str, Any]] = {}

        for row in self.data.get("project_todos", []):
            if not isinstance(row, dict):
                continue
            name = str(row.get("completed_by", "")).strip()
            completed_at = str(row.get("completed_at", "")).strip()
            if not name or not completed_at:
                continue
            try:
                completed_time = _parse_time(completed_at)
            except ValueError:
                continue
            day = completed_time.date()
            if day < start_day or day > end_day:
                continue
            stat = stats.setdefault(name, {"count": 0, "last_time": completed_time})
            stat["count"] += 1
            if completed_time > stat["last_time"]:
                stat["last_time"] = completed_time

        if not stats:
            return None

        winner = max(stats, key=lambda name: (stats[name]["count"], stats[name]["last_time"], name))
        winner_stat = stats[winner]
        return {
            "name": winner,
            "count": int(winner_stat["count"]),
            "last_time": winner_stat["last_time"],
        }

    def badge_detail_report(self, badge_key: str) -> dict[str, Any]:
        start_day, end_day = _previous_week_range()
        if badge_key == "starry":
            return self._starry_badge_detail(start_day, end_day)
        if badge_key == "dawn":
            return self._dawn_badge_detail(start_day, end_day)
        if badge_key == "log":
            return self._log_badge_detail(start_day, end_day)
        if badge_key == "todo":
            return self._todo_badge_detail(start_day, end_day)
        return {"ranking": [], "details": [], "start_day": start_day, "end_day": end_day}

    def _badge_log_entries(self, start_day: date, end_day: date) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []

        def add(row: dict[str, Any], created_at: datetime, name: str, kind: str, content: str) -> None:
            if start_day <= created_at.date() <= end_day and name.strip():
                entries.append(
                    {
                        "day": created_at.date(),
                        "time": created_at,
                        "name": name.strip(),
                        "kind": kind,
                        "content": content.strip(),
                        "words": len("".join(content.split())),
                        "source_id": str(row.get("id", "")),
                    }
                )

        for row in self.data.get("daily_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            add(row, created_at, str(row.get("member_name", "")), "日报", str(row.get("content", "")))

        for row in self.data.get("project_weekly_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            add(row, created_at, str(row.get("author", "")), "项目周报", str(row.get("content", "")))

        for row in self.data.get("weekly_reports", []):
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            add(row, created_at, str(row.get("operator", "")), "个人周报", str(row.get("content", "")))

        entries.sort(key=lambda item: item["time"])
        return entries

    def _starry_badge_detail(self, start_day: date, end_day: date) -> dict[str, Any]:
        entries = self._badge_log_entries(start_day, end_day)
        latest_by_day: dict[date, dict[str, Any]] = {}
        for entry in entries:
            current = latest_by_day.get(entry["day"])
            if current is None or entry["time"] > current["time"]:
                latest_by_day[entry["day"]] = entry
        stats: dict[str, dict[str, Any]] = {}
        for entry in latest_by_day.values():
            stat = stats.setdefault(entry["name"], {"count": 0, "last_time": entry["time"]})
            stat["count"] += 1
            if entry["time"] > stat["last_time"]:
                stat["last_time"] = entry["time"]
        ranking = [
            {
                "姓名": name,
                "命中天数": stat["count"],
                "最近命中": stat["last_time"].strftime("%Y-%m-%d %H:%M"),
            }
            for name, stat in sorted(stats.items(), key=lambda item: (item[1]["count"], item[1]["last_time"], item[0]), reverse=True)
        ]
        details = [
            {
                "日期": entry["day"].isoformat(),
                "时间": entry["time"].strftime("%H:%M"),
                "姓名": entry["name"],
                "类型": entry["kind"],
                "当日最晚": "是" if latest_by_day.get(entry["day"]) is entry else "",
                "内容": entry["content"],
            }
            for entry in entries
        ]
        return {"ranking": ranking, "details": details, "start_day": start_day, "end_day": end_day}

    def _dawn_badge_detail(self, start_day: date, end_day: date) -> dict[str, Any]:
        morning_start = time(7, 0)
        morning_end = time(8, 30)
        entries: list[dict[str, Any]] = []

        def add(created_at: datetime, name: str, kind: str, content: str = "") -> None:
            if (
                start_day <= created_at.date() <= end_day
                and morning_start <= created_at.time() <= morning_end
                and name.strip()
            ):
                entries.append(
                    {
                        "day": created_at.date(),
                        "time": created_at,
                        "name": name.strip(),
                        "kind": kind,
                        "content": content.strip(),
                    }
                )

        for row in self.data.get("activity_events", []):
            if not isinstance(row, dict):
                continue
            try:
                add(_parse_time(str(row.get("created_at", ""))), str(row.get("actor") or row.get("operator", "")), str(row.get("kind", "操作")))
            except ValueError:
                continue
        for entry in self._badge_log_entries(start_day, end_day):
            add(entry["time"], entry["name"], entry["kind"], entry["content"])
        for row in self.data.get("project_todos", []):
            if not isinstance(row, dict):
                continue
            try:
                add(_parse_time(str(row.get("created_at", ""))), str(row.get("creator", "")), "创建代办", str(row.get("title", "")))
            except ValueError:
                pass
            completed_at = str(row.get("completed_at", "")).strip()
            if completed_at:
                try:
                    add(_parse_time(completed_at), str(row.get("completed_by", "")), "完成代办", str(row.get("title", "")))
                except ValueError:
                    pass

        entries.sort(key=lambda item: item["time"])
        earliest_by_day: dict[date, dict[str, Any]] = {}
        for entry in entries:
            earliest_by_day.setdefault(entry["day"], entry)
        stats: dict[str, dict[str, Any]] = {}
        for entry in earliest_by_day.values():
            stat = stats.setdefault(entry["name"], {"count": 0, "last_time": entry["time"]})
            stat["count"] += 1
            if entry["time"] > stat["last_time"]:
                stat["last_time"] = entry["time"]
        ranking = [
            {
                "姓名": name,
                "命中天数": stat["count"],
                "最近命中": stat["last_time"].strftime("%Y-%m-%d %H:%M"),
            }
            for name, stat in sorted(stats.items(), key=lambda item: (item[1]["count"], item[1]["last_time"], item[0]), reverse=True)
        ]
        details = [
            {
                "日期": entry["day"].isoformat(),
                "时间": entry["time"].strftime("%H:%M"),
                "姓名": entry["name"],
                "类型": entry["kind"],
                "当日最早": "是" if earliest_by_day.get(entry["day"]) is entry else "",
                "内容": entry["content"],
            }
            for entry in entries
        ]
        return {"ranking": ranking, "details": details, "start_day": start_day, "end_day": end_day}

    def _log_badge_detail(self, start_day: date, end_day: date) -> dict[str, Any]:
        entries = self._badge_log_entries(start_day, end_day)
        stats: dict[str, dict[str, Any]] = {}
        for entry in entries:
            stat = stats.setdefault(entry["name"], {"days": set(), "count": 0, "words": 0, "last_time": entry["time"]})
            stat["days"].add(entry["day"])
            stat["count"] += 1
            stat["words"] += entry["words"]
            if entry["time"] > stat["last_time"]:
                stat["last_time"] = entry["time"]
        ranking = [
            {
                "姓名": name,
                "记录天数": len(stat["days"]),
                "日志条数": stat["count"],
                "总字数": stat["words"],
                "最近记录": stat["last_time"].strftime("%Y-%m-%d %H:%M"),
            }
            for name, stat in sorted(stats.items(), key=lambda item: (len(item[1]["days"]) == 7, item[1]["count"], item[1]["words"], item[1]["last_time"], item[0]), reverse=True)
        ]
        details = [
            {
                "日期": entry["day"].isoformat(),
                "时间": entry["time"].strftime("%H:%M"),
                "姓名": entry["name"],
                "类型": entry["kind"],
                "字数": entry["words"],
                "内容": entry["content"],
            }
            for entry in entries
        ]
        return {"ranking": ranking, "details": details, "start_day": start_day, "end_day": end_day}

    def _todo_badge_detail(self, start_day: date, end_day: date) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        for row in self.data.get("project_todos", []):
            if not isinstance(row, dict):
                continue
            completed_at = str(row.get("completed_at", "")).strip()
            name = str(row.get("completed_by", "")).strip()
            if not completed_at or not name:
                continue
            try:
                completed_time = _parse_time(completed_at)
            except ValueError:
                continue
            if start_day <= completed_time.date() <= end_day:
                entries.append(
                    {
                        "day": completed_time.date(),
                        "time": completed_time,
                        "name": name,
                        "title": str(row.get("title", "")),
                        "scope": str(row.get("scope", "")),
                    }
                )
        entries.sort(key=lambda item: item["time"])
        stats: dict[str, dict[str, Any]] = {}
        for entry in entries:
            stat = stats.setdefault(entry["name"], {"count": 0, "last_time": entry["time"]})
            stat["count"] += 1
            if entry["time"] > stat["last_time"]:
                stat["last_time"] = entry["time"]
        ranking = [
            {
                "姓名": name,
                "完成数量": stat["count"],
                "最近完成": stat["last_time"].strftime("%Y-%m-%d %H:%M"),
            }
            for name, stat in sorted(stats.items(), key=lambda item: (item[1]["count"], item[1]["last_time"], item[0]), reverse=True)
        ]
        details = [
            {
                "日期": entry["day"].isoformat(),
                "时间": entry["time"].strftime("%H:%M"),
                "姓名": entry["name"],
                "类型": entry["scope"],
                "内容": entry["title"],
            }
            for entry in entries
        ]
        return {"ranking": ranking, "details": details, "start_day": start_day, "end_day": end_day}

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
                    "todo_id": str(row.get("todo_id", "")).strip(),
                    "created_at": created_at.isoformat(timespec="seconds"),
                }
            )
        logs.sort(key=lambda item: str(item["created_at"]), reverse=True)
        return logs if limit is None else logs[:limit]

    def projects_for_member(self, member_name: str) -> list[dict[str, Any]]:
        target = self._normalize_display_name(member_name)
        if not target:
            return []
        projects_by_id = {
            int(row["id"]): row
            for row in self.data["projects"]
            if isinstance(row, dict)
        }
        entries: dict[int, dict[str, Any]] = {}
        today = date.today()

        for project_id, row in projects_by_id.items():
            owner = str(row.get("owner", "")).strip()
            if self._normalize_display_name(owner) != target:
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                created_at = datetime.now()
            entries[project_id] = {
                "project_id": project_id,
                "project_name": str(row.get("name", "未知项目")),
                "role": "产品经理",
                "owner": owner,
                "status": str(row.get("status", "")),
                "description": str(row.get("description", "")),
                "project_link": str(row.get("project_link", "")),
                "backup_project_link": str(row.get("backup_project_link", "")),
                "development_group_link": str(row.get("development_group_link", "")),
                "coordination_group_link": str(row.get("coordination_group_link", "")),
                "project_notes": str(row.get("project_notes", "")),
                "joined_at": created_at.isoformat(timespec="seconds"),
                "joined_days": max(1, (today - created_at.date()).days + 1),
            }

        for member in self.data.get("project_members", []):
            if not isinstance(member, dict):
                continue
            name = str(member.get("name", "")).strip()
            if self._normalize_display_name(name) != target:
                continue
            try:
                project_id = int(member.get("project_id", 0) or 0)
            except (TypeError, ValueError):
                continue
            project = projects_by_id.get(project_id)
            if project is None:
                continue
            try:
                joined_at = _parse_time(str(member.get("created_at", project.get("created_at", ""))))
            except ValueError:
                joined_at = datetime.now()
            entries[project_id] = {
                "project_id": project_id,
                "project_name": str(project.get("name", "未知项目")),
                "role": str(member.get("role", "")),
                "owner": str(project.get("owner", "")),
                "status": str(project.get("status", "")),
                "description": str(project.get("description", "")),
                "project_link": str(project.get("project_link", "")),
                "backup_project_link": str(project.get("backup_project_link", "")),
                "development_group_link": str(project.get("development_group_link", "")),
                "coordination_group_link": str(project.get("coordination_group_link", "")),
                "project_notes": str(project.get("project_notes", "")),
                "joined_at": joined_at.isoformat(timespec="seconds"),
                "joined_days": max(1, (today - joined_at.date()).days + 1),
            }

        projects = list(entries.values())
        projects.sort(key=lambda item: str(item.get("joined_at", "")), reverse=True)
        return projects

    def delete_daily_report(self, report_id: int, mine_only: bool = True) -> bool:
        rows = self.data["daily_reports"]
        for index, row in enumerate(rows):
            if int(row["id"]) != report_id:
                continue
            if mine_only and not self.is_current_user_name(str(row.get("member_name", ""))):
                return False
            self._remember_deleted_record("daily_reports", row)
            del rows[index]
            self._save()
            return True
        return False

    def _daily_from_row(self, row: dict[str, Any]) -> DailyReport:
        raw_todo_id = row.get("todo_id", "")
        try:
            todo_id = int(raw_todo_id) if str(raw_todo_id).strip() else None
        except (TypeError, ValueError):
            todo_id = None
        return DailyReport(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            member_name=str(row["member_name"]),
            role=str(row["role"]),
            content=str(row["content"]),
            created_at=_parse_time(str(row["created_at"])),
            todo_id=todo_id,
        )

    def add_project_todo(
        self,
        project_id: int,
        title: str,
        creator: str,
        scope: str = "personal",
        assignee: str = "",
        assigned_by: str = "",
        due_at: datetime | None = None,
        workflow: str = "",
        designer: str = "",
        developer: str = "",
        tester: str = "",
        acceptor: str = "",
        assigned_by_pet: str = "penguin",
    ) -> ProjectTodo:
        created_at = datetime.now()
        todo_scope = scope if scope in {"personal", "project", "assigned"} else "personal"
        todo_workflow = workflow if workflow == "dev_test_accept" else ""
        todo_designer = designer.strip()
        initial_status = "ui_todo" if todo_workflow and todo_designer else "dev_todo" if todo_workflow else "todo"
        initial_handler = todo_designer if initial_status == "ui_todo" else developer.strip() if todo_workflow else assignee.strip()
        flow_history = []
        if todo_workflow:
            flow_history.append({
                "time": created_at.isoformat(timespec="seconds"),
                "actor": creator.strip(),
                "action": "指派UI" if initial_status == "ui_todo" else "指派开发",
                "status": initial_status,
                "handler": initial_handler,
            })
        row = self._with_operator({
            "id": self._next_id("project_todos", created_at),
            "project_id": project_id,
            "title": title.strip(),
            "creator": creator.strip(),
            "scope": todo_scope,
            "assignee": assignee.strip(),
            "assigned_by": assigned_by.strip(),
            "status": initial_status,
            "completed_by": "",
            "completed_by_pet": "penguin",
            "created_at": created_at.isoformat(timespec="seconds"),
            "completed_at": "",
            "due_at": due_at.isoformat(timespec="seconds") if due_at is not None else "",
            "started_at": "",
            "workflow": todo_workflow,
            "designer": todo_designer,
            "developer": developer.strip(),
            "tester": tester.strip(),
            "acceptor": acceptor.strip(),
            "current_handler": initial_handler,
            "flow_history": json.dumps(flow_history, ensure_ascii=False) if flow_history else "",
            "assigned_by_pet": assigned_by_pet.strip() or "penguin",
        })
        self.data["project_todos"].append(row)
        self._save()
        return self._todo_from_row(row)

    def add_requirement(
        self,
        requester: str,
        description: str,
        recipient_name: str,
        recipient_dingtalk_id: str = "",
        expected_at: date | None = None,
        source_conversation_id: str = "",
        source_message_id: str = "",
    ) -> Requirement:
        existing = self.get_requirement_by_source_message(source_message_id)
        if existing is not None:
            return existing
        created_at = datetime.now()
        row = self._with_operator({
            "id": self._next_id("requirements", created_at),
            "requester": requester.strip(),
            "expected_at": expected_at.isoformat() if expected_at else "",
            "description": description.strip(),
            "recipient_name": recipient_name.strip(),
            "recipient_dingtalk_id": recipient_dingtalk_id.strip(),
            "source_conversation_id": source_conversation_id.strip(),
            "source_message_id": source_message_id.strip(),
            "status": "pending",
            "project_id": "",
            "todo_id": "",
            "transfer_history": "",
            "created_at": created_at.isoformat(timespec="seconds"),
            "updated_at": created_at.isoformat(timespec="seconds"),
        })
        self.data["requirements"].append(row)
        self._save()
        return self._requirement_from_row(row)

    def get_requirement_by_source_message(self, message_id: str) -> Requirement | None:
        message_id = message_id.strip()
        if not message_id:
            return None
        for row in self.data["requirements"]:
            if str(row.get("source_message_id", "")).strip() == message_id:
                return self._requirement_from_row(row)
        return None

    def list_requirements(self, include_converted: bool = False) -> list[Requirement]:
        rows = list(self.data["requirements"])
        if not include_converted:
            rows = [row for row in rows if str(row.get("status", "pending")) == "pending"]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        return [self._requirement_from_row(row) for row in rows]

    def convert_requirement_to_todo(
        self, requirement_id: int, project_id: int, scope: str, assignee: str, actor: str
    ) -> ProjectTodo | None:
        for row in self.data["requirements"]:
            if int(row["id"]) != requirement_id or str(row.get("status", "pending")) != "pending":
                continue
            expected = str(row.get("expected_at", "")).strip()
            due_at = datetime.combine(date.fromisoformat(expected), time.max) if expected else None
            title = str(row.get("description", "")).strip()
            todo = self.add_project_todo(
                project_id, title, actor, scope=scope, assignee=assignee,
                assigned_by=actor if scope == "assigned" else "", due_at=due_at,
            )
            row["status"] = "converted"
            row["project_id"] = project_id
            row["todo_id"] = todo.id
            row["updated_at"] = datetime.now().isoformat(timespec="microseconds")
            self._save()
            return todo
        return None

    def transfer_requirement(self, requirement_id: int, recipient_name: str) -> Requirement | None:
        target = recipient_name.strip()
        if not target:
            return None
        for row in self.data["requirements"]:
            if int(row["id"]) != requirement_id or str(row.get("status", "pending")) != "pending":
                continue
            current = str(row.get("recipient_name", "")).strip()
            try:
                history = json.loads(str(row.get("transfer_history", "")) or "[]")
            except json.JSONDecodeError:
                history = []
            if not isinstance(history, list):
                history = []
            if current and current != target:
                history.append(current)
            row["recipient_name"] = target
            row["recipient_dingtalk_id"] = ""
            row["transfer_history"] = json.dumps(history, ensure_ascii=False)
            row["updated_at"] = datetime.now().isoformat(timespec="microseconds")
            self._save()
            return self._requirement_from_row(row)
        return None

    def return_requirement(self, requirement_id: int) -> Requirement | None:
        for row in self.data["requirements"]:
            if int(row["id"]) != requirement_id or str(row.get("status", "pending")) != "pending":
                continue
            try:
                history = json.loads(str(row.get("transfer_history", "")) or "[]")
            except json.JSONDecodeError:
                history = []
            if not isinstance(history, list):
                history = []
            target = str(history.pop()).strip() if history else str(row.get("requester", "")).strip()
            if not target:
                return None
            row["recipient_name"] = target
            row["recipient_dingtalk_id"] = ""
            row["transfer_history"] = json.dumps(history, ensure_ascii=False) if history else ""
            row["updated_at"] = datetime.now().isoformat(timespec="microseconds")
            self._save()
            return self._requirement_from_row(row)
        return None

    def _requirement_from_row(self, row: dict[str, Any]) -> Requirement:
        expected = str(row.get("expected_at", "")).strip()
        project_id = str(row.get("project_id", "")).strip()
        todo_id = str(row.get("todo_id", "")).strip()
        try:
            transfer_history = json.loads(str(row.get("transfer_history", "")) or "[]")
        except json.JSONDecodeError:
            transfer_history = []
        return Requirement(
            id=int(row["id"]), requester=str(row.get("requester", "")),
            expected_at=date.fromisoformat(expected) if expected else None,
            description=str(row.get("description", "")),
            recipient_name=str(row.get("recipient_name", "")),
            recipient_dingtalk_id=str(row.get("recipient_dingtalk_id", "")),
            source_conversation_id=str(row.get("source_conversation_id", "")),
            source_message_id=str(row.get("source_message_id", "")),
            status=str(row.get("status", "pending")),
            project_id=int(project_id) if project_id else None,
            todo_id=int(todo_id) if todo_id else None,
            created_at=_parse_time(str(row["created_at"])),
            transfer_history=tuple(str(name) for name in transfer_history if str(name).strip()) if isinstance(transfer_history, list) else (),
        )

    def list_project_todos(
        self,
        project_id: int,
        include_completed: bool = False,
        scope: str | None = None,
    ) -> list[ProjectTodo]:
        rows = [row for row in self.data["project_todos"] if int(row["project_id"]) == project_id]
        if scope in {"personal", "project", "assigned"}:
            rows = [row for row in rows if self._todo_row_scope(row) == scope]
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
            rows = [row for row in rows if self._todo_row_scope(row) == scope]
        if not include_completed:
            rows = [row for row in rows if str(row.get("status", "todo")) != "done"]
        rows.sort(key=lambda row: int(row["id"]), reverse=True)
        return [self._todo_from_row(row) for row in rows]

    def get_project_todo(self, todo_id: int) -> ProjectTodo | None:
        for row in self.data["project_todos"]:
            if int(row["id"]) == todo_id:
                return self._todo_from_row(row)
        return None

    def delete_project_todo(self, todo_id: int) -> bool:
        rows = self.data["project_todos"]
        for index, row in enumerate(rows):
            if int(row["id"]) != todo_id:
                continue
            self._remember_deleted_record("project_todos", row)
            del rows[index]
            self._save()
            return True
        return False

    def list_deleted_assigned_todos(self) -> list[dict[str, Any]]:
        rows = self.data.get("deleted_records", [])
        return [
            dict(row)
            for row in rows
            if isinstance(row, dict)
            and str(row.get("table", "")) == "project_todos"
            and str(row.get("scope", "")) == "assigned"
        ]

    def start_project_todo(self, todo_id: int, member_name: str) -> ProjectTodo | None:
        for row in self.data["project_todos"]:
            if int(row["id"]) != todo_id:
                continue
            if str(row.get("status", "todo")) == "done":
                return None
            if str(row.get("scope", "personal")) != "assigned":
                return None
            if self._normalize_display_name(self._todo_current_handler(row)) != self._normalize_display_name(member_name):
                return None
            if str(row.get("workflow", "")) == "dev_test_accept":
                if str(row.get("status", "todo")) != "dev_todo":
                    return self._todo_from_row(row)
                now = datetime.now()
                row["status"] = "dev_doing"
                row["started_at"] = now.isoformat(timespec="seconds")
                self._append_todo_flow(row, member_name, "开始开发", "dev_doing", self._todo_current_handler(row), now)
                self._save()
                return self._todo_from_row(row)
            if str(row.get("started_at", "")).strip():
                return self._todo_from_row(row)
            row["started_at"] = datetime.now().isoformat(timespec="seconds")
            self._save()
            return self._todo_from_row(row)
        return None

    def complete_project_todo(
        self,
        todo_id: int,
        member_name: str,
        role: str,
        progress_prefix: str = "完成代办",
        completed_by_pet: str = "penguin",
    ) -> DailyReport | ProjectTodo | None:
        for row in self.data["project_todos"]:
            if int(row["id"]) != todo_id:
                continue
            if str(row.get("status", "todo")) == "done":
                return None
            if str(row.get("workflow", "")) == "dev_test_accept":
                return self.advance_project_todo(todo_id, member_name, role, "pass", completed_by_pet)
            completed_at = datetime.now()
            row["status"] = "done"
            row["completed_by"] = member_name.strip()
            row["completed_by_pet"] = completed_by_pet.strip() or "penguin"
            row["completed_at"] = completed_at.isoformat(timespec="seconds")
            self._mark_overlapping_project_todos_done(row, member_name, completed_at)
            if str(row.get("scope", "personal")) == "project":
                self._save()
                return self._todo_from_row(row)
            report = self.add_daily_report(
                int(row["project_id"]),
                member_name,
                role,
                f"{progress_prefix}：{str(row.get('title', '')).strip()}",
                todo_id=todo_id,
            )
            return report
        return None

    def advance_project_todo(
        self,
        todo_id: int,
        member_name: str,
        role: str,
        action: str = "pass",
        completed_by_pet: str = "penguin",
    ) -> DailyReport | ProjectTodo | None:
        for row in self.data["project_todos"]:
            if int(row["id"]) != todo_id:
                continue
            if str(row.get("workflow", "")) != "dev_test_accept" or str(row.get("status", "todo")) == "done":
                return None
            if self._normalize_display_name(self._todo_current_handler(row)) != self._normalize_display_name(member_name):
                return None
            now = datetime.now()
            status = str(row.get("status", "todo"))
            if status == "ui_todo":
                developer = str(row.get("developer", "")).strip()
                if not developer:
                    return None
                row["status"] = "dev_todo"
                row["current_handler"] = developer
                action_text = "跳过UI，提交开发" if action == "skip_ui" else "UI完成，提交开发"
                self._append_todo_flow(row, member_name, action_text, "dev_todo", developer, now)
                report = self.add_daily_report(
                    int(row["project_id"]),
                    member_name,
                    role,
                    f"{action_text}：{str(row.get('title', '')).strip()}",
                    todo_id=todo_id,
                )
                return report
            if status == "dev_doing":
                project_id = int(row["project_id"])
                configured_tester = str(row.get("tester", "")).strip()
                tester = ""
                for member in self.list_project_members(project_id):
                    if "测试" not in member.role.strip():
                        continue
                    if not tester:
                        tester = member.name.strip()
                    if self._normalize_display_name(member.name) == self._normalize_display_name(configured_tester):
                        tester = member.name.strip()
                        break
                if not tester:
                    acceptor = str(row.get("acceptor", "")).strip() or str(row.get("assigned_by", "")).strip()
                    if not acceptor:
                        return None
                    row["status"] = "accept_todo"
                    row["current_handler"] = acceptor
                    self._append_todo_flow(row, member_name, "开发完成，提交验收", "accept_todo", acceptor, now)
                    report = self.add_daily_report(
                        project_id,
                        member_name,
                        role,
                        f"开发完成，提交验收：{str(row.get('title', '')).strip()}",
                        todo_id=todo_id,
                    )
                    return report
                row["status"] = "test_todo"
                row["current_handler"] = tester
                row["tester"] = tester
                self._append_todo_flow(row, member_name, "开发完成，提交测试", "test_todo", tester, now)
                report = self.add_daily_report(
                    project_id,
                    member_name,
                    role,
                    f"开发完成，提交测试：{str(row.get('title', '')).strip()}",
                    todo_id=todo_id,
                )
                return report
            if status == "test_todo":
                if "测试" not in role.strip():
                    return None
                developer = str(row.get("developer", "")).strip()
                acceptor = str(row.get("acceptor", "")).strip() or str(row.get("assigned_by", "")).strip()
                if action == "reject":
                    row["status"] = "dev_todo"
                    row["current_handler"] = developer
                    self._append_todo_flow(row, member_name, "测试不通过，打回开发", "dev_todo", developer, now)
                    report = self.add_daily_report(
                        int(row["project_id"]),
                        member_name,
                        role,
                        f"测试不通过，打回开发：{str(row.get('title', '')).strip()}",
                        todo_id=todo_id,
                    )
                    return report
                row["status"] = "accept_todo"
                row["current_handler"] = acceptor
                self._append_todo_flow(row, member_name, "测试通过，提交验收", "accept_todo", acceptor, now)
                report = self.add_daily_report(
                    int(row["project_id"]),
                    member_name,
                    role,
                    f"测试通过，提交验收：{str(row.get('title', '')).strip()}",
                    todo_id=todo_id,
                )
                return report
            if status == "accept_todo":
                if "产品" not in role.strip():
                    return None
                row["status"] = "done"
                row["completed_by"] = member_name.strip()
                row["completed_by_pet"] = completed_by_pet.strip() or "penguin"
                row["completed_at"] = now.isoformat(timespec="seconds")
                row["current_handler"] = ""
                self._append_todo_flow(row, member_name, "验收通过，完成代办", "done", "", now)
                report = self.add_daily_report(
                    int(row["project_id"]),
                    member_name,
                    role,
                    f"验收完成：{str(row.get('title', '')).strip()}",
                    todo_id=todo_id,
                )
                return report
            return None
        return None

    def reject_project_todo(self, todo_id: int, member_name: str, role: str) -> DailyReport | ProjectTodo | None:
        return self.advance_project_todo(todo_id, member_name, role, "reject")

    def skip_project_todo_ui(self, todo_id: int, member_name: str, role: str) -> DailyReport | ProjectTodo | None:
        return self.advance_project_todo(todo_id, member_name, role, "skip_ui")

    def _todo_from_row(self, row: dict[str, Any]) -> ProjectTodo:
        completed_at = str(row.get("completed_at", "")).strip()
        due_at = str(row.get("due_at", "")).strip()
        started_at = str(row.get("started_at", "")).strip()
        try:
            parsed_due_at = _parse_time(due_at) if due_at else None
        except ValueError:
            parsed_due_at = None
        try:
            parsed_started_at = _parse_time(started_at) if started_at else None
        except ValueError:
            parsed_started_at = None
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
            due_at=parsed_due_at,
            started_at=parsed_started_at,
            workflow=str(row.get("workflow", "")),
            designer=str(row.get("designer", "")),
            developer=str(row.get("developer", "")),
            tester=str(row.get("tester", "")),
            acceptor=str(row.get("acceptor", "")),
            current_handler=str(row.get("current_handler", "")),
            flow_history=str(row.get("flow_history", "")),
            assigned_by_pet=str(row.get("assigned_by_pet", "penguin")) or "penguin",
            completed_by_pet=str(row.get("completed_by_pet", "penguin")) or "penguin",
        )

    def _todo_current_handler(self, row: dict[str, Any]) -> str:
        handler = str(row.get("current_handler", "")).strip()
        if handler:
            return handler
        return str(row.get("assignee", "")).strip()

    def _todo_row_scope(self, row: dict[str, Any]) -> str:
        scope = str(row.get("scope", "")).strip()
        return scope if scope in {"personal", "project", "assigned"} else "personal"

    def _normalized_todo_title(self, value: Any) -> str:
        return "".join(str(value or "").split()).casefold()

    def _todo_titles_overlap(self, left: Any, right: Any) -> bool:
        left_title = self._normalized_todo_title(left)
        right_title = self._normalized_todo_title(right)
        if len(left_title) < 5 or len(right_title) < 5:
            return False
        return left_title in right_title or right_title in left_title

    def _todo_rows_same_owner(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_names = {
            self._normalize_display_name(str(left.get("creator", ""))),
            self._normalize_display_name(str(left.get("assignee", ""))),
            self._normalize_display_name(str(left.get("assigned_by", ""))),
            self._normalize_display_name(str(left.get("completed_by", ""))),
        }
        right_names = {
            self._normalize_display_name(str(right.get("creator", ""))),
            self._normalize_display_name(str(right.get("assignee", ""))),
            self._normalize_display_name(str(right.get("assigned_by", ""))),
            self._normalize_display_name(str(right.get("completed_by", ""))),
        }
        left_names.discard("")
        right_names.discard("")
        return bool(left_names and right_names and left_names.intersection(right_names))

    def _mark_overlapping_project_todos_done(
        self,
        completed_row: dict[str, Any],
        completed_by: str,
        completed_at: datetime,
    ) -> bool:
        rows = self.data.get("project_todos")
        if not isinstance(rows, list):
            return False
        changed = False
        completed_project_id = str(completed_row.get("project_id", "")).strip()
        completed_title = str(completed_row.get("title", ""))
        for row in rows:
            if not isinstance(row, dict) or row is completed_row:
                continue
            if str(row.get("status", "todo")) == "done":
                continue
            if str(row.get("project_id", "")).strip() != completed_project_id:
                continue
            if not self._todo_rows_same_owner(completed_row, row):
                continue
            if not self._todo_titles_overlap(completed_title, row.get("title", "")):
                continue
            row["status"] = "done"
            row["completed_by"] = completed_by.strip()
            row["completed_by_pet"] = str(completed_row.get("completed_by_pet", "penguin")) or "penguin"
            row["completed_at"] = completed_at.isoformat(timespec="seconds")
            changed = True
        return changed

    def _append_todo_flow(
        self,
        row: dict[str, Any],
        actor: str,
        action: str,
        status: str,
        handler: str,
        happened_at: datetime | None = None,
    ) -> None:
        history = self._todo_flow_entries(row)
        history.append({
            "time": (happened_at or datetime.now()).isoformat(timespec="seconds"),
            "actor": actor.strip(),
            "action": action,
            "status": status,
            "handler": handler.strip(),
        })
        row["flow_history"] = json.dumps(history, ensure_ascii=False)

    def _todo_flow_entries(self, row: dict[str, Any]) -> list[dict[str, str]]:
        raw = str(row.get("flow_history", "")).strip()
        if not raw:
            return []
        try:
            loaded = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(loaded, list):
            return []
        entries: list[dict[str, str]] = []
        for item in loaded:
            if not isinstance(item, dict):
                continue
            entries.append({str(key): str(value) for key, value in item.items()})
        return entries

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
            self._remember_deleted_record("project_weekly_reports", row)
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
            "id": self._next_id("project_documents", created_at),
            "project_id": project_id,
            "title": title.strip(),
            "doc_type": doc_type.strip(),
            "visibility": visibility.strip(),
            "uploader": uploader.strip(),
            "file_path": file_path,
            "file_sha256": self._document_plaintext_hash(Path(file_path)),
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
            source = Path(str(row.get("file_path", "")))
            if self._document_path_is_inside_library(source):
                try:
                    source.chmod(stat.S_IRUSR | stat.S_IWUSR)
                    source.unlink()
                except OSError:
                    pass
            self._remember_deleted_record("project_documents", row)
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

    def shared_record_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in SHARED_TABLES:
            value = self.data.get(table)
            if isinstance(value, list):
                counts[table] = len(self._recent_activity_events()) if table == "activity_events" else len(value)
        return counts

    def shared_project_fingerprints(self) -> dict[str, dict[str, str]]:
        fingerprints: dict[str, dict[str, str]] = {}
        projects = self.data.get("projects")
        if not isinstance(projects, list):
            return fingerprints
        for row in projects:
            if not isinstance(row, dict):
                continue
            key = self._project_fingerprint_key(row)
            if not key:
                continue
            fingerprints[key] = {
                "name": str(row.get("name", "")),
                "owner": str(row.get("owner", "")),
                "status": str(row.get("status", "")),
                "description": str(row.get("description", "")),
                "project_link": str(row.get("project_link", "")),
                "backup_project_link": str(row.get("backup_project_link", "")),
                "development_group_link": str(row.get("development_group_link", "")),
                "coordination_group_link": str(row.get("coordination_group_link", "")),
                "project_notes": str(row.get("project_notes", "")),
                "updated_at": str(row.get("updated_at", "")),
            }
        return fingerprints

    def peer_may_have_owner_project_deletions(
        self,
        peer_name: str,
        remote_project_fingerprints: dict[str, dict[str, str]],
    ) -> bool:
        owner = self._normalize_display_name(peer_name)
        if not owner or not isinstance(remote_project_fingerprints, dict):
            return False
        remote_keys = {str(key) for key in remote_project_fingerprints}
        for row in self.data.get("projects", []):
            if not isinstance(row, dict):
                continue
            if self._normalize_display_name(str(row.get("owner", ""))) != owner:
                continue
            key = self._project_fingerprint_key(row)
            if key and key not in remote_keys:
                return True
        return False

    def _project_fingerprint_key(self, row: dict[str, Any]) -> str:
        source = self._row_source_key(row)
        if source is not None:
            return f"{source[0]}:{source[1]}"
        return str(row.get("id", "")).strip()

    def _document_vault_key(self) -> bytes:
        key_path = self.path.parent / "vault.key"
        try:
            key = key_path.read_bytes()
            if len(key) == 32:
                return key
        except OSError:
            pass
        key = secrets.token_bytes(32)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(key)
        try:
            key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return key

    def _legacy_crypt_document_bytes(self, content: bytes, nonce: bytes) -> bytes:
        key = self._document_vault_key()
        output = bytearray(len(content))
        for offset in range(0, len(content), 32):
            counter = offset // 32
            block = hmac.new(key, b"stream" + nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
            chunk = content[offset:offset + 32]
            output[offset:offset + len(chunk)] = bytes(left ^ right for left, right in zip(chunk, block))
        return bytes(output)

    def _encrypt_document_bytes(self, content: bytes) -> bytes:
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._document_vault_key()).encrypt(nonce, content, DOCUMENT_VAULT_MAGIC)
        return DOCUMENT_VAULT_MAGIC + nonce + ciphertext

    def _decrypt_document_bytes(self, payload: bytes) -> bytes:
        if payload.startswith(DOCUMENT_VAULT_MAGIC):
            header = len(DOCUMENT_VAULT_MAGIC)
            if len(payload) < header + 28:
                raise ValueError("加密文档内容不完整")
            nonce = payload[header:header + 12]
            ciphertext = payload[header + 12:]
            try:
                return AESGCM(self._document_vault_key()).decrypt(nonce, ciphertext, DOCUMENT_VAULT_MAGIC)
            except Exception as exc:
                raise ValueError("加密文档校验失败") from exc
        if not payload.startswith(LEGACY_DOCUMENT_VAULT_MAGIC):
            return payload
        header = len(LEGACY_DOCUMENT_VAULT_MAGIC)
        if len(payload) < header + 48:
            raise ValueError("加密文档内容不完整")
        nonce = payload[header:header + 16]
        tag = payload[header + 16:header + 48]
        ciphertext = payload[header + 48:]
        expected = hmac.new(self._document_vault_key(), b"auth" + nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("加密文档校验失败")
        return self._legacy_crypt_document_bytes(ciphertext, nonce)

    def document_content(self, path: str | Path) -> bytes:
        return self._decrypt_document_bytes(Path(path).read_bytes())

    def _document_plaintext_hash(self, path: Path) -> str:
        try:
            return hashlib.sha256(self.document_content(path)).hexdigest()
        except (OSError, ValueError):
            return ""

    def store_document_content(self, project_id: int, content: bytes) -> Path:
        target_dir = self.path.parent / "documents" / str(project_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{uuid.uuid4().hex}.szzxdoc"
        target.write_bytes(self._encrypt_document_bytes(content))
        try:
            target.chmod(stat.S_IRUSR)
        except OSError:
            pass
        return target

    def import_document_file(self, project_id: int, source: Path) -> Path:
        return self.store_document_content(project_id, source.read_bytes())

    def materialize_document(self, document: ProjectDocument) -> Path:
        cache_dir = self.path.parent / "open-cache" / str(document.id)
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / safe_document_filename(document.title)
        if target.exists():
            try:
                target.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        target.write_bytes(self.document_content(document.file_path))
        try:
            target.chmod(stat.S_IRUSR)
        except OSError:
            pass
        return target

    def _cleanup_document_open_cache(self) -> None:
        root = self.path.parent / "open-cache"
        if not root.exists():
            return
        for path in sorted(root.rglob("*"), reverse=True):
            try:
                if path.is_file():
                    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            except OSError:
                continue
        try:
            root.rmdir()
        except OSError:
            pass

    def _migrate_document_vault(self) -> bool:
        changed = False
        for row in self.data.get("project_documents", []):
            if not isinstance(row, dict):
                continue
            source = Path(str(row.get("file_path", "")))
            if not source.is_file():
                continue
            try:
                payload = source.read_bytes()
            except OSError:
                continue
            if payload.startswith(DOCUMENT_VAULT_MAGIC) and source.suffix == ".szzxdoc":
                if not str(row.get("file_sha256", "")).strip():
                    try:
                        row["file_sha256"] = hashlib.sha256(self._decrypt_document_bytes(payload)).hexdigest()
                        changed = True
                    except ValueError:
                        pass
                continue
            try:
                content = self._decrypt_document_bytes(payload)
                target = self.store_document_content(int(row.get("project_id", 0)), content)
            except (OSError, ValueError):
                continue
            row["file_path"] = str(target)
            row["file_sha256"] = hashlib.sha256(content).hexdigest()
            if source != target and self._document_path_is_inside_library(source):
                try:
                    source.chmod(stat.S_IRUSR | stat.S_IWUSR)
                    source.unlink()
                except OSError:
                    pass
            changed = True
        return changed

    def _document_file_payloads(self, documents: Any) -> dict[str, dict[str, str]]:
        if not isinstance(documents, list):
            return {}
        files: dict[str, dict[str, str]] = {}
        for row in documents:
            if not isinstance(row, dict):
                continue
            document_id = str(row.get("id", ""))
            source = Path(str(row.get("file_path", "")))
            try:
                if not document_id or not source.is_file():
                    continue
                content = self.document_content(source)
                # Sync payloads must always contain plaintext. Publishing an
                # encrypted vault blob causes every receiver to encrypt it a
                # second time and applications can no longer open the file.
                if content.startswith((DOCUMENT_VAULT_MAGIC, LEGACY_DOCUMENT_VAULT_MAGIC)):
                    continue
                files[document_id] = {
                    "name": safe_document_filename(str(row.get("title") or f"document-{document_id}")),
                    "size": str(len(content)),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "content": base64.b64encode(content).decode("ascii"),
                }
            except (OSError, ValueError):
                continue
        return files

    def shared_snapshot(
        self,
        include_files: bool = False,
        personalized: bool = True,
        project_notes_actor: str | None = None,
        redact_project_notes: bool = False,
    ) -> dict[str, Any]:
        tables: dict[str, Any] = {}
        for table in SHARED_TABLES:
            if table == "activity_events":
                tables[table] = self._recent_activity_events()
                continue
            value = self.data.get(table)
            tables[table] = value.copy() if isinstance(value, dict) else list(value or [])
        if personalized:
            tables = self._personalized_snapshot_tables(tables)
        if redact_project_notes:
            tables = self._redact_project_notes_for_actor(tables, project_notes_actor or "")
        snapshot = {
            "sync": self.sync_state(),
            "owner": {
                "actor": self.display_name(),
                "origin": self.device_id(),
                "scope": "personal" if personalized else "all",
            },
            "tables": tables,
        }
        if include_files:
            snapshot["files"] = self._document_file_payloads(tables.get("project_documents", []))
        return snapshot

    def _recent_activity_events(self) -> list[dict[str, Any]]:
        if ACTIVITY_EVENT_SYNC_DAYS <= 0:
            return []
        rows = self.data.get("activity_events", [])
        if not isinstance(rows, list):
            return []
        cutoff = datetime.now() - timedelta(days=ACTIVITY_EVENT_SYNC_DAYS)
        recent: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                created_at = _parse_time(str(row.get("created_at", "")))
            except ValueError:
                continue
            if created_at >= cutoff:
                recent.append(dict(row))
        return recent

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
                if table in ("name_claims", "project_todos"):
                    tables[table] = []
                elif table in ("deleted_projects", "deleted_records"):
                    tables[table] = list(self.data.get(table, []))
                else:
                    return False
        owner = snapshot.get("owner")
        tables = self._personalized_remote_tables(tables, owner if isinstance(owner, dict) else sync)
        local_has_missing_rows = self._snapshot_missing_local_shared_rows(tables)
        self._backup_before_sync()
        files = snapshot.get("files")
        changed = False
        remote_deleted_projects = self._deleted_project_keys_from(tables.get("deleted_projects"))
        remote_deleted_records = self._deleted_record_keys_by_table_from(tables.get("deleted_records"))
        if self._apply_owner_missing_project_deletions(
            tables.get("projects"),
            owner if isinstance(owner, dict) else sync,
        ):
            changed = True
        if self._merge_deleted_projects(tables.get("deleted_projects")):
            changed = True
        if self._merge_deleted_records(tables.get("deleted_records")):
            changed = True
        active_deleted_projects = self._active_deleted_project_keys(remote_deleted_projects)
        active_deleted_records = self._active_deleted_record_keys_by_table(remote_deleted_records)
        if self._apply_deleted_projects(active_deleted_projects):
            changed = True
        if self._apply_deleted_records(active_deleted_records):
            changed = True
        project_id_map, projects_changed = self._merge_remote_projects(
            tables.get("projects"),
            update_existing=True,
            allow_untimestamped_updates=True,
            deleted_sources=active_deleted_projects,
        )
        changed = changed or projects_changed
        for table in SHARED_TABLES:
            if table in {"projects", "deleted_projects", "deleted_records", "counters"}:
                continue
            if self._merge_remote_table(
                table,
                tables.get(table),
                project_id_map,
                deleted_sources=active_deleted_records.get(table),
            ):
                changed = True
        if self._apply_deleted_projects(active_deleted_projects):
            changed = True
        if self._apply_deleted_records(active_deleted_records):
            changed = True
        if isinstance(files, dict) and self._restore_document_files(self.data, files):
            changed = True
        if self._repair_workflow_todo_handlers():
            changed = True
        if self._repair_project_todo_completion_duplicates():
            changed = True
        if self._repair_daily_report_duplicates():
            changed = True
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

    def replace_shared_snapshot(self, snapshot: dict[str, Any]) -> bool:
        tables = snapshot.get("tables")
        sync = snapshot.get("sync")
        if not isinstance(tables, dict) or not isinstance(sync, dict):
            return False
        normalized_tables: dict[str, Any] = {}
        empty = self._empty_data()
        for table in SHARED_TABLES:
            empty_value = empty[table]
            remote_value = tables.get(table)
            if isinstance(empty_value, dict):
                normalized_tables[table] = dict(remote_value) if isinstance(remote_value, dict) else {}
            else:
                normalized_tables[table] = list(remote_value) if isinstance(remote_value, list) else []

        changed = False
        for table, value in normalized_tables.items():
            if self.data.get(table) != value:
                changed = True
                self.data[table] = value
        next_sync = {
            "revision": int(sync.get("revision", 0) or 0),
            "updated_at": str(sync.get("updated_at", "")),
            "origin": str(sync.get("origin", "")),
            "actor": str(sync.get("actor", "")),
        }
        if self.data.get("sync") != next_sync:
            changed = True
            self.data["sync"] = next_sync
        files = snapshot.get("files")
        if isinstance(files, dict):
            if self._restore_document_files(self.data, files):
                changed = True
        if self._server_files_are_complete(self.data, files) and self._prune_unreferenced_document_files():
            changed = True
        if self._repair_workflow_todo_handlers():
            changed = True
        self._sync_counters_to_rows()
        self._save(bump_sync=False)
        return changed

    def clear_shared_data_cache(
        self,
        prune_documents: bool = False,
        preserve_current_user_records: bool = True,
    ) -> bool:
        preserved = self._current_user_records_to_preserve() if preserve_current_user_records else {}
        empty = self._empty_data()
        changed = False
        for table in SHARED_TABLES:
            empty_value = empty[table]
            next_value = {} if isinstance(empty_value, dict) else list(preserved.get(table, []))
            if self.data.get(table) != next_value:
                self.data[table] = next_value
                changed = True
        next_sync = {"revision": 0, "updated_at": "", "origin": "", "actor": ""}
        if self.data.get("sync") != next_sync:
            self.data["sync"] = next_sync
            changed = True
        if prune_documents and self._prune_unreferenced_document_files():
            changed = True
        if changed:
            self._save(bump_sync=False)
        return changed

    def _current_user_records_to_preserve(self) -> dict[str, list[dict[str, Any]]]:
        preserved: dict[str, list[dict[str, Any]]] = {}
        for table in (
            "weekly_reports",
            "daily_reports",
            "project_weekly_reports",
            "project_todos",
            "rest_days",
            "deleted_records",
        ):
            rows = self.data.get(table)
            if not isinstance(rows, list):
                continue
            current_rows = [
                dict(row)
                for row in rows
                if isinstance(row, dict) and self._is_current_user_owned_record(table, row)
            ]
            if current_rows:
                preserved[table] = current_rows
        return preserved

    def _is_current_user_owned_record(self, table: str, row: dict[str, Any]) -> bool:
        if table in {"weekly_reports", "rest_days"}:
            return self._is_current_user_row(row)
        if table == "daily_reports":
            return self._is_current_user_row(row) or self.is_current_user_name(str(row.get("member_name", "")))
        if table == "project_weekly_reports":
            return self._is_current_user_row(row) or self.is_current_user_name(str(row.get("author", "")))
        if table == "project_todos":
            names = (
                row.get("creator", ""),
                row.get("assignee", ""),
                row.get("assigned_by", ""),
                row.get("completed_by", ""),
                row.get("current_handler", ""),
            )
            return self._is_current_user_row(row) or any(self.is_current_user_name(str(name)) for name in names)
        if table == "deleted_records":
            return self._is_local_deletion_marker(row)
        return False

    def merge_missing_shared_snapshot(self, snapshot: dict[str, Any], honor_deletions: bool = True) -> bool:
        tables = snapshot.get("tables")
        if not isinstance(tables, dict):
            return False
        owner = snapshot.get("owner")
        sync = snapshot.get("sync")
        if not isinstance(sync, dict):
            sync = {}
        tables = self._personalized_remote_tables(tables, owner if isinstance(owner, dict) else sync)
        changed = False
        remote_deleted_projects = self._deleted_project_keys_from(tables.get("deleted_projects"))
        remote_deleted_records = self._deleted_record_keys_by_table_from(tables.get("deleted_records"))
        if honor_deletions:
            if self._apply_owner_missing_project_deletions(
                tables.get("projects"),
                owner if isinstance(owner, dict) else sync,
            ):
                changed = True
            if self._merge_deleted_projects(tables.get("deleted_projects")):
                changed = True
            if self._merge_deleted_records(tables.get("deleted_records")):
                changed = True
            active_deleted_projects = self._active_deleted_project_keys(remote_deleted_projects)
            active_deleted_records = self._active_deleted_record_keys_by_table(remote_deleted_records)
            if self._apply_deleted_projects(active_deleted_projects):
                changed = True
            if self._apply_deleted_records(active_deleted_records):
                changed = True
        else:
            active_deleted_projects = set()
            active_deleted_records = {}
        project_id_map, projects_changed = self._merge_remote_projects(
            tables.get("projects"),
            update_existing=True,
            honor_deleted_projects=honor_deletions,
            deleted_sources=active_deleted_projects,
        )
        changed = changed or projects_changed
        for table in SHARED_TABLES:
            if table in {"projects", "deleted_projects", "deleted_records", "counters"}:
                continue
            if self._merge_remote_table(
                table,
                tables.get(table),
                project_id_map,
                honor_deleted_records=honor_deletions,
                deleted_sources=active_deleted_records.get(table) if honor_deletions else set(),
            ):
                changed = True
        if honor_deletions:
            if self._apply_deleted_projects(active_deleted_projects):
                changed = True
            if self._apply_deleted_records(active_deleted_records):
                changed = True
        if self._repair_workflow_todo_handlers():
            changed = True
        if self._repair_project_todo_completion_duplicates():
            changed = True
        if self._repair_daily_report_duplicates():
            changed = True
        files = snapshot.get("files")
        if isinstance(files, dict) and self._restore_document_files(self.data, files):
            changed = True
        if not changed:
            return False
        self._sync_counters_to_rows()
        self._save()
        return True

    def _merge_remote_projects(
        self,
        remote_value: Any,
        update_existing: bool = False,
        allow_untimestamped_updates: bool = False,
        honor_deleted_projects: bool = True,
        deleted_sources: set[tuple[str, str]] | None = None,
    ) -> tuple[dict[int, int], bool]:
        project_id_map: dict[int, int] = {}
        changed = False
        local_projects = self.data.get("projects")
        if not isinstance(remote_value, list) or not isinstance(local_projects, list):
            return project_id_map, changed
        existing_sources = self._source_index("projects")
        existing_ids = self._id_index("projects")
        deleted_sources = deleted_sources if deleted_sources is not None else (
            self._deleted_project_keys() if honor_deleted_projects else set()
        )
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
                existing = existing_sources[source]
                project_id_map[remote_id] = int(existing.get("id", remote_id))
                if update_existing and self._merge_existing_project(existing, row, allow_untimestamped_updates):
                    changed = True
                continue
            existing = existing_ids.get(remote_id)
            if existing is not None:
                project_id_map[remote_id] = remote_id
                if update_existing and self._merge_existing_project(existing, row, allow_untimestamped_updates):
                    changed = True
                elif self._rows_match(existing, row):
                    self._remember_row_source(existing, row)
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

    def _merge_existing_project(
        self,
        existing: dict[str, Any],
        remote: dict[str, Any],
        allow_untimestamped_updates: bool = False,
    ) -> bool:
        changed = False
        # Older servers stored the project's new timestamp before they knew
        # about these fields. Backfill non-empty public links even when the
        # timestamps are equal, without letting an older empty value erase one.
        for key in ("development_group_link", "coordination_group_link"):
            remote_value = str(remote.get(key, "")).strip()
            if remote_value and not str(existing.get(key, "")).strip():
                existing[key] = remote_value
                changed = True
        if not self._remote_project_is_newer(existing, remote, allow_untimestamped_updates):
            if changed:
                self._remember_row_source(existing, remote)
            return changed
        for key in ("name", "owner", "description", "status", "project_link", "backup_project_link", "development_group_link", "coordination_group_link", "project_notes", "updated_at"):
            if key not in remote:
                continue
            value = remote.get(key)
            if existing.get(key) == value:
                continue
            existing[key] = value
            changed = True
        self._remember_row_source(existing, remote)
        return changed

    def snapshot_missing_local_public_project_links(self, snapshot: dict[str, Any]) -> bool:
        tables = snapshot.get("tables")
        remote_projects = tables.get("projects") if isinstance(tables, dict) else None
        local_projects = self.data.get("projects")
        if not isinstance(remote_projects, list) or not isinstance(local_projects, list):
            return False
        remote_by_source = {
            source: row
            for row in remote_projects
            if isinstance(row, dict) and (source := self._row_source_key(row)) is not None
        }
        remote_by_id = {
            str(row.get("id", "")): row
            for row in remote_projects
            if isinstance(row, dict)
        }
        for local in local_projects:
            if not isinstance(local, dict):
                continue
            source = self._row_source_key(local)
            remote = remote_by_source.get(source) if source is not None else None
            if remote is None:
                remote = remote_by_id.get(str(local.get("id", "")))
            if not isinstance(remote, dict):
                continue
            for key in ("development_group_link", "coordination_group_link"):
                if str(local.get(key, "")).strip() and not str(remote.get(key, "")).strip():
                    return True
        return False

    def _remote_project_is_newer(
        self,
        existing: dict[str, Any],
        remote: dict[str, Any],
        allow_untimestamped_updates: bool = False,
    ) -> bool:
        remote_updated = str(remote.get("updated_at") or remote.get("created_at") or "").strip()
        existing_updated = str(existing.get("updated_at") or existing.get("created_at") or "").strip()
        if remote_updated and existing_updated:
            return remote_updated > existing_updated
        if remote_updated and not existing_updated:
            return True
        if allow_untimestamped_updates and not remote_updated and not existing_updated:
            return True
        return False

    def _merge_remote_table(
        self,
        table: str,
        remote_value: Any,
        project_id_map: dict[int, int],
        honor_deleted_records: bool = True,
        deleted_sources: set[tuple[str, str]] | None = None,
    ) -> bool:
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
        deleted_sources = deleted_sources if deleted_sources is not None else (
            self._deleted_record_keys_for_table(table) if honor_deleted_records else set()
        )
        changed = False
        for row in remote_value:
            if not isinstance(row, dict):
                continue
            next_row = dict(row)
            raw_project_id = str(next_row.get("project_id", "")).strip()
            if "project_id" in next_row and raw_project_id:
                try:
                    remote_project_id = int(raw_project_id)
                except (TypeError, ValueError):
                    continue
                if remote_project_id not in project_id_map:
                    continue
                next_row["project_id"] = project_id_map[remote_project_id]
            source = self._row_source_key(row)
            if source and source in deleted_sources:
                continue
            if source and source in existing_sources:
                if self._merge_existing_shared_row(table, existing_sources[source], next_row):
                    changed = True
                continue
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
            if table == "project_members":
                existing = self._find_project_member_row(
                    int(next_row.get("project_id", 0) or 0),
                    str(next_row.get("name", "")),
                    str(next_row.get("role", "")),
                )
                if existing is not None:
                    self._remember_row_source(existing, row)
                    if (
                        str(next_row.get("dingtalk_id", "")).strip()
                        and not str(existing.get("dingtalk_id", "")).strip()
                    ):
                        existing["dingtalk_id"] = str(next_row.get("dingtalk_id", "")).strip()
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
            if existing is not None and self._merge_existing_shared_row(table, existing, next_row):
                self._remember_row_source(existing, row)
                changed = True
                continue
            self._remember_row_source(next_row, row)
            if existing is not None:
                try:
                    next_created_at = _parse_time(str(next_row.get("created_at", "")))
                except ValueError:
                    next_created_at = datetime.now()
                next_row["id"] = self._next_id(table, next_created_at)
            local_value.append(next_row)
            changed = True
        return changed

    def _merge_existing_shared_row(self, table: str, existing: dict[str, Any], remote: dict[str, Any]) -> bool:
        if table == "requirements":
            remote_updated = str(remote.get("updated_at") or remote.get("created_at") or "")
            existing_updated = str(existing.get("updated_at") or existing.get("created_at") or "")
            if remote_updated <= existing_updated:
                return False
            changed = False
            for key in ("recipient_name", "recipient_dingtalk_id", "status", "project_id", "todo_id", "transfer_history", "updated_at"):
                if key in remote and existing.get(key) != remote.get(key):
                    existing[key] = remote.get(key)
                    changed = True
            return changed
        if table != "project_todos":
            return False
        changed = False
        remote_started_at = str(remote.get("started_at", ""))
        existing_started_at = str(existing.get("started_at", ""))
        if remote_started_at and remote_started_at > existing_started_at:
            existing["started_at"] = remote_started_at
            changed = True
        remote_status = str(remote.get("status", "todo"))
        existing_status = str(existing.get("status", "todo"))
        remote_completed_at = str(remote.get("completed_at", ""))
        existing_completed_at = str(existing.get("completed_at", ""))
        remote_history = str(remote.get("flow_history", ""))
        existing_history = str(existing.get("flow_history", ""))
        if remote_history and len(remote_history) > len(existing_history):
            for key in (
                "status",
                "completed_by",
                "completed_by_pet",
                "completed_at",
                "started_at",
                "workflow",
                "designer",
                "developer",
                "tester",
                "acceptor",
                "current_handler",
                "flow_history",
            ):
                existing[key] = str(remote.get(key, ""))
            return True
        if remote_status != "done":
            return changed
        if existing_status == "done" and remote_completed_at <= existing_completed_at:
            return changed
        for key in ("status", "completed_by", "completed_by_pet", "completed_at", "current_handler", "flow_history"):
            existing[key] = str(remote.get(key, ""))
        return True

    def _repair_project_todo_completion_duplicates(self) -> bool:
        rows = self.data.get("project_todos")
        if not isinstance(rows, list):
            return False
        completed_by_source: dict[tuple[str, str], dict[str, Any]] = {}
        completed_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict) or str(row.get("status", "todo")) != "done":
                continue
            completed_rows.append(row)
            source = self._row_source_key(row)
            if source is None:
                continue
            current = completed_by_source.get(source)
            if current is None or str(row.get("completed_at", "")) > str(current.get("completed_at", "")):
                completed_by_source[source] = row

        changed = False
        rows_to_remove: set[int] = set()
        for row in rows:
            if not isinstance(row, dict) or str(row.get("status", "todo")) == "done":
                continue
            source = self._row_source_key(row)
            if source is None:
                continue
            completed = completed_by_source.get(source)
            if completed is None:
                continue
            for key in ("status", "completed_by", "completed_by_pet", "completed_at"):
                row[key] = str(completed.get(key, ""))
            rows_to_remove.add(id(completed))
            changed = True

        for row in rows:
            if not isinstance(row, dict) or str(row.get("status", "todo")) == "done":
                continue
            for completed in completed_rows:
                if str(row.get("project_id", "")).strip() != str(completed.get("project_id", "")).strip():
                    continue
                if not self._todo_rows_same_owner(completed, row):
                    continue
                if not self._todo_titles_overlap(completed.get("title", ""), row.get("title", "")):
                    continue
                row["status"] = "done"
                row["completed_by"] = str(completed.get("completed_by", ""))
                row["completed_by_pet"] = str(completed.get("completed_by_pet", "penguin")) or "penguin"
                row["completed_at"] = str(completed.get("completed_at", ""))
                changed = True
                break

        if rows_to_remove:
            rows[:] = [row for row in rows if not isinstance(row, dict) or id(row) not in rows_to_remove]
            changed = True
        return changed

    def _repair_workflow_todo_handlers(self) -> bool:
        rows = self.data.get("project_todos")
        if not isinstance(rows, list):
            return False
        changed = False
        for row in rows:
            if not isinstance(row, dict) or str(row.get("workflow", "")) != "dev_test_accept":
                continue
            status = str(row.get("status", "todo"))
            if status == "done":
                if str(row.get("current_handler", "")).strip():
                    row["current_handler"] = ""
                    changed = True
                continue

            fallback_tester = self._workflow_todo_fallback_tester(row)
            if status == "test_todo" and not fallback_tester:
                acceptor = str(row.get("acceptor", "")).strip() or str(row.get("assigned_by", "")).strip()
                if acceptor:
                    row["status"] = "accept_todo"
                    row["tester"] = ""
                    row["current_handler"] = acceptor
                    self._append_todo_flow(
                        row,
                        "系统",
                        "项目未配置测试，跳过测试并提交验收",
                        "accept_todo",
                        acceptor,
                        datetime.now(),
                    )
                    changed = True
                    continue
            if fallback_tester and not str(row.get("tester", "")).strip():
                row["tester"] = fallback_tester
                changed = True

            desired_handler = self._workflow_todo_expected_handler(row)
            if desired_handler and str(row.get("current_handler", "")).strip() != desired_handler:
                row["current_handler"] = desired_handler
                changed = True
        return changed

    def _workflow_todo_fallback_tester(self, row: dict[str, Any]) -> str:
        try:
            project_id = int(row.get("project_id", 0))
        except (TypeError, ValueError):
            return ""
        configured = str(row.get("tester", "")).strip()
        fallback = ""
        for member in self.list_project_members(project_id):
            if "测试" not in member.role.strip():
                continue
            if not fallback:
                fallback = member.name.strip()
            if self._normalize_display_name(member.name) == self._normalize_display_name(configured):
                return member.name.strip()
        if fallback:
            return fallback
        return ""

    def _workflow_todo_expected_handler(self, row: dict[str, Any]) -> str:
        status = str(row.get("status", "todo"))
        if status == "ui_todo":
            return str(row.get("designer", "")).strip() or str(row.get("developer", "")).strip()
        if status in {"dev_todo", "dev_doing"}:
            return str(row.get("developer", "")).strip() or str(row.get("assignee", "")).strip()
        if status == "test_todo":
            return self._workflow_todo_fallback_tester(row)
        if status == "accept_todo":
            return str(row.get("acceptor", "")).strip() or str(row.get("assigned_by", "")).strip()
        return str(row.get("current_handler", "")).strip()

    def _repair_daily_report_duplicates(self) -> bool:
        rows = self.data.get("daily_reports")
        if not isinstance(rows, list):
            return False
        seen: dict[tuple[str, ...], dict[str, Any]] = {}
        remove_ids: set[int] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = self._daily_report_duplicate_key(row)
            if key is None:
                continue
            existing = seen.get(key)
            if existing is None:
                seen[key] = row
                continue
            keep, drop = self._preferred_daily_report_row(existing, row)
            seen[key] = keep
            self._merge_daily_report_duplicate_metadata(keep, drop)
            remove_ids.add(id(drop))
        if not remove_ids:
            return False
        rows[:] = [row for row in rows if not isinstance(row, dict) or id(row) not in remove_ids]
        return True

    def _daily_report_duplicate_key(self, row: dict[str, Any]) -> tuple[str, ...] | None:
        try:
            project_id = str(int(row.get("project_id", 0) or 0))
        except (TypeError, ValueError):
            return None
        created_at = str(row.get("created_at", "")).strip()
        if not created_at:
            return None
        try:
            created_at = _parse_time(created_at).isoformat(timespec="seconds")
        except ValueError:
            created_at = created_at[:19]
        content = " ".join(str(row.get("content", "")).strip().split())
        if not content:
            return None
        return (
            project_id,
            self._normalize_display_name(str(row.get("member_name", ""))),
            self._normalize_display_name(str(row.get("role", ""))),
            created_at,
            content,
        )

    def _preferred_daily_report_row(
        self,
        left: dict[str, Any],
        right: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        left_score = self._daily_report_row_score(left)
        right_score = self._daily_report_row_score(right)
        if right_score > left_score:
            return right, left
        return left, right

    def _daily_report_row_score(self, row: dict[str, Any]) -> tuple[int, int, int]:
        has_source = 1 if self._row_source_key(row) is not None else 0
        has_todo = 1 if str(row.get("todo_id", "")).strip() else 0
        try:
            row_id = int(row.get("id", 0) or 0)
        except (TypeError, ValueError):
            row_id = 0
        return has_source, has_todo, row_id

    def _merge_daily_report_duplicate_metadata(self, keep: dict[str, Any], drop: dict[str, Any]) -> None:
        if not str(keep.get("todo_id", "")).strip() and str(drop.get("todo_id", "")).strip():
            keep["todo_id"] = str(drop.get("todo_id", "")).strip()
        for key in ("operator", "operator_device_id", "source_device_id", "source_id"):
            if not str(keep.get(key, "")).strip() and str(drop.get(key, "")).strip():
                keep[key] = str(drop.get(key, "")).strip()

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

    def _merge_deleted_records(self, remote_value: Any) -> bool:
        if not isinstance(remote_value, list):
            return False
        tombstones = self.data.setdefault("deleted_records", [])
        existing = {
            key: row
            for row in tombstones
            if isinstance(row, dict) and (key := self._deleted_record_key(row)) is not None
        }
        changed = False
        for row in remote_value:
            if not isinstance(row, dict):
                continue
            key = self._deleted_record_key(row)
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

    def _apply_owner_missing_project_deletions(self, remote_value: Any, owner_info: dict[str, Any]) -> bool:
        if not isinstance(remote_value, list) or not isinstance(owner_info, dict):
            return False
        owner_name = self._remote_owner_actor(owner_info)
        owner_key = self._normalize_display_name(owner_name)
        if not owner_key:
            return False

        remote_sources: set[tuple[str, str]] = set()
        remote_identity_keys: set[tuple[str, str, str]] = set()
        for row in remote_value:
            if not isinstance(row, dict):
                continue
            source = self._row_source_key(row)
            if source is not None:
                remote_sources.add(source)
            if self._normalize_display_name(str(row.get("owner", ""))) == owner_key:
                remote_identity_keys.add(self._project_owner_identity_key(row))

        changed = False
        for row in list(self.data.get("projects", [])):
            if not isinstance(row, dict):
                continue
            if self._normalize_display_name(str(row.get("owner", ""))) != owner_key:
                continue
            source = self._row_source_key(row)
            if source is not None:
                if source in remote_sources:
                    continue
            elif self._project_owner_identity_key(row) in remote_identity_keys:
                continue
            try:
                project_id = int(row.get("id", 0) or 0)
            except (TypeError, ValueError):
                continue
            self._remember_deleted_project(
                row,
                deleted_by=owner_name,
                deleted_by_device_id=str(owner_info.get("origin", "")).strip() or None,
            )
            self._remove_project_rows(project_id)
            changed = True
        return changed

    def _remote_owner_actor(self, owner_info: dict[str, Any]) -> str:
        return str(owner_info.get("actor", "")).strip()

    def _project_owner_identity_key(self, row: dict[str, Any]) -> tuple[str, str, str]:
        return (
            self._normalize_display_name(str(row.get("owner", ""))),
            self._normalize_display_name(str(row.get("name", ""))),
            str(row.get("created_at", "")).strip(),
        )

    def _snapshot_missing_local_shared_rows(self, tables: dict[str, Any]) -> bool:
        deleted_by_table: dict[str, set[tuple[str, str]]] = {}
        remote_deleted_records = tables.get("deleted_records")
        if isinstance(remote_deleted_records, list):
            for row in remote_deleted_records:
                if not isinstance(row, dict):
                    continue
                key = self._deleted_record_key(row)
                if key is None:
                    continue
                table, source_device, source_id = key
                deleted_by_table.setdefault(table, set()).add((source_device, source_id))
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
                if source is not None and source in deleted_by_table.get(table, set()):
                    continue
                if source is not None and (table, "source", source[0], source[1]) in remote_keys:
                    continue
                if self._shared_row_key(table, row) in remote_keys:
                    continue
                return True
        return False

    def _apply_deleted_projects(self, deleted_sources: set[tuple[str, str]] | None = None) -> bool:
        if deleted_sources is None:
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

    def _apply_deleted_records(self, deleted_sources_by_table: dict[str, set[tuple[str, str]]] | None = None) -> bool:
        changed = False
        for table in RECORD_TOMBSTONE_TABLES:
            deleted_sources = (
                deleted_sources_by_table.get(table, set())
                if deleted_sources_by_table is not None
                else self._deleted_record_keys_for_table(table)
            )
            if not deleted_sources:
                continue
            rows = self.data.get(table)
            if not isinstance(rows, list):
                continue
            next_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    next_rows.append(row)
                    continue
                source = self._row_source_key(row)
                if source is not None and source in deleted_sources:
                    changed = True
                    continue
                next_rows.append(row)
            if len(next_rows) != len(rows):
                rows[:] = next_rows
        return changed

    def _deleted_project_keys_from(self, value: Any) -> set[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        if not isinstance(value, list):
            return keys
        for row in value:
            if not isinstance(row, dict):
                continue
            key = self._deleted_project_key(row)
            if key is not None:
                keys.add(key)
        return keys

    def _deleted_project_keys(self) -> set[tuple[str, str]]:
        return self._deleted_project_keys_from(self.data.get("deleted_projects", []))

    def _active_deleted_project_keys(self, remote_keys: set[tuple[str, str]]) -> set[tuple[str, str]]:
        keys = set(remote_keys)
        for row in self.data.get("deleted_projects", []):
            if not isinstance(row, dict) or not self._is_local_deletion_marker(row):
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

    def _deleted_record_keys_for_table(self, table: str) -> set[tuple[str, str]]:
        return self._deleted_record_keys_by_table_from(self.data.get("deleted_records", [])).get(table, set())

    def _active_deleted_record_keys_by_table(
        self,
        remote_keys: dict[str, set[tuple[str, str]]],
    ) -> dict[str, set[tuple[str, str]]]:
        keys_by_table = {table: set(keys) for table, keys in remote_keys.items()}
        for row in self.data.get("deleted_records", []):
            if not isinstance(row, dict) or not self._is_local_deletion_marker(row):
                continue
            key = self._deleted_record_key(row)
            if key is None:
                continue
            table, source_device, source_id = key
            keys_by_table.setdefault(table, set()).add((source_device, source_id))
        return keys_by_table

    def _is_local_deletion_marker(self, row: dict[str, Any]) -> bool:
        deleted_by = str(row.get("deleted_by", "")).strip()
        deleted_by_device_id = str(row.get("deleted_by_device_id", "")).strip()
        return (
            bool(deleted_by and self.is_current_user_name(deleted_by))
            or bool(deleted_by_device_id and deleted_by_device_id == self.device_id())
        )

    def _deleted_record_keys_by_table_from(self, value: Any) -> dict[str, set[tuple[str, str]]]:
        keys_by_table: dict[str, set[tuple[str, str]]] = {}
        if not isinstance(value, list):
            return keys_by_table
        for row in value:
            if not isinstance(row, dict):
                continue
            key = self._deleted_record_key(row)
            if key is None:
                continue
            record_table, source_device, source_id = key
            keys_by_table.setdefault(record_table, set()).add((source_device, source_id))
        return keys_by_table

    def _deleted_record_key(self, row: dict[str, Any]) -> tuple[str, str, str] | None:
        table = str(row.get("table", "")).strip()
        if table not in RECORD_TOMBSTONE_TABLES:
            return None
        source_device = str(row.get("source_device_id") or row.get("deleted_by_device_id") or "").strip()
        source_id = str(row.get("source_id") or row.get("record_id") or "").strip()
        if not source_device or not source_id:
            return None
        return table, source_device, source_id

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
        if table == "deleted_records":
            key = self._deleted_record_key(row)
            if key is not None:
                return (table, key[0], key[1], key[2])
        if "id" in row:
            return (table, str(row.get("id", "")))
        return (table, json.dumps(row, ensure_ascii=False, sort_keys=True))

    def _backup_before_sync(self) -> None:
        if not self.enable_before_sync_backup:
            return
        backup_dir = self.path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backups = sorted(
            backup_dir.glob("szzx-before-sync-*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for expired in backups[BEFORE_SYNC_BACKUP_LIMIT:]:
            try:
                expired.unlink()
            except OSError:
                continue
        backups = backups[:BEFORE_SYNC_BACKUP_LIMIT]
        if backups:
            try:
                newest_created_at = datetime.fromtimestamp(backups[0].stat().st_mtime)
            except OSError:
                newest_created_at = datetime.min
            if datetime.now() - newest_created_at < BEFORE_SYNC_BACKUP_INTERVAL:
                return
        backup_path = backup_dir / f"szzx-before-sync-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        try:
            with backup_path.open("w", encoding="utf-8") as file:
                json.dump(self.data, file, ensure_ascii=False, indent=2)
        except OSError:
            return

    def _restore_document_files(self, tables: dict[str, Any], files: dict[str, Any]) -> bool:
        documents = tables.get("project_documents")
        if not isinstance(documents, list):
            return False
        changed = False
        for row in documents:
            if not isinstance(row, dict):
                continue
            document_id = str(row.get("id", ""))
            payload = files.get(document_id)
            if not isinstance(payload, dict):
                continue
            expected_hash = str(payload.get("sha256", "")).strip()
            current = Path(str(row.get("file_path", "")))
            if (
                expected_hash
                and str(row.get("file_sha256", "")).strip() == expected_hash
                and current.exists()
                and self._document_path_is_inside_library(current)
            ):
                continue
            try:
                content = base64.b64decode(str(payload.get("content", "")))
            except ValueError:
                continue
            # A remote vault blob is encrypted with the remote machine's key
            # and must never be stored as if it were plaintext.
            if content.startswith((DOCUMENT_VAULT_MAGIC, LEGACY_DOCUMENT_VAULT_MAGIC)):
                continue
            if expected_hash and hashlib.sha256(content).hexdigest() != expected_hash:
                continue
            project_id = int(row.get("project_id", 0))
            if current.exists() and self._document_path_is_inside_library(current):
                try:
                    existing = self.document_content(current)
                except (OSError, ValueError):
                    existing = b""
                if expected_hash and hashlib.sha256(existing).hexdigest() == expected_hash:
                    row["file_sha256"] = expected_hash
                    changed = True
                    continue
            try:
                target = self.store_document_content(project_id, content)
            except OSError:
                continue
            if current.exists() and self._document_path_is_inside_library(current):
                try:
                    current.chmod(stat.S_IRUSR | stat.S_IWUSR)
                    current.unlink()
                except OSError:
                    pass
            if row.get("file_path") != str(target):
                row["file_path"] = str(target)
            row["file_sha256"] = expected_hash or hashlib.sha256(content).hexdigest()
            changed = True
        return changed

    def _server_files_are_complete(self, tables: dict[str, Any], files: Any) -> bool:
        if not isinstance(files, dict):
            return False
        documents = tables.get("project_documents")
        if not isinstance(documents, list):
            return False
        document_ids = {
            str(row.get("id", "")).strip()
            for row in documents
            if isinstance(row, dict) and str(row.get("id", "")).strip()
        }
        if not document_ids:
            return True
        return document_ids.issubset(set(files.keys()))

    def _document_path_is_inside_library(self, path: Path) -> bool:
        try:
            path.resolve().relative_to((self.path.parent / "documents").resolve())
        except (OSError, ValueError):
            return False
        return True

    def _prune_unreferenced_document_files(self) -> bool:
        root = self.path.parent / "documents"
        if not root.exists():
            return False
        referenced: set[Path] = set()
        for row in self.data.get("project_documents", []):
            if not isinstance(row, dict):
                continue
            path = Path(str(row.get("file_path", "")))
            if not self._document_path_is_inside_library(path):
                continue
            try:
                referenced.add(path.resolve())
            except OSError:
                continue
        changed = False
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in referenced:
                continue
            try:
                path.chmod(stat.S_IRUSR | stat.S_IWUSR)
                path.unlink()
                changed = True
            except OSError:
                continue
        return changed

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

        created_at = datetime.now()
        row = self._with_operator({
            "id": self._next_id("rest_days", created_at),
            "day": day_text,
            "note": note.strip(),
            "created_at": created_at.isoformat(timespec="seconds"),
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
            self._remember_deleted_record("rest_days", row)
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
