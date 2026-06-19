from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QNetworkDatagram, QUdpSocket


LAN_PORT = 45454
APP_PROTOCOL = "szzx-local-desk"


@dataclass(frozen=True)
class LanPeer:
    device_id: str
    name: str
    address: str
    last_seen: datetime


class LanDiscovery(QObject):
    peers_changed = Signal(list)

    def __init__(self, device_id: str, display_name: str, port: int = LAN_PORT) -> None:
        super().__init__()
        self.device_id = device_id
        self.display_name = display_name
        self.port = port
        self.peers: dict[str, LanPeer] = {}

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

        self.sweep_timer = QTimer(self)
        self.sweep_timer.timeout.connect(self._sweep)

    def start(self) -> None:
        self.announce()
        self.announce_timer.start(3500)
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
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_socket.writeDatagram(data, QHostAddress.SpecialAddress.Broadcast, self.port)

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

        if payload.get("protocol") != APP_PROTOCOL or payload.get("kind") != "presence":
            return False

        device_id = str(payload.get("device_id") or "")
        if not device_id or device_id == self.device_id:
            return False

        name = str(payload.get("name") or "未命名")
        address = datagram.senderAddress().toString()
        if datagram.senderAddress().protocol() == QAbstractSocket.NetworkLayerProtocol.IPv6Protocol:
            return False

        self.peers[device_id] = LanPeer(
            device_id=device_id,
            name=name,
            address=address,
            last_seen=datetime.now(),
        )
        return True

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
