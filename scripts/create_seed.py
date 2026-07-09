from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path


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
    "activity_events",
    "name_claims",
    "deleted_projects",
    "deleted_records",
    "counters",
)
ACTIVITY_EVENT_SYNC_DAYS = 0
PROJECT_CHILD_TABLES = (
    "project_members",
    "daily_reports",
    "project_weekly_reports",
    "project_decks",
    "project_documents",
    "project_todos",
)
RECORD_TOMBSTONE_TABLES = {
    "project_members",
    "daily_reports",
    "project_weekly_reports",
    "project_decks",
    "project_documents",
    "project_todos",
    "rest_days",
}


def load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def row_source_key(row: dict) -> tuple[str, str] | None:
    source_device = str(row.get("source_device_id") or row.get("operator_device_id") or "").strip()
    source_id = str(row.get("source_id") or row.get("id") or "").strip()
    if not source_device or not source_id:
        return None
    return source_device, source_id


def deleted_project_key(row: dict) -> tuple[str, str] | None:
    source_device = str(row.get("source_device_id") or row.get("deleted_by_device_id") or "").strip()
    source_id = str(row.get("source_id") or row.get("project_id") or "").strip()
    if not source_device or not source_id:
        return None
    return source_device, source_id


def deleted_record_key(row: dict) -> tuple[str, str, str] | None:
    table = str(row.get("table", "")).strip()
    if table not in RECORD_TOMBSTONE_TABLES:
        return None
    source_device = str(row.get("source_device_id") or row.get("deleted_by_device_id") or "").strip()
    source_id = str(row.get("source_id") or row.get("record_id") or "").strip()
    if not source_device or not source_id:
        return None
    return table, source_device, source_id


def project_id(row: dict) -> int | None:
    try:
        return int(row.get("project_id", 0) or 0)
    except (TypeError, ValueError):
        return None


def cleaned_shared_data(data: dict) -> dict:
    cleaned = json.loads(json.dumps(data, ensure_ascii=False))
    deleted_projects = {
        key
        for row in cleaned.get("deleted_projects", [])
        if isinstance(row, dict) and (key := deleted_project_key(row)) is not None
    }
    if deleted_projects and isinstance(cleaned.get("projects"), list):
        removed_project_ids: set[int] = set()
        next_projects = []
        for row in cleaned["projects"]:
            if not isinstance(row, dict):
                next_projects.append(row)
                continue
            source = row_source_key(row)
            if source is not None and source in deleted_projects:
                try:
                    removed_project_ids.add(int(row.get("id", 0) or 0))
                except (TypeError, ValueError):
                    pass
                continue
            next_projects.append(row)
        cleaned["projects"] = next_projects
        for table in PROJECT_CHILD_TABLES:
            rows = cleaned.get(table)
            if not isinstance(rows, list):
                continue
            cleaned[table] = [
                row
                for row in rows
                if not isinstance(row, dict) or project_id(row) not in removed_project_ids
            ]

    deleted_records: dict[str, set[tuple[str, str]]] = {}
    for row in cleaned.get("deleted_records", []):
        if not isinstance(row, dict):
            continue
        key = deleted_record_key(row)
        if key is None:
            continue
        table, source_device, source_id = key
        deleted_records.setdefault(table, set()).add((source_device, source_id))
    for table, keys in deleted_records.items():
        rows = cleaned.get(table)
        if not isinstance(rows, list):
            continue
        cleaned[table] = [
            row
            for row in rows
            if not isinstance(row, dict) or row_source_key(row) not in keys
        ]
    return cleaned


def score(path: Path, data: dict) -> tuple[int, str, int, int, int, int]:
    sync = data.get("sync") if isinstance(data.get("sync"), dict) else {}
    projects = data.get("projects") if isinstance(data.get("projects"), list) else []
    members = data.get("project_members") if isinstance(data.get("project_members"), list) else []
    todos = data.get("project_todos") if isinstance(data.get("project_todos"), list) else []
    reports = data.get("daily_reports") if isinstance(data.get("daily_reports"), list) else []
    try:
        stat = path.stat()
    except OSError:
        return (0, "", 0, 0, 0, 0)
    return (
        int(sync.get("revision", 0) or 0),
        str(sync.get("updated_at", "")),
        len(projects),
        len(members) + len(todos) + len(reports),
        int(stat.st_mtime),
        int(stat.st_size),
    )


def platform_app_db() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "SZZXLocalDesk" / "szzx.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SZZXLocalDesk" / "szzx.json"
    return Path.home() / ".local" / "share" / "SZZXLocalDesk" / "szzx.json"


def recent_activity_events(rows: object) -> list[dict]:
    if ACTIVITY_EVENT_SYNC_DAYS <= 0:
        return []
    if not isinstance(rows, list):
        return []
    cutoff = datetime.now().timestamp() - ACTIVITY_EVENT_SYNC_DAYS * 24 * 60 * 60
    recent: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            created_at = datetime.fromisoformat(str(row.get("created_at", ""))).timestamp()
        except ValueError:
            continue
        if created_at >= cutoff:
            recent.append(dict(row))
    return recent


def candidate_paths() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("SZZX_SEED_DB_PATH", "").strip()
    if override:
        candidates.append(Path(override))
    candidates.extend(
        [
            platform_app_db(),
            Path.cwd() / "local_data" / "szzx.json",
        ]
    )
    return candidates


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/create_seed.py <output-dir>", file=sys.stderr)
        return 2
    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)

    best_path: Path | None = None
    best_data: dict | None = None
    best_score = (0, "", 0, 0, 0, 0)
    for candidate in candidate_paths():
        data = load_json(candidate)
        if data is None:
            continue
        data = cleaned_shared_data(data)
        candidate_score = score(candidate, data)
        if candidate_score > best_score:
            best_path = candidate
            best_data = data
            best_score = candidate_score

    if best_path is None or best_data is None or best_score[2] == 0:
        print("No shared data seed was bundled.")
        return 0

    tables: dict[str, object] = {}
    for table in SHARED_TABLES:
        value = best_data.get(table)
        if table == "counters":
            tables[table] = dict(value) if isinstance(value, dict) else {}
        elif table == "activity_events":
            tables[table] = recent_activity_events(value)
        else:
            tables[table] = list(value) if isinstance(value, list) else []
    sync = best_data.get("sync") if isinstance(best_data.get("sync"), dict) else {}
    settings = best_data.get("settings") if isinstance(best_data.get("settings"), dict) else {}
    seed = {
        "kind": "szzx_shared_seed",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_path": str(best_path),
        "sync": sync,
        "owner": {
            "actor": str(sync.get("actor") or settings.get("display_name") or ""),
            "origin": str(sync.get("origin") or settings.get("device_id") or ""),
        },
        "tables": tables,
    }
    target = output_dir / "szzx_seed.json"
    target.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Bundled shared data seed from {best_path} ({best_score[2]} projects).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
