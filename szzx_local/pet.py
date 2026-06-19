from __future__ import annotations

import math
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


PET_KINDS = {
    "penguin": "小企鹅",
    "bunny": "小兔子",
    "kitten": "小猫咪",
    "crayfish": "小龙虾",
}

LEGACY_PET_KINDS = {
    "sprout": "penguin",
    "cat": "kitten",
    "blob": "crayfish",
}

PET_ACTIONS = {
    "calm": "待机",
    "happy": "开心",
    "sleepy": "困困",
    "wave": "挥手",
    "jump": "跳跳",
}


PET_ASSET_FILES = {
    "penguin": "qie.png",
    "bunny": "tuzi.png",
    "kitten": "mao.png",
    "crayfish": "longxia.png",
}


def _asset_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "szzx_local" / "assets" / Path(*parts)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "assets" / Path(*parts)


class DesktopPet(QWidget):
    _pixmaps: dict[str, QPixmap] = {}

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("数智中心桌宠")
        self.setFixedSize(240, 240)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.kind = "penguin"
        self.mood = "calm"
        self._drag_pos: QPoint | None = None
        self._tick = 0
        self._placed_once = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(80)

    def set_mood(self, mood: str) -> None:
        self.mood = "sleepy" if mood == "tired" else mood if mood in PET_ACTIONS else "calm"
        self.update()

    def set_kind(self, kind: str) -> None:
        kind = LEGACY_PET_KINDS.get(kind, kind)
        self.kind = kind if kind in PET_KINDS else "penguin"
        self.setWindowTitle(f"{PET_KINDS[self.kind]} - 数智中心桌宠")
        self.update()

    def _animate(self) -> None:
        self._tick = (self._tick + 1) % 360
        self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.set_mood("happy")

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_pos = None

    def showEvent(self, event) -> None:  # type: ignore[override]
        if not self._placed_once:
            self.move_to_bottom_right()
            self._placed_once = True
        super().showEvent(event)

    def show(self) -> None:  # type: ignore[override]
        if not self._placed_once:
            self.move_to_bottom_right()
            self._placed_once = True
        super().show()

    def move_to_bottom_right(self) -> None:
        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = 22
        x = area.right() - self.width() - margin + 1
        y = area.bottom() - self.height() - margin + 1
        self.move(max(area.left(), x), max(area.top(), y))

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pet = self._pet_pixmap()
        if pet.isNull():
            self._draw_missing_asset(painter)
            return

        jump = 0
        breathe = math.sin(self._tick / 7) * 2.5
        tilt = math.sin(self._tick / 10) * 1.4
        squash = 1.0
        if self.mood == "happy":
            jump = int(abs(math.sin(self._tick / 4)) * 10)
            tilt = math.sin(self._tick / 4) * 5
        elif self.mood == "jump":
            jump = int(abs(math.sin(self._tick / 5)) * 34)
            squash = 0.93 + abs(math.sin(self._tick / 5)) * 0.12
        elif self.mood == "wave":
            tilt = math.sin(self._tick / 3) * 7
        elif self.mood == "sleepy":
            breathe = math.sin(self._tick / 14) * 1.2
            tilt = math.sin(self._tick / 18) * 1.0

        self._draw_shadow(painter, jump)
        target = QRectF(29, 25 + breathe - jump, 182, 182)

        painter.save()
        painter.translate(target.center())
        painter.rotate(tilt)
        painter.scale(1.0, squash)
        painter.translate(-target.center())
        painter.drawPixmap(target, pet, QRectF(pet.rect()))
        painter.restore()

        if self.mood == "happy":
            self._draw_hearts(painter)
        elif self.mood == "wave":
            self._draw_wave_sparkles(painter)
        elif self.mood == "sleepy":
            self._draw_sleep_mark(painter)

    def _draw_shadow(self, painter: QPainter, jump: int) -> None:
        width = 116 - jump
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(32, 28, 24, max(16, 36 - jump)))
        painter.drawEllipse(int((240 - width) / 2), 207, width, 16)

    def _pet_pixmap(self) -> QPixmap:
        if self.kind not in DesktopPet._pixmaps:
            asset_file = PET_ASSET_FILES.get(self.kind, PET_ASSET_FILES["penguin"])
            DesktopPet._pixmaps[self.kind] = QPixmap(str(_asset_path("pets", asset_file)))
        return DesktopPet._pixmaps[self.kind]

    def _draw_hearts(self, painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ff7f9c"))
        drift = int(math.sin(self._tick / 5) * 4)
        self._heart(painter, 50 + drift, 44, 9)
        self._heart(painter, 178 - drift, 58, 7)

    def _draw_wave_sparkles(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor("#ffd45c"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        shift = int(math.sin(self._tick / 3) * 4)
        for x, y in ((186, 55), (199, 82), (43, 66)):
            painter.drawLine(x - 5, y + shift, x + 5, y + shift)
            painter.drawLine(x, y - 5 + shift, x, y + 5 + shift)

    def _draw_sleep_mark(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor("#587384"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        rise = int(math.sin(self._tick / 8) * 4)
        painter.drawText(178, 65 - rise, "Z")
        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        painter.drawText(196, 47 - rise, "z")

    def _heart(self, painter: QPainter, x: int, y: int, size: int) -> None:
        path = QPainterPath()
        path.moveTo(x, y + size)
        path.cubicTo(x - size * 2, y - size // 2, x - size, y - size * 2, x, y - size)
        path.cubicTo(x + size, y - size * 2, x + size * 2, y - size // 2, x, y + size)
        painter.drawPath(path)

    def _draw_missing_asset(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor("#596d5b"), 2))
        painter.setBrush(QColor("#fff7dc"))
        painter.drawRoundedRect(50, 54, 140, 130, 42, 42)
        painter.drawText(78, 124, "Pet")
