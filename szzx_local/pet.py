from __future__ import annotations

import math
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMovie, QPainter, QPainterPath, QPen, QPixmap
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


PET_ASSET_DIRS = {
    "penguin": "企鹅",
    "bunny": "兔子",
    "kitten": "小猫",
    "crayfish": "龙虾",
}

PET_ACTION_GIFS = {
    "calm": ("待机.gif",),
    "happy": ("开心.gif",),
    "sleepy": ("困困.gif",),
    "wave": ("挥手.gif", "招手.gif"),
    "jump": ("跳跳.gif", "跳跳 .gif"),
}


def _asset_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "szzx_local" / "assets" / Path(*parts)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "assets" / Path(*parts)


class DesktopPet(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("数智中心桌宠")
        self._base_size = (240, 240)
        self.setFixedSize(*self._base_size)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.kind = "penguin"
        self.mood = "calm"
        self.speech_text = ""
        self._drag_pos: QPoint | None = None
        self._drag_moved = False
        self._tick = 0
        self._placed_once = False
        self._auto_hide_after_speech = False
        self._movie: QMovie | None = None
        self._movie_key: tuple[str, str] | None = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(80)

        self.speech_timer = QTimer(self)
        self.speech_timer.setSingleShot(True)
        self.speech_timer.timeout.connect(self._clear_speech)

    def set_mood(self, mood: str) -> None:
        self.mood = "sleepy" if mood == "tired" else mood if mood in PET_ACTIONS else "calm"
        self._load_movie()
        self.update()

    def speak(self, text: str, mood: str = "wave", duration_ms: int = 16000, auto_hide: bool = True) -> None:
        self.speech_text = text.strip()
        self._auto_hide_after_speech = auto_hide
        self._resize_for_speech()
        self.set_mood(mood)
        self.show()
        if self.speech_text:
            self.speech_timer.start(duration_ms)

    def _clear_speech(self) -> None:
        self.speech_text = ""
        self._resize_for_speech()
        self.set_mood("calm")
        if self._auto_hide_after_speech:
            self._auto_hide_after_speech = False
            self.hide()

    def show_manually(self) -> None:
        self._auto_hide_after_speech = False
        self.speech_timer.stop()
        self._resize_for_speech()
        self.show()

    def set_kind(self, kind: str) -> None:
        kind = LEGACY_PET_KINDS.get(kind, kind)
        self.kind = kind if kind in PET_KINDS else "penguin"
        self.setWindowTitle(f"{PET_KINDS[self.kind]} - 数智中心桌宠")
        self._load_movie()
        self.update()

    def _animate(self) -> None:
        self._tick = (self._tick + 1) % 360
        self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_moved = False
            self.set_mood("happy")

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_pos is not None:
            self._drag_moved = True
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._drag_moved
            and (self.speech_text or self._auto_hide_after_speech)
        ):
            self.speech_timer.stop()
            self.speech_text = ""
            self._auto_hide_after_speech = False
            self._resize_for_speech()
            self.set_mood("calm")
            self.hide()
        self._drag_pos = None
        self._drag_moved = False

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.speech_timer.stop()
            self.speech_text = ""
            self._auto_hide_after_speech = False
            self._resize_for_speech()
            self.set_mood("calm")
            self.hide()

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

        if self.speech_text:
            self._draw_speech_bubble(painter)

        pet_y = self._pet_top()
        self._draw_shadow(painter, 0, pet_y + 179)
        target = QRectF((self.width() - 192) / 2, pet_y, 192, 192)
        painter.drawPixmap(target, pet, QRectF(pet.rect()))

    def _draw_shadow(self, painter: QPainter, jump: int, y: int = 207) -> None:
        width = 116 - jump
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(32, 28, 24, max(16, 36 - jump)))
        painter.drawEllipse(int((self.width() - width) / 2), y, width, 16)

    def _draw_speech_bubble(self, painter: QPainter) -> None:
        bubble_height = self._speech_bubble_height()
        rect = QRectF(12, 8, self.width() - 24, bubble_height)
        painter.setPen(QPen(QColor("#d7ddd3"), 1))
        painter.setBrush(QColor(255, 255, 250, 238))
        painter.drawRoundedRect(rect, 10, 10)
        tail = QPainterPath()
        tail_x = self.width() / 2
        tail_y = 8 + bubble_height - 1
        tail.moveTo(tail_x - 12, tail_y)
        tail.lineTo(tail_x + 4, tail_y + 15)
        tail.lineTo(tail_x + 14, tail_y)
        tail.closeSubpath()
        painter.drawPath(tail)
        painter.setPen(QPen(QColor("#263126"), 1))
        font = self._speech_font()
        painter.setFont(font)
        painter.drawText(
            QRectF(24, 17, self.width() - 48, bubble_height - 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            self.speech_text,
        )

    def _speech_font(self) -> QFont:
        return QFont("Arial", 10, QFont.Weight.Bold)

    def _speech_bubble_height(self) -> int:
        if not self.speech_text:
            return 0
        metrics = QFontMetrics(self._speech_font())
        text_width = max(180, self.width() - 48)
        rect = metrics.boundingRect(
            QRect(0, 0, text_width, 1000),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            self.speech_text,
        )
        return max(58, min(180, rect.height() + 24))

    def _pet_top(self) -> int:
        if not self.speech_text:
            return 28
        return self._speech_bubble_height() + 24

    def _resize_for_speech(self) -> None:
        old_bottom_right = self.frameGeometry().bottomRight()
        if self.speech_text:
            width = 300
            bubble_height = self._speech_bubble_height_for_width(width)
            height = bubble_height + 230
            self.setFixedSize(width, height)
        else:
            self.setFixedSize(*self._base_size)
        if self._placed_once:
            self.move(old_bottom_right.x() - self.width() + 1, old_bottom_right.y() - self.height() + 1)

    def _speech_bubble_height_for_width(self, width: int) -> int:
        if not self.speech_text:
            return 0
        metrics = QFontMetrics(self._speech_font())
        rect = metrics.boundingRect(
            QRect(0, 0, max(180, width - 48), 1000),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            self.speech_text,
        )
        return max(58, min(180, rect.height() + 24))

    def _pet_pixmap(self) -> QPixmap:
        self._load_movie()
        if self._movie is None:
            return QPixmap()
        pixmap = self._movie.currentPixmap()
        if pixmap.isNull():
            self._movie.jumpToFrame(0)
            pixmap = self._movie.currentPixmap()
        return pixmap

    def _load_movie(self) -> None:
        key = (self.kind, self.mood)
        if self._movie_key == key and self._movie is not None:
            return
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        path = self._pet_gif_path(self.kind, self.mood)
        if path is None:
            self._movie_key = key
            return
        movie = QMovie(str(path))
        if not movie.isValid():
            self._movie_key = key
            return
        movie.setCacheMode(QMovie.CacheMode.CacheAll)
        movie.frameChanged.connect(lambda _frame: self.update())
        movie.start()
        self._movie = movie
        self._movie_key = key

    def _pet_gif_path(self, kind: str, mood: str) -> Path | None:
        folder = _asset_path("cartoon", PET_ASSET_DIRS.get(kind, PET_ASSET_DIRS["penguin"]))
        candidates = PET_ACTION_GIFS.get(mood, PET_ACTION_GIFS["calm"])
        for filename in candidates:
            path = folder / filename
            if path.exists():
                return path
        wanted = {Path(filename).stem.replace(" ", "") for filename in candidates}
        for path in folder.glob("*.gif"):
            if path.stem.replace(" ", "") in wanted:
                return path
        calm = folder / "待机.gif"
        if calm.exists():
            return calm
        gifs = sorted(folder.glob("*.gif"))
        return gifs[0] if gifs else None

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
