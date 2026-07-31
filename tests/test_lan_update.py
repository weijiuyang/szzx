from datetime import datetime
import json
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from szzx_local.lan import LanDiscovery, LanPeer, best_lan_update_peer
from szzx_local.version import APP_VERSION


def _peer(version: str, *, system: str = "win32", architecture: str = "amd64", size: int = 10) -> LanPeer:
    return LanPeer(
        device_id=version,
        name=f"peer-{version}",
        address="192.0.2.1",
        last_seen=datetime.now(),
        sync_port=45455,
        sync={},
        app_version=version,
        platform=system,
        update_package={"version": version, "architecture": architecture, "size": size},
        record_counts={},
        project_fingerprints={},
        today_project_logs=[],
    )


class BestLanUpdatePeerTests(unittest.TestCase):
    def test_selects_highest_compatible_version(self) -> None:
        selected = best_lan_update_peer(
            [_peer("0.2.64"), _peer("0.3.0"), _peer("1.0.0", system="darwin")],
            current_version="0.2.63",
            local_platform="win32",
            local_architecture="amd64",
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.app_version, "0.3.0")

    def test_ignores_old_missing_and_wrong_arch_packages(self) -> None:
        selected = best_lan_update_peer(
            [
                _peer("0.2.63", system="darwin", architecture="arm64"),
                _peer("0.2.64", system="darwin", architecture="x86_64"),
                _peer("0.2.65", system="darwin", architecture="arm64", size=0),
            ],
            current_version="0.2.63",
            local_platform="darwin",
            local_architecture="arm64",
        )

        self.assertIsNone(selected)


class UpdatePackageDownloadTests(unittest.TestCase):
    def test_replaces_existing_package_instead_of_creating_numbered_copy(self) -> None:
        package_data = b"new executable"
        metadata = {
            "name": "SZZXLocalDesk.exe",
            "version": "999.0.0",
            "architecture": "amd64",
        }
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def serve() -> None:
            connection, _ = server.accept()
            with connection:
                connection.recv(32)
                encoded = json.dumps(metadata).encode("utf-8")
                connection.sendall(struct.pack("!Q", len(encoded)))
                connection.sendall(encoded)
                connection.sendall(struct.pack("!Q", len(package_data)))
                connection.sendall(package_data)
            server.close()

        thread = threading.Thread(target=serve)
        thread.start()
        peer = _peer("999.0.0")
        peer = LanPeer(**{**peer.__dict__, "address": "127.0.0.1", "sync_port": port})
        discovery = LanDiscovery("device", "tester")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / metadata["name"]
            target.write_bytes(b"old executable")
            with patch("szzx_local.lan.sys.platform", "win32"), patch(
                "szzx_local.lan.APP_VERSION", APP_VERSION
            ):
                downloaded = discovery.download_update_package(peer, Path(directory))
            self.assertEqual(downloaded, target)
            self.assertEqual(target.read_bytes(), package_data)
            self.assertEqual(list(Path(directory).glob("SZZXLocalDesk-*.exe")), [])
            self.assertFalse(Path(f"{target}.part").exists())
        thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
