from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .database import Database, _platform_app_dir
from .protocol import (
    APP_PROTOCOL,
    DEFAULT_DATA_SERVER_NAME,
    DEFAULT_DATA_SERVER_PORT,
    DISCOVERY_SERVER_KIND,
    LAN_PORT,
    SERVER_AUTHORITATIVE_HEADER,
    SERVER_AUTHORITATIVE_VALUE,
)
from .version import APP_VERSION
from .dingtalk_bot import start_requirement_bot


def _ipv4_broadcast_interfaces() -> list[tuple[str, str]]:
    """Return active broadcast-capable interfaces as (address, broadcast)."""
    if sys.platform == "win32":
        # Windows does not expose getifaddrs. The limited broadcast fallback in
        # _announce_once remains available there.
        return []

    class IfAddrs(ctypes.Structure):
        pass

    IfAddrsPointer = ctypes.POINTER(IfAddrs)
    IfAddrs._fields_ = [
        ("ifa_next", IfAddrsPointer),
        ("ifa_name", ctypes.c_char_p),
        ("ifa_flags", ctypes.c_uint),
        ("ifa_addr", ctypes.c_void_p),
        ("ifa_netmask", ctypes.c_void_p),
        ("ifa_broadcast", ctypes.c_void_p),
        ("ifa_data", ctypes.c_void_p),
    ]

    libc = ctypes.CDLL(None)
    getifaddrs = libc.getifaddrs
    getifaddrs.argtypes = [ctypes.POINTER(IfAddrsPointer)]
    getifaddrs.restype = ctypes.c_int
    freeifaddrs = libc.freeifaddrs
    freeifaddrs.argtypes = [IfAddrsPointer]

    head = IfAddrsPointer()
    if getifaddrs(ctypes.byref(head)) != 0:
        return []
    interfaces: set[tuple[str, str]] = set()
    try:
        current = head
        while current:
            item = current.contents
            flags = item.ifa_flags
            # IFF_UP | IFF_BROADCAST, excluding loopback and point-to-point.
            if (
                item.ifa_addr
                and item.ifa_broadcast
                and flags & 0x1
                and flags & 0x2
                and not flags & 0x18
            ):
                if sys.platform == "darwin":
                    family = ctypes.c_ubyte.from_address(item.ifa_addr + 1).value
                else:
                    family = ctypes.c_ushort.from_address(item.ifa_addr).value
                if family == socket.AF_INET:
                    address = socket.inet_ntoa(ctypes.string_at(item.ifa_addr + 4, 4))
                    broadcast = socket.inet_ntoa(ctypes.string_at(item.ifa_broadcast + 4, 4))
                    interfaces.add((address, broadcast))
            current = item.ifa_next
    finally:
        freeifaddrs(head)
    return sorted(interfaces)


class DataService:
    def __init__(self, db: Database, name: str, port: int) -> None:
        self.db = db
        self.name = name.strip() or DEFAULT_DATA_SERVER_NAME
        self.port = port
        self.device_id = f"server-{uuid.uuid4().hex}"
        self.lock = threading.RLock()
        self._stopped = threading.Event()
        self._ai_lock = threading.Lock()
        self._ensure_ai_config()

    @property
    def ai_config_path(self) -> Path:
        return self.db.path.parent / "ai_config.json"

    def _ensure_ai_config(self) -> None:
        if self.ai_config_path.exists():
            return
        self.ai_config_path.parent.mkdir(parents=True, exist_ok=True)
        config = {
            "api_url": "https://api.openai.com/v1/chat/completions",
            "model": "your-model-name",
            "prompt": (
                "你是一名中文工作周报编辑。请整理用户提供的本周记录，保留事实和项目分组，"
                "合并重复内容，突出完成事项、推进情况、问题风险和后续计划。不要编造信息，"
                "不要添加日期或时间，直接输出可继续编辑和保存的周报正文。"
            ),
        }
        self.ai_config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def summarize_weekly(self, content: str, actor: str) -> dict[str, Any]:
        api_key = os.environ.get("SZZX_AI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("server AI API key is not configured")
        actor_key = " ".join(actor.strip().split()).casefold()
        if not actor_key:
            raise ValueError("AI request actor is required")
        content = content.strip()
        if not content or len(content) > 100_000:
            raise ValueError("invalid weekly content")
        config_path = self.ai_config_path
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError(f"server AI config does not exist: {config_path}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"server AI config is invalid: {config_path}") from exc
        if not isinstance(config, dict):
            raise RuntimeError("server AI config must be a JSON object")
        prompt = str(config.get("prompt", "")).strip()
        api_url = str(config.get("api_url", "")).strip()
        model = str(config.get("model", "")).strip()
        if not api_url:
            raise RuntimeError("server AI API URL is not configured")
        if not model:
            raise RuntimeError("server AI model is not configured")
        if not prompt:
            raise RuntimeError("server AI prompt is not configured")
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
        }, ensure_ascii=False).encode("utf-8")
        request = Request(
            api_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        if not self._ai_lock.acquire(blocking=False):
            raise RuntimeError("server AI is busy")
        try:
            week_key = (datetime.now().date() - timedelta(days=datetime.now().weekday())).isoformat()
            usage_setting = "weekly_ai_usage"
            try:
                usage = json.loads(self.db.get_setting(usage_setting) or "{}")
            except json.JSONDecodeError:
                usage = {}
            if not isinstance(usage, dict):
                usage = {}
            actor_usage = usage.get(actor_key)
            if not isinstance(actor_usage, dict) or actor_usage.get("week") != week_key:
                actor_usage = {"week": week_key, "count": 0}
            count = int(actor_usage.get("count", 0) or 0)
            if count >= 5:
                raise PermissionError("weekly AI limit reached (5/5)")
            with urlopen(request, timeout=75) as response:
                raw = response.read(10 * 1024 * 1024)
            result = json.loads(raw.decode("utf-8"))
            choices = result.get("choices") if isinstance(result, dict) else None
            if not isinstance(choices, list) or not choices:
                raise RuntimeError("AI response has no choices")
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            summary = str(message.get("content", "")).strip() if isinstance(message, dict) else ""
            if not summary:
                raise RuntimeError("AI response is empty")
            actor_usage["count"] = count + 1
            usage[actor_key] = actor_usage
            self.db.set_setting(usage_setting, json.dumps(usage, ensure_ascii=False))
            return {"ok": True, "summary": summary, "remaining": 4 - count}
        except PermissionError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"AI request failed: {exc}") from exc
        finally:
            self._ai_lock.release()

    def start_announcing(self) -> None:
        thread = threading.Thread(target=self._announce_loop, daemon=True)
        thread.start()

    def start_backups(self) -> None:
        self.ensure_daily_backup()
        thread = threading.Thread(target=self._backup_loop, daemon=True)
        thread.start()

    @property
    def backup_dir(self) -> Path:
        return self.db.path.parent / "Backups"

    def ensure_daily_backup(self) -> None:
        with self.lock:
            target = self.backup_dir / f"daily-{datetime.now():%Y-%m-%d}.zip"
            if not target.exists():
                self._create_backup(target)
            daily_backups = sorted(self.backup_dir.glob("daily-*.zip"), reverse=True)
            for expired in daily_backups[30:]:
                try:
                    expired.unlink()
                except OSError:
                    continue

    def list_backups(self, actor: str, origin: str) -> dict[str, Any]:
        if not self._is_restore_admin(actor, origin):
            raise PermissionError("restore access denied")
        with self.lock:
            self.ensure_daily_backup()
            backups = []
            for path in sorted(self.backup_dir.glob("*.zip"), reverse=True):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                backups.append({
                    "name": path.name,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    "size": stat.st_size,
                    "kind": "回滚前保护" if path.name.startswith("before-restore-") else "每日备份",
                })
            return {"ok": True, "backups": backups}

    def restore_backup(self, backup_name: str, actor: str, origin: str) -> dict[str, Any]:
        if not self._is_restore_admin(actor, origin):
            raise PermissionError("restore access denied")
        safe_name = Path(backup_name).name
        if safe_name != backup_name or not safe_name.endswith(".zip"):
            raise ValueError("invalid backup name")
        with self.lock:
            source = self.backup_dir / safe_name
            if not source.is_file():
                raise FileNotFoundError("backup not found")
            safety = self.backup_dir / f"before-restore-{datetime.now():%Y%m%d-%H%M%S}.zip"
            self._create_backup(safety)
            current_revision = int(self.db.sync_state().get("revision", 0))
            with tempfile.TemporaryDirectory(prefix="szzx-restore-") as temp_dir:
                temp_root = Path(temp_dir)
                with zipfile.ZipFile(source) as archive:
                    archive.extractall(temp_root)
                database_path = temp_root / "database.json"
                try:
                    restored = json.loads(database_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise ValueError("backup database is invalid") from exc
                if not isinstance(restored, dict):
                    raise ValueError("backup database is invalid")
                restored_sync = restored.setdefault("sync", {})
                if not isinstance(restored_sync, dict):
                    restored_sync = {}
                    restored["sync"] = restored_sync
                restored_sync["revision"] = max(current_revision, int(restored_sync.get("revision", 0)))

                documents_dir = self.db.path.parent / "documents"
                restored_documents = temp_root / "documents"
                if documents_dir.exists():
                    shutil.rmtree(documents_dir)
                if restored_documents.exists():
                    shutil.copytree(restored_documents, documents_dir)
                self.db.data = restored
                self.db._migrate()
                self.db._save()
            return {
                "ok": True,
                "restored": safe_name,
                "safety_backup": safety.name,
                "sync": self.db.sync_state(),
                "record_counts": self.db.shared_record_counts(),
            }

    def preview_backup(self, backup_name: str, actor: str, origin: str) -> dict[str, Any]:
        if not self._is_restore_admin(actor, origin):
            raise PermissionError("restore access denied")
        safe_name = Path(backup_name).name
        if safe_name != backup_name or not safe_name.endswith(".zip"):
            raise ValueError("invalid backup name")
        with self.lock:
            source = self.backup_dir / safe_name
            if not source.is_file():
                raise FileNotFoundError("backup not found")
            try:
                with zipfile.ZipFile(source) as archive:
                    backup_data = json.loads(archive.read("database.json").decode("utf-8"))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
                raise ValueError("backup database is invalid") from exc
            if not isinstance(backup_data, dict):
                raise ValueError("backup database is invalid")
            return {
                "ok": True,
                "backup": safe_name,
                "backup_json": backup_data,
                "current_json": self.db.data,
            }

    def _create_backup(self, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(self.db.path, "database.json")
                documents_dir = self.db.path.parent / "documents"
                if documents_dir.exists():
                    for path in documents_dir.rglob("*"):
                        if path.is_file():
                            archive.write(path, path.relative_to(self.db.path.parent).as_posix())
                archive.writestr(
                    "manifest.json",
                    json.dumps({
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                        "sync": self.db.sync_state(),
                        "record_counts": self.db.shared_record_counts(),
                    }, ensure_ascii=False, indent=2),
                )
            temp.replace(target)
        finally:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass

    def _is_restore_admin(self, actor: str, origin: str) -> bool:
        normalized = " ".join(actor.strip().split()).casefold()
        if normalized != "尉久洋" or not origin.strip():
            return False
        for row in self.db.data.get("name_claims", []):
            if not isinstance(row, dict):
                continue
            row_name = " ".join(str(row.get("name", "")).strip().split()).casefold()
            if row_name == normalized and str(row.get("device_id", "")).strip() == origin.strip():
                return True
        return False

    def _backup_loop(self) -> None:
        while not self._stopped.wait(60 * 60):
            try:
                self.ensure_daily_backup()
            except OSError:
                continue

    def snapshot(self, actor: str = "", origin: str = "") -> dict[str, Any]:
        with self.lock:
            return self.db.shared_snapshot(
                include_files=True,
                personalized=False,
                project_notes_actor=actor,
                redact_project_notes=True,
            )

    def merge_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.db.apply_shared_snapshot(snapshot, force=True)
            return {
                "ok": True,
                "sync": self.db.sync_state(),
                "record_counts": self.db.shared_record_counts(),
            }

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
        sync = self.db.sync_state()
        payload = {
            "protocol": APP_PROTOCOL,
            "kind": DISCOVERY_SERVER_KIND,
            "device_id": self.device_id,
            "name": self.name,
            "data_port": self.port,
            "app_version": APP_VERSION,
            "sync": {
                "revision": sync.get("revision", 0),
                "updated_at": sync.get("updated_at", ""),
            },
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        interfaces = _ipv4_broadcast_interfaces()
        sent = False
        for address, broadcast in interfaces:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                try:
                    udp.bind((address, 0))
                    udp.sendto(data, (broadcast, LAN_PORT))
                    sent = True
                except OSError:
                    continue
        if sent:
            return
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                udp.sendto(data, ("255.255.255.255", LAN_PORT))
            except OSError:
                return


class DataServiceHandler(BaseHTTPRequestHandler):
    server_version = "SZZXDataService/0.2"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(self.service.health())
            return
        if self.path == "/snapshot":
            self._send_json(self.service.snapshot(self._request_actor(), self._request_origin()))
            return
        if self.path == "/backups":
            try:
                payload = self.service.list_backups(self._request_actor(), self._request_origin())
            except PermissionError:
                self.send_error(403, "restore access denied")
                return
            self._send_json(payload)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/ai/weekly-summary":
            try:
                payload = self._read_json_body(max_length=200 * 1024)
                result = self.service.summarize_weekly(
                    str(payload.get("content", "")),
                    self._request_actor(),
                )
            except ValueError:
                self.send_error(400, "invalid weekly content")
                return
            except PermissionError:
                self.send_error(429, "weekly AI limit reached (5/5)")
                return
            except RuntimeError as exc:
                self.send_error(503, str(exc))
                return
            self._send_json(result)
            return
        if self.path == "/restore":
            try:
                payload = self._read_json_body(max_length=1024 * 1024)
                backup_name = str(payload.get("backup", ""))
                result = self.service.restore_backup(backup_name, self._request_actor(), self._request_origin())
            except PermissionError:
                self.send_error(403, "restore access denied")
                return
            except FileNotFoundError:
                self.send_error(404, "backup not found")
                return
            except (ValueError, OSError, zipfile.BadZipFile):
                self.send_error(400, "invalid backup")
                return
            self._send_json(result)
            return
        if self.path == "/backup-preview":
            try:
                payload = self._read_json_body(max_length=1024 * 1024)
                result = self.service.preview_backup(
                    str(payload.get("backup", "")),
                    self._request_actor(),
                    self._request_origin(),
                )
            except PermissionError:
                self.send_error(403, "restore access denied")
                return
            except FileNotFoundError:
                self.send_error(404, "backup not found")
                return
            except ValueError:
                self.send_error(400, "invalid backup")
                return
            self._send_json(result)
            return
        if self.path != "/snapshot":
            self.send_error(404)
            return
        if self.headers.get(SERVER_AUTHORITATIVE_HEADER, "") != SERVER_AUTHORITATIVE_VALUE:
            self.send_error(409, "client must pull the authoritative server snapshot before pushing")
            return
        try:
            snapshot = self._read_json_body(max_length=500 * 1024 * 1024)
        except ValueError:
            self.send_error(400, "invalid json")
            return
        if not isinstance(snapshot, dict):
            self.send_error(400, "snapshot must be an object")
            return
        self._send_json(self.service.merge_snapshot(snapshot))

    def _read_json_body(self, max_length: int) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if length <= 0 or length > max_length:
            raise ValueError("invalid content length")
        try:
            payload = self.rfile.read(length)
            result = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid json") from exc
        if not isinstance(result, dict):
            raise ValueError("json must be an object")
        return result

    @property
    def service(self) -> DataService:
        return self.server.service  # type: ignore[attr-defined]

    def _request_actor(self) -> str:
        return unquote(self.headers.get("X-SZZX-Actor", "").strip())

    def _request_origin(self) -> str:
        return self.headers.get("X-SZZX-Origin", "").strip()

    def _send_json(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

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
    logging.basicConfig(
        level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="Run the SZZX central LAN data service.")
    parser.add_argument("--host", default=os.environ.get("SZZX_DATA_SERVER_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SZZX_DATA_SERVER_PORT", DEFAULT_DATA_SERVER_PORT)))
    parser.add_argument("--name", default=os.environ.get("SZZX_DATA_SERVER_NAME", DEFAULT_DATA_SERVER_NAME))
    parser.add_argument("--data", type=Path, default=default_server_db_path())
    parser.add_argument("--reset-data", action="store_true", help="Back up and clear all shared records in the server database before starting.")
    args = parser.parse_args(argv)

    db = Database(path=args.data, enable_before_sync_backup=True)
    if args.reset_data:
        if args.data.exists():
            backup = args.data.with_name(f"{args.data.stem}.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}{args.data.suffix}")
            backup.write_bytes(args.data.read_bytes())
            print(f"Backed up server database to: {backup}")
        db.clear_shared_data_cache()
    service = DataService(db, args.name, args.port)
    start_requirement_bot(db)
    service.start_backups()
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
