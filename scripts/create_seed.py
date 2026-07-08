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


def load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def score(path: Path, data: dict) -> tuple[int, int, int, int, int]:
    sync = data.get("sync") if isinstance(data.get("sync"), dict) else {}
    projects = data.get("projects") if isinstance(data.get("projects"), list) else []
    members = data.get("project_members") if isinstance(data.get("project_members"), list) else []
    todos = data.get("project_todos") if isinstance(data.get("project_todos"), list) else []
    reports = data.get("daily_reports") if isinstance(data.get("daily_reports"), list) else []
    try:
        stat = path.stat()
    except OSError:
        return (0, 0, 0, 0, 0)
    return (
        len(projects),
        len(members) + len(todos) + len(reports),
        int(sync.get("revision", 0) or 0),
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
    best_score = (0, 0, 0, 0, 0)
    for candidate in candidate_paths():
        data = load_json(candidate)
        if data is None:
            continue
        candidate_score = score(candidate, data)
        if candidate_score > best_score:
            best_path = candidate
            best_data = data
            best_score = candidate_score

    if best_path is None or best_data is None or best_score[0] == 0:
        print("No shared data seed was bundled.")
        return 0

    tables: dict[str, object] = {}
    for table in SHARED_TABLES:
        value = best_data.get(table)
        if table == "counters":
            tables[table] = dict(value) if isinstance(value, dict) else {}
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
    print(f"Bundled shared data seed from {best_path} ({best_score[0]} projects).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
