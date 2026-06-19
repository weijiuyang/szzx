from __future__ import annotations

import json
import socket
import struct
import threading
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QNetworkDatagram, QUdpSocket


LAN_PORT = 45454
SYNC_TCP_PORT = 45455
APP_PROTOCOL = "szzx-local-desk"
SNAPSHOT_MAGIC = b"SZZXSNAP1\n"


@dataclass(frozen=True)
class LanPeer:
    device_id: str
    name: str
    address: str
    last_seen: datetime
    sync_port: int
    sync: dict[str, Any]


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
                request = client.recv(len(SNAPSHOT_MAGIC))
                if request != SNAPSHOT_MAGIC or self.db is None:
                    return
                data = zlib.compress(
                    json.dumps(self.db.shared_snapshot(include_files=True), ensure_ascii=False).encode("utf-8")
                )
                client.sendall(struct.pack("!Q", len(data)))
                client.sendall(data)
            except OSError:
                return

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
