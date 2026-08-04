from __future__ import annotations

import sys
import ctypes
import platform
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QProcess, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QProgressDialog, QSystemTrayIcon

from .ai import LocalSummarizer
from .autostart import set_autostart
from .central_sync import CentralDataSync
from .database import Database
from .lan import LanDiscovery, best_lan_update_peer
from .pet import DesktopPet
from .self_update import clear_old_update_packages, start_in_place_update, update_cache_dir
from .single_instance import SingleInstanceController
from .ui import LoginDialog, MainWindow, SettingsDialog
from .version import APP_NAME, APP_VERSION


def _app_icon_path() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    filename = "unframed_logo.png" if sys.platform == "win32" else "logo.png"
    return bundle_root / "szzx_local" / "assets" / "icon" / filename


def _launch_update_package(target: Path) -> bool:
    if start_in_place_update(target):
        return True
    if sys.platform == "win32" and target.suffix.lower() == ".exe":
        result = QProcess.startDetached(str(target), ["--update-restart"])
        return result[0] if isinstance(result, tuple) else bool(result)
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def _force_startup_lan_update(app: QApplication, discovery: LanDiscovery) -> bool:
    """Check before login; return False when this process must stop."""
    progress = QProgressDialog("正在查找局域网内的最新版本…", "", 0, 0)
    progress.setWindowTitle("启动检查")
    progress.setCancelButton(None)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.show()
    discovery.announce_burst()
    deadline = time.monotonic() + 2.2
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.04)

    peer = best_lan_update_peer(
        discovery.sorted_peers(),
        current_version=APP_VERSION,
        local_platform=sys.platform,
        local_architecture=platform.machine(),
    )
    if peer is None:
        progress.close()
        return True

    package_version = str(peer.update_package.get("version") or peer.app_version).strip()
    progress.setLabelText(f"发现 v{package_version}，正在从 {peer.name} 自动更新…")
    app.processEvents()
    try:
        clear_old_update_packages()
        target = discovery.download_update_package(peer, update_cache_dir())
        started = _launch_update_package(target)
    except Exception as exc:
        progress.close()
        QMessageBox.critical(None, "必须更新", f"发现局域网新版本 v{package_version}，但自动更新失败：\n{exc}\n\n请重新打开程序后再试。")
        return False
    progress.close()
    if not started:
        QMessageBox.critical(None, "必须更新", f"更新包已经下载，但无法自动安装：\n{target}")
        return False
    return False


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

    instance_controller = None
    if "--smoke-test" not in sys.argv:
        instance_controller = SingleInstanceController(app)
        instance_controller.replacement_requested.connect(app.quit)
        app.aboutToQuit.connect(instance_controller.close)
        if not instance_controller.take_over():
            return 1

    db = Database()
    if "--smoke-test" in sys.argv:
        pet = DesktopPet()
        window = MainWindow(db, LocalSummarizer(), pet)
        print(window.windowTitle())
        db.close()
        return 0

    bootstrap_snapshot = db.shared_snapshot(include_files=True)
    discovery = LanDiscovery(db.device_id(), db.display_name(), db=db, peer_data_sync_enabled=False)
    central_sync = CentralDataSync(db, bootstrap_snapshot=bootstrap_snapshot)
    discovery.data_server_seen.connect(central_sync.set_discovered_server)
    discovery.start()

    if not _force_startup_lan_update(app, discovery):
        db.close()
        return 0

    while True:
        session_is_valid = False
        if central_sync.auth_token and central_sync.server_url:
            try:
                session_is_valid = central_sync.validate_saved_session()
            except Exception:
                session_is_valid = False
        if not session_is_valid:
            login = LoginDialog(db, central_sync)
            if login.exec() != LoginDialog.DialogCode.Accepted:
                db.close()
                return 0

        if db.dingtalk_id().strip():
            break
        required_profile = SettingsDialog(
            db,
            central_sync=central_sync,
            require_dingtalk_id=True,
        )
        required_profile.exec()
        if required_profile.switch_account_requested:
            continue
        if db.dingtalk_id().strip():
            break

    if db.get_setting("autostart_enabled") != "false":
        set_autostart(True)

    pet = DesktopPet()
    summarizer = LocalSummarizer()
    discovery.set_display_name(db.display_name())
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
