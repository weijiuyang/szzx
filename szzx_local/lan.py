from __future__ import annotations

import json
import os
import socket
import struct
import sys
import threading
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QNetworkDatagram, QUdpSocket

from .changelog import CHANGELOG, current_release_notes
from .version import APP_VERSION


LAN_PORT = 45454
SYNC_TCP_PORT = 45455
APP_PROTOCOL = "szzx-local-desk"
SNAPSHOT_MAGIC = b"SZZXSNAP1\n"
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
    today_project_logs: list[dict[str, Any]]


class LanDiscovery(QObject):
    peers_changed = Signal(list)
    data_synced = Signal()

    def __init__(self, device_id: str, display_name: str, port: int = LAN_PORT, db: Any | None = None) -> None:
        super().__init__()
        self.device_id = device_id
        self.display_name = display_name
        self.port = port
        self.sync_port = port + 1
        self.db = db
        self.peers: dict[str, LanPeer] = {}
        self.server_socket: socket.socket | None = None
        self.update_package_path = self._find_update_package()

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

    def start(self) -> None:
        self._start_snapshot_server()
        self.announce()
        self.broadcast_database()
        self.announce_timer.start(3500)
        self.sync_timer.start(8000)
        self.sweep_timer.start(5000)

    def set_display_name(self, name: str) -> None:
        self.display_name = name.strip() or self.display_name
        self.announce()

    def announce(self) -> None:
        payload = {
            "protocol": APP_PROTOCOL,
            "kind": "presence",
            "device_id": self.device_id,
            "name": self.display_name,
            "port": self.port,
            "sync_port": self.sync_port,
            "sync": self.db.sync_state() if self.db is not None else {},
            "app_version": APP_VERSION,
            "platform": sys.platform,
            "update_package": self._update_package_info(),
            "today_project_logs": self._today_project_logs(),
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_socket.writeDatagram(data, QHostAddress.SpecialAddress.Broadcast, self.port)

    def broadcast_database(self) -> None:
        if self.db is None:
            return
        payload = {
            "protocol": APP_PROTOCOL,
            "kind": "db_state",
            "device_id": self.device_id,
            "name": self.display_name,
            "sync_port": self.sync_port,
            "sync": self.db.sync_state(),
            "app_version": APP_VERSION,
            "platform": sys.platform,
            "update_package": self._update_package_info(),
            "today_project_logs": self._today_project_logs(),
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_socket.writeDatagram(data, QHostAddress.SpecialAddress.Broadcast, self.port)
        self._pull_newer_peer_snapshots()

    def _start_snapshot_server(self) -> None:
        if self.db is None or self.server_socket is not None:
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
                if request != SNAPSHOT_MAGIC or self.db is None:
                    return
                data = zlib.compress(
                    json.dumps(self.db.shared_snapshot(include_files=True), ensure_ascii=False).encode("utf-8")
                )
                client.sendall(struct.pack("!Q", len(data)))
                client.sendall(data)
            except OSError:
                return

    def _find_update_package(self) -> Path | None:
        override = os.environ.get(PACKAGE_ENV, "").strip()
        candidates: list[Path] = []
        if override:
            candidates.append(Path(override))

        cwd = Path.cwd()
        if sys.platform == "win32":
            candidates.extend([
                cwd / "dist" / "SZZXLocalDesk.exe",
                Path(sys.executable),
            ])
        elif sys.platform == "darwin":
            candidates.extend([
                cwd / "dist" / "SZZXLocalDesk-mac.dmg",
                cwd / "dist" / "SZZXLocalDesk.app.zip",
            ])
        else:
            candidates.extend([
                cwd / "dist" / "SZZXLocalDesk",
                Path(sys.executable),
            ])

        for path in candidates:
            try:
                if path.is_file() and path.stat().st_size > 0:
                    return path
            except OSError:
                continue
        return None

    def _update_package_info(self) -> dict[str, Any]:
        path = self.update_package_path
        if path is None:
            return {}
        try:
            stat = path.stat()
        except OSError:
            return {}
        return {
            "name": path.name,
            "size": stat.st_size,
            "version": APP_VERSION,
            "platform": sys.platform,
            "notes": current_release_notes(),
            "changelog": CHANGELOG,
        }

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

        device_id = str(payload.get("device_id") or "")
        if not device_id or device_id == self.device_id:
            return False

        kind = payload.get("kind")
        if kind not in {"presence", "db_state"}:
            return False

        name = str(payload.get("name") or "未命名")
        address = datagram.senderAddress().toString()
        if datagram.senderAddress().protocol() == QAbstractSocket.NetworkLayerProtocol.IPv6Protocol:
            return False
        sync = payload.get("sync")
        if not isinstance(sync, dict):
            sync = {}
        try:
            sync_port = int(payload.get("sync_port") or self.sync_port)
        except (TypeError, ValueError):
            sync_port = self.sync_port

        peer = LanPeer(
            device_id=device_id,
            name=name,
            address=address,
            last_seen=datetime.now(),
            sync_port=sync_port,
            sync=sync,
            app_version=str(payload.get("app_version") or ""),
            platform=str(payload.get("platform") or ""),
            update_package=payload.get("update_package") if isinstance(payload.get("update_package"), dict) else {},
            today_project_logs=(
                payload.get("today_project_logs")
                if isinstance(payload.get("today_project_logs"), list)
                else []
            ),
        )
        self.peers[device_id] = peer
        if kind == "db_state":
            self._pull_peer_snapshot_if_newer(peer)
        return True

    def _pull_newer_peer_snapshots(self) -> None:
        for peer in list(self.peers.values()):
            self._pull_peer_snapshot_if_newer(peer)

    def _pull_peer_snapshot_if_newer(self, peer: LanPeer) -> None:
        if self.db is None:
            return
        if not peer.sync or not self.db.remote_sync_is_newer(peer.sync):
            return
        try:
            snapshot = self._fetch_snapshot(peer)
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(snapshot, dict):
            return
        changed = self.db.apply_shared_snapshot(snapshot)
        if changed:
            self.data_synced.emit()

    def _fetch_snapshot(self, peer: LanPeer) -> dict[str, Any]:
        with socket.create_connection((peer.address, peer.sync_port), timeout=1.5) as client:
            client.settimeout(8)
            client.sendall(SNAPSHOT_MAGIC)
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
