from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .ai import LocalSummarizer
from .autostart import set_autostart
from .central_sync import CentralDataSync
from .database import Database
from .lan import LanDiscovery
from .pet import DesktopPet
from .ui import MainWindow, PinDialog
from .version import APP_NAME, APP_VERSION


def _app_icon_path() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    filename = "unframed_logo.png" if sys.platform == "win32" else "logo.png"
    return bundle_root / "szzx_local" / "assets" / "icon" / filename


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(QIcon(str(_app_icon_path())))

    db = Database()
    if "--smoke-test" in sys.argv:
        pet = DesktopPet()
        window = MainWindow(db, LocalSummarizer(), pet)
        print(window.windowTitle())
        db.close()
        return 0

    pin = PinDialog(db)
    if pin.exec() != PinDialog.DialogCode.Accepted:
        db.close()
        return 0

    if db.get_setting("autostart_enabled") != "false":
        set_autostart(True)

    pet = DesktopPet()
    summarizer = LocalSummarizer()
    bootstrap_snapshot = db.shared_snapshot(include_files=True)
    discovery = LanDiscovery(db.device_id(), db.display_name(), db=db, peer_data_sync_enabled=False)
    central_sync = CentralDataSync(db, bootstrap_snapshot=bootstrap_snapshot)
    discovery.data_server_seen.connect(central_sync.set_discovered_server)
    window = MainWindow(db, summarizer, pet, discovery)
    window.central_sync = central_sync
    central_sync.data_synced.connect(window._refresh_after_lan_sync)
    central_sync.start()
    window.show()

    try:
        return app.exec()
    finally:
        db.close()
