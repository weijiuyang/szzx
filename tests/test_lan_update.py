from datetime import datetime
import unittest

from szzx_local.lan import LanPeer, best_lan_update_peer


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


if __name__ == "__main__":
    unittest.main()
