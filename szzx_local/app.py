from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ai import LocalSummarizer
from .database import Database
from .lan import LanDiscovery
from .pet import DesktopPet
from .ui import MainWindow, PinDialog
from .version import APP_NAME, APP_VERSION


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

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

    pet = DesktopPet()
    summarizer = LocalSummarizer()
    discovery = LanDiscovery(db.device_id(), db.display_name())
    window = MainWindow(db, summarizer, pet, discovery)
    window.show()
    pet.show()

    try:
        return app.exec()
    finally:
        db.close()
