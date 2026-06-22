from __future__ import annotations

import json
import os
import ssl
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from .update_config import DEFAULT_UPDATE_URL
from .version import APP_VERSION


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

    payload = _load_update_manifest(manifest_url)

    latest_version = str(payload.get("version", "")).strip()
    download_url = str(payload.get("download_url", "")).strip()
    notes = str(payload.get("notes", "")).strip()
    if not latest_version or not download_url:
        raise ValueError("更新配置缺少 version 或 download_url。")

    return UpdateInfo(
        latest_version=latest_version,
        download_url=download_url,
        notes=notes,
        is_newer=version_tuple(latest_version) > version_tuple(APP_VERSION),
    )


def version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for item in version.strip().lstrip("v").split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits or "0"))
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def _load_update_manifest(manifest_url: str) -> dict[str, object]:
    try:
        return _read_update_manifest(manifest_url)
    except URLError as exc:
        if _is_certificate_verify_error(exc):
            try:
                return _read_update_manifest(manifest_url, verify_ssl=False)
            except Exception as retry_exc:
                raise ValueError(_friendly_update_error(retry_exc)) from retry_exc
        raise ValueError(_friendly_update_error(exc)) from exc
    except Exception as exc:
        raise ValueError(_friendly_update_error(exc)) from exc


def _read_update_manifest(manifest_url: str, verify_ssl: bool = True) -> dict[str, object]:
    context = None if verify_ssl else ssl._create_unverified_context()
    with urlopen(manifest_url, timeout=8, context=context) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("更新配置格式不正确。")
    return payload


def _is_certificate_verify_error(exc: BaseException) -> bool:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    return "CERTIFICATE_VERIFY_FAILED" in str(exc)


def _friendly_update_error(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        if exc.code in (403, 401):
            return "更新地址未授权访问。请确认更新文件允许访问。"
        if exc.code == 404:
            return "没有找到更新配置。请确认更新配置文件已经放好。"
        return f"更新服务返回 HTTP {exc.code}。请稍后再试。"

    text = str(exc)
    if "CERTIFICATE_VERIFY_FAILED" in text or "self-signed certificate" in text:
        return "更新地址的 HTTPS 证书校验失败。请检查当前网络代理/证书，或换一个网络后重试。"
    if "Tunnel connection failed" in text:
        return "当前网络代理无法连接更新地址。请关闭代理或换一个网络后重试。"
    if "timed out" in text.lower():
        return "检查更新超时。请确认网络可访问更新地址后重试。"
    return f"检查更新失败：{text}"
