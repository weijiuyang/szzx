from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .database import Database


DEFAULT_DINGTALK_CONFIG: dict[str, Any] = {
    "requirement_bot": {
        "app_key": "",
        "app_secret": "",
        "bot_name": "需求搜集机器人",
    },
    "daily_report_bot": {
        "app_key": "",
        "app_secret": "",
        "robot_code": "",
    },
}


def dingtalk_config_path(db: Database) -> Path:
    return db.path.parent / "dingtalk_config.json"


def load_dingtalk_config(db: Database) -> dict[str, Any]:
    path = dingtalk_config_path(db)
    loaded: dict[str, Any] = json.loads(json.dumps(DEFAULT_DINGTALK_CONFIG))
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                loaded = value
        except (OSError, json.JSONDecodeError):
            return loaded

    # 旧部署首次升级时，把当前环境变量中的两套凭证迁移进持久文件。
    environment_values = {
        "requirement_bot": {
            "app_key": os.environ.get("DINGTALK_CLIENT_ID", "").strip(),
            "app_secret": os.environ.get("DINGTALK_CLIENT_SECRET", "").strip(),
            "bot_name": os.environ.get("DINGTALK_BOT_NAME", "").strip(),
        },
        "daily_report_bot": {
            "app_key": os.environ.get("DINGTALK_DAILY_CLIENT_ID", "").strip(),
            "app_secret": os.environ.get("DINGTALK_DAILY_CLIENT_SECRET", "").strip(),
            "robot_code": os.environ.get("DINGTALK_DAILY_ROBOT_CODE", "").strip(),
        },
    }
    changed = not path.exists()
    for section, defaults in DEFAULT_DINGTALK_CONFIG.items():
        current = loaded.get(section)
        if not isinstance(current, dict):
            current = {}
            loaded[section] = current
            changed = True
        for key, default in defaults.items():
            if key not in current:
                current[key] = default
                changed = True
            migrated = str(environment_values[section].get(key, "")).strip()
            if migrated and not str(current.get(key, "")).strip():
                current[key] = migrated
                changed = True
    if changed:
        path.write_text(json.dumps(loaded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return loaded


def bot_credentials(db: Database, section: str) -> dict[str, str]:
    config = load_dingtalk_config(db)
    values = config.get(section)
    values = values if isinstance(values, dict) else {}
    if section == "requirement_bot":
        return {
            "app_key": str(values.get("app_key", "")).strip() or os.environ.get("DINGTALK_CLIENT_ID", "").strip(),
            "app_secret": str(values.get("app_secret", "")).strip() or os.environ.get("DINGTALK_CLIENT_SECRET", "").strip(),
            "bot_name": str(values.get("bot_name", "")).strip() or os.environ.get("DINGTALK_BOT_NAME", "需求搜集机器人").strip(),
        }
    return {
        "app_key": str(values.get("app_key", "")).strip() or os.environ.get("DINGTALK_DAILY_CLIENT_ID", "").strip(),
        "app_secret": str(values.get("app_secret", "")).strip() or os.environ.get("DINGTALK_DAILY_CLIENT_SECRET", "").strip(),
        "robot_code": str(values.get("robot_code", "")).strip() or os.environ.get("DINGTALK_DAILY_ROBOT_CODE", "").strip(),
    }
