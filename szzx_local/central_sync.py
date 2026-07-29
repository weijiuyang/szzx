from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, QTimer, Signal

from .protocol import DEFAULT_DATA_SERVER_NAME, SERVER_AUTHORITATIVE_HEADER, SERVER_AUTHORITATIVE_VALUE

PULL_INTERVAL_MS = 5000
PULL_INTERVAL_SECONDS = PULL_INTERVAL_MS / 1000


@dataclass(frozen=True)
class CentralDataServer:
    name: str
    address: str
    port: int
    url: str
    last_seen: float


class CentralDataSync(QObject):
    data_synced = Signal()
    server_changed = Signal(object)
    _snapshot_received = Signal(object)
    _sync_failed = Signal(str)

    def __init__(
        self,
        db: Any,
        server_name: str | None = None,
        server_url: str | None = None,
        bootstrap_snapshot: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.db = db
        self.server_name = (server_name or os.environ.get("SZZX_DATA_SERVER_NAME") or DEFAULT_DATA_SERVER_NAME).strip()
        configured_url = server_url or os.environ.get("SZZX_DATA_SERVER_URL") or db.get_setting("data_server_url")
        self.server_url = self._normalize_url(configured_url or "")
        self.current_server: CentralDataServer | None = None
        self.auth_token = self._saved_auth_token(self.server_url)
        self._busy = False
        self._pending = False
        self._pending_push = False
        self._server_ready = False
        self._pending_sync_path = self._resolve_pending_sync_path()
        self._local_dirty = self._pending_sync_exists()
        self._active_mode = "pull"
        self._bootstrap_snapshot = bootstrap_snapshot if isinstance(bootstrap_snapshot, dict) else None
        self._bootstrap_files_uploaded = False
        self._last_success = 0.0
        self._snapshot_received.connect(self._apply_server_snapshot)
        self._sync_failed.connect(self._handle_sync_failed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync_now)
        self.db.add_after_save_callback(self._after_db_save)

    def start(self) -> None:
        self.timer.start(PULL_INTERVAL_MS)
        QTimer.singleShot(600, self.sync_now)

    def set_discovered_server(self, server: object) -> None:
        if not isinstance(server, CentralDataServer):
            return
        if not self._server_name_matches(server.name):
            return
        self.current_server = server
        self.server_url = server.url
        self.auth_token = self._saved_auth_token(self.server_url)
        self.db.set_setting("data_server_url", self.server_url, save=True)
        self.server_changed.emit(server)
        if self.auth_token:
            self.sync_now()

    def login(self, username: str, password: str) -> dict[str, Any]:
        if not self.server_url:
            raise ValueError("尚未发现数据服务器")
        payload = json.dumps({"username": username, "password": password}, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.server_url}/auth/login",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read(64 * 1024).decode("utf-8"))
        if not isinstance(result, dict) or not result.get("token"):
            raise ValueError("服务器登录响应无效")
        self.auth_token = str(result["token"])
        self._save_auth_token(self.server_url, self.auth_token)
        self.db.set_setting("display_name", str(result.get("username", username)).strip(), save=False)
        self.db.set_setting("display_name_locked", "false", save=False)
        self.db.save_local_settings()
        return result

    def validate_saved_session(self) -> bool:
        if not self.server_url or not self.auth_token:
            return False
        request = Request(
            f"{self.server_url}/auth/session",
            headers=self._auth_headers(),
            method="GET",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read(64 * 1024).decode("utf-8"))
        return isinstance(result, dict) and result.get("ok") is True

    def change_account(self, current_password: str, username: str, new_password: str | None = None) -> str:
        values: dict[str, str] = {
            "current_password": current_password,
            "username": username,
        }
        if new_password is not None:
            values["new_password"] = new_password
        payload = json.dumps(values, ensure_ascii=False).encode("utf-8")
        try:
            result = self._admin_request("/auth/account", data=payload)
        except HTTPError as exc:
            if exc.code != 404:
                raise
            if username.strip() != self.db.display_name().strip():
                raise ValueError("当前数据服务器版本较旧，升级服务器后才能修改账户名。") from exc
            if new_password is None:
                raise ValueError("当前数据服务器版本较旧，请先升级服务器。") from exc
            legacy_payload = json.dumps({
                "current_password": current_password,
                "new_password": new_password,
            }, ensure_ascii=False).encode("utf-8")
            result = self._admin_request("/auth/password", data=legacy_payload)
        if result.get("token"):
            self.auth_token = str(result["token"])
            self._save_auth_token(self.server_url, self.auth_token)
        return str(result.get("username", username)).strip()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.auth_token}"} if self.auth_token else {}

    def _saved_auth_tokens(self) -> dict[str, str]:
        try:
            value = json.loads(self.db.get_setting("data_server_auth_tokens") or "{}")
        except (json.JSONDecodeError, TypeError):
            value = {}
        return {str(url): str(token) for url, token in value.items()} if isinstance(value, dict) else {}

    def _saved_auth_token(self, server_url: str) -> str:
        return self._saved_auth_tokens().get(self._normalize_url(server_url), "")

    def _save_auth_token(self, server_url: str, token: str) -> None:
        normalized_url = self._normalize_url(server_url)
        if not normalized_url or not token:
            return
        tokens = self._saved_auth_tokens()
        tokens[normalized_url] = token
        self.db.set_setting("data_server_auth_tokens", json.dumps(tokens, ensure_ascii=False))

    def sync_now(self, push_first: bool = False) -> None:
        if not self.server_url:
            return
        if self._local_dirty and not self._server_ready:
            # Establish the server baseline first, then immediately upload the
            # locally preserved changes. This also handles app/server restarts.
            self._pending = True
            self._pending_push = True
        if self._busy:
            if push_first:
                self._local_dirty = True
                self._pending_push = True
            self._pending = True
            return
        mode = "push" if self._server_ready and (push_first or self._local_dirty) else "pull"
        if mode == "pull" and self._last_success and time.monotonic() - self._last_success < PULL_INTERVAL_SECONDS:
            return
        self._busy = True
        self._active_mode = mode
        thread = threading.Thread(target=self._sync_worker, args=(self.server_url, mode), daemon=True)
        thread.start()

    def _after_db_save(self, bump_sync: bool) -> None:
        if not bump_sync:
            return
        self._push_local_changes_now()

    def mark_local_dirty(self) -> None:
        self._push_local_changes_now()

    def _push_local_changes_now(self) -> None:
        """Push a local save immediately, or immediately after server setup/pending I/O."""
        self._local_dirty = True
        self._write_pending_sync_marker()
        if not self.server_url:
            return
        if not self._server_ready:
            # The first pull establishes the authoritative server baseline.
            # Queue the push now so it runs as soon as that pull completes.
            self._pending = True
            self._pending_push = True
            self.sync_now()
            return
        self.sync_now(push_first=True)

    def _resolve_pending_sync_path(self) -> Path | None:
        db_path = getattr(self.db, "path", None)
        if db_path is None:
            return None
        try:
            return Path(db_path).with_name(".pending-server-sync")
        except TypeError:
            return None

    def _pending_sync_exists(self) -> bool:
        return self._pending_sync_path is not None and self._pending_sync_path.exists()

    def _write_pending_sync_marker(self) -> None:
        path = self._pending_sync_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(time.time_ns()), encoding="utf-8")
        except OSError:
            # The database itself remains the source of truth; snapshot
            # comparison on the next successful pull is the fallback.
            pass

    def _clear_pending_sync_marker(self) -> None:
        path = self._pending_sync_path
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def list_server_backups(self) -> list[dict[str, Any]]:
        payload = self._admin_request("/backups")
        backups = payload.get("backups")
        return [item for item in backups if isinstance(item, dict)] if isinstance(backups, list) else []

    def restore_server_backup(self, backup_name: str) -> dict[str, Any]:
        payload = json.dumps({"backup": backup_name}, ensure_ascii=False).encode("utf-8")
        result = self._admin_request("/restore", data=payload)
        self._server_ready = False
        self._local_dirty = False
        self._last_success = 0.0
        return result

    def preview_server_backup(self, backup_name: str) -> dict[str, Any]:
        payload = json.dumps({"backup": backup_name}, ensure_ascii=False).encode("utf-8")
        return self._admin_request("/backup-preview", data=payload, timeout=30, max_bytes=100 * 1024 * 1024)

    def summarize_weekly(self, content: str) -> str:
        payload = json.dumps({"content": content}, ensure_ascii=False).encode("utf-8")
        result = self._admin_request("/ai/weekly-summary", data=payload, timeout=90)
        summary = str(result.get("summary", "")).strip()
        if not summary:
            raise ValueError("服务器没有返回整理结果")
        return summary

    def send_yesterday_daily_reports(self) -> dict[str, Any]:
        return self._admin_request(
            "/dingtalk/daily-reports/send-yesterday",
            data=b"{}",
            timeout=45,
        )

    def _admin_request(
        self,
        path: str,
        data: bytes | None = None,
        timeout: int = 10,
        max_bytes: int = 10 * 1024 * 1024,
    ) -> dict[str, Any]:
        if not self.server_url:
            raise ValueError("尚未发现数据服务器")
        request = Request(
            f"{self.server_url}{path}",
            data=data,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-SZZX-Actor": quote(str(self.db.display_name()), safe=""),
                "X-SZZX-Origin": str(self.db.device_id()),
                **self._auth_headers(),
            },
            method="POST" if data is not None else "GET",
        )
        with urlopen(request, timeout=timeout) as response:
            body = response.read(max_bytes)
        result = json.loads(body.decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("服务器返回的数据无效")
        return result

    def _server_name_matches(self, name: str) -> bool:
        expected = self.server_name.strip()
        actual = name.strip()
        if not expected:
            return True
        return expected == actual or expected in actual or actual in expected

    def _sync_worker(
        self,
        server_url: str,
        mode: str,
        snapshot_override: dict[str, Any] | None = None,
    ) -> None:
        try:
            if mode == "push":
                snapshot = snapshot_override or self.db.shared_snapshot(include_files=True)
                payload = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
                request = Request(
                    f"{server_url}/snapshot",
                    data=payload,
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        SERVER_AUTHORITATIVE_HEADER: SERVER_AUTHORITATIVE_VALUE,
                        "X-SZZX-Actor": quote(str(self.db.display_name()), safe=""),
                        "X-SZZX-Origin": str(self.db.device_id()),
                        **self._auth_headers(),
                    },
                    method="POST",
                )
            else:
                request = Request(
                    f"{server_url}/snapshot",
                    headers={
                        "X-SZZX-Actor": quote(str(self.db.display_name()), safe=""),
                        "X-SZZX-Origin": str(self.db.device_id()),
                        **self._auth_headers(),
                    },
                    method="GET",
                )
            with urlopen(request, timeout=30) as response:
                body = response.read(500 * 1024 * 1024)
            server_snapshot = json.loads(body.decode("utf-8"))
            if not isinstance(server_snapshot, dict):
                raise ValueError("server snapshot is invalid")
        except (OSError, HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            self._sync_failed.emit(str(exc))
            return
        self._snapshot_received.emit(server_snapshot)

    def _apply_server_snapshot(self, snapshot: object) -> None:
        self._busy = False
        changed = False
        if isinstance(snapshot, dict):
            self._server_ready = True
            is_ack = snapshot.get("ok") is True and "tables" not in snapshot
            if not is_ack:
                needs_public_link_backfill = self.db.snapshot_missing_local_public_project_links(snapshot)
                changed = self.db.apply_shared_snapshot(snapshot, force=True)
                if needs_public_link_backfill:
                    self._local_dirty = True
                    self._pending = True
                    self._pending_push = True
                if not self._bootstrap_files_uploaded and self._post_bootstrap_files(snapshot):
                    self._bootstrap_files_uploaded = True
                    self._pending = True
            if self._active_mode == "push":
                # A save may have happened while this upload was in flight. In
                # that case the queued follow-up push still owns the marker.
                if self._pending_push:
                    self._local_dirty = True
                else:
                    self._local_dirty = False
                    self._clear_pending_sync_marker()
        self._last_success = time.monotonic()
        if changed:
            self.data_synced.emit()
        if self._pending:
            pending_push = self._pending_push
            self._pending = False
            self._pending_push = False
            self.sync_now(push_first=pending_push)

    def _handle_sync_failed(self, message: str) -> None:
        self._busy = False
        # Keep the durable dirty marker and retry on the regular sync tick.
        # Avoid a tight retry loop while the server is powered off.
        self._pending = False
        self._pending_push = False

    def _post_bootstrap_files(self, server_snapshot: dict[str, Any]) -> bool:
        bootstrap = self._bootstrap_snapshot
        self._bootstrap_snapshot = None
        if not isinstance(bootstrap, dict) or not self.server_url:
            return False
        bootstrap_files = bootstrap.get("files")
        if not isinstance(bootstrap_files, dict) or not bootstrap_files:
            return False
        tables = server_snapshot.get("tables")
        if not isinstance(tables, dict):
            return False
        server_documents = tables.get("project_documents")
        if not isinstance(server_documents, list):
            return False
        server_files = server_snapshot.get("files") if isinstance(server_snapshot.get("files"), dict) else {}
        missing_files: dict[str, Any] = {}
        for row in server_documents:
            if not isinstance(row, dict):
                continue
            document_id = str(row.get("id", ""))
            if not document_id or document_id in server_files or document_id not in bootstrap_files:
                continue
            missing_files[document_id] = bootstrap_files[document_id]
        if not missing_files:
            return False
        hydrate_snapshot = dict(server_snapshot)
        hydrate_snapshot["files"] = missing_files
        self._busy = True
        self._active_mode = "push"
        thread = threading.Thread(
            target=self._sync_worker,
            args=(self.server_url, "push", hydrate_snapshot),
            daemon=True,
        )
        thread.start()
        return True

    def _normalize_url(self, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value:
            return ""
        if not value.startswith(("http://", "https://")):
            value = f"http://{value}"
        return value
