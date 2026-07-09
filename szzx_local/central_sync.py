from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, QTimer, Signal

from .protocol import DEFAULT_DATA_SERVER_NAME, SERVER_AUTHORITATIVE_HEADER, SERVER_AUTHORITATIVE_VALUE


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
        self._busy = False
        self._pending = False
        self._server_ready = False
        self._local_dirty = False
        self._active_mode = "pull"
        self._bootstrap_snapshot = bootstrap_snapshot if isinstance(bootstrap_snapshot, dict) else None
        self._bootstrap_files_uploaded = False
        self._last_success = 0.0
        self._snapshot_received.connect(self._apply_server_snapshot)
        self._sync_failed.connect(self._handle_sync_failed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync_now)
        self.push_timer = QTimer(self)
        self.push_timer.setSingleShot(True)
        self.push_timer.timeout.connect(lambda: self.sync_now(push_first=True))
        self.db.add_after_save_callback(self._after_db_save)

    def start(self) -> None:
        self.timer.start(7000)
        QTimer.singleShot(600, self.sync_now)

    def set_discovered_server(self, server: object) -> None:
        if not isinstance(server, CentralDataServer):
            return
        if not self._server_name_matches(server.name):
            return
        self.current_server = server
        self.server_url = server.url
        self.db.set_setting("data_server_url", self.server_url, save=True)
        self.server_changed.emit(server)
        self.sync_now()

    def sync_now(self, push_first: bool = False) -> None:
        if not self.server_url:
            return
        if self._busy:
            self._pending = True
            return
        self._busy = True
        mode = "push" if self._server_ready and (push_first or self._local_dirty) else "pull"
        self._active_mode = mode
        snapshot = self.db.shared_snapshot(include_files=True) if mode == "push" else None
        thread = threading.Thread(target=self._sync_worker, args=(self.server_url, snapshot, mode), daemon=True)
        thread.start()

    def _after_db_save(self, bump_sync: bool) -> None:
        if not bump_sync or not self._server_ready:
            return
        self._local_dirty = True
        self.push_timer.start(800)

    def _server_name_matches(self, name: str) -> bool:
        expected = self.server_name.strip()
        actual = name.strip()
        if not expected:
            return True
        return expected == actual or expected in actual or actual in expected

    def _sync_worker(self, server_url: str, snapshot: dict[str, Any] | None, mode: str) -> None:
        try:
            if mode == "push" and snapshot is not None:
                payload = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
                request = Request(
                    f"{server_url}/snapshot",
                    data=payload,
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        SERVER_AUTHORITATIVE_HEADER: SERVER_AUTHORITATIVE_VALUE,
                    },
                    method="POST",
                )
            else:
                request = Request(f"{server_url}/snapshot", method="GET")
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
            changed = self.db.replace_shared_snapshot(snapshot)
            self._server_ready = True
            if not self._bootstrap_files_uploaded and self._post_bootstrap_files(snapshot):
                self._bootstrap_files_uploaded = True
                self._pending = True
            if self._active_mode == "push":
                self._local_dirty = False
        self._last_success = time.monotonic()
        if changed:
            self.data_synced.emit()
        if self._pending:
            self._pending = False
            self.sync_now(push_first=self._server_ready)

    def _handle_sync_failed(self, message: str) -> None:
        self._busy = False
        if self._pending:
            self._pending = False
            self.sync_now(push_first=True)

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
        thread = threading.Thread(target=self._sync_worker, args=(self.server_url, hydrate_snapshot, "push"), daemon=True)
        thread.start()
        return True

    def _normalize_url(self, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value:
            return ""
        if not value.startswith(("http://", "https://")):
            value = f"http://{value}"
        return value
