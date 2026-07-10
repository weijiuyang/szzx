from __future__ import annotations

import json
import os
import socket
import struct
import sys
import threading
import time
import zipfile
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QNetworkDatagram, QNetworkInterface, QUdpSocket

from .changelog import CHANGELOG, current_release_notes
from .central_sync import CentralDataServer
from .protocol import APP_PROTOCOL, DISCOVERY_SERVER_KIND, LAN_PORT, SYNC_TCP_PORT
from .updater import version_tuple
from .version import APP_VERSION


SNAPSHOT_MAGIC = b"SZZXSNAP1\n"
SNAPSHOT_MAGIC_V2 = b"SZZXSNAP2\n"
PEER_MAGIC = b"SZZXPEER1\n"
PACKAGE_MAGIC = b"SZZXPKG01\n"
PACKAGE_ENV = "SZZX_UPDATE_PACKAGE"


@dataclass(frozen=True)
class LanPeer:
    device_id: str
    name: str
    address: str
    last_seen: datetime
    sync_port: int
    sync: dict[str, Any]
    app_version: str
    platform: str
    update_package: dict[str, Any]
    record_counts: dict[str, int]
    project_fingerprints: dict[str, dict[str, str]]
    today_project_logs: list[dict[str, Any]]


class LanDiscovery(QObject):
    peers_changed = Signal(list)
    data_synced = Signal()
    data_server_seen = Signal(object)
    _snapshot_fetched = Signal(object, object, bool)
    _snapshot_failed = Signal(object)
    _direct_peer_seen = Signal(object)

    def __init__(
        self,
        device_id: str,
        display_name: str,
        port: int = LAN_PORT,
        db: Any | None = None,
        peer_data_sync_enabled: bool = True,
    ) -> None:
        super().__init__()
        self.device_id = device_id
        self.display_name = display_name
        self.port = port
        self.sync_port = port + 1
        self.db = db
        self.peers: dict[str, LanPeer] = {}
        self.server_socket: socket.socket | None = None
        self.peer_data_sync_enabled = peer_data_sync_enabled
        self.update_package_path = self._find_update_package()
        self._pulling_peer_ids: set[str] = set()
        self._last_pull_started: dict[str, float] = {}
        self.direct_peer_addresses: list[str] = []

        self.listen_socket = QUdpSocket(self)
        self.send_socket = QUdpSocket(self)
        bind_flags = (
            QUdpSocket.BindFlag.ShareAddress
            | QUdpSocket.BindFlag.ReuseAddressHint
        )
        self.is_bound = self.listen_socket.bind(
            QHostAddress.SpecialAddress.AnyIPv4,
            self.port,
            bind_flags,
        )
        self.listen_socket.readyRead.connect(self._read_pending)

        self.announce_timer = QTimer(self)
        self.announce_timer.timeout.connect(self.announce)

        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self.broadcast_database)

        self.sweep_timer = QTimer(self)
        self.sweep_timer.timeout.connect(self._sweep)
        self._snapshot_fetched.connect(self._apply_fetched_snapshot)
        self._snapshot_failed.connect(self._finish_snapshot_pull)
        self._direct_peer_seen.connect(self._apply_direct_peer_seen)

    def start(self) -> None:
        if self.peer_data_sync_enabled or self.update_package_path is not None:
            self._start_snapshot_server()
        self.announce_burst()
        self.announce_timer.start(3500)
        if self.peer_data_sync_enabled:
            self.sync_timer.start(8000)
        self.sweep_timer.start(5000)

    def set_display_name(self, name: str) -> None:
        self.display_name = name.strip() or self.display_name
        self.announce()

    def set_direct_peer_addresses(self, addresses: list[str]) -> None:
        self.direct_peer_addresses = []
        for address in addresses:
            address = address.strip()
            if address and address not in self.direct_peer_addresses:
                self.direct_peer_addresses.append(address)
        self.announce_burst()
        self._poll_direct_peers()

    def _presence_payload(self, kind: str = "presence", direct_reply: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "protocol": APP_PROTOCOL,
            "kind": kind,
            "device_id": self.device_id,
            "name": self.display_name,
            "sync_port": self.sync_port,
            "sync": self.db.sync_state() if self.db is not None else {},
            "app_version": APP_VERSION,
            "platform": sys.platform,
            "update_package": self._update_package_info(compact=not self.peer_data_sync_enabled),
            "record_counts": (
                self.db.shared_record_counts()
                if self.db is not None and self.peer_data_sync_enabled
                else {}
            ),
            "project_fingerprints": (
                self.db.shared_project_fingerprints()
                if self.db is not None and self.peer_data_sync_enabled
                else {}
            ),
            "today_project_logs": self._today_project_logs(),
        }
        if kind == "presence":
            payload["port"] = self.port
        if direct_reply:
            payload["direct_reply"] = True
        return payload

    def announce(self) -> None:
        self._send_broadcast_payload(self._presence_payload("presence"))

    def announce_burst(self) -> None:
        self.announce()
        if self.peer_data_sync_enabled:
            self.broadcast_database()
        QTimer.singleShot(250, self.announce)
        if self.peer_data_sync_enabled:
            QTimer.singleShot(500, self.broadcast_database)
        QTimer.singleShot(900, self.announce)

    def broadcast_database(self) -> None:
        if self.db is None:
            return
        self._send_broadcast_payload(self._presence_payload("db_state"))
        self._poll_direct_peers()
        self._pull_newer_peer_snapshots()

    def _send_broadcast_payload(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_broadcast(data)

    def _send_broadcast(self, data: bytes) -> None:
        for address in self._broadcast_targets():
            self.send_socket.writeDatagram(data, address, self.port)
        for address in self.direct_peer_addresses:
            self.send_socket.writeDatagram(data, QHostAddress(address), self.port)

    def _send_direct_presence_reply(self, address: QHostAddress) -> None:
        data = json.dumps(self._presence_payload("presence", direct_reply=True), ensure_ascii=False).encode("utf-8")
        self.send_socket.writeDatagram(data, address, self.port)

    def _poll_direct_peers(self) -> None:
        for address in self.direct_peer_addresses:
            thread = threading.Thread(target=self._fetch_direct_peer_worker, args=(address,), daemon=True)
            thread.start()

    def _fetch_direct_peer_worker(self, address: str) -> None:
        try:
            peer = self._fetch_peer_info(address, self.sync_port)
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return
        self._direct_peer_seen.emit(peer)

    def _fetch_peer_info(self, address: str, sync_port: int) -> LanPeer:
        with socket.create_connection((address, sync_port), timeout=1.5) as client:
            client.settimeout(3)
            client.sendall(PEER_MAGIC)
            size = struct.unpack("!I", self._recv_exact(client, 4))[0]
            if size <= 0 or size > 64 * 1024:
                raise ValueError("peer info size is invalid")
            payload = json.loads(self._recv_exact(client, size).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("peer info is invalid")
        return self._peer_from_payload(payload, address)

    def _broadcast_targets(self) -> list[QHostAddress]:
        targets: dict[str, QHostAddress] = {}

        def add(address: QHostAddress) -> None:
            text = address.toString()
            if text and text not in {"0.0.0.0", "127.0.0.1"}:
                targets[text] = address

        add(QHostAddress(QHostAddress.SpecialAddress.Broadcast))
        for interface in QNetworkInterface.allInterfaces():
            flags = interface.flags()
            if not flags & QNetworkInterface.InterfaceFlag.IsUp:
                continue
            if flags & QNetworkInterface.InterfaceFlag.IsLoopBack:
                continue
            for entry in interface.addressEntries():
                ip = entry.ip()
                if ip.protocol() != QAbstractSocket.NetworkLayerProtocol.IPv4Protocol:
                    continue
                broadcast = entry.broadcast()
                if not broadcast.isNull():
                    add(broadcast)
                inferred = self._infer_class_c_broadcast(ip.toString())
                if inferred is not None:
                    add(inferred)
        return list(targets.values())

    def _infer_class_c_broadcast(self, address: str) -> QHostAddress | None:
        parts = address.split(".")
        if len(parts) != 4:
            return None
        try:
            values = [int(part) for part in parts]
        except ValueError:
            return None
        if values[0] in {0, 127} or any(value < 0 or value > 255 for value in values):
            return None
        return QHostAddress(f"{values[0]}.{values[1]}.{values[2]}.255")

    def _start_snapshot_server(self) -> None:
        if self.server_socket is not None:
            return
        if self.db is None and self.update_package_path is None:
            return
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("", self.sync_port))
            server.listen(5)
        except OSError:
            return
        self.server_socket = server
        thread = threading.Thread(target=self._serve_snapshots, daemon=True)
        thread.start()

    def _serve_snapshots(self) -> None:
        while self.server_socket is not None:
            try:
                client, _ = self.server_socket.accept()
            except OSError:
                return
            threading.Thread(target=self._handle_snapshot_client, args=(client,), daemon=True).start()

    def _handle_snapshot_client(self, client: socket.socket) -> None:
        with client:
            client.settimeout(3)
            try:
                request = self._recv_exact(client, len(SNAPSHOT_MAGIC))
                if request == PACKAGE_MAGIC:
                    self._send_update_package(client)
                    return
                if request == PEER_MAGIC:
                    data = json.dumps(self._presence_payload("presence"), ensure_ascii=False).encode("utf-8")
                    client.sendall(struct.pack("!I", len(data)))
                    client.sendall(data)
                    return
                if request not in {SNAPSHOT_MAGIC, SNAPSHOT_MAGIC_V2} or self.db is None or not self.peer_data_sync_enabled:
                    return
                requester = self._snapshot_requester(client) if request == SNAPSHOT_MAGIC_V2 else ""
                data = zlib.compress(
                    json.dumps(
                        self.db.shared_snapshot(
                            project_notes_actor=requester,
                            redact_project_notes=True,
                        ),
                        ensure_ascii=False,
                    ).encode("utf-8")
                )
                client.sendall(struct.pack("!Q", len(data)))
                client.sendall(data)
            except OSError:
                return

    def _snapshot_requester(self, client: socket.socket) -> str:
        try:
            header = self._recv_exact(client, 4)
            size = struct.unpack("!I", header)[0]
            if size <= 0 or size > 4096:
                return ""
            payload = json.loads(self._recv_exact(client, size).decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return ""
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("actor", "")).strip()

    def _find_update_package(self) -> Path | None:
        override = os.environ.get(PACKAGE_ENV, "").strip()
        candidates: list[Path] = []
        if override:
            candidates.append(Path(override))

        cwd = Path.cwd()
        executable = Path(sys.executable)
        if sys.platform == "win32":
            candidates.extend([
                cwd / "dist" / "SZZXLocalDesk.exe",
                executable,
            ])
        elif sys.platform == "darwin":
            app_bundle = executable.parents[2] if len(executable.parents) >= 3 else executable.parent
            candidates.extend([
                cwd / "dist" / "SZZXLocalDesk-mac.dmg",
                cwd / "dist" / "SZZXLocalDesk.app.zip",
                app_bundle.parent / "SZZXLocalDesk-mac.dmg",
                app_bundle.parent / "SZZXLocalDesk.app.zip",
                Path.home() / "Downloads" / "SZZXLocalDesk-mac.dmg",
                Path.home() / "Downloads" / "SZZXLocalDesk.app.zip",
            ])
        else:
            candidates.extend([
                cwd / "dist" / "SZZXLocalDesk",
                executable,
            ])

        for path in candidates:
            try:
                if path.is_file() and path.stat().st_size > 0:
                    return path
            except OSError:
                continue
        if sys.platform == "darwin":
            return self._create_macos_app_zip(executable)
        return None

    def _create_macos_app_zip(self, executable: Path) -> Path | None:
        if not getattr(sys, "frozen", False):
            return None
        app_bundle = self._macos_app_bundle(executable)
        if app_bundle is None or not app_bundle.is_dir():
            return None
        target_dir = Path.home() / "Library" / "Application Support" / "SZZXLocalDesk" / "updates"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"SZZXLocalDesk-v{APP_VERSION}-mac.app.zip"
        if target.is_file() and target.stat().st_size > 0:
            return target
        tmp_target = target.with_suffix(".tmp")
        try:
            if tmp_target.exists():
                tmp_target.unlink()
            with zipfile.ZipFile(tmp_target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in app_bundle.rglob("*"):
                    if path.is_dir():
                        continue
                    archive.write(path, path.relative_to(app_bundle.parent))
            tmp_target.replace(target)
        except OSError:
            return None
        return target if target.is_file() and target.stat().st_size > 0 else None

    def _macos_app_bundle(self, executable: Path) -> Path | None:
        for parent in executable.parents:
            if parent.suffix == ".app":
                return parent
        return None

    def _update_package_info(self, compact: bool = False) -> dict[str, Any]:
        path = self.update_package_path
        if path is None:
            return {}
        try:
            stat = path.stat()
        except OSError:
            return {}
        info = {
            "name": path.name,
            "size": stat.st_size,
            "version": APP_VERSION,
            "platform": sys.platform,
            "notes": current_release_notes(),
        }
        if not compact:
            info["changelog"] = CHANGELOG
        return info

    def _today_project_logs(self) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        logs: list[dict[str, Any]] = []
        for item in self.db.today_project_logs(self.display_name):
            content = str(item.get("content", "")).strip()
            logs.append(
                {
                    "project_name": str(item.get("project_name", "未知项目")),
                    "member_name": str(item.get("member_name", self.display_name)),
                    "role": str(item.get("role", "")),
                    "content": content[:260],
                    "created_at": str(item.get("created_at", "")),
                }
            )
        return logs[:12]

    def _send_update_package(self, client: socket.socket) -> None:
        path = self.update_package_path
        if path is None or not path.is_file():
            client.sendall(struct.pack("!Q", 0))
            return
        info = self._update_package_info()
        metadata = json.dumps(info, ensure_ascii=False).encode("utf-8")
        client.sendall(struct.pack("!Q", len(metadata)))
        client.sendall(metadata)
        client.sendall(struct.pack("!Q", int(info.get("size", 0))))
        with path.open("rb") as file:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                client.sendall(chunk)

    def _read_pending(self) -> None:
        changed = False
        while self.listen_socket.hasPendingDatagrams():
            datagram = self.listen_socket.receiveDatagram()
            if self._accept_datagram(datagram):
                changed = True
        if changed:
            self.peers_changed.emit(self.sorted_peers())

    def _accept_datagram(self, datagram: QNetworkDatagram) -> bool:
        try:
            payload = json.loads(bytes(datagram.data()).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False

        if payload.get("protocol") != APP_PROTOCOL:
            return False

        kind = payload.get("kind")
        if kind == DISCOVERY_SERVER_KIND:
            self.data_server_seen.emit(self._data_server_from_payload(payload, datagram.senderAddress().toString()))
            return False

        device_id = str(payload.get("device_id") or "")
        if not device_id or device_id == self.device_id:
            return False

        if kind not in {"presence", "db_state"}:
            return False

        address = datagram.senderAddress().toString()
        if datagram.senderAddress().protocol() == QAbstractSocket.NetworkLayerProtocol.IPv6Protocol:
            return False
        peer = self._peer_from_payload(payload, address)
        self.peers[device_id] = peer
        if not bool(payload.get("direct_reply")):
            self._send_direct_presence_reply(datagram.senderAddress())
        if kind == "db_state" and self.peer_data_sync_enabled:
            self._pull_peer_snapshot_if_newer(peer)
        return True

    def _data_server_from_payload(self, payload: dict[str, Any], address: str) -> CentralDataServer:
        try:
            port = int(payload.get("data_port") or 0)
        except (TypeError, ValueError):
            port = 0
        if port <= 0:
            port = self.sync_port + 1
        name = str(payload.get("name") or "数据服务")
        return CentralDataServer(
            name=name,
            address=address,
            port=port,
            url=f"http://{address}:{port}",
            last_seen=time.monotonic(),
        )

    def _peer_from_payload(self, payload: dict[str, Any], address: str) -> LanPeer:
        sync = payload.get("sync")
        if not isinstance(sync, dict):
            sync = {}
        try:
            sync_port = int(payload.get("sync_port") or self.sync_port)
        except (TypeError, ValueError):
            sync_port = self.sync_port
        return LanPeer(
            device_id=str(payload.get("device_id") or ""),
            name=str(payload.get("name") or "未命名"),
            address=address,
            last_seen=datetime.now(),
            sync_port=sync_port,
            sync=sync,
            app_version=str(payload.get("app_version") or ""),
            platform=str(payload.get("platform") or ""),
            update_package=payload.get("update_package") if isinstance(payload.get("update_package"), dict) else {},
            record_counts=payload.get("record_counts") if isinstance(payload.get("record_counts"), dict) else {},
            project_fingerprints=(
                payload.get("project_fingerprints")
                if isinstance(payload.get("project_fingerprints"), dict)
                else {}
            ),
            today_project_logs=(
                payload.get("today_project_logs")
                if isinstance(payload.get("today_project_logs"), list)
                else []
            ),
        )

    def _apply_direct_peer_seen(self, peer: object) -> None:
        if not isinstance(peer, LanPeer) or not peer.device_id or peer.device_id == self.device_id:
            return
        self.peers[peer.device_id] = peer
        self.peers_changed.emit(self.sorted_peers())
        if self.peer_data_sync_enabled:
            self._pull_peer_snapshot_if_newer(peer)

    def _pull_newer_peer_snapshots(self) -> None:
        for peer in list(self.peers.values()):
            self._pull_peer_snapshot_if_newer(peer)

    def request_peer_snapshot_refresh(self) -> int:
        if not self.peer_data_sync_enabled:
            return 0
        started_count = 0
        for peer in list(self.peers.values()):
            if self._start_snapshot_pull(peer, force=False, bypass_throttle=True):
                started_count += 1
        return started_count

    def _pull_peer_snapshot_if_newer(self, peer: LanPeer) -> None:
        if self.db is None:
            return
        if (
            (not peer.sync or not self.db.remote_sync_is_newer(peer.sync))
            and not self._peer_may_have_missing_shared_rows(peer)
            and not self._peer_may_have_project_updates(peer)
            and not self._peer_may_have_owner_project_deletions(peer)
        ):
            return
        self._start_snapshot_pull(peer, force=False)

    def _peer_may_have_project_updates(self, peer: LanPeer) -> bool:
        if self.db is None or not peer.project_fingerprints:
            return False
        local_fingerprints = self.db.shared_project_fingerprints()
        for key, remote in peer.project_fingerprints.items():
            if not isinstance(remote, dict):
                continue
            local = local_fingerprints.get(str(key))
            if local is None:
                return True
            for field in ("name", "owner", "status", "description", "project_link", "backup_project_link"):
                if str(remote.get(field, "")) != str(local.get(field, "")):
                    return True
        return False

    def _peer_may_have_owner_project_deletions(self, peer: LanPeer) -> bool:
        if self.db is None:
            return False
        checker = getattr(self.db, "peer_may_have_owner_project_deletions", None)
        if checker is None:
            return False
        return bool(checker(peer.name, peer.project_fingerprints))

    def _peer_may_have_missing_shared_rows(self, peer: LanPeer) -> bool:
        if self.db is None or not peer.record_counts:
            return False
        local_counts = self.db.shared_record_counts()
        for table in (
            "projects",
            "project_members",
            "daily_reports",
            "project_weekly_reports",
            "project_documents",
            "project_todos",
        ):
            remote_count = int(peer.record_counts.get(table, 0) or 0)
            local_count = int(local_counts.get(table, 0) or 0)
            if remote_count > local_count:
                return True
        return False

    def _start_snapshot_pull(self, peer: LanPeer, force: bool = False, bypass_throttle: bool = False) -> bool:
        if not self.peer_data_sync_enabled:
            return False
        if peer.device_id in self._pulling_peer_ids:
            return False
        now = time.monotonic()
        last_started = self._last_pull_started.get(peer.device_id, 0)
        if not bypass_throttle and not force and now - last_started < 6:
            return False
        self._pulling_peer_ids.add(peer.device_id)
        self._last_pull_started[peer.device_id] = now
        thread = threading.Thread(target=self._fetch_snapshot_worker, args=(peer, force), daemon=True)
        thread.start()
        return True

    def _fetch_snapshot_worker(self, peer: LanPeer, force: bool) -> None:
        try:
            snapshot = self._fetch_snapshot(peer)
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._snapshot_failed.emit(peer.device_id)
            return
        self._snapshot_fetched.emit(peer, snapshot, force)

    def _finish_snapshot_pull(self, device_id: object) -> None:
        self._pulling_peer_ids.discard(str(device_id))

    def _apply_fetched_snapshot(self, peer: object, snapshot: object, force: bool) -> None:
        if isinstance(peer, LanPeer):
            self._finish_snapshot_pull(peer.device_id)
        if not self.peer_data_sync_enabled:
            return
        if self.db is None or not isinstance(snapshot, dict):
            return
        changed = False
        if self.db.apply_shared_snapshot(snapshot, force=force):
            changed = True
        elif not force and self.db.merge_missing_shared_snapshot(snapshot):
            changed = True
        if changed:
            self.data_synced.emit()

    def _pull_peer_snapshot(self, peer: LanPeer, force: bool = False) -> bool:
        if not self.peer_data_sync_enabled:
            return False
        if self.db is None:
            return False
        snapshot = self._fetch_snapshot(peer)
        if not isinstance(snapshot, dict):
            return False
        if self.db.apply_shared_snapshot(snapshot, force=force):
            return True
        if force:
            return False
        return self.db.merge_missing_shared_snapshot(snapshot)

    def _fetch_snapshot(self, peer: LanPeer) -> dict[str, Any]:
        try:
            return self._fetch_snapshot_with_protocol(peer, SNAPSHOT_MAGIC_V2, include_requester=True)
        except (OSError, ValueError, json.JSONDecodeError, zlib.error):
            return self._fetch_snapshot_with_protocol(peer, SNAPSHOT_MAGIC, include_requester=False)

    def _fetch_snapshot_with_protocol(
        self,
        peer: LanPeer,
        magic: bytes,
        include_requester: bool,
    ) -> dict[str, Any]:
        with socket.create_connection((peer.address, peer.sync_port), timeout=1.5) as client:
            client.settimeout(8)
            client.sendall(magic)
            if include_requester:
                requester = json.dumps(
                    {"actor": self.display_name, "origin": self.device_id},
                    ensure_ascii=False,
                ).encode("utf-8")
                client.sendall(struct.pack("!I", len(requester)))
                client.sendall(requester)
            header = self._recv_exact(client, 8)
            size = struct.unpack("!Q", header)[0]
            if size > 100 * 1024 * 1024:
                raise ValueError("snapshot too large")
            data = self._recv_exact(client, size)
        return json.loads(zlib.decompress(data).decode("utf-8"))

    def download_update_package(self, peer: LanPeer, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        with socket.create_connection((peer.address, peer.sync_port), timeout=3) as client:
            client.settimeout(30)
            client.sendall(PACKAGE_MAGIC)
            metadata_size = struct.unpack("!Q", self._recv_exact(client, 8))[0]
            if metadata_size <= 0 or metadata_size > 64 * 1024:
                raise ValueError("对方没有可下载的安装包。")
            metadata = json.loads(self._recv_exact(client, metadata_size).decode("utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("安装包信息格式不正确。")
            package_version = str(metadata.get("version") or peer.app_version or "").strip()
            if not package_version:
                raise ValueError("安装包缺少版本信息。")
            if version_tuple(package_version) <= version_tuple(APP_VERSION):
                raise ValueError(f"不能下载 v{package_version} 安装包；本机已经是 v{APP_VERSION}。")
            package_size = struct.unpack("!Q", self._recv_exact(client, 8))[0]
            if package_size <= 0 or package_size > 500 * 1024 * 1024:
                raise ValueError("安装包大小异常。")
            filename = Path(str(metadata.get("name") or "SZZXLocalDesk-update")).name
            target = self._unique_target(target_dir / filename)
            remaining = package_size
            with target.open("wb") as file:
                while remaining > 0:
                    chunk = client.recv(min(1024 * 1024, remaining))
                    if not chunk:
                        raise OSError("连接中断，安装包没有下载完整。")
                    file.write(chunk)
                    remaining -= len(chunk)
        return target

    def _unique_target(self, target: Path) -> Path:
        if not target.exists():
            return target
        stem = target.stem or "SZZXLocalDesk-update"
        suffix = target.suffix
        for index in range(1, 1000):
            candidate = target.with_name(f"{stem}-{index}{suffix}")
            if not candidate.exists():
                return candidate
        return target.with_name(f"{stem}-{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}")

    def _recv_exact(self, client: socket.socket, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = client.recv(min(65536, remaining))
            if not chunk:
                raise OSError("connection closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _sweep(self) -> None:
        now = datetime.now()
        stale_ids = [
            device_id
            for device_id, peer in self.peers.items()
            if (now - peer.last_seen).total_seconds() > 12
        ]
        for device_id in stale_ids:
            del self.peers[device_id]
        if stale_ids:
            self.peers_changed.emit(self.sorted_peers())

    def sorted_peers(self) -> list[LanPeer]:
        return sorted(self.peers.values(), key=lambda peer: peer.name.casefold())
