from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


# This name is deliberately independent of the executable name, install path, and
# application version.  Do not change it between releases: that is what lets a new
# build replace an older build.
INSTANCE_CHANNEL = "com.szzx.localdesk.instance"
_REPLACE_COMMAND = b"REPLACE\n"


class SingleInstanceController(QObject):
    """Own the app-wide local endpoint and ask an existing owner to exit."""

    replacement_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept_connections)
        self._clients: list[QLocalSocket] = []

    def take_over(self, timeout_ms: int = 8000) -> bool:
        """Replace an existing instance and become the endpoint owner."""
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if self._server.listen(INSTANCE_CHANNEL):
                return True

            if not self._request_replacement():
                # A crashed Unix process can leave its socket path behind.  Only
                # remove it after proving that nothing is accepting connections.
                QLocalServer.removeServer(INSTANCE_CHANNEL)
            time.sleep(0.08)
        return False

    def close(self) -> None:
        self._server.close()
        for client in self._clients:
            client.abort()
        self._clients.clear()

    def _request_replacement(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(INSTANCE_CHANNEL)
        if not socket.waitForConnected(250):
            return False
        socket.write(_REPLACE_COMMAND)
        socket.flush()
        socket.waitForBytesWritten(250)
        socket.disconnectFromServer()
        return True

    def _accept_connections(self) -> None:
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            if client is None:
                continue
            self._clients.append(client)
            client.readyRead.connect(lambda current=client: self._read_command(current))
            client.disconnected.connect(lambda current=client: self._forget_client(current))
            self._read_command(client)

    def _read_command(self, client: QLocalSocket) -> None:
        if _REPLACE_COMMAND.strip() not in bytes(client.readAll()):
            return
        # Release the name first, so the new process cannot continue until this
        # instance has accepted the shutdown request.
        self._server.close()
        self.replacement_requested.emit()

    def _forget_client(self, client: QLocalSocket) -> None:
        if client in self._clients:
            self._clients.remove(client)
        client.deleteLater()
