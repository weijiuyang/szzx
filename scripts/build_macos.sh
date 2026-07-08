#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
export PYINSTALLER_CONFIG_DIR="$ROOT_DIR/.pyinstaller-cache"
MACOS_TARGET_ARCH="${MACOS_TARGET_ARCH:-universal2}"

PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version="$($candidate - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
PY
)"
    if [[ "$version" != 3.13* ]]; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3.12/3.11/3.10 is required for packaging. Install the official macOS Python from https://www.python.org/downloads/macos/ and rerun this script."
  exit 1
fi

if [ -x ".venv/bin/python" ]; then
  venv_version="$(.venv/bin/python - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
  if [[ "$venv_version" == "3.13" ]]; then
    echo "Recreating .venv because Python 3.13 is not recommended for packaging."
    rm -rf .venv
  fi
fi

if [ ! -x ".venv/bin/python" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
.venv/bin/python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org pyinstaller

for path in build dist; do
  if [ -e "$path" ]; then
    chflags -R nouchg,nohidden "$path" 2>/dev/null || true
  fi
done
rm -rf build dist 2>/dev/null || true
for path in build dist; do
  if [ -e "$path" ]; then
    chflags -R nouchg,nohidden "$path" 2>/dev/null || true
    find "$path" -mindepth 1 -maxdepth 1 -exec chflags -R nouchg,nohidden {} \; -exec rm -rf {} \; 2>/dev/null || true
    rm -rf "$path" 2>/dev/null || true
  fi
done
rm -rf .packaging-assets
mkdir -p .packaging-assets/assets .packaging-assets/seed
rsync -a \
  --exclude '.DS_Store' \
  --exclude '*.mp4' \
  szzx_local/assets/ .packaging-assets/assets/
.venv/bin/python - <<'PY'
from __future__ import annotations

import json
import os
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


candidates: list[Path] = []
override = os.environ.get("SZZX_SEED_DB_PATH", "").strip()
if override:
    candidates.append(Path(override))
candidates.extend(
    [
        Path.home() / "Library" / "Application Support" / "SZZXLocalDesk" / "szzx.json",
        Path.cwd() / "local_data" / "szzx.json",
    ]
)

best_path: Path | None = None
best_data: dict | None = None
best_score = (0, 0, 0, 0, 0)
for candidate in candidates:
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
else:
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
    target = Path(".packaging-assets") / "seed" / "szzx_seed.json"
    target.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Bundled shared data seed from {best_path} ({best_score[0]} projects).")
PY
.venv/bin/pyinstaller \
  --noconfirm \
  --windowed \
  --name SZZXLocalDesk \
  --osx-bundle-identifier com.szzx.localdesk \
  --target-architecture "$MACOS_TARGET_ARCH" \
  --add-data ".packaging-assets/assets:szzx_local/assets" \
  --add-data ".packaging-assets/seed:szzx_local/seed" \
  --clean \
  run.py
rm -rf .packaging-assets

APP_PLIST="dist/SZZXLocalDesk.app/Contents/Info.plist"
if [ -f "$APP_PLIST" ]; then
  /usr/libexec/PlistBuddy -c "Set :NSLocalNetworkUsageDescription 数智中心需要访问本地网络，用于发现在线同事并同步项目数据。" "$APP_PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :NSLocalNetworkUsageDescription string 数智中心需要访问本地网络，用于发现在线同事并同步项目数据。" "$APP_PLIST"
fi

if SZZX_LOCAL_DATA_DIR="$ROOT_DIR/.smoke-data" \
  QT_QPA_PLATFORM=offscreen \
  dist/SZZXLocalDesk.app/Contents/MacOS/SZZXLocalDesk --smoke-test; then
  echo "Packaged app smoke test passed."
else
  echo "Packaged app smoke test did not pass on this machine. Continuing to create the DMG."
  echo "For broad distribution on macOS, sign and notarize with an Apple Developer ID."
fi

rm -f dist/SZZXLocalDesk-mac.dmg
if hdiutil create \
  -volname "数智中心" \
  -srcfolder dist/SZZXLocalDesk.app \
  -ov \
  -format UDZO \
  -fs HFS+ \
  dist/SZZXLocalDesk-mac.dmg; then
  echo "Built dist/SZZXLocalDesk-mac.dmg"
else
  echo "Built dist/SZZXLocalDesk.app"
  echo "DMG creation failed. You can still distribute the .app, or run hdiutil create manually."
  exit 0
fi

echo "Built dist/SZZXLocalDesk.app"
