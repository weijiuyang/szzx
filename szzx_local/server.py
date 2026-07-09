from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .database import Database, _platform_app_dir
from .protocol import (
    APP_PROTOCOL,
    DEFAULT_DATA_SERVER_NAME,
    DEFAULT_DATA_SERVER_PORT,
    DISCOVERY_SERVER_KIND,
    LAN_PORT,
)
from .version import APP_VERSION


class DataService:
    def __init__(self, db: Database, name: str, port: int) -> None:
        self.db = db
        self.name = name.strip() or DEFAULT_DATA_SERVER_NAME
        self.port = port
        self.device_id = f"server-{uuid.uuid4().hex}"
        self.lock = threading.RLock()
        self._stopped = threading.Event()

    def start_announcing(self) -> None:
        thread = threading.Thread(target=self._announce_loop, daemon=True)
        thread.start()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return self.db.shared_snapshot(include_files=False)

    def merge_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.db.apply_shared_snapshot(snapshot, force=True)
            return self.db.shared_snapshot(include_files=False)

    def health(self) -> dict[str, Any]:
        with self.lock:
            return {
                "ok": True,
                "name": self.name,
                "version": APP_VERSION,
                "port": self.port,
                "sync": self.db.sync_state(),
                "record_counts": self.db.shared_record_counts(),
            }

    def _announce_loop(self) -> None:
        while not self._stopped.is_set():
            self._announce_once()
            self._stopped.wait(2.5)

    def _announce_once(self) -> None:
        payload = {
            "protocol": APP_PROTOCOL,
            "kind": DISCOVERY_SERVER_KIND,
            "device_id": self.device_id,
            "name": self.name,
            "data_port": self.port,
            "app_version": APP_VERSION,
            "sync": self.db.sync_state(),
            "record_counts": self.db.shared_record_counts(),
            "project_fingerprints": self.db.shared_project_fingerprints(),
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp.sendto(data, ("255.255.255.255", LAN_PORT))


class DataServiceHandler(BaseHTTPRequestHandler):
    server_version = "SZZXDataService/0.2"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(self.service.health())
            return
        if self.path == "/snapshot":
            self._send_json(self.service.snapshot())
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/snapshot":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "invalid content length")
            return
        if length <= 0 or length > 120 * 1024 * 1024:
            self.send_error(413, "snapshot too large")
            return
        try:
            payload = self.rfile.read(length)
            snapshot = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400, "invalid json")
            return
        if not isinstance(snapshot, dict):
            self.send_error(400, "snapshot must be an object")
            return
        self._send_json(self.service.merge_snapshot(snapshot))

    @property
    def service(self) -> DataService:
        return self.server.service  # type: ignore[attr-defined]

    def _send_json(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return


class SZZXDataHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], service: DataService) -> None:
        super().__init__(address, handler)
        self.service = service


def default_server_db_path() -> Path:
    override = os.environ.get("SZZX_DATA_SERVER_DATA_DIR", "").strip()
    base = Path(override) if override else _platform_app_dir() / "DataServer"
    return base / "szzx_server.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SZZX central LAN data service.")
    parser.add_argument("--host", default=os.environ.get("SZZX_DATA_SERVER_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SZZX_DATA_SERVER_PORT", DEFAULT_DATA_SERVER_PORT)))
    parser.add_argument("--name", default=os.environ.get("SZZX_DATA_SERVER_NAME", DEFAULT_DATA_SERVER_NAME))
    parser.add_argument("--data", type=Path, default=default_server_db_path())
    args = parser.parse_args(argv)

    db = Database(path=args.data)
    service = DataService(db, args.name, args.port)
    service.start_announcing()
    httpd = SZZXDataHTTPServer((args.host, args.port), DataServiceHandler, service)
    print(f"SZZX data service '{service.name}' listening on {args.host}:{args.port}")
    print(f"Database: {args.data}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
