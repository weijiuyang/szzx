from __future__ import annotations

import sys
import ctypes
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

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


class _WindowsTrayController(QObject):
    def __init__(self, app: QApplication, window: MainWindow, icon: QIcon) -> None:
        super().__init__(app)
        self.app = app
        self.window = window
        self.exiting = False
        self._close_hint_shown = False

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        show_action = QAction("打开数智中心", menu)
        show_action.triggered.connect(self.show_window)
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self.window.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if watched is self.window and event.type() == QEvent.Type.Close and not self.exiting:
            event.ignore()
            self.window.hide()
            if not self._close_hint_shown:
                self._close_hint_shown = True
                self.tray.showMessage(APP_NAME, "程序仍在右下角运行，双击图标可以重新打开。")
            return True
        return super().eventFilter(watched, event)

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.show_window()

    def show_window(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def quit_app(self) -> None:
        self.exiting = True
        self.tray.hide()
        self.window.close()
        self.app.quit()


def main() -> int:
    if "--update-restart" in sys.argv:
        time.sleep(2)
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SZZX.DigitalCenter")  # type: ignore[attr-defined]
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app_icon = QIcon(str(_app_icon_path()))
    app.setWindowIcon(app_icon)

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
    tray_controller = None
    if sys.platform == "win32" and QSystemTrayIcon.isSystemTrayAvailable():
        app.setQuitOnLastWindowClosed(False)
        tray_controller = _WindowsTrayController(app, window, app_icon)

    try:
        return app.exec()
    finally:
        db.close()
