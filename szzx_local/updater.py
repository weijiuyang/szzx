from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.request import urlopen

from .version import APP_VERSION


DEFAULT_UPDATE_URL = ""
UPDATE_URL_ENV = "SZZX_UPDATE_URL"


@dataclass(frozen=True)
class UpdateInfo:
    latest_version: str
    download_url: str
    notes: str
    is_newer: bool


def configured_update_url() -> str:
    return os.environ.get(UPDATE_URL_ENV, DEFAULT_UPDATE_URL).strip()


def check_for_update(url: str | None = None) -> UpdateInfo:
    manifest_url = (url or configured_update_url()).strip()
    if not manifest_url:
        raise ValueError(f"未配置更新地址。请设置环境变量 {UPDATE_URL_ENV}。")

    with urlopen(manifest_url, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))

    latest_version = str(payload.get("version", "")).strip()
    download_url = str(payload.get("download_url", "")).strip()
    notes = str(payload.get("notes", "")).strip()
    if not latest_version or not download_url:
        raise ValueError("更新配置缺少 version 或 download_url。")

    return UpdateInfo(
        latest_version=latest_version,
        download_url=download_url,
        notes=notes,
        is_newer=_version_tuple(latest_version) > _version_tuple(APP_VERSION),
    )


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for item in version.strip().lstrip("v").split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts)

