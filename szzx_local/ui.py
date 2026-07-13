from __future__ import annotations

import calendar
import ipaddress
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from PySide6.QtCore import QProcess, QRect, QStandardPaths, QThread, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTextCursor, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from .ai import LocalSummarizer
from .autostart import autostart_registered, is_supported as autostart_supported, set_autostart
from .changelog import changelog_text, current_release_notes
from .database import APP_DIR, Database, safe_document_filename, unique_document_path
from .lan import LanDiscovery, LanPeer
from .models import (
    DailyReport,
    Project,
    ProjectDocument,
    ProjectMember,
    ProjectTodo,
    ProjectWeeklyReport,
    RestDay,
    WeeklyReport,
)
from .pet import DesktopPet, PET_ACTIONS, PET_KINDS
from .updater import check_for_update, configured_update_url, version_tuple
from .version import APP_VERSION


class AutoHeightTextEdit(QTextEdit):
    def __init__(self, minimum_height: int = 96, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auto_minimum_height = minimum_height
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().contentsChanged.connect(self._update_auto_height)
        QTimer.singleShot(0, self._update_auto_height)

    def resizeEvent(self, event: object) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_auto_height()

    def _update_auto_height(self) -> None:
        self.document().setTextWidth(max(1, self.viewport().width()))
        content_height = int(self.document().size().height()) + 28
        self.setFixedHeight(max(self._auto_minimum_height, content_height))


def _is_qt_object_alive(obj: object) -> bool:
    try:
        return isValid(obj)
    except RuntimeError:
        return False


APP_STYLE = """
* {
    font-family: "Songti SC", "Noto Serif CJK SC", "Yu Mincho", "Hiragino Mincho ProN", "Microsoft YaHei UI", serif;
    font-size: 14px;
    color: #23241f;
}
QMainWindow, QDialog {
    background: #f7f7f4;
}
QLabel#appTitle {
    font-size: 22px;
    font-weight: 600;
    color: #1d1e1b;
}
QLabel#muted, QLabel.muted {
    color: #777b72;
}
QLabel#sectionTitle {
    font-size: 26px;
    font-weight: 500;
    color: #1d1e1b;
}
QLabel#heroTitle {
    font-size: 32px;
    font-weight: 700;
    color: #11130f;
}
QLabel#metricValue {
    font-size: 28px;
    font-weight: 700;
    color: #1d1e1b;
}
QLabel#eyebrow {
    color: #596d5b;
    font-size: 12px;
    font-weight: 600;
}
QPushButton {
    border: 1px solid #d9d9d1;
    border-radius: 6px;
    padding: 10px 14px;
    background: #f2f2ee;
    color: #2b2c27;
    font-weight: 500;
}
QPushButton:hover {
    background: #ecece7;
    border-color: #c8c9bf;
}
QPushButton#primaryButton {
    background: #24251f;
    color: #f8f8f3;
    border-color: #24251f;
}
QPushButton#primaryButton:hover {
    background: #383930;
    border-color: #383930;
}
QPushButton#dangerButton {
    background: #fff6f3;
    color: #8f2d1f;
    border-color: #e2b8ad;
}
QPushButton#dangerButton:hover {
    background: #fbe9e3;
    border-color: #d59a8a;
}
QPushButton#smallButton {
    padding: 7px 12px;
    min-width: 58px;
}
QPushButton#projectSearchButton {
    padding: 2px;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
}
QLineEdit#projectSearchInput {
    padding: 6px 8px;
    min-height: 18px;
}
QPushButton#dailyReportDeleteButton {
    padding: 7px 18px;
    min-width: 82px;
}
QPushButton#nameLink {
    border: none;
    background: transparent;
    padding: 0;
    margin: 0;
    text-align: left;
    color: #20231f;
    font-size: 14px;
    font-weight: 500;
    min-height: 18px;
    max-height: 18px;
}
QPushButton#nameLink:hover {
    color: #42624d;
    background: transparent;
    text-decoration: underline;
}
QPushButton#chatButton {
    border: none;
    border-radius: 0;
    padding: 0;
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
    background: transparent;
}
QPushButton#chatButton:hover {
    background: transparent;
}
QPushButton#projectTextButton, QPushButton#projectPrimaryLinkButton, QPushButton#projectBackupLinkButton {
    border: none;
    border-radius: 11px;
    padding: 0;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
    background: transparent;
}
QPushButton#projectTextButton:hover {
    background: #dceee4;
}
QPushButton#projectPrimaryLinkButton {
    background: transparent;
}
QPushButton#projectPrimaryLinkButton:hover {
    background: #dceee4;
}
QPushButton#projectBackupLinkButton {
    background: transparent;
}
QPushButton#projectBackupLinkButton:hover {
    background: #edf4ed;
}
QPushButton#calendarDay {
    min-width: 76px;
    min-height: 64px;
    padding: 8px;
    text-align: left;
    background: #fbfbf8;
}
QPushButton#calendarMuted {
    min-width: 76px;
    min-height: 64px;
    padding: 8px;
    text-align: left;
    background: #f1f1ec;
    color: #a0a39a;
}
QPushButton#calendarToday {
    min-width: 76px;
    min-height: 64px;
    padding: 8px;
    text-align: left;
    border-color: #596d5b;
    background: #eef3ed;
}
QPushButton#calendarRest {
    min-width: 76px;
    min-height: 64px;
    padding: 8px;
    text-align: left;
    background: #fff6f3;
    border-color: #d59a8a;
    color: #8f2d1f;
}
QPushButton#navButton {
    text-align: left;
    padding: 12px 8px;
    border-radius: 0;
    border: 0;
    border-left: 2px solid transparent;
    background: transparent;
    color: #777b72;
}
QPushButton#navButton:checked {
    background: transparent;
    color: #1d1e1b;
    border-left: 2px solid #596d5b;
}
QLineEdit, QTextEdit, QListWidget, QComboBox {
    background: #fbfbf8;
    border: 1px solid #deded6;
    border-radius: 6px;
    padding: 12px;
    selection-background-color: #596d5b;
}
QTextEdit {
    line-height: 1.4;
}
QListWidget {
    outline: 0;
}
QListWidget::item {
    min-height: 44px;
    border-radius: 4px;
    padding: 8px 10px;
    margin: 2px;
}
QListWidget::item:selected {
    background: #ecefe9;
    color: #23241f;
}
QListWidget#dailyReportFeed {
    padding: 8px 12px;
}
QListWidget#dailyReportFeed::item {
    min-height: 0;
    padding: 0;
    margin: 0;
    background: transparent;
}
QListWidget#dailyReportFeed::item:selected {
    background: transparent;
}
QListWidget#projectList {
    padding: 6px;
}
QListWidget#projectList::item {
    padding: 0;
    margin: 6px 0;
    border-radius: 0;
    background: transparent;
}
QListWidget#projectList::item:selected {
    background: transparent;
}
QListWidget#personProjectList {
    padding: 6px;
}
QListWidget#personProjectList::item {
    padding: 0;
    margin: 0;
    border-radius: 0;
    background: transparent;
}
QListWidget#personProjectList::item:selected {
    background: transparent;
}
QSplitter::handle {
    background: transparent;
    width: 18px;
}
QWidget#shell {
    background: #f7f7f4;
}
QWidget#sidebar {
    background: #efefea;
    border-right: 1px solid #dcdcD3;
}
QWidget#panel {
    background: #fbfbf8;
    border: 1px solid #deded6;
    border-radius: 6px;
}
QWidget#softPanel {
    background: #edf4f1;
    border: 1px solid #cfddd7;
    border-radius: 6px;
}
QWidget#heroPanel {
    background: #e9efe8;
    border: 1px solid #d5ded2;
    border-radius: 8px;
}
QWidget#feedCard {
    background: #eef2eb;
    border: 1px solid #d8ded2;
    border-radius: 6px;
}
QWidget#projectListCard {
    background: #eef2eb;
    border: 1px solid #d8ded2;
    border-radius: 6px;
}
QWidget#projectListCardActive {
    background: #e2ebe2;
    border: 1px solid #c9d7c9;
    border-radius: 6px;
}
QWidget#memberCard {
    background: #f4f6f2;
    border: 1px solid #dfe4dc;
    border-radius: 6px;
}
QWidget#compactMemberCard {
    background: #f6f8f4;
    border: 1px solid #dfe7dd;
    border-radius: 6px;
}
QLabel#avatar {
    background: #263126;
    color: #faf9f2;
    border-radius: 16px;
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
    font-weight: 700;
}
QLabel#compactAvatar {
    background: #263126;
    color: #faf9f2;
    border-radius: 14px;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    font-weight: 700;
    font-size: 12px;
}
QLabel#memberName {
    font-size: 15px;
    font-weight: 700;
    color: #20231f;
}
QLabel#roleBadge {
    background: #e5eee8;
    color: #42624d;
    border: 1px solid #cfded3;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 12px;
    font-weight: 600;
}
QLabel#compactRoleBadge {
    background: #e5eee8;
    color: #42624d;
    border: 1px solid #cfded3;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 600;
}
QWidget#darkPanel {
    background: #20231f;
    border: 1px solid #20231f;
    border-radius: 8px;
}
QWidget#darkPanel QLabel {
    color: #f6f5ef;
}
QWidget#darkPanel QLabel#muted {
    color: #bfc5ba;
}
QWidget#badgeWallPage {
    background: #eef3ec;
}
QWidget#badgeWallPage QLabel#sectionTitle {
    color: #17251c;
}
QWidget#badgeWallPage QLabel#muted {
    color: #66756a;
}
QWidget#badgeItem {
    background: transparent;
    border: none;
}
QLabel#badgeIcon {
    font-size: 38px;
    color: #596d5b;
    background: transparent;
    border: none;
}
QLabel#badgeWinner {
    font-size: 18px;
    font-weight: 700;
    color: #1d1e1b;
    background: transparent;
    border: none;
}
QLabel#badgeRule {
    font-size: 18px;
    font-weight: 700;
    color: #1d1e1b;
}
"""


def _safe_local_path(value: str) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if sys.platform != "win32" and len(raw) >= 3 and raw[1:3] == ":\\":
        return None
    try:
        path = Path(raw)
        path.exists()
    except (OSError, ValueError):
        return None
    return path


def _path_exists_safely(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return path.exists()
    except (OSError, ValueError):
        return False


DOCUMENT_TYPES = [
    "产品原型图",
    "PRD",
    "需求文档",
    "项目汇报PPT",
    "设计图",
    "测试文档",
    "对接文档",
    "交接文档",
    "调研/可行性报告",
    "竞品调研报告",
    "会议纪要",
    "压缩包",
    "其他",
]
ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
DOCUMENT_OPEN_FILTER = (
    "文档和压缩包 "
    "(*.ppt *.pptx *.doc *.docx *.pdf *.xls *.xlsx *.png *.jpg *.jpeg *.fig "
    "*.zip *.rar *.7z *.tar *.gz *.tgz *.bz2 *.xz *.txt *.md);;All Files (*)"
)
PROJECT_HERO_HEIGHT = 300
PROJECT_TASK_SECTION_HEIGHT = 430
PROJECT_DAILY_SECTION_HEIGHT = 560
PROJECT_TASK_SIDE_HEIGHT = PROJECT_TASK_SECTION_HEIGHT + 18
PROJECT_DAILY_SIDE_HEIGHT = PROJECT_DAILY_SECTION_HEIGHT + 18
SUPER_ADMIN_NAMES = {"尉久洋"}
ASSIGNED_TODO_MIN_VERSION = "0.1.61"
ASSIGNED_TODO_WORKFLOW_MIN_VERSION = "0.1.114"


def _asset_path(*parts: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "szzx_local" / "assets" / Path(*parts)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "assets" / Path(*parts)


DINGTALK_ICON_PATH = _asset_path("dingtalk.svg")


def _desktop_path() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    return Path(location) if location else Path.home() / "Desktop"


def _label(text: str, object_name: str | None = None) -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(True)
    return label


def _nowrap_label(text: str, object_name: str | None = None) -> QLabel:
    label = _label(text, object_name)
    label.setWordWrap(False)
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return label


def _dingtalk_chat_url(dingtalk_id: str) -> str:
    return f"dingtalk://dingtalkclient/action/sendmsg?dingtalk_id={quote(dingtalk_id.strip())}"


def _normalize_project_link(value: str) -> str:
    link = value.strip()
    if not link:
        return ""
    url = QUrl.fromUserInput(link)
    if url.scheme().lower() not in {"http", "https"} or not url.host():
        return ""
    return url.toString()


def _normalize_dingtalk_group_link(value: str) -> str:
    link = value.strip()
    if not link:
        return ""
    url = QUrl.fromUserInput(link)
    if url.scheme().lower() not in {"http", "https", "dingtalk"}:
        return ""
    if url.scheme().lower() in {"http", "https"} and not url.host():
        return ""
    return url.toString()


def _dingtalk_group_app_url(link: str) -> QUrl:
    url = QUrl.fromUserInput(link)
    if url.scheme().lower() == "dingtalk":
        return url
    if url.host().lower() != "qr.dingtalk.com" or url.path() != "/action/joingroup":
        return QUrl()
    app_url = QUrl("dingtalk://dingtalkclient/action/joingroup")
    app_url.setQuery(url.query())
    return app_url


def _project_link_icon(kind: str) -> QIcon:
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#2f7557" if kind == "primary" else "#3d7a5b")
    pen = QPen(color, 5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    if kind == "primary":
        painter.drawRect(12, 18, 18, 18)
        painter.drawLine(24, 13, 36, 13)
        painter.drawLine(36, 13, 36, 25)
        painter.drawLine(23, 26, 36, 13)
    else:
        painter.drawArc(10, 17, 18, 14, 35 * 16, 250 * 16)
        painter.drawArc(20, 17, 18, 14, -145 * 16, 250 * 16)
        painter.drawLine(21, 24, 27, 24)
    painter.end()
    return QIcon(pixmap)


def _project_text_icon() -> QIcon:
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#2f7557")
    pen = QPen(color, 5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawRect(12, 9, 24, 30)
    painter.drawLine(18, 18, 30, 18)
    painter.drawLine(18, 25, 30, 25)
    painter.drawLine(18, 32, 26, 32)
    painter.end()
    return QIcon(pixmap)


def _project_group_icon(kind: str) -> QIcon:
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#2f7557"), 4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawRoundedRect(7, 9, 34, 25, 7, 7)
    painter.drawLine(16, 34, 13, 40)
    painter.drawLine(13, 40, 22, 34)
    painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
    painter.drawText(QRect(8, 10, 32, 22), Qt.AlignmentFlag.AlignCenter, "DEV" if kind == "development" else "CO")
    painter.end()
    return QIcon(pixmap)


def _show_project_notes_dialog(parent: QWidget, project_name: str, notes: str) -> None:
    text = notes.strip()
    if not text:
        QMessageBox.information(parent, "项目资料为空", "这个项目还没有配置文本资料。")
        return
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"{project_name} · 项目资料")
    dialog.resize(560, 420)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)
    viewer = AutoHeightTextEdit(120)
    viewer.setReadOnly(True)
    viewer.setPlainText(text)
    layout.addWidget(viewer)
    close_button = QPushButton("关闭")
    close_button.setObjectName("smallButton")
    close_button.clicked.connect(dialog.accept)
    layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)
    dialog.exec()


def _try_click_dingtalk_send_message() -> None:
    if sys.platform != "darwin":
        return
    script = """
tell application "System Events"
    set appNames to {"DingTalk", "钉钉"}
    repeat with appName in appNames
        if exists process appName then
            tell process appName
                set frontmost to true
                repeat 15 times
                    try
                        click (first button of entire contents of front window whose name is "发消息")
                        return
                    end try
                    try
                        click (first UI element of entire contents of front window whose description is "发消息")
                        return
                    end try
                    delay 0.2
                end repeat
            end tell
        end if
    end repeat
end tell
"""
    try:
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return


def _panel() -> QWidget:
    widget = QWidget()
    widget.setObjectName("panel")
    return widget


def _soft_panel() -> QWidget:
    widget = QWidget()
    widget.setObjectName("softPanel")
    return widget


class PinDialog(QDialog):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self.setWindowTitle("数智中心")
        self.setFixedWidth(470)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 34)
        layout.setSpacing(16)
        title = _label("数智中心", "appTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = _label("安静地开始今天的记录", "muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pin_hint = _label("PIN 是本机本地密码，默认 1234。", "muted")
        pin_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        setup_hint = _label("进入后请在左下角「名字/PIN」修改名字、PIN、钉钉号", "muted")
        setup_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setMaxLength(12)
        self.pin_input.setPlaceholderText("PIN")
        self.pin_input.returnPressed.connect(self._try_unlock)

        unlock = QPushButton("进入")
        unlock.setObjectName("primaryButton")
        unlock.clicked.connect(self._try_unlock)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(pin_hint)
        layout.addWidget(setup_hint)
        layout.addWidget(self.pin_input)
        layout.addWidget(unlock)
        self.pin_input.setFocus()

    def _try_unlock(self) -> None:
        if self.db.verify_pin(self.pin_input.text()):
            self.accept()
        else:
            QMessageBox.warning(self, "PIN 错误", "PIN 不对。")
            self.pin_input.clear()


class SettingsDialog(QDialog):
    def __init__(self, db: Database, peers: list[LanPeer] | None = None) -> None:
        super().__init__()
        self.db = db
        self.peers = peers or []
        self.setWindowTitle("名字和本地密码")
        self.setFixedWidth(420)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        form = QFormLayout()
        form.setSpacing(14)
        self.display_name: QLineEdit | None = None
        if self.db.display_name_locked():
            locked_name = _label(self.db.display_name(), "memberName")
            locked_name.setToolTip("名字已经锁定")
            form.addRow("名字", locked_name)
        else:
            self.display_name = QLineEdit()
            self.display_name.setMaxLength(32)
            self.display_name.setText(self.db.display_name())
            self.display_name.setPlaceholderText("显示给局域网同事的名字")
            form.addRow("名字", self.display_name)

        self.new_pin = QLineEdit()
        self.new_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pin.setMaxLength(12)
        self.new_pin.setPlaceholderText("本地密码，留空则不修改")

        form.addRow("本地密码", self.new_pin)
        self.dingtalk_id = QLineEdit()
        self.dingtalk_id.setMaxLength(80)
        self.dingtalk_id.setText(self.db.dingtalk_id())
        self.dingtalk_id.setPlaceholderText("自己的钉钉号，用于点击姓名发起聊天")
        form.addRow("钉钉号", self.dingtalk_id)
        layout.addLayout(form)
        self.autostart = QCheckBox("开机自动启动")
        self.autostart.setChecked(self.db.get_setting("autostart_enabled") != "false")
        self.autostart.setEnabled(autostart_supported())
        layout.addWidget(self.autostart)
        if not autostart_supported():
            layout.addWidget(_label("当前系统暂不支持开机自动启动。", "muted"))
        elif self.db.get_setting("autostart_enabled") != "false" and not autostart_registered():
            layout.addWidget(_label("打包安装后的应用会在下次启动时写入开机自动启动。", "muted"))
        layout.addWidget(_label("换电脑时，先在旧电脑退出当前姓名，再在新电脑设置同一个姓名。", "muted"))

        save = QPushButton("保存")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save)
        logout = QPushButton("退出登录")
        logout.setObjectName("dangerButton")
        logout.clicked.connect(self._release_name)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(logout)
        actions.addWidget(save)
        layout.addLayout(actions)

    def _save(self) -> None:
        if self.display_name is not None:
            name = self.display_name.text().strip()
            if not name:
                QMessageBox.warning(self, "名字为空", "名字至少写一个字。")
                return
            if name != self.db.display_name():
                if self._online_name_owner(name) is not None or self.db.display_name_claim_owner(name) is not None:
                    QMessageBox.warning(self, "名字已被使用", "这个名字已经被别人使用。")
                    return
                try:
                    self.db.set_display_name(name)
                except ValueError as exc:
                    QMessageBox.warning(self, "不能改名", str(exc))
                    return

        pin = self.new_pin.text().strip()
        if pin and len(pin) < 4:
            QMessageBox.warning(self, "太短了", "PIN 至少 4 位。")
            return
        if pin:
            self.db.change_pin(pin)
        self.db.set_dingtalk_id(self.dingtalk_id.text().strip(), save=False)
        self.db.set_setting("autostart_enabled", "true" if self.autostart.isChecked() else "false", save=False)
        try:
            set_autostart(self.autostart.isChecked())
        except OSError as exc:
            QMessageBox.warning(self, "开机启动失败", f"保存名字和密码成功，但开机自动启动设置失败：{exc}")
            self.db.save_local_settings()
            self.accept()
            return
        self.db.save_local_settings()
        self.accept()

    def _release_name(self) -> None:
        name = self.db.display_name()
        message = f"确定在这台电脑退出登录「{name}」吗？\n\n退出后，新电脑同步刷新后才能使用这个姓名。"
        if QMessageBox.question(self, "退出登录", message) != QMessageBox.StandardButton.Yes:
            return
        self.db.release_display_name()
        self.accept()

    def _online_name_owner(self, name: str) -> str | None:
        target = " ".join(name.strip().split()).casefold()
        for peer in self.peers:
            if " ".join(peer.name.strip().split()).casefold() == target:
                return peer.device_id
        return None


class PetDialog(QDialog):
    def __init__(self, db: Database, pet: DesktopPet) -> None:
        super().__init__()
        self.db = db
        self.pet = pet
        self.pet_buttons: dict[str, QPushButton] = {}
        self.setWindowTitle("桌宠")
        self.setFixedWidth(430)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(_label("选择桌宠", "eyebrow"))

        pets = QGridLayout()
        pets.setSpacing(10)
        for index, (kind, name) in enumerate(PET_KINDS.items()):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setChecked(kind == self.pet.kind)
            button.clicked.connect(lambda checked=False, selected=kind: self._select_pet(selected))
            self.pet_buttons[kind] = button
            pets.addWidget(button, index // 2, index % 2)
        layout.addLayout(pets)

        layout.addWidget(_label("动作", "eyebrow"))
        actions = QGridLayout()
        actions.setSpacing(10)
        for index, (action, label) in enumerate(PET_ACTIONS.items()):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, selected=action: self._play_action(selected))
            actions.addWidget(button, index // 3, index % 3)
        layout.addLayout(actions)

        visibility_actions = QHBoxLayout()
        visibility_actions.setSpacing(10)
        hide_pet = QPushButton("隐藏桌宠")
        hide_pet.clicked.connect(self._hide_pet)
        show_pet = QPushButton("显示桌宠")
        show_pet.setObjectName("primaryButton")
        show_pet.clicked.connect(self._show_pet_bottom_right)
        visibility_actions.addWidget(hide_pet)
        visibility_actions.addWidget(show_pet)
        layout.addLayout(visibility_actions)

    def _select_pet(self, kind: str) -> None:
        self.db.set_pet_kind(kind)
        self.db.record_activity("更换桌宠")
        self.pet.set_kind(kind)
        for button_kind, button in self.pet_buttons.items():
            button.setChecked(button_kind == kind)
        self._show_pet_bottom_right()

    def _play_action(self, action: str) -> None:
        self.db.record_activity("桌宠互动")
        self.pet.set_mood(action)
        self._show_pet_bottom_right()

    def _show_pet_bottom_right(self) -> None:
        self.db.record_activity("显示桌宠")
        self.pet.move_to_bottom_right()
        self.pet.show_manually()

    def _hide_pet(self) -> None:
        self.db.record_activity("隐藏桌宠")
        self.pet.hide()


class VersionDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("版本")
        self.setFixedWidth(470)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        layout.addWidget(_label("数智中心", "appTitle"))
        layout.addWidget(_label(f"当前版本：v{APP_VERSION}", "muted"))
        layout.addWidget(_label(f"本版更新：{current_release_notes()}", "muted"))
        layout.addWidget(_label("更新方式：本地 / 局域网", "muted"))
        layout.addWidget(_label("打开「局域网」面板，可以从同系统、高版本同事电脑下载安装包。", "muted"))
        history_title = _label("全部历史记录", "eyebrow")
        history = QTextEdit()
        history.setReadOnly(True)
        history.setFixedHeight(210)
        history.setPlainText(changelog_text())
        layout.addWidget(history_title)
        layout.addWidget(history)


class BadgeDialog(QDialog):
    def __init__(self, title: str, image_path: Path, rule: str, detail: str = "", report: dict[str, object] | None = None) -> None:
        super().__init__()
        self.title = title
        self.report = report
        self.setWindowTitle(title)
        self.setFixedWidth(620)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 28)
        layout.setSpacing(16)

        heading = _label(title, "sectionTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)

        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setFixedSize(560, 560)
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            image.setText("徽章图片未找到")
        else:
            image.setPixmap(
                pixmap.scaled(
                    560,
                    560,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        layout.addWidget(image, alignment=Qt.AlignmentFlag.AlignCenter)

        rule_label = _label(rule, "badgeRule")
        rule_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(rule_label)
        if detail:
            detail_label = _label(detail, "muted")
            detail_label.setWordWrap(True)
            detail_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(detail_label)
        if report is not None:
            export_button = QPushButton("下载排名细节")
            export_button.setObjectName("primaryButton")
            export_button.clicked.connect(self._export_report)
            layout.addWidget(export_button)

    def _export_report(self) -> None:
        if self.report is None:
            return
        start_day = self.report.get("start_day")
        end_day = self.report.get("end_day")
        if isinstance(start_day, date) and isinstance(end_day, date):
            suffix = f"{start_day:%Y%m%d}-{end_day:%Y%m%d}"
        else:
            suffix = datetime.now().strftime("%Y%m%d")
        default_name = str(Path.home() / "Downloads" / f"{self.title}-排名细节-{suffix}.xlsx")
        target, _ = QFileDialog.getSaveFileName(self, "下载排名细节", default_name, "Excel 工作簿 (*.xlsx)")
        if not target:
            return
        target_path = Path(target)
        if target_path.suffix.lower() != ".xlsx":
            target_path = target_path.with_suffix(".xlsx")
        try:
            self._write_report_xlsx(target_path)
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", f"保存 Excel 失败：{exc}")
            return
        QMessageBox.information(self, "导出完成", f"已导出：\n{target_path}")

    def _write_report_xlsx(self, path: Path) -> None:
        if self.report is None:
            return
        sheets = [
            ("排名", self._rows_from_dicts(self.report.get("ranking"))),
            ("明细", self._rows_from_dicts(self.report.get("details"))),
        ]
        sheet_xml = []
        workbook_sheets = []
        rels = []
        content_overrides = []
        for sheet_index, (sheet_name, rows) in enumerate(sheets, start=1):
            sheet_xml.append((sheet_index, self._worksheet_xml(rows)))
            workbook_sheets.append(f'<sheet name="{escape(sheet_name)}" sheetId="{sheet_index}" r:id="rId{sheet_index}"/>')
            rels.append(f'<Relationship Id="rId{sheet_index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{sheet_index}.xml"/>')
            content_overrides.append(f'<Override PartName="/xl/worksheets/sheet{sheet_index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        workbook = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(workbook_sheets)}</sheets></workbook>'
        )
        styles = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/></font><font><b/><sz val="11"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellXfs count="2"><xf fontId="0" fillId="0" borderId="0"/><xf fontId="1" fillId="0" borderId="0" applyFont="1"/></cellXfs>'
            '</styleSheet>'
        )
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f'{"".join(content_overrides)}</Types>'
        )
        root_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        )
        workbook_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(rels)}'
            f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        )
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", root_rels)
            archive.writestr("xl/workbook.xml", workbook)
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
            archive.writestr("xl/styles.xml", styles)
            for sheet_index, xml in sheet_xml:
                archive.writestr(f"xl/worksheets/sheet{sheet_index}.xml", xml)

    def _rows_from_dicts(self, value: object) -> list[list[str]]:
        if not isinstance(value, list) or not value:
            return [["暂无数据"]]
        keys: list[str] = []
        for row in value:
            if isinstance(row, dict):
                for key in row:
                    if key not in keys:
                        keys.append(str(key))
        rows = [keys]
        for row in value:
            if isinstance(row, dict):
                rows.append([str(row.get(key, "")) for key in keys])
        return rows

    def _worksheet_xml(self, rows: list[list[str]]) -> str:
        sheet_rows = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for column_index, value in enumerate(row, start=1):
                cell_ref = f"{self._excel_column(column_index)}{row_index}"
                style = ' s="1"' if row_index == 1 else ""
                cells.append(f'<c r="{cell_ref}"{style} t="inlineStr"><is><t>{escape(value)}</t></is></c>')
            sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<cols><col min="1" max="10" width="22" customWidth="1"/></cols>'
            f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
        )

    def _excel_column(self, index: int) -> str:
        value = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            value = chr(65 + remainder) + value
        return value


class ProjectLogHistoryDialog(QDialog):
    def __init__(
        self,
        member_name: str,
        logs: list[dict[str, object]],
        projects: list[dict[str, object]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{member_name} 的个人主页")
        self.resize(900, 700)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(_label(f"{member_name} 的个人主页", "sectionTitle"))
        layout.addWidget(_label(f"参与 {len(projects)} 个项目，项目日志 {len(logs)} 条。", "muted"))

        layout.addWidget(_label("参与项目", "eyebrow"))
        self.project_list = QListWidget()
        self.project_list.setObjectName("personProjectList")
        self.project_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.project_list.setFlow(QListWidget.Flow.LeftToRight)
        self.project_list.setWrapping(False)
        self.project_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.project_list.setMovement(QListWidget.Movement.Static)
        self.project_list.setGridSize(QSize(184, 124))
        self.project_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.project_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.project_list.setSpacing(10)
        self.project_list.setFixedHeight(138 if projects else 74)
        self.project_list.itemClicked.connect(self._open_project_item)
        layout.addWidget(self.project_list)
        if projects:
            for project in projects:
                self._add_project_card(project)
        else:
            item = QListWidgetItem("还没有同步到这个人的参与项目。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.project_list.addItem(item)

        layout.addWidget(_label("项目日志", "eyebrow"))
        self.log_list = QListWidget()
        self.log_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.log_list, 1)

        if not logs:
            item = QListWidgetItem("还没有同步到这个人的项目日志。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.log_list.addItem(item)
            return

        for log in logs:
            self._add_log_card(log)

    def _add_project_card(self, project: dict[str, object]) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        project_id = int(project.get("project_id", 0) or 0)
        item.setData(Qt.ItemDataRole.UserRole, project_id)
        card = QWidget()
        card.setObjectName("projectListCard")
        card.setFixedSize(170, 112)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mousePressEvent = lambda event, selected=project_id: self._open_project_id(selected)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        name = _label(str(project.get("project_name", "未知项目")), "memberName")
        name.setMaximumHeight(42)
        top.addWidget(name, 1)
        if str(project.get("project_notes", "")).strip():
            top.addWidget(self._project_notes_button(project), 0, Qt.AlignmentFlag.AlignTop)
        if str(project.get("project_link", "")).strip():
            top.addWidget(self._project_link_button(project, "primary"), 0, Qt.AlignmentFlag.AlignTop)
        if str(project.get("backup_project_link", "")).strip():
            top.addWidget(self._project_link_button(project, "backup"), 0, Qt.AlignmentFlag.AlignTop)
        if str(project.get("development_group_link", "")).strip():
            top.addWidget(self._project_link_button(project, "development_group"), 0, Qt.AlignmentFlag.AlignTop)
        if str(project.get("coordination_group_link", "")).strip():
            top.addWidget(self._project_link_button(project, "coordination_group"), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        role = str(project.get("role", "")).strip() or "未配置角色"
        owner = str(project.get("owner", "")).strip() or "未知负责人"
        days = str(project.get("joined_days", ""))
        layout.addWidget(_label(role, "compactRoleBadge"), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(_label(f"参与 {days} 天", "muted"))
        layout.addWidget(_label(f"负责人 {owner}", "muted"))
        layout.addStretch()

        item.setSizeHint(QSize(184, 124))
        self.project_list.addItem(item)
        self.project_list.setItemWidget(item, card)

    def _project_link_button(self, project: dict[str, object], kind: str) -> QPushButton:
        link_key = {
            "primary": "project_link",
            "backup": "backup_project_link",
            "development_group": "development_group_link",
            "coordination_group": "coordination_group_link",
        }.get(kind, "project_link")
        link = str(project.get(link_key, "")).strip()
        button = QPushButton()
        button.setObjectName("projectBackupLinkButton" if kind == "backup" else "projectPrimaryLinkButton")
        button.setIcon(_project_group_icon("development" if kind == "development_group" else "coordination") if kind.endswith("_group") else _project_link_icon(kind))
        button.setIconSize(QSize(16, 16))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        tooltip = {
            "primary": "打开主要项目",
            "backup": "打开备用项目",
            "development_group": "打开开发群",
            "coordination_group": "打开对接群",
        }.get(kind, "打开连接")
        button.setToolTip(tooltip)
        button.clicked.connect(lambda checked=False, selected=link, selected_kind=kind: self._open_project_link(selected, selected_kind))
        return button

    def _project_notes_button(self, project: dict[str, object]) -> QPushButton:
        name = str(project.get("project_name", "未知项目")).strip() or "未知项目"
        notes = str(project.get("project_notes", "")).strip()
        button = QPushButton()
        button.setObjectName("projectTextButton")
        button.setIcon(_project_text_icon())
        button.setIconSize(QSize(16, 16))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip("查看项目资料")
        button.clicked.connect(lambda checked=False, title=name, text=notes: _show_project_notes_dialog(self, title, text))
        return button

    def _open_project_link(self, link: str, kind: str = "primary") -> None:
        if not link:
            return
        if kind in {"development_group", "coordination_group"}:
            app_url = _dingtalk_group_app_url(link)
            if app_url.isValid() and not app_url.isEmpty() and QDesktopServices.openUrl(app_url):
                return
        url = QUrl.fromUserInput(link)
        if not url.isValid() or url.scheme().lower() not in {"http", "https", "dingtalk"}:
            QMessageBox.information(self, "连接无效", "这个项目还没有配置可打开的链接。")
            return
        QDesktopServices.openUrl(url)

    def _open_project_item(self, item: QListWidgetItem) -> None:
        project_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(project_id, int):
            self._open_project_id(project_id)

    def _open_project_id(self, project_id: int) -> None:
        if not project_id:
            return
        parent = self.parent()
        opener = getattr(parent, "_open_project_from_person_home", None)
        if callable(opener):
            self.accept()
            opener(project_id)

    def _add_log_card(self, log: dict[str, object]) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        card = QWidget()
        card.setObjectName("feedCard")
        todo_id = self._log_todo_id(log)
        if todo_id is not None:
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setToolTip("查看代办详情")
            card.mousePressEvent = lambda event, selected=todo_id: self._open_todo_detail_id(selected)  # type: ignore[method-assign]
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        created_at = self._format_log_time(str(log.get("created_at", "")))
        project_name = str(log.get("project_name", "未知项目"))
        role = str(log.get("role", "")).strip()
        content = str(log.get("content", "")).strip() or "空日志"
        meta = " · ".join(part for part in (created_at, project_name, role) if part)

        layout.addWidget(_label(meta, "eyebrow"))
        layout.addWidget(_label(content))

        item.setSizeHint(QSize(0, self._history_card_height(content)))
        self.log_list.addItem(item)
        self.log_list.setItemWidget(item, card)

    def _log_todo_id(self, log: dict[str, object]) -> int | None:
        raw = str(log.get("todo_id", "")).strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _open_todo_detail_id(self, todo_id: int) -> None:
        parent = self.parent()
        opener = getattr(parent, "_open_todo_detail_by_id", None)
        if callable(opener):
            opener(todo_id)

    def _format_log_time(self, value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value

    def _history_card_height(self, content: str) -> int:
        normalized = " ".join(content.strip().split())
        visual_width = sum(1 if ord(char) < 128 else 2 for char in normalized)
        explicit_lines = len([line for line in content.splitlines() if line.strip()])
        visual_lines = max(1, (visual_width // 72) + 1)
        lines = max(1, explicit_lines, visual_lines)
        return 66 + lines * 24


class ProjectMemberDailyDialog(QDialog):
    def __init__(
        self,
        project: Project,
        member: ProjectMember,
        reports: list[DailyReport],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{member.name} 的项目日报")
        self.resize(860, 640)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(_label(f"{member.name} 的项目日报", "sectionTitle"))
        layout.addWidget(_label(f"{project.name} · {member.role} · 共 {len(reports)} 篇日报", "muted"))

        self.report_list = QListWidget()
        self.report_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.report_list, 1)

        if not reports:
            item = QListWidgetItem("这个成员在当前项目还没有日报。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.report_list.addItem(item)
            return

        for report in reports:
            self._add_report_card(report)

    def _add_report_card(self, report: DailyReport) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        card = QWidget()
        card.setObjectName("feedCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        layout.addWidget(_label(report.created_at.strftime("%Y-%m-%d %H:%M"), "eyebrow"))
        layout.addWidget(_label(report.content.strip() or "空日报"))

        item.setSizeHint(QSize(0, self._card_height(report.content)))
        self.report_list.addItem(item)
        self.report_list.setItemWidget(item, card)

    def _card_height(self, content: str) -> int:
        normalized = " ".join(content.strip().split())
        explicit_lines = len([line for line in content.splitlines() if line.strip()])
        visual_width = sum(1 if ord(char) < 128 else 2 for char in normalized)
        visual_lines = max(1, (visual_width + 72 - 1) // 72)
        lines = max(1, explicit_lines, visual_lines)
        return 58 + lines * 24


class ProjectMetricDialog(QDialog):
    def __init__(
        self,
        project: Project,
        title: str,
        rows: list[object],
        parent: QWidget | None = None,
        open_document=None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.open_document = open_document
        self.setWindowTitle(f"{project.name} · {title}")
        self.resize(820, 640)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(_label(f"{project.name} · {title}", "sectionTitle"))
        layout.addWidget(_label(f"共 {len(rows)} 条", "muted"))

        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.list_widget, 1)

        if not rows:
            item = QListWidgetItem(f"当前项目还没有{title}。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(item)
            return

        for row in rows:
            self._add_row(row)

    def _add_row(self, row: object) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        card = QWidget()
        card.setObjectName("feedCard")
        if isinstance(row, ProjectTodo):
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setToolTip("查看代办详情")
            card.mousePressEvent = lambda event, selected=row: self._open_todo_detail(selected)  # type: ignore[method-assign]
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        body = QVBoxLayout()
        body.setSpacing(7)
        meta, content = self._row_text(row)
        if isinstance(row, ProjectTodo):
            meta_lines = [line for line in meta.splitlines() if line.strip()]
            for meta_line in meta_lines:
                body.addWidget(_label(meta_line, "eyebrow"))
        else:
            body.addWidget(_label(meta, "eyebrow"))
        body.addWidget(_label(content))
        layout.addLayout(body, 1)

        if isinstance(row, ProjectDocument) and self.open_document is not None:
            open_button = QPushButton("打开")
            open_button.setObjectName("smallButton")
            open_button.clicked.connect(lambda checked=False, selected=row: self.open_document(selected))
            layout.addWidget(open_button)

        item.setSizeHint(QSize(0, self._row_height(content, meta if isinstance(row, ProjectTodo) else "")))
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, card)

    def _row_text(self, row: object) -> tuple[str, str]:
        if isinstance(row, ProjectMember):
            return (
                row.created_at.strftime("%Y-%m-%d %H:%M"),
                f"{row.name} · {row.role}",
            )
        if isinstance(row, ProjectTodo):
            status = {
                "ui_todo": "待UI",
                "dev_todo": "待开发",
                "dev_doing": "开发中",
                "test_todo": "待测试",
                "accept_todo": "待验收",
                "done": "已完成",
                "todo": "待完成",
            }.get(row.status, "进行中")
            scope = {"personal": "个人代办", "assigned": "分配代办", "project": "项目代办"}.get(row.scope, "代办")
            lines = [
                f"{row.created_at.strftime('%Y-%m-%d %H:%M')} · {scope} · {status}",
            ]
            if row.scope == "assigned":
                lines.append(f"分配：{row.assigned_by or row.creator or '未记录'} -> {row.assignee or '未记录'}")
            elif row.completed_by:
                lines.append(f"完成人：{row.completed_by}")
            due = self._todo_due_text(row)
            if due:
                lines.append(due)
            started = self._todo_started_text(row)
            if started:
                lines.append(started)
            return (
                "\n".join(lines),
                row.title,
            )
        if isinstance(row, DailyReport):
            linked_todo = self._daily_report_todo_text(row)
            suffix = f" · {linked_todo}" if linked_todo else ""
            return (
                f"{row.created_at.strftime('%Y-%m-%d %H:%M')} · {row.member_name} · {row.role}{suffix}",
                row.content,
            )
        if isinstance(row, ProjectWeeklyReport):
            return (
                f"{row.created_at.strftime('%Y-%m-%d %H:%M')} · {row.author}",
                row.content,
            )
        if isinstance(row, ProjectDocument):
            visibility = "团队" if row.visibility == "team" else "本人"
            return (
                f"{row.created_at.strftime('%Y-%m-%d %H:%M')} · {row.doc_type} · {visibility} · {row.uploader}",
                row.title,
            )
        return ("", str(row))

    def _row_height(self, content: str, meta: str = "") -> int:
        normalized = " ".join(content.strip().split())
        explicit_lines = len([line for line in content.splitlines() if line.strip()])
        visual_width = sum(1 if ord(char) < 128 else 2 for char in normalized)
        visual_lines = max(1, (visual_width + 80 - 1) // 80)
        content_lines = max(1, explicit_lines, visual_lines)
        meta_lines = len([line for line in meta.splitlines() if line.strip()])
        return 52 + (content_lines + meta_lines) * 24

    def _open_todo_detail(self, todo: ProjectTodo) -> None:
        db = getattr(self.parent(), "db", None)
        reports = db.list_daily_reports_for_todo(todo.id, limit=1000) if db is not None else []
        TodoDetailDialog(todo, self.project.name, reports, self).exec()

    def _days_since(self, value: datetime) -> int:
        return max(1, (date.today() - value.date()).days + 1)

    def _todo_due_text(self, todo: ProjectTodo) -> str:
        if todo.due_at is None:
            return ""
        now = datetime.now()
        prefix = f"截止 {todo.due_at.strftime('%m-%d %H:%M')}"
        if todo.status == "done":
            return prefix
        delta = todo.due_at - now
        if delta.total_seconds() < 0:
            overdue_days = max(1, (now.date() - todo.due_at.date()).days + 1)
            return f"{prefix} · 已逾期 {overdue_days} 天"
        remaining_days = max(1, delta.days + (1 if delta.seconds else 0))
        return f"{prefix} · 剩 {remaining_days} 天"

    def _todo_started_text(self, todo: ProjectTodo) -> str:
        if todo.started_at is None:
            return ""
        return f"开始 {todo.started_at.strftime('%m-%d %H:%M')} · 已开始 {self._days_since(todo.started_at)} 天"

    def _daily_report_todo_text(self, report: DailyReport) -> str:
        if report.todo_id is None:
            return ""
        return f"关联代办 #{report.todo_id}"


class TodoDetailDialog(QDialog):
    def __init__(
        self,
        todo: ProjectTodo,
        project_name: str,
        reports: list[DailyReport],
        parent: QWidget | None = None,
        highlight_report_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("代办详情")
        self.setFixedWidth(620)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        layout.addWidget(_label(todo.title, "sectionTitle"))
        layout.addWidget(_label(project_name, "muted"))

        detail = QTextEdit()
        detail.setReadOnly(True)
        detail.setMinimumHeight(420)
        detail.setHtml(self._detail_html(todo, project_name, reports, highlight_report_id))
        layout.addWidget(detail)

    def _detail_html(
        self,
        todo: ProjectTodo,
        project_name: str,
        reports: list[DailyReport],
        highlight_report_id: int | None = None,
    ) -> str:
        lines = [
            "基本信息",
            f"项目：{project_name}",
            f"分配人：{todo.assigned_by or todo.creator or '未记录'}",
            f"接收人：{todo.assignee or '未记录'}",
            f"状态：{self._todo_status_text(todo)}",
            f"创建时间：{todo.created_at.strftime('%Y-%m-%d %H:%M')}",
        ]
        if todo.workflow == "dev_test_accept":
            lines.extend(
                [
                    f"UI/设计：{todo.designer or '无'}",
                    f"开发：{todo.developer or '未记录'}",
                    f"测试：{todo.tester or '未记录'}",
                    f"验收：{todo.acceptor or todo.assigned_by or '未记录'}",
                    f"当前处理人：{todo.current_handler or '已结束'}",
                ]
            )
        if todo.due_at is not None:
            lines.append(f"截止时间：{todo.due_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append(
            f"开始时间：{todo.started_at.strftime('%Y-%m-%d %H:%M')}"
            if todo.started_at is not None
            else "开始时间：未记录"
        )
        if todo.completed_at is not None:
            lines.append(f"完成时间：{todo.completed_at.strftime('%Y-%m-%d %H:%M')}")
        if todo.completed_by:
            lines.append(f"完成人：{todo.completed_by}")

        flow_lines = self._todo_flow_lines(todo)
        if flow_lines:
            lines.extend(["", "流转记录", *flow_lines])

        lines.extend(["", "关联日报"])
        parts = [f"<div style='white-space: pre-wrap;'>{escape(chr(10).join(lines))}</div>"]
        if not reports:
            parts.append("<p>暂无关联日报。</p>")
        for report in reports:
            color = "#8f2d1f" if report.id == highlight_report_id else "#23241f"
            weight = "600" if report.id == highlight_report_id else "400"
            meta = f"{report.created_at.strftime('%Y-%m-%d %H:%M')} · {report.member_name} · {report.role}"
            content = report.content.strip() or "空日报"
            parts.append(
                "<div style='white-space: pre-wrap; margin-top: 12px; "
                f"color: {color}; font-weight: {weight};'>"
                f"{escape(meta)}\n{escape(content)}</div>"
            )
        return "".join(parts)

    def _todo_status_text(self, todo: ProjectTodo) -> str:
        return {
            "ui_todo": "待UI",
            "dev_todo": "待开发",
            "dev_doing": "开发中",
            "test_todo": "待测试",
            "accept_todo": "待验收",
            "done": "已完成",
            "todo": "待完成",
        }.get(todo.status, "进行中")

    def _todo_flow_lines(self, todo: ProjectTodo) -> list[str]:
        raw = todo.flow_history.strip()
        if not raw:
            return []
        try:
            entries = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(entries, list):
            return []
        lines: list[str] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            time_text = str(item.get("time", "")).replace("T", " ")[:16]
            actor = str(item.get("actor", "")).strip() or "未记录"
            action = str(item.get("action", "")).strip() or "流转"
            handler = str(item.get("handler", "")).strip()
            handler_text = f" -> {handler}" if handler else ""
            lines.append(f"{time_text} · {actor} · {action}{handler_text}")
        return lines


class DailyReportDetailDialog(QDialog):
    def __init__(
        self,
        report: DailyReport,
        linked_todo: ProjectTodo | None,
        linked_text: str,
        can_delete: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("日报详情")
        self.setFixedWidth(620)
        self.setStyleSheet(APP_STYLE)
        self.delete_requested = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        layout.addWidget(_label("日报详情", "sectionTitle"))
        layout.addWidget(_label(f"{report.created_at.strftime('%Y-%m-%d %H:%M')} · {report.member_name} · {report.role}", "muted"))

        linked_label = _label(f"关联代办：{linked_text}" if linked_text else "未关联代办", "muted")
        linked_label.setWordWrap(True)
        layout.addWidget(linked_label)

        content = QTextEdit()
        content.setReadOnly(True)
        content.setMinimumHeight(220)
        content.setPlainText(report.content)
        layout.addWidget(content)

        actions = QHBoxLayout()
        actions.addStretch()
        if can_delete:
            delete_button = QPushButton("删除")
            delete_button.setObjectName("dangerButton")
            delete_button.clicked.connect(self._request_delete)
            actions.addWidget(delete_button)
        close = QPushButton("关闭")
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        layout.addLayout(actions)

    def _request_delete(self) -> None:
        self.delete_requested = True
        self.accept()


class TodoDailyReportDialog(QDialog):
    def __init__(self, todo: ProjectTodo, project_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("记录代办日报")
        self.setFixedWidth(560)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        layout.addWidget(_label("记录代办日报", "sectionTitle"))
        layout.addWidget(_label(f"{project_name} · {todo.title}", "muted"))

        self.editor = QTextEdit()
        self.editor.setMinimumHeight(180)
        self.editor.setPlaceholderText("记录这条代办今天的进展、问题或下一步。")
        layout.addWidget(self.editor)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

    def content(self) -> str:
        return self.editor.toPlainText().strip()


class RosterBlockedNamesDialog(QDialog):
    def __init__(self, names: list[str], blocked_names: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("配置屏蔽人员")
        self.resize(460, 520)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(_label("屏蔽人员", "sectionTitle"))
        layout.addWidget(_label("勾选后不会出现在“全员下周”表格和 Excel 中。名字含 @ 的机器账号会自动屏蔽。", "muted"))

        self.name_list = QListWidget()
        self.name_list.setAlternatingRowColors(True)
        blocked_keys = {self._name_key(name) for name in blocked_names}
        for name in names:
            if "@" in name:
                continue
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if self._name_key(name) in blocked_keys else Qt.CheckState.Unchecked)
            self.name_list.addItem(item)
        layout.addWidget(self.name_list, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

    @staticmethod
    def _name_key(name: str) -> str:
        return " ".join(name.strip().split()).casefold()

    def blocked_names(self) -> list[str]:
        return [
            self.name_list.item(index).text().strip()
            for index in range(self.name_list.count())
            if self.name_list.item(index).checkState() == Qt.CheckState.Checked
        ]


class ServerBackupDialog(QDialog):
    def __init__(self, central_sync: object, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.central_sync = central_sync
        self.setWindowTitle("服务器数据回滚")
        self.resize(1180, 760)
        self.setStyleSheet(APP_STYLE)
        self.previewed_backup = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(_label("服务器数据回滚", "sectionTitle"))
        layout.addWidget(_label("仅尉久洋可查看和操作。必须先对比备份 JSON 与当前 JSON，完成两次确认后才能回滚。", "muted"))
        self.backup_list = QListWidget()
        self.backup_list.itemClicked.connect(self._select_backup)
        self.backup_list.setMaximumHeight(180)
        layout.addWidget(self.backup_list)

        comparison = QSplitter()
        backup_panel = QWidget()
        backup_layout = QVBoxLayout(backup_panel)
        backup_layout.setContentsMargins(0, 0, 0, 0)
        backup_layout.addWidget(_label("所选备份 JSON", "eyebrow"))
        self.backup_json = QTextEdit()
        self.backup_json.setReadOnly(True)
        self.backup_json.setPlaceholderText("选择备份后点击“加载并对比”。")
        backup_layout.addWidget(self.backup_json)
        current_panel = QWidget()
        current_layout = QVBoxLayout(current_panel)
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.addWidget(_label("当前服务器 JSON", "eyebrow"))
        self.current_json = QTextEdit()
        self.current_json.setReadOnly(True)
        self.current_json.setPlaceholderText("这里会展示当前服务器数据。")
        current_layout.addWidget(self.current_json)
        comparison.addWidget(backup_panel)
        comparison.addWidget(current_panel)
        comparison.setSizes([560, 560])
        layout.addWidget(comparison, 1)

        actions = QHBoxLayout()
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self._load_backups)
        self.preview_button = QPushButton("加载并对比")
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self._preview_selected)
        self.restore_button = QPushButton("恢复所选备份")
        self.restore_button.setObjectName("dangerButton")
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self._restore_selected)
        actions.addWidget(refresh)
        actions.addWidget(self.preview_button)
        actions.addStretch()
        actions.addWidget(self.restore_button)
        layout.addLayout(actions)
        QTimer.singleShot(0, self._load_backups)

    def _load_backups(self) -> None:
        self.backup_list.clear()
        self.previewed_backup = ""
        self.backup_json.clear()
        self.current_json.clear()
        self.preview_button.setEnabled(False)
        self.restore_button.setEnabled(False)
        try:
            backups = self.central_sync.list_server_backups()  # type: ignore[attr-defined]
        except Exception as exc:
            QMessageBox.warning(self, "读取失败", f"无法读取服务器备份：{exc}")
            return
        for backup in backups:
            name = str(backup.get("name", ""))
            created_at = str(backup.get("created_at", "")).replace("T", " ")
            kind = str(backup.get("kind", "备份"))
            size_mb = int(backup.get("size", 0) or 0) / (1024 * 1024)
            item = QListWidgetItem(f"{created_at}  ·  {kind}  ·  {size_mb:.1f} MB")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(name)
            self.backup_list.addItem(item)
        self.backup_list.setCurrentRow(-1)
        self.restore_button.setEnabled(False)
        if not backups:
            item = QListWidgetItem("服务器还没有可用备份。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.backup_list.addItem(item)

    def _select_backup(self, item: QListWidgetItem) -> None:
        backup_name = str(item.data(Qt.ItemDataRole.UserRole) or "")
        self.previewed_backup = ""
        self.backup_json.clear()
        self.current_json.clear()
        self.preview_button.setEnabled(bool(backup_name))
        self.restore_button.setEnabled(False)

    def _preview_selected(self) -> None:
        item = self.backup_list.currentItem()
        backup_name = str(item.data(Qt.ItemDataRole.UserRole) or "") if item is not None else ""
        if not backup_name:
            return
        try:
            result = self.central_sync.preview_server_backup(backup_name)  # type: ignore[attr-defined]
        except Exception as exc:
            QMessageBox.warning(self, "对比失败", f"无法读取服务器 JSON：{exc}")
            return
        self.backup_json.setPlainText(json.dumps(result.get("backup_json", {}), ensure_ascii=False, indent=2))
        self.current_json.setPlainText(json.dumps(result.get("current_json", {}), ensure_ascii=False, indent=2))
        self.previewed_backup = backup_name
        self.restore_button.setEnabled(True)

    def _restore_selected(self) -> None:
        item = self.backup_list.currentItem()
        if item is None:
            return
        backup_name = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not backup_name:
            return
        if self.previewed_backup != backup_name:
            QMessageBox.information(self, "需要先对比", "请先加载并核对所选备份与当前服务器 JSON。")
            return
        message = (
            f"第一次确认：你是否已经逐项核对「{backup_name}」与当前服务器 JSON？\n\n"
            "继续后还需要手动输入备份文件名。恢复前会自动保存当前状态。"
        )
        if QMessageBox.warning(
            self,
            "确认数据回滚",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) != QMessageBox.StandardButton.Yes:
            return
        typed_name, accepted = QInputDialog.getText(
            self,
            "最终确认数据回滚",
            f"第二次确认：请输入完整备份文件名：\n{backup_name}",
        )
        if not accepted:
            return
        if typed_name.strip() != backup_name:
            QMessageBox.warning(self, "确认失败", "输入的备份文件名不一致，已取消回滚。")
            return
        try:
            result = self.central_sync.restore_server_backup(backup_name)  # type: ignore[attr-defined]
        except Exception as exc:
            QMessageBox.warning(self, "回滚失败", f"服务器没有完成恢复：{exc}")
            return
        self.central_sync.sync_now()  # type: ignore[attr-defined]
        QMessageBox.information(
            self,
            "回滚完成",
            f"服务器已恢复到：{result.get('restored', backup_name)}\n当前状态已另存为保护备份。",
        )
        self.accept()


class NextWeekRosterDialog(QDialog):
    BLOCKED_NAMES_SETTING = "rest_roster_blocked_names"

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.days = self._next_week_days()
        self.setWindowTitle("全员下周休息")
        self.resize(940, 560)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.addWidget(_label("全员下周休息", "sectionTitle"))
        title_box.addWidget(_label(f"{self.days[0].strftime('%Y-%m-%d')} 至 {self.days[-1].strftime('%Y-%m-%d')}", "muted"))
        header.addLayout(title_box)
        header.addStretch()
        self.blocked_names_button = QPushButton()
        self.blocked_names_button.clicked.connect(self._configure_blocked_names)
        header.addWidget(self.blocked_names_button)
        export_button = QPushButton("导出 Excel")
        export_button.setObjectName("primaryButton")
        export_button.clicked.connect(self._export_excel)
        header.addWidget(export_button)
        layout.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.days) + 1)
        self.table.setHorizontalHeaderLabels(["姓名", *[self._day_header(day) for day in self.days]])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setMinimumHeight(38)
        self.table.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(self.table)
        self._refresh_blocked_names_button()
        self._fill_table()

    def _fill_table(self) -> None:
        rows = self._roster_rows()
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(row[0]))
            for column, value in enumerate(row[1:], start=1):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if value == "休":
                    item.setBackground(Qt.GlobalColor.lightGray)
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 120)

    def _roster_rows(self) -> list[list[str]]:
        blocked_keys = {self._name_key(name) for name in self._blocked_names()}
        names = [
            name
            for name in self.db.known_display_names()
            if "@" not in name and self._name_key(name) not in blocked_keys
        ]
        rest_days = self.db.list_rest_days(mine_only=False)
        rest_lookup = {(item.author, item.day) for item in rest_days}
        rows: list[list[str]] = []
        for name in names:
            row = [name]
            for day in self.days:
                row.append("休" if (name, day) in rest_lookup else "早班")
            rows.append(row)
        return rows

    @staticmethod
    def _name_key(name: str) -> str:
        return " ".join(name.strip().split()).casefold()

    def _blocked_names(self) -> list[str]:
        raw = self.db.get_setting(self.BLOCKED_NAMES_SETTING) or ""
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(loaded, list):
            return []
        return [str(name).strip() for name in loaded if str(name).strip()]

    def _refresh_blocked_names_button(self) -> None:
        count = len(self._blocked_names())
        self.blocked_names_button.setText(f"屏蔽人员（{count}）" if count else "屏蔽人员")

    def _configure_blocked_names(self) -> None:
        dialog = RosterBlockedNamesDialog(
            self.db.known_display_names(),
            set(self._blocked_names()),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.db.set_setting(
            self.BLOCKED_NAMES_SETTING,
            json.dumps(dialog.blocked_names(), ensure_ascii=False),
        )
        self._refresh_blocked_names_button()
        self._fill_table()

    def _export_excel(self) -> None:
        default_name = f"下周休息安排-{self.days[0].strftime('%Y%m%d')}.xlsx"
        target, _ = QFileDialog.getSaveFileName(self, "导出 Excel", default_name, "Excel 工作簿 (*.xlsx)")
        if not target:
            return
        if not target.lower().endswith(".xlsx"):
            target = f"{target}.xlsx"
        try:
            self._write_xlsx(Path(target), [["姓名", *[self._day_header(day) for day in self.days]], *self._roster_rows()])
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", f"保存 Excel 失败：{exc}")
            return
        QMessageBox.information(self, "导出完成", f"已导出：\n{target}")

    def _write_xlsx(self, path: Path, rows: list[list[str]]) -> None:
        sheet_rows = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for column_index, value in enumerate(row, start=1):
                cell_ref = f"{self._excel_column(column_index)}{row_index}"
                style = ""
                if row_index == 1:
                    style = ' s="1"'
                elif column_index == 1:
                    style = ' s="2"'
                elif value == "休":
                    style = ' s="3"'
                cells.append(f'<c r="{cell_ref}"{style} t="inlineStr"><is><t>{escape(value)}</t></is></c>')
            sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

        worksheet = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView workbookViewId="0"><pane xSplit="1" ySplit="1" topLeftCell="B2" activePane="bottomRight" state="frozen"/></sheetView></sheetViews>'
            '<cols><col min="1" max="1" width="16" customWidth="1"/><col min="2" max="8" width="13" customWidth="1"/></cols>'
            f'<sheetData>{"".join(sheet_rows)}</sheetData>'
            '</worksheet>'
        )
        workbook = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="下周休息" sheetId="1" r:id="rId1"/></sheets></workbook>'
        )
        workbook_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        )
        root_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        )
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        )
        styles = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/></font></fonts>'
            '<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFDDEBF7"/><bgColor indexed="64"/></patternFill></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFFFE6E0"/><bgColor indexed="64"/></patternFill></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '<xf numFmtId="0" fontId="1" fillId="3" borderId="0" xfId="0" applyFill="1" applyFont="1"/></cellXfs>'
            '</styleSheet>'
        )
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", root_rels)
            archive.writestr("xl/workbook.xml", workbook)
            archive.writestr("xl/styles.xml", styles)
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
            archive.writestr("xl/worksheets/sheet1.xml", worksheet)

    def _excel_column(self, index: int) -> str:
        letters = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters

    def _next_week_days(self) -> list[date]:
        today = date.today()
        start = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return [start + timedelta(days=offset) for offset in range(7)]

    def _day_header(self, day: date) -> str:
        return f"{day.month}/{day.day} 周{'一二三四五六日'[day.weekday()]}"


class UpdateCheckWorker(QThread):
    update_found = Signal(object)
    no_update = Signal()
    failed = Signal(str)

    def run(self) -> None:
        try:
            info = check_for_update()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        if info.is_newer:
            self.update_found.emit(info)
        else:
            self.no_update.emit()


class WeeklyAIWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, central_sync: object, content: str) -> None:
        super().__init__()
        self.central_sync = central_sync
        self.content = content

    def run(self) -> None:
        try:
            summary = self.central_sync.summarize_weekly(self.content)  # type: ignore[attr-defined]
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(summary)


class MainWindow(QMainWindow):
    def __init__(
        self,
        db: Database,
        summarizer: LocalSummarizer,
        pet: DesktopPet,
        discovery: LanDiscovery | None = None,
    ) -> None:
        super().__init__()
        self.db = db
        self.summarizer = summarizer
        self.pet = pet
        self.discovery = discovery
        self.pet.set_kind(self.db.pet_kind())
        self.current_project_id: int | None = None
        self.selected_document_id: int | None = None
        self._metric_labels: dict[str, QLabel] = {}
        self._update_worker: UpdateCheckWorker | None = None
        self._weekly_ai_worker: WeeklyAIWorker | None = None
        self._notified_update_version: str | None = None
        self._last_daily_reminder_date: date | None = None
        self._last_lan_update_reminder_at: datetime | None = None
        self._last_dingtalk_id_reminder_date: date | None = None
        self._last_task_pet_animation_at: datetime | None = None
        self.lan_view_mode = "peers"
        self.todo_view_mode = "personal"
        self.current_lan_peers: list[LanPeer] = []
        self._lan_logs_signature: tuple[object, ...] | None = None
        self._lan_peer_scroll_generation = 0
        self.lan_direct_peers = self._load_lan_direct_peers()
        self.calendar_mode = "rest"
        self.rest_calendar_month = date.today().replace(day=1)
        self.selected_rest_day: date | None = None
        self._pending_project_refresh_id: int | None = None

        self.setWindowTitle(f"{self.db.display_name()} - 数智中心")
        self.resize(1360, 820)
        self.setMinimumSize(1280, 720)
        self.setStyleSheet(APP_STYLE)

        self.stack = QStackedWidget()
        self.nav_buttons: list[QPushButton] = []

        shell = QWidget()
        shell.setObjectName("shell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self._sidebar())

        self.stack.addWidget(self._my_tab())
        self.stack.addWidget(self._project_tab())
        self.stack.addWidget(self._weekly_tab())
        self.stack.addWidget(self._rest_calendar_tab())
        self.stack.addWidget(self._lan_tab())
        self.stack.addWidget(self._home_tab())
        self.stack.addWidget(self._badge_wall_tab())
        self.stack.addWidget(self._docs_tab())
        self.stack.addWidget(self._feature_guide_tab())
        shell_layout.addWidget(self.stack, 1)

        self.setCentralWidget(shell)
        self._select_page(0)
        self.db.record_activity("打开程序")
        self._refresh_badge_wall()

        if self.discovery is not None:
            self.discovery.set_direct_peer_addresses(self.lan_direct_peers)
            self.discovery.peers_changed.connect(self._refresh_peers)
            self.discovery.data_synced.connect(self._refresh_after_lan_sync)
            self.discovery.start()
            self._refresh_peers(self.discovery.sorted_peers())

        self._load_projects()
        self._load_reports()
        self._refresh_rest_calendar()
        self._refresh_document_library()
        self._start_update_timer()
        self._start_daily_report_reminder()
        self._start_weekly_report_reminder()
        self._start_lan_update_reminder()
        self._start_dingtalk_id_reminder()

    def _sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(204)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(26, 30, 22, 24)
        layout.setSpacing(12)

        self.app_title = _label(self.db.display_name(), "appTitle")
        self.app_title.setToolTip(self.db.display_name())
        subtitle = _label("数智中心", "muted")
        layout.addWidget(self.app_title)
        layout.addWidget(subtitle)
        layout.addSpacing(28)

        for index, text in enumerate(("我的面板", "项目面板", "个人周报", "日历", "局域网", "成长履历", "徽章墙", "文档库", "功能介绍")):
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=index: self._select_page(page))
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch()
        if self.db.is_current_user_name("尉久洋"):
            rollback_button = QPushButton("数据回滚")
            rollback_button.clicked.connect(self._open_server_backup_dialog)
            layout.addWidget(rollback_button)
        pet_button = QPushButton("桌宠")
        pet_button.clicked.connect(self._open_pet)
        version = QPushButton("版本")
        version.clicked.connect(self._open_version)
        settings = QPushButton("名字/PIN")
        settings.clicked.connect(self._open_settings)
        layout.addWidget(pet_button)
        layout.addWidget(version)
        layout.addWidget(settings)
        return sidebar

    def _open_server_backup_dialog(self) -> None:
        if not self.db.is_current_user_name("尉久洋"):
            QMessageBox.warning(self, "无权访问", "只有尉久洋可以查看和执行服务器数据回滚。")
            return
        central_sync = getattr(self, "central_sync", None)
        if central_sync is None or not getattr(central_sync, "server_url", ""):
            QMessageBox.information(self, "服务器未连接", "尚未发现中央数据服务器，请稍后再试。")
            return
        ServerBackupDialog(central_sync, self).exec()

    def _badge_wall_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("badgeWallPage")
        page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(42, 34, 42, 42)
        outer.setSpacing(28)

        header = QVBoxLayout()
        header.setSpacing(4)
        header.addWidget(_label("徽章墙", "sectionTitle"))
        header.addWidget(_label("把团队里的小习惯和高光时刻收集起来。", "muted"))
        outer.addLayout(header)

        self.badge_grid = QGridLayout()
        self.badge_grid.setHorizontalSpacing(34)
        self.badge_grid.setVerticalSpacing(30)
        outer.addLayout(self.badge_grid)
        outer.addStretch()

        self._add_badge_card(
            0,
            0,
            "星夜徽章",
            "moon.png",
            "starry_badge_holder",
            "上周工作最晚",
            "统计上一个完整自然周内的日报、项目周报和个人周报。每天取最晚提交的人记 1 次，次数最多者获得；次数相同取最近一次最晚提交更晚的人。",
            "starry",
        )
        self._add_badge_card(
            0,
            1,
            "启明徽章",
            "sun.png",
            "dawn_badge_holder",
            "上周最早来",
            "统计上一个完整自然周内 07:00 到 08:30 的记录和操作。每天取最早产生动作的人记 1 次，次数最多者获得；次数相同取最近一次更晚的人。",
            "dawn",
        )
        self._add_badge_card(
            0,
            2,
            "千里徽章",
            "log.png",
            "log_badge_holder",
            "上周日志记录最多",
            "统计上一个完整自然周内的日报、项目周报和个人周报。优先看是否 7 天每天都有记录；多人满足时比日志条数；条数相同再比正文总字数。",
            "log",
        )
        self._add_badge_card(
            1,
            0,
            "先锋徽章",
            "todo.png",
            "todo_badge_holder",
            "上周完成代办最多",
            "统计上一个完整自然周内完成的项目代办。按完成数量排序，数量相同取最近完成时间更晚的人。",
            "todo",
        )
        self._refresh_badge_wall()
        return page

    def _add_badge_card(
        self,
        row: int,
        column: int,
        title: str,
        image_name: str,
        holder_name: str,
        rule: str,
        detail: str,
        badge_key: str,
    ) -> None:
        item = QWidget()
        item.setObjectName("badgeItem")
        item.setFixedSize(260, 318)
        item.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(item)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setObjectName("badgeIcon")
        icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_badge_pixmap(icon, _asset_path("badges", image_name), 240)
        icon.setFixedHeight(260)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        holder = _label("暂无获得者", "badgeWinner")
        holder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        holder.setFixedHeight(30)
        setattr(self, holder_name, holder)
        layout.addWidget(holder)

        image_path = _asset_path("badges", image_name)
        open_badge = lambda event, badge_title=title, path=image_path, badge_rule=rule, badge_detail=detail, key=badge_key: self._open_badge_dialog(
            badge_title,
            path,
            badge_rule,
            badge_detail,
            key,
        )
        item.mousePressEvent = open_badge
        icon.mousePressEvent = open_badge
        self.badge_grid.addWidget(item, row, column)

    def _set_badge_pixmap(self, label: QLabel, path: Path, logical_size: int) -> None:
        source = QPixmap(str(path))
        if source.isNull():
            label.setText("徽")
            return
        device_ratio = max(1.0, self.devicePixelRatioF())
        physical_size = int(logical_size * device_ratio)
        scaled = source.scaled(
            physical_size,
            physical_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(device_ratio)
        label.setFixedSize(logical_size, logical_size)
        label.setPixmap(scaled)

    def _refresh_badge_wall(self) -> None:
        if hasattr(self, "starry_badge_holder"):
            starry_badge = self.db.starry_night_badge()
            self.starry_badge_holder.setText(str(starry_badge["name"]) if starry_badge else "暂无获得者")
        if hasattr(self, "dawn_badge_holder"):
            dawn_badge = self.db.dawn_badge()
            self.dawn_badge_holder.setText(str(dawn_badge["name"]) if dawn_badge else "暂无获得者")
        if hasattr(self, "log_badge_holder"):
            log_badge = self.db.log_badge()
            self.log_badge_holder.setText(str(log_badge["name"]) if log_badge else "暂无获得者")
        if hasattr(self, "todo_badge_holder"):
            todo_badge = self.db.todo_badge()
            self.todo_badge_holder.setText(str(todo_badge["name"]) if todo_badge else "暂无获得者")

    def _open_badge_dialog(self, title: str, image_path: Path, rule: str, detail: str, badge_key: str) -> None:
        can_view_detail = any(self.db.is_current_user_name(name) for name in SUPER_ADMIN_NAMES)
        visible_detail = detail if can_view_detail else ""
        report = self.db.badge_detail_report(badge_key) if can_view_detail else None
        BadgeDialog(title, image_path, rule, visible_detail, report).exec()

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)

    def _start_update_timer(self) -> None:
        if not configured_update_url():
            return
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(10 * 60 * 1000)
        self.update_timer.timeout.connect(self._auto_check_update)
        self.update_timer.start()
        QTimer.singleShot(10 * 1000, self._auto_check_update)

    def _start_daily_report_reminder(self) -> None:
        self.daily_reminder_timer = QTimer(self)
        self.daily_reminder_timer.setInterval(60 * 1000)
        self.daily_reminder_timer.timeout.connect(self._check_daily_report_reminder)
        self.daily_reminder_timer.start()
        QTimer.singleShot(5 * 1000, self._check_daily_report_reminder)

    def _start_weekly_report_reminder(self) -> None:
        self.weekly_reminder_timer = QTimer(self)
        self.weekly_reminder_timer.setInterval(5 * 60 * 1000)
        self.weekly_reminder_timer.timeout.connect(self._check_weekly_report_reminder)
        self.weekly_reminder_timer.start()
        QTimer.singleShot(12 * 1000, self._check_weekly_report_reminder)

    def _check_weekly_report_reminder(self) -> None:
        now = datetime.now()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        week_days = [week_start + timedelta(days=offset) for offset in range(7)]
        rest_days = {
            item.day for item in self.db.list_rest_days()
            if week_start <= item.day <= week_days[-1]
        }
        work_days = [day for day in week_days if day not in rest_days]
        if not work_days or today != work_days[-1] or now.hour < 17:
            return
        reminder_key = "last_weekly_report_reminder_week"
        if self.db.get_setting(reminder_key) == week_start.isoformat():
            return
        if any(week_start <= report.created_at.date() <= today for report in self.db.list_weekly_reports()):
            self.db.set_setting(reminder_key, week_start.isoformat())
            return
        self.db.set_setting(reminder_key, week_start.isoformat())
        self.pet.move_to_bottom_right()
        self.pet.speak("今天是你本周最后一个工作日，17:00 到啦，记得整理并保存本周周报。", mood="wave")

    def _start_dingtalk_id_reminder(self) -> None:
        self.dingtalk_id_reminder_timer = QTimer(self)
        self.dingtalk_id_reminder_timer.setInterval(30 * 60 * 1000)
        self.dingtalk_id_reminder_timer.timeout.connect(self._check_dingtalk_id_reminder)
        self.dingtalk_id_reminder_timer.start()
        QTimer.singleShot(8 * 1000, self._check_dingtalk_id_reminder)

    def _check_dingtalk_id_reminder(self) -> None:
        if self.db.dingtalk_id().strip():
            return
        today = date.today()
        last_value = self.db.get_setting("last_dingtalk_id_reminder_date")
        if last_value == today.isoformat() or self._last_dingtalk_id_reminder_date == today:
            return
        self._last_dingtalk_id_reminder_date = today
        self.db.set_setting("last_dingtalk_id_reminder_date", today.isoformat())
        self.pet.move_to_bottom_right()
        self.pet.speak("还没有设置钉钉号。去左下角「名字/PIN」里填写钉钉号，同事点聊天图标才能直接找你。", mood="wave")

    def _check_daily_report_reminder(self) -> None:
        now = datetime.now()
        today = now.date()
        if now.hour < 18:
            return
        if self._last_daily_reminder_date == today:
            return
        if self.db.today_project_logs():
            return
        self._last_daily_reminder_date = today
        self.pet.move_to_bottom_right()
        self.pet.speak("18:00 到啦，今天还没写项目日报。先记一下今天做了什么吧。")

    def _nudge_after_late_record(self) -> None:
        if datetime.now().hour < 20:
            return
        self.pet.move_to_bottom_right()
        self.pet.speak("辛苦了，工作到这么晚，要保重身体啊", mood="sleepy")

    def _start_lan_update_reminder(self) -> None:
        self.lan_update_reminder_timer = QTimer(self)
        self.lan_update_reminder_timer.setInterval(5 * 60 * 1000)
        self.lan_update_reminder_timer.timeout.connect(self._check_lan_update_reminder)
        self.lan_update_reminder_timer.start()
        QTimer.singleShot(20 * 1000, self._check_lan_update_reminder)

    def _check_lan_update_reminder(self) -> None:
        if self.discovery is None:
            return
        peers = [peer for peer in self.discovery.sorted_peers() if self._peer_has_lan_update(peer)]
        if not peers:
            return
        now = datetime.now()
        if (
            self._last_lan_update_reminder_at is not None
            and (now - self._last_lan_update_reminder_at).total_seconds() < 60 * 60
        ):
            return
        self._last_lan_update_reminder_at = now
        peer = max(peers, key=lambda item: version_tuple(self._peer_update_package_version(item)))
        package_version = self._peer_update_package_version(peer)
        self.pet.move_to_bottom_right()
        self.pet.speak(f"{peer.name} 那里有 v{package_version} 更新包，可以去局域网下载更新。", mood="wave")

    def _auto_check_update(self) -> None:
        if self._update_worker is not None and self._update_worker.isRunning():
            return
        self._update_worker = UpdateCheckWorker(self)
        self._update_worker.update_found.connect(self._notify_update_available)
        self._update_worker.start()

    def _notify_update_available(self, info: object) -> None:
        latest_version = getattr(info, "latest_version", "")
        if not latest_version or self._notified_update_version == latest_version:
            return
        self._notified_update_version = latest_version
        notes = getattr(info, "notes", "")
        download_url = getattr(info, "download_url", "")
        history = getattr(info, "history", [])
        history_text = ""
        if isinstance(history, list):
            lines: list[str] = []
            for entry in history[:5]:
                if not isinstance(entry, dict):
                    continue
                version = str(entry.get("version", "")).strip()
                note = str(entry.get("notes", "")).strip()
                if version and note:
                    lines.append(f"v{version}：{note}")
            if lines:
                history_text = "\n\n全部历史记录：\n" + "\n".join(lines)
        message = f"发现新版本 v{latest_version}。\n\n{notes}{history_text}\n\n是否打开下载地址？"
        if QMessageBox.question(self, "发现新版本", message) == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl(str(download_url)))

    def _my_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget()
        scroll.setWidget(page)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(42, 38, 42, 38)
        outer.setSpacing(22)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.addWidget(_label("我的面板", "sectionTitle"))
        title_box.addWidget(_label("集中查看参与项目、分配代办和完成提醒。", "muted"))
        header.addLayout(title_box)
        header.addStretch()
        export_week = QPushButton("导出近一周")
        export_week.clicked.connect(self._export_owned_projects_recent_week)
        header.addWidget(export_week, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(header)

        projects_panel = _panel()
        projects_layout = QVBoxLayout(projects_panel)
        projects_layout.setContentsMargins(20, 20, 20, 20)
        projects_layout.setSpacing(14)
        projects_layout.addWidget(_label("参与项目", "eyebrow"))
        self.my_projects_body = QWidget()
        self.my_projects_layout = QGridLayout(self.my_projects_body)
        self.my_projects_layout.setContentsMargins(0, 0, 0, 0)
        self.my_projects_layout.setSpacing(12)
        projects_layout.addWidget(self.my_projects_body)

        tasks_panel = _panel()
        tasks_layout = QVBoxLayout(tasks_panel)
        tasks_layout.setContentsMargins(0, 0, 0, 0)
        tasks_layout.setSpacing(0)
        self.my_tasks_body = QWidget()
        self.my_tasks_layout = QVBoxLayout(self.my_tasks_body)
        self.my_tasks_layout.setContentsMargins(0, 0, 0, 0)
        self.my_tasks_layout.setSpacing(12)
        tasks_layout.addWidget(self.my_tasks_body)

        messages_panel = _panel()
        messages_layout = QVBoxLayout(messages_panel)
        messages_layout.setContentsMargins(20, 20, 20, 20)
        messages_layout.setSpacing(14)
        messages_layout.addWidget(_label("消息提醒", "eyebrow"))
        self.my_messages_body = QWidget()
        self.my_messages_layout = QVBoxLayout(self.my_messages_body)
        self.my_messages_layout.setContentsMargins(0, 0, 0, 0)
        self.my_messages_layout.setSpacing(10)
        messages_layout.addWidget(self.my_messages_body)

        outer.addWidget(projects_panel)
        outer.addWidget(tasks_panel)
        outer.addWidget(messages_panel)
        outer.addStretch()
        return scroll

    def _export_owned_projects_recent_week(self) -> None:
        end_day = date.today()
        start_day = end_day - timedelta(days=6)
        start_at = datetime.combine(start_day, datetime.min.time())
        end_at = datetime.combine(end_day, datetime.max.time())
        owned_projects = [project for project in self.db.list_projects() if self.db.is_current_user_name(project.owner)]
        project_exports: list[dict[str, object]] = []

        for project in owned_projects:
            activities: list[dict[str, str]] = []

            def add_activity(created_at: datetime, kind: str, actor: str, content: str) -> None:
                if created_at < start_at or created_at > end_at:
                    return
                activities.append({
                    "sort_time": created_at.isoformat(timespec="microseconds"),
                    "day": created_at.strftime("%Y-%m-%d 周") + "一二三四五六日"[created_at.weekday()],
                    "time": created_at.strftime("%m-%d %H:%M"),
                    "type": kind,
                    "actor": actor.strip() or "未记录",
                    "content": " ".join(content.strip().split()) or "无内容",
                })

            for report in self.db.list_daily_reports(project.id, limit=1000):
                add_activity(report.created_at, "日报", report.member_name, report.content)
            for report in self.db.list_project_weekly_reports(project.id, limit=1000):
                add_activity(report.created_at, "项目周报", report.author, report.content)
            for member in self.db.list_project_members(project.id):
                add_activity(member.created_at, "成员记录", member.name, f"加入项目，角色：{member.role}")
            for document in self.db.list_project_documents(project.id, limit=1000):
                add_activity(document.created_at, "文档记录", document.uploader, f"上传 {document.doc_type}：{document.title}")
            for todo in self.db.list_project_todos(project.id, include_completed=True):
                add_activity(todo.created_at, "代办记录", todo.creator, f"创建代办：{todo.title}")
                try:
                    flow_entries = json.loads(todo.flow_history) if todo.flow_history.strip() else []
                except json.JSONDecodeError:
                    flow_entries = []
                if isinstance(flow_entries, list):
                    for entry in flow_entries:
                        if not isinstance(entry, dict):
                            continue
                        try:
                            happened_at = datetime.fromisoformat(str(entry.get("time", "")))
                        except ValueError:
                            continue
                        action = str(entry.get("action", "项目流转"))
                        handler = str(entry.get("handler", "")).strip()
                        suffix = f" → {handler}" if handler else ""
                        add_activity(happened_at, "项目进展流", str(entry.get("actor", "")), f"{todo.title}：{action}{suffix}")
                if todo.completed_at is not None and not todo.flow_history.strip():
                    add_activity(todo.completed_at, "完成代办", todo.completed_by, todo.title)

            activities.sort(key=lambda item: item["sort_time"])
            project_exports.append({
                "name": project.name,
                "owner": project.owner,
                "status": project.status,
                "description": project.description,
                "activities": activities,
            })

        default_name = str(Path.home() / "Downloads" / f"负责项目近一周进展-{end_day:%Y%m%d}.md")
        target, _ = QFileDialog.getSaveFileName(self, "导出近一周项目进展", default_name, "Markdown 文档 (*.md)")
        if not target:
            return
        target_path = Path(target)
        if target_path.suffix.lower() != ".md":
            target_path = target_path.with_suffix(".md")
        try:
            from .markdown_export import write_owned_projects_weekly_markdown

            write_owned_projects_weekly_markdown(
                target_path,
                self.db.display_name(),
                start_day,
                end_day,
                project_exports,
            )
        except (ImportError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "导出失败", f"生成 Markdown 文档失败：{exc}")
            return
        QMessageBox.information(self, "导出完成", f"已导出：\n{target_path}")

    def _project_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget()
        page.setMinimumWidth(1020)
        scroll.setWidget(page)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(34, 22, 34, 30)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title_box.addWidget(_label("项目面板", "sectionTitle"))
        self.project_sync_hint = _label("项目数据会通过局域网同步。", "muted")
        title_box.addWidget(self.project_sync_hint)
        header.addLayout(title_box)
        header.addStretch()
        show_page = QPushButton("自己")
        show_page.setCheckable(True)
        show_page.clicked.connect(lambda checked=False: self._select_project_scope("mine"))
        all_page = QPushButton("全部")
        all_page.setCheckable(True)
        all_page.clicked.connect(lambda checked=False: self._select_project_scope("all"))
        config_page = QPushButton("配置")
        config_page.setCheckable(True)
        config_page.clicked.connect(lambda checked=False: self._select_project_mode(1))
        self.project_scope_buttons = {"mine": show_page, "all": all_page}
        self.project_config_button = config_page
        self.project_scope_value = "mine"
        header.addWidget(show_page)
        header.addWidget(all_page)
        header.addWidget(config_page)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self._manual_project_refresh)
        header.addWidget(refresh)
        outer.addLayout(header)

        splitter = QSplitter()
        outer.addWidget(splitter)

        left = _panel()
        left.setMinimumWidth(230)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(12)

        project_list_header = QHBoxLayout()
        project_list_header.setContentsMargins(0, 0, 0, 0)
        project_list_header.setSpacing(6)
        self.project_search_input = QLineEdit()
        self.project_search_input.setObjectName("projectSearchInput")
        self.project_search_input.setPlaceholderText("搜索项目")
        self.project_search_input.returnPressed.connect(self._search_projects)
        project_list_header.addWidget(self.project_search_input, 1)
        clear_project_search = QPushButton("×")
        clear_project_search.setObjectName("projectSearchButton")
        clear_project_search.setToolTip("清空搜索")
        clear_project_search.clicked.connect(self._clear_project_search)
        project_list_header.addWidget(clear_project_search)
        left_layout.addLayout(project_list_header)
        self.project_list = QListWidget()
        self.project_list.setObjectName("projectList")
        self.project_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.project_list.setFixedHeight(390)
        self.project_list.itemClicked.connect(self._select_project_item)
        left_layout.addWidget(self.project_list)
        left_layout.addSpacing(10)
        left_layout.addWidget(_label("新建项目", "eyebrow"))
        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText("项目名称")
        self.project_desc = QTextEdit()
        self.project_desc.setFixedHeight(120)
        self.project_desc.setPlaceholderText("项目目标、范围或当前阶段")
        add_project = QPushButton("创建项目")
        add_project.setObjectName("primaryButton")
        add_project.clicked.connect(self._create_project)
        left_layout.addWidget(self.project_name)
        left_layout.addWidget(self.project_desc)
        left_layout.addWidget(add_project)
        left_layout.addStretch()

        middle = QWidget()
        middle.setMinimumWidth(480)
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(0)
        self.project_content_stack = QStackedWidget()
        middle_layout.addWidget(self.project_content_stack)

        overview_page = QWidget()
        overview_layout = QVBoxLayout(overview_page)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(14)
        hero = QWidget()
        hero.setObjectName("heroPanel")
        hero.setFixedHeight(PROJECT_HERO_HEIGHT)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(10)
        self.project_status = _label("推进中", "eyebrow")
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self.project_title = _label("选择一个项目", "heroTitle")
        self.project_notes_button = QPushButton()
        self.project_notes_button.setObjectName("projectTextButton")
        self.project_notes_button.setIcon(_project_text_icon())
        self.project_notes_button.setIconSize(QSize(16, 16))
        self.project_notes_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.project_notes_button.setToolTip("查看项目资料")
        self.project_notes_button.clicked.connect(lambda checked=False: self._open_current_project_notes())
        self.project_notes_button.setVisible(False)
        self.project_primary_link_button = QPushButton()
        self.project_primary_link_button.setObjectName("projectPrimaryLinkButton")
        self.project_primary_link_button.setIcon(_project_link_icon("primary"))
        self.project_primary_link_button.setIconSize(QSize(16, 16))
        self.project_primary_link_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.project_primary_link_button.setToolTip("打开主要项目")
        self.project_primary_link_button.clicked.connect(lambda checked=False: self._open_current_project_link("primary"))
        self.project_primary_link_button.setVisible(False)
        self.project_backup_link_button = QPushButton()
        self.project_backup_link_button.setObjectName("projectBackupLinkButton")
        self.project_backup_link_button.setIcon(_project_link_icon("backup"))
        self.project_backup_link_button.setIconSize(QSize(16, 16))
        self.project_backup_link_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.project_backup_link_button.setToolTip("打开备用项目")
        self.project_backup_link_button.clicked.connect(lambda checked=False: self._open_current_project_link("backup"))
        self.project_backup_link_button.setVisible(False)
        self.project_development_group_button = QPushButton()
        self.project_development_group_button.setObjectName("projectPrimaryLinkButton")
        self.project_development_group_button.setIcon(_project_group_icon("development"))
        self.project_development_group_button.setIconSize(QSize(16, 16))
        self.project_development_group_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.project_development_group_button.setToolTip("打开开发群")
        self.project_development_group_button.clicked.connect(lambda checked=False: self._open_current_project_link("development_group"))
        self.project_development_group_button.setVisible(False)
        self.project_coordination_group_button = QPushButton()
        self.project_coordination_group_button.setObjectName("projectBackupLinkButton")
        self.project_coordination_group_button.setIcon(_project_group_icon("coordination"))
        self.project_coordination_group_button.setIconSize(QSize(16, 16))
        self.project_coordination_group_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.project_coordination_group_button.setToolTip("打开对接群")
        self.project_coordination_group_button.clicked.connect(lambda checked=False: self._open_current_project_link("coordination_group"))
        self.project_coordination_group_button.setVisible(False)
        title_row.addWidget(self.project_title, 1)
        title_row.addWidget(self.project_notes_button, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.project_primary_link_button, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.project_backup_link_button, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.project_development_group_button, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.project_coordination_group_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.project_description = _label("项目负责人可以在这里查看所有日报、维护项目周报，并归档项目文档。", "muted")
        hero_layout.addWidget(self.project_status)
        hero_layout.addLayout(title_row)
        hero_layout.addWidget(self.project_description)
        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.metric_members = self._metric_card("成员", "0")
        self.metric_todos = self._metric_card("代办", "0")
        self.metric_daily = self._metric_card("日报", "0")
        self.metric_weekly = self._metric_card("周报", "0")
        self.metric_decks = self._metric_card("文档", "0")
        for card in (self.metric_members, self.metric_todos, self.metric_daily, self.metric_weekly, self.metric_decks):
            metrics.addWidget(card)
        hero_layout.addLayout(metrics)
        overview_layout.addWidget(hero)

        member_panel = _panel()
        member_panel.setFixedHeight(PROJECT_HERO_HEIGHT)
        member_layout = QVBoxLayout(member_panel)
        member_layout.setContentsMargins(18, 18, 18, 18)
        member_layout.setSpacing(12)
        member_layout.addWidget(_label("项目成员与角色", "eyebrow"))
        member_scroll = QScrollArea()
        member_scroll.setWidgetResizable(True)
        member_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        member_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        member_scroll.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.member_cards = QWidget()
        self.member_cards_layout = QGridLayout(self.member_cards)
        self.member_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.member_cards_layout.setSpacing(10)
        self.member_cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        member_scroll.setWidget(self.member_cards)
        member_layout.addWidget(member_scroll, 1)

        self.progress_panel = _panel()
        progress_panel = self.progress_panel
        progress_panel.setFixedHeight(PROJECT_TASK_SECTION_HEIGHT + PROJECT_DAILY_SECTION_HEIGHT + 14 + 36)
        progress_layout = QVBoxLayout(progress_panel)
        progress_layout.setContentsMargins(18, 18, 18, 18)
        progress_layout.setSpacing(14)

        product_feed_panel = QWidget()
        product_feed_panel.setFixedHeight(PROJECT_TASK_SECTION_HEIGHT)
        product_feed_layout = QVBoxLayout(product_feed_panel)
        product_feed_layout.setContentsMargins(0, 0, 0, 0)
        product_feed_layout.setSpacing(8)
        product_feed_layout.addWidget(_label("项目进展流", "eyebrow"))
        self.product_feed = QListWidget()
        self.product_feed.setMinimumHeight(0)
        product_feed_layout.addWidget(self.product_feed, 1)

        developer_feed_panel = QWidget()
        developer_feed_panel.setFixedHeight(PROJECT_DAILY_SECTION_HEIGHT)
        developer_feed_layout = QVBoxLayout(developer_feed_panel)
        developer_feed_layout.setContentsMargins(0, 0, 0, 0)
        developer_feed_layout.setSpacing(8)
        developer_feed_layout.addWidget(_label("日报流", "eyebrow"))
        self.developer_feed = QListWidget()
        self.developer_feed.setObjectName("dailyReportFeed")
        self.developer_feed.setMinimumHeight(0)
        self.developer_feed.setSpacing(8)
        developer_feed_layout.addWidget(self.developer_feed, 1)

        progress_layout.addWidget(product_feed_panel)
        progress_layout.addWidget(developer_feed_panel)

        self.config_project_panel = _panel()
        self.config_project_panel.setMinimumHeight(500)
        config_project_layout = QVBoxLayout(self.config_project_panel)
        config_project_layout.setContentsMargins(18, 18, 18, 18)
        config_project_layout.setSpacing(10)
        config_project_layout.addWidget(_label("项目名称", "eyebrow"))
        self.config_project_name = QLineEdit()
        self.config_project_name.setPlaceholderText("项目名称")
        config_project_layout.addWidget(self.config_project_name)
        config_project_layout.addWidget(_label("项目简介", "eyebrow"))
        self.config_project_description = QTextEdit()
        self.config_project_description.setPlaceholderText("项目目标、范围、当前进展或代办。")
        self.config_project_description.setFixedHeight(112)
        self.config_project_link = QLineEdit()
        self.config_project_link.setPlaceholderText("主要项目连接，例如 https://example.com")
        self.config_project_backup_link = QLineEdit()
        self.config_project_backup_link.setPlaceholderText("备用项目连接，例如 https://preview.example.com")
        self.config_development_group_link = QLineEdit()
        self.config_development_group_link.setPlaceholderText("开发钉钉群链接")
        self.config_coordination_group_link = QLineEdit()
        self.config_coordination_group_link.setPlaceholderText("对接钉钉群链接")
        self.config_project_notes = AutoHeightTextEdit(96)
        self.config_project_notes.setPlaceholderText("项目地址、启动命令、测试账号、部署说明等。")
        self.config_project_notes_label = _label("项目文本资料", "eyebrow")
        self.save_project_description_button = QPushButton("保存项目配置")
        self.save_project_description_button.setObjectName("primaryButton")
        self.save_project_description_button.clicked.connect(self._save_project_description)
        config_project_layout.addWidget(self.config_project_description)
        config_project_layout.addWidget(_label("主要项目连接", "eyebrow"))
        config_project_layout.addWidget(self.config_project_link)
        config_project_layout.addWidget(_label("备用项目连接", "eyebrow"))
        config_project_layout.addWidget(self.config_project_backup_link)
        config_project_layout.addWidget(_label("开发群", "eyebrow"))
        config_project_layout.addWidget(self.config_development_group_link)
        config_project_layout.addWidget(_label("对接群", "eyebrow"))
        config_project_layout.addWidget(self.config_coordination_group_link)
        config_project_layout.addWidget(self.config_project_notes_label)
        config_project_layout.addWidget(self.config_project_notes)
        config_project_layout.addWidget(self.save_project_description_button)
        self.config_project_panel.setVisible(False)

        overview_layout.addWidget(progress_panel)
        overview_layout.addWidget(self.config_project_panel)
        overview_layout.addStretch()
        self.project_content_stack.addWidget(overview_page)
        self.project_content_stack.addWidget(self._deck_detail_page())

        self.project_side_stack = QStackedWidget()
        self.project_side_stack.setMinimumWidth(380)
        self.project_side_stack.setMaximumWidth(520)

        display_side = QWidget()
        display_side_layout = QVBoxLayout(display_side)
        display_side_layout.setContentsMargins(0, 0, 0, 0)
        display_side_layout.setSpacing(14)

        config_side = QWidget()
        config_side_layout = QVBoxLayout(config_side)
        config_side_layout.setContentsMargins(0, 0, 0, 0)
        config_side_layout.setSpacing(14)

        member_form = _panel()
        member_form_layout = QVBoxLayout(member_form)
        member_form_layout.setContentsMargins(18, 18, 18, 18)
        member_form_layout.setSpacing(10)
        member_form_layout.addWidget(_label("配置成员", "eyebrow"))
        self.member_name = QLineEdit()
        self.member_name.setPlaceholderText("姓名，例如 张三")
        self.member_role = QComboBox()
        self.member_role.addItems(["前端开发", "后端开发", "数据开发", "算法", "UI/设计", "测试", "产品经理", "运营", "设计", "运维"])
        self.add_member_button = QPushButton("添加成员")
        self.add_member_button.clicked.connect(self._add_project_member)
        member_form_layout.addWidget(self.member_name)
        member_form_layout.addWidget(self.member_role)
        member_form_layout.addWidget(self.add_member_button)

        owner_form = _panel()
        owner_form_layout = QVBoxLayout(owner_form)
        owner_form_layout.setContentsMargins(18, 18, 18, 18)
        owner_form_layout.setSpacing(10)
        owner_form_layout.addWidget(_label("更改负责人", "eyebrow"))
        self.project_owner_select = QComboBox()
        self.save_project_owner_button = QPushButton("保存负责人")
        self.save_project_owner_button.clicked.connect(self._save_project_owner)
        owner_form_layout.addWidget(self.project_owner_select)
        owner_form_layout.addWidget(self.save_project_owner_button)

        config_member_panel = _panel()
        config_member_layout = QVBoxLayout(config_member_panel)
        config_member_layout.setContentsMargins(18, 18, 18, 18)
        config_member_layout.setSpacing(10)
        config_member_layout.addWidget(_label("删除成员", "eyebrow"))
        self.config_member_list = QListWidget()
        self.config_member_list.setMinimumHeight(220)
        self.config_member_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        config_member_layout.addWidget(self.config_member_list)

        project_danger = _panel()
        project_danger_layout = QVBoxLayout(project_danger)
        project_danger_layout.setContentsMargins(18, 18, 18, 18)
        project_danger_layout.setSpacing(10)
        project_danger_layout.addWidget(_label("项目操作", "eyebrow"))
        self.delete_project_button = QPushButton("删除项目")
        self.delete_project_button.setObjectName("dangerButton")
        self.delete_project_button.clicked.connect(self._delete_current_project)
        project_danger_layout.addWidget(self.delete_project_button)

        self.todo_panel = _panel()
        todo_panel = self.todo_panel
        todo_panel.setFixedHeight(PROJECT_TASK_SIDE_HEIGHT)
        todo_layout = QVBoxLayout(todo_panel)
        todo_layout.setContentsMargins(18, 18, 18, 18)
        todo_layout.setSpacing(10)
        todo_header = QHBoxLayout()
        self.personal_todo_button = QPushButton("个人代办")
        self.personal_todo_button.setCheckable(True)
        self.personal_todo_button.clicked.connect(lambda checked=False: self._set_todo_view("personal"))
        self.assigned_todo_button = QPushButton("分配代办")
        self.assigned_todo_button.setCheckable(True)
        self.assigned_todo_button.clicked.connect(lambda checked=False: self._set_todo_view("assigned"))
        self.project_todo_button = QPushButton("项目代办")
        self.project_todo_button.setCheckable(True)
        self.project_todo_button.clicked.connect(lambda checked=False: self._set_todo_view("project"))
        todo_header.addWidget(self.personal_todo_button)
        todo_header.addWidget(self.assigned_todo_button)
        todo_header.addWidget(self.project_todo_button)
        todo_header.addStretch()
        self.todo_count_label = _label("0 个待完成", "muted")
        todo_header.addWidget(self.todo_count_label)
        todo_layout.addLayout(todo_header)
        self.assigned_todo_assignee = QComboBox()
        self.assigned_todo_assignee.setVisible(False)
        todo_layout.addWidget(self.assigned_todo_assignee)
        self.assigned_todo_deadline_days: int | None = None
        self.assigned_todo_deadline_buttons: dict[int, QPushButton] = {}
        self.assigned_todo_deadline_row = QWidget()
        deadline_layout = QHBoxLayout(self.assigned_todo_deadline_row)
        deadline_layout.setContentsMargins(0, 0, 0, 0)
        deadline_layout.setSpacing(8)
        deadline_layout.addWidget(_label("期限", "eyebrow"))
        for label, days in (("1天", 1), ("2天", 2), ("1周", 7), ("2周", 14)):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("smallButton")
            button.clicked.connect(lambda checked=False, value=days: self._toggle_assigned_deadline(value))
            self.assigned_todo_deadline_buttons[days] = button
            deadline_layout.addWidget(button)
        deadline_layout.addStretch()
        self.assigned_todo_deadline_row.setVisible(False)
        todo_layout.addWidget(self.assigned_todo_deadline_row)
        todo_input_row = QHBoxLayout()
        todo_input_row.setSpacing(8)
        self.project_todo_input = QLineEdit()
        self.project_todo_input.setPlaceholderText("新增一个代办")
        self.add_todo_button = QPushButton("添加")
        self.add_todo_button.clicked.connect(self._add_project_todo)
        todo_input_row.addWidget(self.project_todo_input, 1)
        todo_input_row.addWidget(self.add_todo_button)
        todo_layout.addLayout(todo_input_row)
        self.todo_board = QListWidget()
        self.todo_board.setMinimumHeight(168)
        self.todo_board.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        todo_layout.addWidget(self.todo_board, 1)

        self.activity_forms_panel = _panel()
        self.activity_forms_panel.setFixedHeight(PROJECT_DAILY_SIDE_HEIGHT)
        activity_forms_layout = QVBoxLayout(self.activity_forms_panel)
        activity_forms_layout.setContentsMargins(18, 18, 18, 18)
        activity_forms_layout.setSpacing(12)

        self.daily_form = QWidget()
        daily_form = self.daily_form
        daily_layout = QVBoxLayout(daily_form)
        daily_layout.setContentsMargins(0, 0, 0, 0)
        daily_layout.setSpacing(8)
        daily_layout.addWidget(_label("日报", "eyebrow"))
        self.daily_member_label = _label("当前身份：自己", "muted")
        self.daily_todo_link = QComboBox()
        self.daily_todo_link.addItem("不关联代办", 0)
        self.daily_editor = QTextEdit()
        self.daily_editor.setFixedHeight(76)
        self.daily_editor.setPlaceholderText("今天完成了什么、遇到什么阻塞、明天准备做什么。")
        self.save_daily_button = QPushButton("保存日报")
        self.save_daily_button.setObjectName("primaryButton")
        self.save_daily_button.clicked.connect(self._save_daily_report)
        daily_layout.addWidget(self.daily_member_label)
        daily_layout.addWidget(self.daily_todo_link)
        daily_layout.addWidget(self.daily_editor)
        daily_layout.addWidget(self.save_daily_button)

        self.weekly_form = QWidget()
        weekly_form = self.weekly_form
        weekly_layout = QVBoxLayout(weekly_form)
        weekly_layout.setContentsMargins(0, 0, 0, 0)
        weekly_layout.setSpacing(8)
        self.weekly_form_title = _label("负责人周报 / 文档", "eyebrow")
        weekly_layout.addWidget(self.weekly_form_title)
        self.project_weekly_editor = QTextEdit()
        self.project_weekly_editor.setFixedHeight(70)
        self.project_weekly_editor.setPlaceholderText("本周项目整体进度、风险、下周计划。")
        self.save_project_weekly_button = QPushButton("保存项目周报")
        self.save_project_weekly_button.clicked.connect(self._save_project_weekly_report)
        self.project_document_type = QComboBox()
        self.project_document_type.addItems(DOCUMENT_TYPES)
        self.project_document_type.setCurrentText("项目汇报PPT")
        self.project_document_visibility = QComboBox()
        self.project_document_visibility.addItem("团队文档", "team")
        self.project_document_visibility.addItem("本人文档", "personal")
        self.upload_deck_button = QPushButton("上传项目文档")
        self.upload_deck_button.clicked.connect(self._upload_project_deck)
        weekly_layout.addWidget(self.project_weekly_editor)
        weekly_layout.addWidget(self.save_project_weekly_button)
        weekly_layout.addWidget(self.project_document_type)
        weekly_layout.addWidget(self.project_document_visibility)
        weekly_layout.addWidget(self.upload_deck_button)
        activity_forms_layout.addWidget(daily_form)
        activity_forms_layout.addWidget(weekly_form)
        activity_forms_layout.addStretch()

        display_side_layout.addWidget(member_panel, 0, Qt.AlignmentFlag.AlignTop)
        display_side_layout.addWidget(todo_panel, 0, Qt.AlignmentFlag.AlignTop)
        display_side_layout.addWidget(self.activity_forms_panel, 0, Qt.AlignmentFlag.AlignTop)
        display_side_layout.addStretch()
        config_side_layout.addWidget(member_form)
        config_side_layout.addWidget(owner_form)
        config_side_layout.addWidget(project_danger)
        config_side_layout.addWidget(config_member_panel)
        config_side_layout.addStretch()
        config_scroll = QScrollArea()
        config_scroll.setWidgetResizable(True)
        config_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        config_scroll.setWidget(config_side)
        self.project_side_stack.addWidget(display_side)
        self.project_side_stack.addWidget(config_scroll)

        splitter.addWidget(left)
        splitter.addWidget(middle)
        splitter.addWidget(self.project_side_stack)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([260, 560, 430])
        self._select_project_scope("mine")
        self._select_project_mode(0)
        return scroll

    def _deck_detail_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        hero = QWidget()
        hero.setObjectName("darkPanel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(26, 24, 26, 24)
        hero_layout.setSpacing(12)
        back = QPushButton("返回项目面板")
        back.clicked.connect(self._show_project_overview)
        back.setFixedWidth(130)
        self.deck_detail_title = _label("项目文档", "heroTitle")
        self.deck_detail_meta = _label("选择项目进展流里的文档后，会在这里显示。", "muted")
        hero_layout.addWidget(back)
        hero_layout.addWidget(_label("文档详情", "eyebrow"))
        hero_layout.addWidget(self.deck_detail_title)
        hero_layout.addWidget(self.deck_detail_meta)

        detail = _panel()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(22, 22, 22, 22)
        detail_layout.setSpacing(14)
        detail_layout.addWidget(_label("文件信息", "eyebrow"))
        self.deck_detail_path = QTextEdit()
        self.deck_detail_path.setReadOnly(True)
        self.deck_detail_path.setFixedHeight(96)
        detail_layout.addWidget(self.deck_detail_path)

        actions = QHBoxLayout()
        self.open_deck_button = QPushButton("打开文档")
        self.open_deck_button.setObjectName("primaryButton")
        self.open_deck_button.clicked.connect(self._open_selected_deck_file)
        actions.addWidget(self.open_deck_button)
        actions.addStretch()
        detail_layout.addLayout(actions)

        layout.addWidget(hero)
        layout.addWidget(detail)
        layout.addStretch()
        return page

    def _metric_card(self, title: str, value: str) -> QWidget:
        card = _soft_panel()
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)
        value_label = _label(value, "metricValue")
        title_label = _label(title, "muted")
        layout.addWidget(value_label)
        layout.addWidget(title_label)
        self._metric_labels[title] = value_label
        card.setProperty("metricTitle", title)
        card.mousePressEvent = lambda event, selected=title: self._open_project_metric(selected)
        return card

    def _set_metric(self, card: QWidget, value: int) -> None:
        title = card.property("metricTitle")
        label = self._metric_labels.get(str(title))
        if label is not None:
            label.setText(str(value))

    def _open_project_metric(self, title: str) -> None:
        project = self._current_project()
        if project is None:
            return
        rows: list[object]
        if title == "成员":
            rows = self.db.list_project_members(project.id)
        elif title == "代办":
            rows = self.db.list_project_todos(project.id)
        elif title == "日报":
            rows = self.db.list_daily_reports(project.id, limit=1000)
        elif title == "周报":
            rows = self.db.list_project_weekly_reports(project.id, limit=1000)
        elif title == "文档":
            rows = self.db.list_project_documents(project.id, limit=1000)
        else:
            return
        dialog = ProjectMetricDialog(
            project,
            title,
            rows,
            self,
            open_document=self._open_deck_file if title == "文档" else None,
        )
        dialog.exec()

    def _load_projects(self) -> None:
        if not hasattr(self, "project_list"):
            return
        previous_scroll = self.project_list.verticalScrollBar().value()
        previous_project_id = self.current_project_id
        self.project_list.clear()
        projects = self._visible_projects()
        should_restore_scroll = previous_project_id is not None and any(
            project.id == previous_project_id for project in projects
        )
        for project in projects:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, project.id)
            item.setSizeHint(QSize(0, 82))
            self.project_list.addItem(item)
            self.project_list.setItemWidget(item, self._project_list_card(project, project.id == self.current_project_id))
        if projects:
            selected_id = self.current_project_id or projects[0].id
            if all(project.id != selected_id for project in projects):
                selected_id = projects[0].id
            for index in range(self.project_list.count()):
                item = self.project_list.item(index)
                if item.data(Qt.ItemDataRole.UserRole) == selected_id:
                    self.project_list.setCurrentItem(item)
                    self.current_project_id = selected_id
                    break
            self._refresh_project_workspace()
        else:
            self.current_project_id = None
            self._clear_project_workspace()
        if should_restore_scroll:
            QTimer.singleShot(0, lambda value=previous_scroll: self._restore_project_list_scroll(value))
        self._update_project_sync_hint()
        self._refresh_my_panel()

    def _project_page_has_edit_focus(self) -> bool:
        if not hasattr(self, "stack") or self.stack.currentIndex() != 1:
            return False
        focused = self.focusWidget()
        if focused is None:
            return False
        containers = [
            getattr(self, "project_content_stack", None),
            getattr(self, "project_side_stack", None),
            getattr(self, "project_list", None),
        ]
        if not any(container is not None and (focused is container or container.isAncestorOf(focused)) for container in containers):
            return False
        widget: QWidget | None = focused
        while widget is not None:
            if isinstance(widget, (QLineEdit, QTextEdit, QComboBox)):
                return True
            widget = widget.parentWidget()
        return False

    def _restore_project_list_scroll(self, value: int) -> None:
        if not hasattr(self, "project_list"):
            return
        scroll_bar = self.project_list.verticalScrollBar()
        scroll_bar.setValue(min(value, scroll_bar.maximum()))

    def _project_list_card(self, project: Project, active: bool = False) -> QWidget:
        card = QWidget()
        card.setObjectName("projectListCardActive" if active else "projectListCard")
        card.setProperty("projectId", project.id)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)
        title = _label(project.name, "memberName")
        title.setWordWrap(True)
        title_row.addWidget(title, 1)
        if project.project_notes and self._can_view_project_notes(project):
            title_row.addWidget(self._project_notes_button(project), 0, Qt.AlignmentFlag.AlignTop)
        if project.project_link:
            title_row.addWidget(self._project_link_button(project, "primary"), 0, Qt.AlignmentFlag.AlignTop)
        if project.backup_project_link:
            title_row.addWidget(self._project_link_button(project, "backup"), 0, Qt.AlignmentFlag.AlignTop)
        if project.development_group_link:
            title_row.addWidget(self._project_link_button(project, "development_group"), 0, Qt.AlignmentFlag.AlignTop)
        if project.coordination_group_link:
            title_row.addWidget(self._project_link_button(project, "coordination_group"), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(title_row)
        owner_row = QHBoxLayout()
        owner_row.setContentsMargins(0, 0, 0, 0)
        owner_row.setSpacing(4)
        owner_row.addWidget(_label("负责人", "muted"))
        owner_row.addWidget(self._name_with_chat(project.owner))
        owner_row.addStretch()
        layout.addLayout(owner_row)
        return card

    def _refresh_project_list_active_state(self) -> None:
        if not hasattr(self, "project_list"):
            return
        for index in range(self.project_list.count()):
            item = self.project_list.item(index)
            widget = self.project_list.itemWidget(item)
            if widget is None:
                continue
            active = item.data(Qt.ItemDataRole.UserRole) == self.current_project_id
            widget.setObjectName("projectListCardActive" if active else "projectListCard")
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _update_project_sync_hint(self, message: str | None = None) -> None:
        if not hasattr(self, "project_sync_hint"):
            return
        total = len(self.db.list_projects())
        visible = len(self._visible_projects())
        scope = "全部" if getattr(self, "project_scope_value", "mine") == "all" else "自己"
        source = "服务器数据" if getattr(self, "central_sync", None) is not None else "本机已同步"
        base = f"{scope}视角：显示 {visible} / {source} {total} 个项目。"
        self.project_sync_hint.setText(f"{message} · {base}" if message else base)

    def _manual_project_refresh(self) -> None:
        central_sync = getattr(self, "central_sync", None)
        if central_sync is not None:
            central_sync.sync_now()
            message = "已请求中央数据服务同步。"
        else:
            message = "已刷新本机项目。"
        if self.discovery is not None:
            self.discovery.announce_burst()
            started_count = self.discovery.request_peer_snapshot_refresh()
            if started_count:
                message = f"已开始后台同步 {started_count} 位同事，界面不会卡住。"
            elif central_sync is None:
                message = "已刷新，没有发现比本机更新的同事数据。"
        self._refresh_after_lan_sync()
        if self.discovery is not None:
            self._refresh_peers(self.discovery.sorted_peers())
        self._update_project_sync_hint(message)

    def _visible_projects(self) -> list[Project]:
        projects = self.db.list_projects()
        if getattr(self, "project_scope_value", "mine") != "all":
            projects = [project for project in projects if self._project_involves_current_user(project)]
        keyword = getattr(self, "project_search_keyword", "").strip().casefold()
        if keyword:
            projects = [
                project for project in projects
                if keyword in project.name.casefold() or keyword in project.owner.casefold()
            ]
        return projects

    def _search_projects(self) -> None:
        self.project_search_keyword = self.project_search_input.text()
        self._load_projects()

    def _clear_project_search(self) -> None:
        self.project_search_input.clear()
        self.project_search_keyword = ""
        self._load_projects()

    def _project_involves_current_user(self, project: Project) -> bool:
        if self.db.is_current_user_name(project.owner):
            return True
        return any(
            self.db.is_current_user_name(member.name)
            for member in self.db.list_project_members(project.id)
        )

    def _can_view_project_notes(self, project: Project) -> bool:
        return self._is_super_admin() or self._project_involves_current_user(project)

    def _projects_with_notes_for_current_user(self, projects: list[dict[str, object]]) -> list[dict[str, object]]:
        visible_projects: list[dict[str, object]] = []
        for project in projects:
            next_project = dict(project)
            try:
                project_id = int(next_project.get("project_id", 0) or 0)
            except (TypeError, ValueError):
                project_id = 0
            stored_project = self.db.get_project(project_id) if project_id else None
            if stored_project is None or not self._can_view_project_notes(stored_project):
                next_project["project_notes"] = ""
            visible_projects.append(next_project)
        return visible_projects

    def _project_role_for_me(self, project: Project) -> str:
        if self.db.is_current_user_name(project.owner):
            return "产品经理"
        for member in self.db.list_project_members(project.id):
            if self.db.is_current_user_name(member.name):
                return member.role
        return "未参与"

    def _refresh_my_panel(self) -> None:
        if not hasattr(self, "my_projects_layout"):
            return
        projects = [project for project in self.db.list_projects() if self._project_involves_current_user(project)]
        all_projects = self.db.list_projects()
        projects_by_id = {project.id: project for project in all_projects}

        self._clear_layout(self.my_projects_layout)
        if not projects:
            self.my_projects_layout.addWidget(self._empty_my_card("还没有参与项目。"), 0, 0)
        for index, project in enumerate(projects):
            self.my_projects_layout.addWidget(self._my_project_card(project), index // 3, index % 3)
        for column in range(3):
            self.my_projects_layout.setColumnStretch(column, 1)

        all_assigned = self.db.list_all_project_todos(include_completed=True, scope="assigned")
        active_tasks = [
            todo
            for todo in all_assigned
            if todo.status != "done"
            and (self._todo_visible_to_current_user(todo) or self.db.is_current_user_name(todo.assigned_by))
        ]
        assigned_to_me = [todo for todo in active_tasks if self._todo_visible_to_current_user(todo)]
        assigned_by_me = [todo for todo in active_tasks if self.db.is_current_user_name(todo.assigned_by)]
        self._clear_layout(self.my_tasks_layout)
        if not active_tasks:
            self.my_tasks_layout.addWidget(self._empty_my_card("当前没有分配代办。"))
        elif assigned_to_me and assigned_by_me:
            task_row = QWidget()
            task_row_layout = QHBoxLayout(task_row)
            task_row_layout.setContentsMargins(0, 0, 0, 0)
            task_row_layout.setSpacing(12)
            task_row_layout.addWidget(self._my_task_bucket_panel("我的代办", assigned_to_me, projects_by_id), 1)
            task_row_layout.addWidget(self._my_task_bucket_panel("由我分配", assigned_by_me, projects_by_id), 1)
            self.my_tasks_layout.addWidget(task_row)
        elif assigned_to_me:
            self.my_tasks_layout.addWidget(self._my_task_bucket_panel("我的代办", assigned_to_me, projects_by_id))
        else:
            self.my_tasks_layout.addWidget(self._my_task_bucket_panel("由我分配", assigned_by_me, projects_by_id))
        self.my_tasks_layout.addStretch()

        messages = [
            todo
            for todo in all_assigned
            if todo.status == "done"
            and todo.completed_at is not None
            and self.db.is_current_user_name(todo.assigned_by)
        ]
        messages.sort(key=lambda todo: todo.completed_at or todo.created_at, reverse=True)
        self._clear_layout(self.my_messages_layout)
        if not messages:
            self.my_messages_layout.addWidget(self._empty_my_card("暂时没有新的完成提醒。"))
        for todo in messages[:10]:
            project = projects_by_id.get(todo.project_id)
            self.my_messages_layout.addWidget(self._my_message_card(todo, project.name if project is not None else "未知项目"))
        self.my_messages_layout.addStretch()
        if self._check_project_membership_pet_notifications(projects_by_id):
            return
        self._check_todo_pet_notifications(all_assigned, projects_by_id)

    def _group_todos_by_project(self, todos: list[ProjectTodo]) -> dict[int, list[ProjectTodo]]:
        grouped: dict[int, list[ProjectTodo]] = {}
        for todo in todos:
            grouped.setdefault(todo.project_id, []).append(todo)
        for rows in grouped.values():
            rows.sort(key=lambda todo: todo.created_at, reverse=True)
        return grouped

    def _seen_notification_ids(self, key: str) -> set[int]:
        raw = self.db.get_setting(key) or "[]"
        try:
            values = json.loads(raw)
        except json.JSONDecodeError:
            return set()
        if not isinstance(values, list):
            return set()
        seen: set[int] = set()
        for value in values:
            try:
                seen.add(int(value))
            except (TypeError, ValueError):
                continue
        return seen

    def _store_notification_ids(self, key: str, values: set[int]) -> None:
        trimmed = sorted(values)[-300:]
        self.db.set_setting(key, json.dumps(trimmed), save=True)

    def _current_user_project_memberships(self, projects_by_id: dict[int, Project]) -> list[ProjectMember]:
        memberships: list[ProjectMember] = []
        for project in projects_by_id.values():
            if self.db.is_current_user_name(project.owner):
                continue
            for member in self.db.list_project_members(project.id):
                if self.db.is_current_user_name(member.name):
                    memberships.append(member)
                    break
        return memberships

    def _check_project_membership_pet_notifications(self, projects_by_id: dict[int, Project]) -> bool:
        key = "notified_project_membership_ids"
        memberships = self._current_user_project_memberships(projects_by_id)
        membership_ids = {member.id for member in memberships}
        if self.db.get_setting(key) is None:
            self._store_notification_ids(key, membership_ids)
            return False

        seen = self._seen_notification_ids(key)
        new_memberships = [member for member in memberships if member.id not in seen]
        if not new_memberships:
            return False

        member = max(new_memberships, key=lambda item: item.created_at)
        project = projects_by_id.get(member.project_id)
        if project is None:
            seen.update(member.id for member in new_memberships)
            self._store_notification_ids(key, seen)
            return False

        self.pet.move_to_bottom_right()
        self.pet.speak(f"你被加入项目「{project.name}」，当前身份：{member.role}。", mood="wave")
        seen.update(member.id for member in new_memberships)
        self._store_notification_ids(key, seen)
        return True

    def _check_todo_pet_notifications(self, todos: list[ProjectTodo], projects_by_id: dict[int, Project]) -> None:
        assigned_seen = self._seen_notification_ids("notified_assigned_todo_ids")
        completed_seen = self._seen_notification_ids("notified_completed_todo_ids")
        report_seen = self._seen_notification_ids("notified_todo_report_ids")

        new_assigned = [
            todo
            for todo in todos
            if todo.scope == "assigned"
            and todo.status != "done"
            and self._todo_visible_to_current_user(todo)
            and todo.id not in assigned_seen
        ]
        new_completed = [
            todo
            for todo in todos
            if todo.scope == "assigned"
            and todo.status == "done"
            and todo.completed_at is not None
            and self.db.is_current_user_name(todo.assigned_by)
            and todo.id not in completed_seen
        ]

        self._check_cancelled_todo_pet_notifications()

        todo_by_id = {todo.id: todo for todo in todos if todo.scope == "assigned"}
        new_reports: list[tuple[DailyReport, ProjectTodo]] = []
        for report in self.db.daily_reports_between(date.today() - timedelta(days=30), date.today(), mine_only=False):
            raw_report = report.get("report")
            if not isinstance(raw_report, DailyReport) or raw_report.todo_id is None:
                continue
            todo = todo_by_id.get(raw_report.todo_id) or self.db.get_project_todo(raw_report.todo_id)
            if todo is None or not self.db.is_current_user_name(todo.assigned_by):
                continue
            if raw_report.id in report_seen:
                continue
            if raw_report.content.strip().startswith(("完成待办：", "完成代办：")):
                continue
            new_reports.append((raw_report, todo))

        if new_assigned:
            todo = max(new_assigned, key=lambda item: item.created_at)
            project = projects_by_id.get(todo.project_id)
            assigned_seen.update(item.id for item in new_assigned)
            self._store_notification_ids("notified_assigned_todo_ids", assigned_seen)
            if self._claim_task_pet_animation():
                project_text = f"，是「{project.name}」里的任务" if project else ""
                self.pet.enter_and_speak(
                    todo.assigned_by_pet,
                    f"你好，{todo.assigned_by or todo.creator}有一个任务需要这边做一下{project_text}：{todo.title}。",
                )
            return

        if new_completed:
            todo = max(new_completed, key=lambda item: item.completed_at or item.created_at)
            completed_seen.update(item.id for item in new_completed)
            self._store_notification_ids("notified_completed_todo_ids", completed_seen)
            if self._claim_task_pet_animation():
                completed_by = todo.completed_by or todo.assignee
                self.pet.enter_and_speak(
                    todo.completed_by_pet,
                    f"你好，{todo.assigned_by or todo.creator}交给我的任务被我完成了：{todo.title}。我是{completed_by}。",
                )
            return

        if new_reports:
            report, todo = max(new_reports, key=lambda item: item[0].created_at)
            self.pet.move_to_bottom_right()
            self.pet.speak(f"{report.member_name} 给代办「{todo.title}」新增了一条记录。", mood="wave")
            report_seen.update(report.id for report, _todo in new_reports)
            self._store_notification_ids("notified_todo_report_ids", report_seen)

    def _claim_task_pet_animation(self) -> bool:
        now = datetime.now()
        if (
            self._last_task_pet_animation_at is not None
            and (now - self._last_task_pet_animation_at).total_seconds() < 60
        ):
            return False
        self._last_task_pet_animation_at = now
        return True

    def _check_cancelled_todo_pet_notifications(self) -> None:
        key = "notified_cancelled_assigned_todo_keys"
        cancellations = self.db.list_deleted_assigned_todos()
        cancellation_keys = {
            f"{row.get('source_device_id', '')}:{row.get('source_id', '')}"
            for row in cancellations
        }
        raw = self.db.get_setting(key)
        if raw is None:
            self.db.set_setting(key, json.dumps(sorted(cancellation_keys)), save=True)
            return
        try:
            seen = {str(value) for value in json.loads(raw)}
        except (json.JSONDecodeError, TypeError):
            seen = set()
        new_rows = [
            row for row in cancellations
            if f"{row.get('source_device_id', '')}:{row.get('source_id', '')}" not in seen
            and self.db.is_current_user_name(str(row.get("assignee", "")))
        ]
        seen.update(cancellation_keys)
        self.db.set_setting(key, json.dumps(sorted(seen)[-300:]), save=True)
        if not new_rows or not self._claim_task_pet_animation():
            return
        row = max(new_rows, key=lambda item: str(item.get("deleted_at", "")))
        assigned_by = str(row.get("assigned_by", "")).strip() or "分配人"
        title = str(row.get("title", "")).strip()
        suffix = f"，原任务是：{title}" if title else ""
        self.pet.enter_and_speak(
            str(row.get("assigned_by_pet", "penguin")),
            f"你好，{assigned_by}的任务先取消了{suffix}。",
        )

    def _days_since(self, value: datetime) -> int:
        return max(1, (date.today() - value.date()).days + 1)

    def _todo_due_text(self, todo: ProjectTodo) -> str:
        if todo.due_at is None:
            return ""
        now = datetime.now()
        prefix = f"截止 {todo.due_at.strftime('%m-%d %H:%M')}"
        if todo.status == "done":
            return prefix
        delta = todo.due_at - now
        if delta.total_seconds() < 0:
            overdue_days = max(1, (now.date() - todo.due_at.date()).days + 1)
            return f"{prefix} · 已逾期 {overdue_days} 天"
        remaining_days = max(1, delta.days + (1 if delta.seconds else 0))
        return f"{prefix} · 剩 {remaining_days} 天"

    def _todo_started_text(self, todo: ProjectTodo) -> str:
        if todo.started_at is None:
            return ""
        return f"开始 {todo.started_at.strftime('%m-%d %H:%M')} · 已开始 {self._days_since(todo.started_at)} 天"

    def _daily_report_todo_text(self, report: DailyReport) -> str:
        if self._completion_todo_title_from_report(report.content):
            return ""
        todo = self._todo_for_daily_report(report)
        if todo is None:
            return "关联的代办已删除" if report.todo_id is not None else ""
        title = todo.title.strip()
        if len(title) > 36:
            title = f"{title[:36]}..."
        return title

    def _todo_for_daily_report(self, report: DailyReport) -> ProjectTodo | None:
        if report.todo_id is not None:
            todo = self.db.get_project_todo(report.todo_id)
            if todo is not None:
                return todo
        completed_title = self._completion_todo_title_from_report(report.content)
        if not completed_title:
            return None
        target_title = " ".join(completed_title.split()).casefold()
        for todo in self.db.list_project_todos(report.project_id, include_completed=True):
            todo_title = " ".join(todo.title.strip().split()).casefold()
            if todo_title == target_title:
                return todo
        return None

    def _completion_todo_title_from_report(self, content: str) -> str:
        text = content.strip()
        for prefix in ("完成待办：", "完成代办：", "完成待办:", "完成代办:"):
            if text.startswith(prefix):
                return text[len(prefix):].strip()
        return ""

    def _todo_progress_text(self, todo: ProjectTodo) -> str:
        reports = [
            report
            for report in self.db.list_daily_reports_for_todo(todo.id, limit=1000)
            if not report.content.strip().startswith(("完成待办：", "完成代办："))
        ]
        if not reports:
            return ""
        latest = reports[0]
        content = " ".join(latest.content.split())
        if len(content) > 22:
            content = f"{content[:22]}..."
        count = len(reports)
        return f"进展 {count} 条 · 最近 {latest.created_at.strftime('%m-%d %H:%M')} · {content}"

    def _project_joined_days(self, project: Project) -> int:
        joined_at = project.created_at
        if not self.db.is_current_user_name(project.owner):
            for member in self.db.list_project_members(project.id):
                if self.db.is_current_user_name(member.name):
                    joined_at = member.created_at
                    break
        return self._days_since(joined_at)

    def _empty_my_card(self, text: str) -> QWidget:
        card = QWidget()
        card.setObjectName("feedCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        label = _label(text, "muted")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return card

    def _my_project_card(self, project: Project) -> QWidget:
        card = QWidget()
        card.setObjectName("feedCard")
        card.setMinimumHeight(116)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setToolTip("进入项目面板")
        card.mousePressEvent = lambda event, selected=project.id: self._open_project_from_my_panel(selected)  # type: ignore[method-assign]
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.addWidget(_label(project.name, "memberName"))
        if project.project_notes and self._can_view_project_notes(project):
            title_row.addWidget(self._project_notes_button(project), 0, Qt.AlignmentFlag.AlignVCenter)
        if project.project_link:
            title_row.addWidget(self._project_link_button(project, "primary"), 0, Qt.AlignmentFlag.AlignVCenter)
        if project.backup_project_link:
            title_row.addWidget(self._project_link_button(project, "backup"), 0, Qt.AlignmentFlag.AlignVCenter)
        if project.development_group_link:
            title_row.addWidget(self._project_link_button(project, "development_group"), 0, Qt.AlignmentFlag.AlignVCenter)
        if project.coordination_group_link:
            title_row.addWidget(self._project_link_button(project, "coordination_group"), 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch()
        title_row.addWidget(_label(project.status, "compactRoleBadge"))
        layout.addLayout(title_row)
        layout.addWidget(_label(f"{self._project_role_for_me(project)} · 参与 {self._project_joined_days(project)} 天", "muted"))
        owner_row = QHBoxLayout()
        owner_row.setContentsMargins(0, 0, 0, 0)
        owner_row.setSpacing(6)
        owner_row.addWidget(_label("负责人", "eyebrow"))
        owner_row.addWidget(self._name_with_chat(project.owner))
        owner_row.addStretch()
        layout.addLayout(owner_row)
        return card

    def _open_project_from_my_panel(self, project_id: int) -> None:
        self.current_project_id = project_id
        self.project_scope_value = "mine"
        self._select_page(1)
        self._select_project_mode(0)
        self._load_projects()
        self._show_project_overview()

    def _open_project_from_person_home(self, project_id: int) -> None:
        self.current_project_id = project_id
        self.project_scope_value = "all"
        self._select_page(1)
        self._select_project_mode(0)
        self._load_projects()
        self._show_project_overview()

    def _project_link_button(self, project: Project, kind: str) -> QPushButton:
        link = {
            "primary": project.project_link,
            "backup": project.backup_project_link,
            "development_group": project.development_group_link,
            "coordination_group": project.coordination_group_link,
        }.get(kind, "")
        button = QPushButton()
        button.setObjectName("projectBackupLinkButton" if kind == "backup" else "projectPrimaryLinkButton")
        button.setIcon(_project_group_icon("development" if kind == "development_group" else "coordination") if kind.endswith("_group") else _project_link_icon(kind))
        button.setIconSize(QSize(16, 16))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip({
            "primary": "打开主要项目",
            "backup": "打开备用项目",
            "development_group": "打开开发群",
            "coordination_group": "打开对接群",
        }.get(kind, "打开连接"))
        button.clicked.connect(lambda checked=False, selected=project, selected_kind=kind: self._open_project_link(selected, selected_kind))
        return button

    def _project_notes_button(self, project: Project) -> QPushButton:
        button = QPushButton()
        button.setObjectName("projectTextButton")
        button.setIcon(_project_text_icon())
        button.setIconSize(QSize(16, 16))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip("查看项目资料")
        button.clicked.connect(lambda checked=False, selected=project: self._open_project_notes(selected))
        return button

    def _open_project_link(self, project: Project, kind: str = "primary") -> None:
        link = {
            "primary": project.project_link,
            "backup": project.backup_project_link,
            "development_group": project.development_group_link,
            "coordination_group": project.coordination_group_link,
        }.get(kind, "")
        if not link:
            return
        if kind in {"development_group", "coordination_group"}:
            app_url = _dingtalk_group_app_url(link)
            if app_url.isValid() and not app_url.isEmpty():
                if QDesktopServices.openUrl(app_url):
                    return
        url = QUrl.fromUserInput(link)
        if not url.isValid() or url.scheme().lower() not in {"http", "https", "dingtalk"}:
            QMessageBox.information(self, "连接无效", "这个项目还没有配置可打开的链接。")
            return
        QDesktopServices.openUrl(url)

    def _open_project_notes(self, project: Project) -> None:
        if not self._can_view_project_notes(project):
            QMessageBox.warning(self, "不能查看", "只有参与这个项目的人可以查看项目文本资料。")
            return
        _show_project_notes_dialog(self, project.name, project.project_notes)

    def _open_current_project_notes(self) -> None:
        project = self._current_project()
        if project is None:
            return
        self._open_project_notes(project)

    def _open_current_project_link(self, kind: str = "primary") -> None:
        project = self._current_project()
        if project is None:
            return
        self._open_project_link(project, kind)

    def _open_dingtalk_chat(self, name: str, dingtalk_id: str = "") -> None:
        target_id = dingtalk_id.strip() or self.db.dingtalk_id_for_name(name)
        if not target_id:
            QMessageBox.information(self, "没有钉钉号", f"还没有配置「{name}」的钉钉号。")
            return
        QDesktopServices.openUrl(QUrl(_dingtalk_chat_url(target_id)))
        QTimer.singleShot(900, _try_click_dingtalk_send_message)

    def _open_person_home(self, name: str) -> None:
        logs = self.db.project_logs_for_member(name)
        projects = self._projects_with_notes_for_current_user(self.db.projects_for_member(name))
        dialog = ProjectLogHistoryDialog(name, logs, projects, self)
        dialog.exec()

    def _open_project_member_daily_reports(self, member: ProjectMember) -> None:
        project = self._current_project()
        if project is None:
            return
        reports = self.db.list_member_daily_reports(project.id, member.name)
        dialog = ProjectMemberDailyDialog(project, member, reports, self)
        dialog.exec()

    def _name_link(self, name: str) -> QPushButton:
        button = QPushButton(name)
        button.setObjectName("nameLink")
        button.setFixedHeight(18)
        button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip("查看个人主页")
        button.clicked.connect(lambda checked=False, label=name: self._open_person_home(label))
        return button

    def _name_with_chat(self, name: str, dingtalk_id: str = "") -> QWidget:
        row = QWidget()
        row.setFixedHeight(20)
        row.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._name_link(name))
        target_id = dingtalk_id.strip() or self.db.dingtalk_id_for_name(name)
        if target_id:
            chat = QPushButton()
            chat.setObjectName("chatButton")
            chat.setFixedSize(16, 16)
            chat.setIcon(QIcon(str(DINGTALK_ICON_PATH)))
            chat.setIconSize(QSize(13, 13))
            chat.setCursor(Qt.CursorShape.PointingHandCursor)
            chat.setToolTip("打开钉钉聊天")
            chat.clicked.connect(lambda checked=False, label=name, ding_id=target_id: self._open_dingtalk_chat(label, ding_id))
            layout.addWidget(chat)
        layout.addStretch()
        return row

    def _my_task_bucket_panel(
        self,
        title: str,
        todos: list[ProjectTodo],
        projects_by_id: dict[int, Project],
    ) -> QWidget:
        panel = QWidget()
        panel.setObjectName("softPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(_label(title, "memberName"))
        header.addStretch()
        header.addWidget(_label(f"{len(todos)} 个进行中", "eyebrow"))
        layout.addLayout(header)

        for project_id, project_todos in self._group_todos_by_project(todos).items():
            project = projects_by_id.get(project_id)
            project_name = project.name if project is not None else "未知项目"
            layout.addWidget(self._my_task_project_card(project_name, project_todos))
        layout.addStretch()
        return panel

    def _my_task_project_card(self, project_name: str, todos: list[ProjectTodo]) -> QWidget:
        card = QWidget()
        card.setObjectName("feedCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(_label(project_name, "memberName"))
        header.addStretch()
        header.addWidget(_label(f"{len(todos)} 个代办", "eyebrow"))
        layout.addLayout(header)

        for todo in todos:
            layout.addWidget(self._my_task_card(todo))
        return card

    def _my_task_card(self, todo: ProjectTodo) -> QWidget:
        card = QWidget()
        card.setObjectName("compactMemberCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setToolTip("查看代办详情")
        card.mousePressEvent = lambda event, selected=todo: self._open_todo_detail(selected)  # type: ignore[method-assign]
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        body = QVBoxLayout()
        body.setSpacing(4)
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(5)
        assigned_days = self._days_since(todo.created_at)
        if self._todo_visible_to_current_user(todo):
            meta_row.addWidget(_nowrap_label(
                f"{self._todo_status_text(todo)} · {todo.created_at.strftime('%m-%d %H:%M')} · 已分配 {assigned_days} 天",
                "eyebrow",
            ))
        else:
            meta_row.addWidget(_nowrap_label("我分配给", "eyebrow"))
            meta_row.addWidget(self._name_with_chat(self._todo_current_handler(todo) or todo.assignee))
            meta_row.addWidget(_nowrap_label(
                f"· {todo.created_at.strftime('%m-%d %H:%M')} · 已分配 {assigned_days} 天",
                "eyebrow",
            ))
        due_text = self._todo_due_text(todo)
        started_text = self._todo_started_text(todo)
        meta_row.addStretch()
        body.addLayout(meta_row)
        if due_text:
            body.addWidget(_label(due_text, "eyebrow"))
        if started_text:
            body.addWidget(_label(started_text, "eyebrow"))
        body.addWidget(_label(todo.title))
        progress_text = self._todo_progress_text(todo)
        if progress_text:
            body.addWidget(_label(progress_text, "muted"))
        layout.addLayout(body, 1)

        project = self.db.get_project(todo.project_id)
        if project is not None and self._todo_visible_to_current_user(todo):
            if todo.scope == "assigned" and self._todo_can_start(todo):
                start_button = QPushButton("开始开发" if todo.workflow == "dev_test_accept" else "开始")
                start_button.setObjectName("smallButton")
                start_button.clicked.connect(lambda checked=False, selected=todo: self._start_project_todo(selected))
                layout.addWidget(start_button)
            elif todo.scope == "assigned" and self._todo_can_record(todo):
                record_button = QPushButton("记录")
                record_button.setObjectName("smallButton")
                record_button.clicked.connect(lambda checked=False, selected=todo: self._record_todo_daily_report(selected))
                layout.addWidget(record_button)
            if self._todo_can_advance(todo):
                done_button = QPushButton("完成")
                done_button.setText(self._todo_primary_action_text(todo))
                done_button.setObjectName("smallButton")
                done_button.clicked.connect(lambda checked=False, p=project, selected=todo: self._complete_todo_for_project(p, selected))
                layout.addWidget(done_button)
            if self._todo_can_reject(todo):
                reject_button = QPushButton("打回")
                reject_button.setObjectName("smallButton")
                reject_button.clicked.connect(lambda checked=False, p=project, selected=todo: self._reject_todo_for_project(p, selected))
                layout.addWidget(reject_button)
            if self._todo_can_skip_ui(todo):
                skip_button = QPushButton("跳过UI")
                skip_button.setObjectName("smallButton")
                skip_button.clicked.connect(lambda checked=False, p=project, selected=todo: self._skip_todo_ui_for_project(p, selected))
                layout.addWidget(skip_button)
        if self.db.is_current_user_name(todo.assigned_by):
            delete_button = QPushButton("删除")
            delete_button.setObjectName("smallButton")
            delete_button.clicked.connect(lambda checked=False, selected=todo: self._delete_assigned_todo_from_my_panel(selected))
            layout.addWidget(delete_button)

        return card

    def _my_message_card(self, todo: ProjectTodo, project_name: str) -> QWidget:
        card = QWidget()
        card.setObjectName("feedCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setToolTip("查看代办详情")
        card.mousePressEvent = lambda event, selected=todo: self._open_todo_detail(selected)  # type: ignore[method-assign]
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        completed_at = todo.completed_at.strftime("%m-%d %H:%M") if todo.completed_at is not None else ""
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(5)
        meta = _label(f"{completed_at} · {project_name} ·", "eyebrow")
        meta.setWordWrap(False)
        meta.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        message = _label("完成了你分配的代办", "eyebrow")
        message.setWordWrap(False)
        message.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        meta_row.addWidget(meta)
        meta_row.addWidget(self._name_with_chat(todo.completed_by or todo.assignee))
        meta_row.addWidget(message)
        meta_row.addStretch()
        layout.addLayout(meta_row)
        layout.addWidget(_label(todo.title, "muted"))
        return card

    def _open_todo_detail(self, todo: ProjectTodo, highlight_report_id: int | None = None) -> None:
        latest = self.db.get_project_todo(todo.id) or todo
        project = self.db.get_project(latest.project_id)
        project_name = project.name if project is not None else "未知项目"
        reports = self.db.list_daily_reports_for_todo(latest.id, limit=1000)
        TodoDetailDialog(latest, project_name, reports, self, highlight_report_id=highlight_report_id).exec()

    def _open_todo_detail_by_id(self, todo_id: int) -> None:
        todo = self.db.get_project_todo(todo_id)
        if todo is None:
            QMessageBox.information(self, "代办不存在", "这条代办已经不存在。")
            return
        self._open_todo_detail(todo)

    def _select_project_item(self, item: QListWidgetItem) -> None:
        project_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(project_id, int):
            self.current_project_id = project_id
            self._pending_project_refresh_id = project_id
            self._refresh_project_list_active_state()
            self._show_project_overview()
            QTimer.singleShot(0, lambda selected=project_id: self._refresh_project_workspace_if_current(selected))

    def _refresh_project_workspace_if_current(self, project_id: int) -> None:
        if self.current_project_id != project_id or self._pending_project_refresh_id != project_id:
            return
        self._pending_project_refresh_id = None
        self._refresh_project_workspace()

    def _select_project_mode(self, index: int) -> None:
        if index == 1:
            project = self._current_project()
            if project is None or not self._can_manage_project(project, None):
                QMessageBox.information(self, "不能配置", "只有这个项目的负责人或最高权限用户可以配置成员。")
                index = 0
        if hasattr(self, "project_side_stack"):
            self.project_side_stack.setCurrentIndex(index)
        is_config = index == 1
        if hasattr(self, "progress_panel"):
            self.progress_panel.setVisible(not is_config)
        if hasattr(self, "config_project_panel"):
            self.config_project_panel.setVisible(is_config)
        if hasattr(self, "project_config_button"):
            self.project_config_button.setChecked(is_config)
            self.project_config_button.setObjectName("primaryButton" if is_config else "")
            self.project_config_button.style().unpolish(self.project_config_button)
            self.project_config_button.style().polish(self.project_config_button)
        if not hasattr(self, "project_scope_buttons"):
            return
        for value, button in self.project_scope_buttons.items():
            selected = not is_config and value == self.project_scope_value
            button.setChecked(selected)
            button.setObjectName("primaryButton" if selected else "")
            button.style().unpolish(button)
            button.style().polish(button)

    def _select_project_scope(self, scope: str) -> None:
        self.project_scope_value = scope
        self._select_project_mode(0)
        self._load_projects()

    def _set_todo_view(self, mode: str) -> None:
        self.todo_view_mode = mode if mode in {"personal", "assigned", "project"} else "personal"
        self._set_todo_view_buttons()
        if self._current_project() is not None:
            self._refresh_project_workspace()

    def _set_todo_view_buttons(self) -> None:
        if hasattr(self, "personal_todo_button"):
            self.personal_todo_button.setChecked(self.todo_view_mode == "personal")
            self.assigned_todo_button.setChecked(self.todo_view_mode == "assigned")
            self.project_todo_button.setChecked(self.todo_view_mode == "project")
            self.personal_todo_button.setObjectName("primaryButton" if self.todo_view_mode == "personal" else "")
            self.assigned_todo_button.setObjectName("primaryButton" if self.todo_view_mode == "assigned" else "")
            self.project_todo_button.setObjectName("primaryButton" if self.todo_view_mode == "project" else "")
            for button in (self.personal_todo_button, self.assigned_todo_button, self.project_todo_button):
                button.style().unpolish(button)
                button.style().polish(button)

    def _toggle_assigned_deadline(self, days: int) -> None:
        self.assigned_todo_deadline_days = None if self.assigned_todo_deadline_days == days else days
        self._refresh_assigned_deadline_buttons()

    def _refresh_assigned_deadline_buttons(self) -> None:
        if not hasattr(self, "assigned_todo_deadline_buttons"):
            return
        for days, button in self.assigned_todo_deadline_buttons.items():
            selected = self.assigned_todo_deadline_days == days
            button.setChecked(selected)
            button.setObjectName("primaryButton" if selected else "smallButton")
            button.style().unpolish(button)
            button.style().polish(button)

    def _current_project(self) -> Project | None:
        if self.current_project_id is None:
            return None
        return self.db.get_project(self.current_project_id)

    def _create_project(self) -> None:
        name = self.project_name.text().strip()
        owner = self.db.display_name()
        description = self.project_desc.toPlainText().strip()
        if not name:
            QMessageBox.information(self, "项目名称为空", "先写项目名称。")
            return
        if self._project_name_exists(name):
            QMessageBox.information(self, "项目名称重复", "已经有同名项目，请换一个名称。")
            return
        project = self.db.add_project(name, owner, description or "这个项目还没有填写说明。")
        self.db.add_project_member(project.id, owner, "产品经理")
        self.project_name.clear()
        self.project_desc.clear()
        self.current_project_id = project.id
        self._load_projects()
        self._refresh_document_library()

    def _add_project_member(self) -> None:
        project = self._current_project()
        if project is None:
            return
        if not self._can_manage_project(project, None):
            QMessageBox.warning(self, "不能配置", "只有这个项目的负责人或最高权限用户可以添加成员。")
            return
        name = self.member_name.text().strip()
        role = self.member_role.currentText().strip()
        if not name:
            QMessageBox.information(self, "成员为空", "先写成员姓名。")
            return
        self.db.add_project_member(project.id, name, role)
        self.member_name.clear()
        self._refresh_project_workspace()

    def _save_project_description(self) -> None:
        project = self._current_project()
        if project is None:
            return
        if not self._can_manage_project(project, None):
            QMessageBox.warning(self, "不能保存", "只有这个项目的负责人或最高权限用户可以编辑项目配置。")
            return
        name = self.config_project_name.text().strip()
        if not name:
            QMessageBox.information(self, "项目名称为空", "项目名称不能为空。")
            return
        if self._project_name_exists(name, exclude_project_id=project.id):
            QMessageBox.information(self, "项目名称重复", "已经有同名项目，请换一个名称。")
            return
        description = self.config_project_description.toPlainText().strip()
        can_edit_project_notes = self._can_view_project_notes(project)
        project_notes = (
            self.config_project_notes.toPlainText().strip()
            if can_edit_project_notes and hasattr(self, "config_project_notes")
            else project.project_notes
        )
        raw_link = self.config_project_link.text().strip() if hasattr(self, "config_project_link") else ""
        project_link = _normalize_project_link(raw_link)
        if raw_link and not project_link:
            QMessageBox.information(self, "主要项目连接无效", "请填写网页链接，例如 example.com 或 https://example.com。")
            return
        raw_backup_link = (
            self.config_project_backup_link.text().strip()
            if hasattr(self, "config_project_backup_link")
            else ""
        )
        backup_project_link = _normalize_project_link(raw_backup_link)
        if raw_backup_link and not backup_project_link:
            QMessageBox.information(self, "备用项目连接无效", "请填写网页链接，例如 preview.example.com 或 https://preview.example.com。")
            return
        raw_development_group_link = self.config_development_group_link.text().strip()
        development_group_link = _normalize_dingtalk_group_link(raw_development_group_link)
        if raw_development_group_link and not development_group_link:
            QMessageBox.information(self, "开发群链接无效", "请填写有效的钉钉群链接。")
            return
        raw_coordination_group_link = self.config_coordination_group_link.text().strip()
        coordination_group_link = _normalize_dingtalk_group_link(raw_coordination_group_link)
        if raw_coordination_group_link and not coordination_group_link:
            QMessageBox.information(self, "对接群链接无效", "请填写有效的钉钉群链接。")
            return
        updated = self.db.update_project_details(
            project_id=project.id,
            name=name,
            description=description,
            project_link=project_link,
            backup_project_link=backup_project_link,
            development_group_link=development_group_link,
            coordination_group_link=coordination_group_link,
            project_notes=project_notes,
        )
        if updated is None:
            QMessageBox.warning(self, "保存失败", "这个项目记录已经不存在。")
            self._load_projects()
            return
        central_sync = getattr(self, "central_sync", None)
        if central_sync is not None:
            central_sync.mark_local_dirty()
            central_sync.sync_now(push_first=True)
        self._load_projects()
        self._refresh_document_library()

    def _project_name_exists(self, name: str, exclude_project_id: int | None = None) -> bool:
        normalized = " ".join(name.split()).casefold()
        return any(
            project.id != exclude_project_id and " ".join(project.name.split()).casefold() == normalized
            for project in self.db.list_projects()
        )

    def _delete_current_project(self) -> None:
        project = self._current_project()
        if project is None:
            return
        if not self._can_manage_project(project, None):
            QMessageBox.warning(self, "不能删除", "只有这个项目的负责人或最高权限用户可以删除项目。")
            return
        message = f"确定删除项目「{project.name}」吗？\n\n项目成员、代办、日报、项目周报和文档记录都会一起删除。"
        if QMessageBox.question(self, "删除项目", message) != QMessageBox.StandardButton.Yes:
            return
        if not self.db.delete_project(project.id):
            QMessageBox.warning(self, "删除失败", "这个项目记录已经不存在。")
            self._load_projects()
            return
        project_docs_dir = APP_DIR / "documents" / str(project.id)
        if project_docs_dir.exists():
            shutil.rmtree(project_docs_dir, ignore_errors=True)
        self.current_project_id = None
        self._show_project_overview()
        self._load_projects()
        self._refresh_document_library()
        self._announce_presence()

    def _save_daily_report(self) -> None:
        project = self._current_project()
        if project is None:
            return
        members = self.db.list_project_members(project.id)
        current_member = self._current_project_member(project, members)
        content = self.daily_editor.toPlainText().strip()
        if current_member is None:
            QMessageBox.information(self, "不能保存", "只有项目成员可以写日报。")
            return
        if not content:
            QMessageBox.information(self, "日报为空", "先写一点日报内容。")
            return
        linked_todo_id = int(self.daily_todo_link.currentData() or 0) if hasattr(self, "daily_todo_link") else 0
        self.db.add_daily_report(project.id, current_member.name, current_member.role, content, todo_id=linked_todo_id or None)
        self.daily_editor.clear()
        if hasattr(self, "daily_todo_link"):
            self.daily_todo_link.setCurrentIndex(0)
        self._refresh_project_workspace()
        self._refresh_badge_wall()
        self._nudge_after_late_record()
        self._announce_presence()

    def _add_project_todo(self) -> None:
        project = self._current_project()
        if project is None:
            return
        members = self.db.list_project_members(project.id)
        current_member = self._current_project_member(project, members)
        is_manager = self._can_manage_project(project, current_member)
        can_assign_todos = self._can_assign_todo(project, current_member)
        if self.todo_view_mode == "assigned" and not can_assign_todos:
            QMessageBox.information(self, "不能分配", "只有产品经理、测试或最高权限用户可以分配代办。")
            return
        if self.todo_view_mode == "project" and not is_manager:
            QMessageBox.information(self, "不能添加", "只有项目负责人或最高权限用户可以添加项目代办。")
            return
        if self.todo_view_mode == "personal" and current_member is None and not is_manager:
            QMessageBox.information(self, "不能添加", "只有项目成员可以添加个人代办。")
            return
        title = self.project_todo_input.text().strip()
        if not title:
            QMessageBox.information(self, "代办为空", "先写一个代办。")
            return
        assignee = ""
        due_at = None
        workflow = ""
        designer = ""
        developer = ""
        tester = ""
        acceptor = ""
        if self.todo_view_mode == "assigned":
            assignee = str(self.assigned_todo_assignee.currentData() or self.assigned_todo_assignee.currentText()).strip()
            if not assignee:
                QMessageBox.information(self, "没有接收人", "先选择要分配给谁。")
                return
            assignee_member = self._project_member_by_name(members, assignee)
            if self._member_is_developer(assignee_member) and (is_manager or self._member_is_product(current_member)):
                tester_member = self._first_project_tester(members, exclude_name=assignee)
                workflow = "dev_test_accept"
                designer_member = self._first_project_designer(members, exclude_name=assignee)
                designer = designer_member.name if designer_member is not None else ""
                developer = assignee
                tester = tester_member.name if tester_member is not None else ""
                acceptor = self.db.display_name()
            if self.assigned_todo_deadline_days is not None:
                due_at = datetime.now() + timedelta(days=self.assigned_todo_deadline_days)
            if not self._assignee_version_supports_todo(assignee, workflow):
                return
        self.db.add_project_todo(
            project.id,
            title,
            self.db.display_name(),
            scope=self.todo_view_mode,
            assignee=assignee,
            assigned_by=self.db.display_name() if self.todo_view_mode == "assigned" else "",
            due_at=due_at,
            workflow=workflow,
            designer=designer,
            developer=developer,
            tester=tester,
            acceptor=acceptor,
            assigned_by_pet=self.db.pet_kind(),
        )
        self.project_todo_input.clear()
        self.assigned_todo_deadline_days = None
        self._refresh_assigned_deadline_buttons()
        self._refresh_project_workspace()
        self._refresh_my_panel()
        if self.todo_view_mode == "assigned" and self._claim_task_pet_animation():
            self.pet.move_to_bottom_right()
            self.pet.speak(f"我给{assignee}分配任务了。", mood="leave")

    def _assignee_version_supports_todo(self, assignee: str, workflow: str) -> bool:
        peer = self._peer_for_display_name(assignee)
        if peer is None or not peer.app_version:
            return True
        minimum_version = ASSIGNED_TODO_WORKFLOW_MIN_VERSION if workflow else ASSIGNED_TODO_MIN_VERSION
        if version_tuple(peer.app_version) >= version_tuple(minimum_version):
            return True
        feature_text = "开发-测试-验收流转代办" if workflow else "分配代办"
        QMessageBox.warning(
            self,
            "对方版本过低",
            (
                f"{assignee} 当前在线版本是 v{peer.app_version}，低于 {feature_text} 需要的 "
                f"v{minimum_version}。\n\n"
                "请先让对方更新到新版本，否则他那边可能看不到这条代办。"
            ),
        )
        return False

    def _peer_for_display_name(self, name: str) -> LanPeer | None:
        normalized = name.strip()
        if not normalized:
            return None
        peers = getattr(self, "current_lan_peers", [])
        for peer in peers:
            if peer.name.strip() == normalized:
                return peer
        if self.discovery is not None:
            for peer in self.discovery.sorted_peers():
                if peer.name.strip() == normalized:
                    return peer
        return None

    def _complete_project_todo(self, todo: ProjectTodo) -> None:
        project = self._current_project()
        if project is None:
            return
        self._complete_todo_for_project(project, todo)

    def _complete_todo_for_project(self, project: Project, todo: ProjectTodo) -> None:
        latest_todo = self.db.get_project_todo(todo.id)
        if latest_todo is None:
            self._refresh_project_workspace()
            self._refresh_my_panel()
            return
        if latest_todo.status == "done":
            self._refresh_project_workspace()
            self._refresh_my_panel()
            return
        todo = latest_todo
        members = self.db.list_project_members(project.id)
        current_member = self._current_project_member(project, members)
        is_manager = self._can_manage_project(project, current_member)
        if current_member is None:
            QMessageBox.information(self, "不能完成", "只有项目成员可以完成代办。")
            return
        if todo.scope == "project" and not is_manager:
            QMessageBox.information(self, "不能完成", "只有项目负责人或最高权限用户可以完成项目代办。")
            return
        if todo.scope == "assigned" and not self._todo_visible_to_current_user(todo):
            QMessageBox.information(self, "不能流转", "只有当前处理人可以处理这条代办。")
            return
        report = self.db.complete_project_todo(
            todo.id,
            current_member.name,
            current_member.role,
            completed_by_pet=self.db.pet_kind(),
        )
        if report is None:
            QMessageBox.information(self, "不能流转", "这个代办已经完成、状态不匹配，或已经不存在。")
        else:
            self._nudge_after_late_record()
            completed = self.db.get_project_todo(todo.id)
            if (
                completed is not None
                and completed.scope == "assigned"
                and completed.status == "done"
                and self._claim_task_pet_animation()
            ):
                self.pet.move_to_bottom_right()
                self.pet.speak(f"我去通知{completed.assigned_by or completed.creator}，任务完成了。", mood="leave")
        self._refresh_project_workspace()
        self._refresh_my_panel()
        self._refresh_badge_wall()
        self._announce_presence()

    def _reject_project_todo(self, todo: ProjectTodo) -> None:
        project = self._current_project()
        if project is None:
            return
        self._reject_todo_for_project(project, todo)

    def _reject_todo_for_project(self, project: Project, todo: ProjectTodo) -> None:
        current_member = self._current_project_member(project, self.db.list_project_members(project.id))
        if current_member is None:
            QMessageBox.information(self, "不能打回", "只有项目成员可以处理代办。")
            return
        if not self._todo_can_reject(todo) or not self._todo_visible_to_current_user(todo):
            QMessageBox.information(self, "不能打回", "只有测试人在待测试阶段可以打回开发。")
            return
        report = self.db.reject_project_todo(todo.id, current_member.name, current_member.role)
        if report is None:
            QMessageBox.information(self, "不能打回", "这个代办状态已经变化或不存在。")
            return
        self._refresh_project_workspace()
        self._refresh_my_panel()
        self._refresh_badge_wall()
        self._announce_presence()

    def _skip_project_todo_ui(self, todo: ProjectTodo) -> None:
        project = self._current_project()
        if project is None:
            return
        self._skip_todo_ui_for_project(project, todo)

    def _skip_todo_ui_for_project(self, project: Project, todo: ProjectTodo) -> None:
        current_member = self._current_project_member(project, self.db.list_project_members(project.id))
        if current_member is None:
            QMessageBox.information(self, "不能跳过", "只有项目成员可以处理代办。")
            return
        if not self._todo_can_skip_ui(todo) or not self._todo_visible_to_current_user(todo):
            QMessageBox.information(self, "不能跳过", "只有 UI/设计在待 UI 阶段可以跳过。")
            return
        report = self.db.skip_project_todo_ui(todo.id, current_member.name, current_member.role)
        if report is None:
            QMessageBox.information(self, "不能跳过", "这个代办状态已经变化或不存在。")
            return
        self._refresh_project_workspace()
        self._refresh_my_panel()
        self._refresh_badge_wall()
        self._announce_presence()

    def _delete_assigned_todo_from_my_panel(self, todo: ProjectTodo) -> None:
        if not self.db.is_current_user_name(todo.assigned_by):
            QMessageBox.information(self, "不能删除", "只能删除自己分配出去的代办。")
            return
        if todo.status == "done":
            QMessageBox.information(self, "不能删除", "已完成的分配代办会作为提醒保留。")
            return
        message = f"确定删除分配给「{todo.assignee}」的代办吗？"
        if QMessageBox.question(self, "删除分配代办", message) != QMessageBox.StandardButton.Yes:
            return
        if not self.db.delete_project_todo(todo.id):
            QMessageBox.warning(self, "删除失败", "这条代办已经不存在。")
            return
        if self._claim_task_pet_animation():
            self.pet.move_to_bottom_right()
            self.pet.speak(f"我去通知{todo.assignee}任务取消。", mood="leave")
        self._refresh_project_workspace()
        self._refresh_my_panel()
        self._announce_presence()

    def _save_project_weekly_report(self) -> None:
        project = self._current_project()
        if project is None:
            return
        content = self.project_weekly_editor.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "周报为空", "先写项目周报内容。")
            return
        self.db.add_project_weekly_report(project.id, self.db.display_name(), content)
        self.project_weekly_editor.clear()
        self._refresh_project_workspace()
        self._refresh_badge_wall()
        self._nudge_after_late_record()

    def _upload_project_deck(self) -> None:
        project = self._current_project()
        if project is None:
            return
        members = self.db.list_project_members(project.id)
        current_member = self._current_project_member(project, members)
        is_manager = self._can_manage_project(project, current_member)
        if not self._can_upload_project_document(project, current_member, is_manager):
            QMessageBox.information(self, "不能上传", "只有项目负责人或测试成员可以上传项目文档。")
            return
        doc_type = self.project_document_type.currentText().strip() or "其他"
        visibility = self.project_document_visibility.currentData() or "team"
        self._upload_project_document(project.id, doc_type, str(visibility))

    def _upload_project_document(self, project_id: int, doc_type: str, visibility: str = "team") -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择项目文档",
            "",
            DOCUMENT_OPEN_FILTER,
        )
        if not file_path:
            return
        source = Path(file_path)
        if source.suffix.lower() in ARCHIVE_SUFFIXES and doc_type == "项目汇报PPT":
            doc_type = "压缩包"
        stored = self._copy_document_into_library(project_id, source)
        if stored is None:
            return
        self.db.add_project_document(
            project_id,
            source.name,
            doc_type,
            visibility,
            self.db.display_name(),
            str(stored),
        )
        self._refresh_project_workspace()
        self._refresh_document_library()

    def _copy_document_into_library(self, project_id: int, source: Path) -> Path | None:
        target_dir = APP_DIR / "documents" / str(project_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_name = safe_document_filename(source.name)
        source_name = Path(safe_name)
        target = unique_document_path(target_dir, f"{source_name.stem}-{timestamp}{source_name.suffix}", timestamp)
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            QMessageBox.warning(self, "上传失败", f"复制文件失败：{exc}")
            return None
        return target

    def _refresh_project_workspace(self) -> None:
        project = self._current_project()
        if project is None:
            return
        developer_scroll_value = 0
        developer_was_at_bottom = False
        if hasattr(self, "developer_feed"):
            developer_scrollbar = self.developer_feed.verticalScrollBar()
            developer_scroll_value = developer_scrollbar.value()
            developer_was_at_bottom = developer_scrollbar.value() >= developer_scrollbar.maximum() - 2
        members = self.db.list_project_members(project.id)
        daily_reports = self.db.list_daily_reports(project.id)
        weekly_reports = self.db.list_project_weekly_reports(project.id)
        documents = self.db.list_project_documents(project.id)
        open_todos = self.db.list_project_todos(project.id)
        completed_project_todos = [
            todo
            for todo in self.db.list_project_todos(project.id, include_completed=True, scope="project")
            if todo.status == "done" and todo.completed_at is not None
        ]
        current_member = self._current_project_member(project, members)
        is_manager = self._can_manage_project(project, current_member)
        can_view_project_notes = self._can_view_project_notes(project)
        can_edit_project_notes = is_manager and can_view_project_notes

        self.project_status.setText(f"{project.status} · 负责人 {project.owner}")
        self.project_title.setText(project.name)
        self.project_notes_button.setVisible(can_view_project_notes and bool(project.project_notes))
        self.project_notes_button.setToolTip("查看项目资料" if can_view_project_notes and project.project_notes else "项目资料")
        self.project_primary_link_button.setVisible(bool(project.project_link))
        self.project_primary_link_button.setToolTip(project.project_link or "打开主要项目")
        self.project_backup_link_button.setVisible(bool(project.backup_project_link))
        self.project_backup_link_button.setToolTip(project.backup_project_link or "打开备用项目")
        self.project_development_group_button.setVisible(bool(project.development_group_link))
        self.project_development_group_button.setToolTip("打开开发群")
        self.project_coordination_group_button.setVisible(bool(project.coordination_group_link))
        self.project_coordination_group_button.setToolTip("打开对接群")
        self.project_description.setText(project.description)
        editing_config = (
            self.project_side_stack.currentIndex() == 1
            and (
                self.config_project_description.hasFocus()
                or self.config_project_name.hasFocus()
                or (hasattr(self, "config_project_link") and self.config_project_link.hasFocus())
                or (hasattr(self, "config_project_backup_link") and self.config_project_backup_link.hasFocus())
                or self.config_development_group_link.hasFocus()
                or self.config_coordination_group_link.hasFocus()
                or (hasattr(self, "config_project_notes") and self.config_project_notes.hasFocus())
            )
        )
        if not editing_config:
            self.config_project_name.setText(project.name)
            self.config_project_description.setPlainText(project.description)
            if hasattr(self, "config_project_link"):
                self.config_project_link.setText(project.project_link)
            if hasattr(self, "config_project_backup_link"):
                self.config_project_backup_link.setText(project.backup_project_link)
            self.config_development_group_link.setText(project.development_group_link)
            self.config_coordination_group_link.setText(project.coordination_group_link)
            if hasattr(self, "config_project_notes"):
                self.config_project_notes.setPlainText(project.project_notes if can_view_project_notes else "")
        self._set_metric(self.metric_members, len(members))
        self._set_metric(self.metric_todos, len(open_todos))
        self._set_metric(self.metric_daily, len(daily_reports))
        self._set_metric(self.metric_weekly, len(weekly_reports))
        self._set_metric(self.metric_decks, len(documents))

        self._clear_layout(self.member_cards_layout)
        can_assign_todos = self._can_assign_todo(project, current_member)
        if hasattr(self, "project_config_button"):
            self.project_config_button.setEnabled(is_manager)
        if not is_manager and self.project_side_stack.currentIndex() == 1:
            self._select_project_mode(0)
        if current_member is None and not is_manager and self.todo_view_mode != "project":
            self.todo_view_mode = "project"
        self._set_todo_view_buttons()
        self.personal_todo_button.setEnabled(current_member is not None or is_manager)
        self.assigned_todo_button.setEnabled(current_member is not None or is_manager)
        self.project_todo_button.setEnabled(True)
        can_add_todos = (
            (self.todo_view_mode == "assigned" and can_assign_todos)
            or is_manager
            or (self.todo_view_mode == "personal" and current_member is not None)
        )
        self.todo_panel.setVisible(current_member is not None or is_manager or self.todo_view_mode == "project")
        can_write_daily = current_member is not None
        can_upload_project_document = self._can_upload_project_document(project, current_member, is_manager)
        self.activity_forms_panel.setVisible(can_write_daily or is_manager or can_upload_project_document)
        self.daily_form.setVisible(can_write_daily)
        placeholder_by_mode = {
            "personal": "新增一个个人代办",
            "assigned": "写下要分配的代办",
            "project": "新增一个项目代办",
        }
        self.project_todo_input.setPlaceholderText(placeholder_by_mode.get(self.todo_view_mode, "新增一个代办"))
        self._refresh_assigned_todo_assignees(members, can_assign_todos)
        self.assigned_todo_assignee.setVisible(self.todo_view_mode == "assigned" and can_assign_todos)
        self.assigned_todo_deadline_row.setVisible(self.todo_view_mode == "assigned" and can_assign_todos)
        self.assigned_todo_deadline_row.setEnabled(self.todo_view_mode == "assigned" and can_assign_todos)
        self._refresh_assigned_deadline_buttons()
        self.project_todo_input.setVisible(can_add_todos)
        self.add_todo_button.setVisible(can_add_todos)
        self.project_todo_input.setEnabled(can_add_todos)
        self.add_todo_button.setEnabled(can_add_todos)
        self.daily_editor.setEnabled(can_write_daily)
        self.save_daily_button.setEnabled(can_write_daily)
        self._refresh_daily_todo_links(project, current_member, is_manager, can_write_daily)
        self.daily_member_label.setText(
            f"当前身份：{current_member.name} · {current_member.role}" if current_member is not None else "当前身份：非项目成员"
        )
        self.member_name.setEnabled(is_manager)
        self.member_role.setEnabled(is_manager)
        self.add_member_button.setEnabled(is_manager)
        if hasattr(self, "project_owner_select"):
            self._refresh_project_owner_options(project, members, is_manager)
        self.config_project_description.setEnabled(is_manager)
        self.config_project_name.setEnabled(is_manager)
        if hasattr(self, "config_project_link"):
            self.config_project_link.setEnabled(is_manager)
        if hasattr(self, "config_project_backup_link"):
            self.config_project_backup_link.setEnabled(is_manager)
        self.config_development_group_link.setEnabled(is_manager)
        self.config_coordination_group_link.setEnabled(is_manager)
        if hasattr(self, "config_project_notes"):
            self.config_project_notes.setEnabled(can_edit_project_notes)
            self.config_project_notes.setVisible(can_view_project_notes)
        if hasattr(self, "config_project_notes_label"):
            self.config_project_notes_label.setVisible(can_view_project_notes)
        self.save_project_description_button.setEnabled(is_manager)
        self.delete_project_button.setEnabled(is_manager)
        self.weekly_form.setVisible(is_manager or can_upload_project_document)
        self.weekly_form_title.setText("负责人周报 / 文档" if is_manager else "项目文档")
        self.project_weekly_editor.setEnabled(is_manager)
        self.project_weekly_editor.setVisible(is_manager)
        self.save_project_weekly_button.setEnabled(is_manager)
        self.save_project_weekly_button.setVisible(is_manager)
        self._refresh_project_document_type_options(is_manager, can_upload_project_document)
        self.project_document_type.setEnabled(can_upload_project_document)
        self.project_document_visibility.setEnabled(can_upload_project_document)
        self.upload_deck_button.setEnabled(can_upload_project_document)
        for member in members:
            self._add_member_card(member)
        self._refresh_config_member_list(project, members, is_manager)

        self.todo_board.clear()
        todos = self._todos_for_current_view(project.id, is_manager)
        self.todo_count_label.setText(f"{len(todos)} 个待完成")
        if not todos:
            empty_todo_text = {
                "personal": "当前没有待完成个人代办。",
                "assigned": "当前没有待完成分配代办。",
                "project": "当前没有待完成项目代办。",
            }.get(self.todo_view_mode, "当前没有待完成代办。")
            self._add_todo_card(None, empty_todo_text, False)
        for todo in todos:
            self._add_todo_card(todo, todo.title, self._can_complete_todo(todo, current_member, is_manager))

        self.product_feed.clear()
        product_items: list[tuple[str, str, str, str, ProjectDocument | None, tuple[str, int, str] | None]] = []
        for member in members:
            product_items.append(
                (
                    member.created_at.isoformat(),
                    member.created_at.strftime("%m-%d %H:%M"),
                    "成员配置",
                    f"{member.name} · {member.role}",
                    None,
                    ("member", member.id, f"成员配置：{member.name}") if is_manager else None,
                )
            )
        for report in weekly_reports:
            product_items.append(
                (
                    report.created_at.isoformat(),
                    report.created_at.strftime("%m-%d %H:%M"),
                    f"项目周报 · {report.author}",
                    report.content,
                    None,
                    ("project_weekly", report.id, "项目周报") if is_manager else None,
                )
            )
        for document in documents:
            product_items.append(
                (
                    document.created_at.isoformat(),
                    document.created_at.strftime("%m-%d %H:%M"),
                    f"{document.doc_type} · {'团队' if document.visibility == 'team' else '本人'}",
                    document.title,
                    document,
                    ("document", document.id, f"文档：{document.title}") if is_manager else None,
                )
            )
        for todo in completed_project_todos:
            completed_at = todo.completed_at
            product_items.append(
                (
                    completed_at.isoformat(),
                    completed_at.strftime("%m-%d %H:%M"),
                    f"完成项目代办 · {todo.completed_by or '项目成员'}",
                    todo.title,
                    None,
                    ("todo", todo.id, f"完成项目代办：{todo.title}") if is_manager else None,
                )
            )
        if product_items:
            for _, time_text, kind, content, document, progress_delete in sorted(
                product_items,
                key=lambda item: (
                    item[0],
                    item[2],
                    item[3],
                    item[4].id if item[4] is not None else 0,
                    item[5][1] if item[5] is not None else 0,
                ),
                reverse=True,
            )[:5]:
                self._add_feed_card(
                    self.product_feed,
                    time_text,
                    kind,
                    content,
                    document,
                    progress_delete=progress_delete,
                    max_content_lines=None,
                )
        else:
            self._add_feed_card(
                self.product_feed,
                "",
                "项目进展",
                "还没有项目进展。",
                max_content_lines=None,
            )

        self.developer_feed.clear()
        visible_daily_reports = daily_reports if is_manager else [
            report for report in daily_reports if self.db.is_current_user_name(report.member_name)
        ]
        if not visible_daily_reports:
            empty_text = "还没有日报。" if is_manager else "你还没有写过日报。"
            self._add_feed_card(
                self.developer_feed,
                "",
                "日报",
                empty_text,
                min_content_lines=1,
                max_content_lines=None,
                visual_chars_per_line=46,
            )
        for group in self._daily_report_groups(visible_daily_reports)[:5]:
            self._add_daily_report_group_card(self.developer_feed, group)
        QTimer.singleShot(
            0,
            lambda value=developer_scroll_value, bottom=developer_was_at_bottom: self._restore_developer_feed_scroll(value, bottom),
        )
        self._refresh_my_panel()

    def _restore_developer_feed_scroll(self, value: int, was_at_bottom: bool) -> None:
        if not hasattr(self, "developer_feed"):
            return
        scrollbar = self.developer_feed.verticalScrollBar()
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(min(value, scrollbar.maximum()))

    def _clear_project_workspace(self) -> None:
        if not hasattr(self, "project_title"):
            return
        self.project_status.setText("暂无项目")
        self.project_title.setText("创建一个项目")
        if hasattr(self, "project_notes_button"):
            self.project_notes_button.setVisible(False)
        if hasattr(self, "project_primary_link_button"):
            self.project_primary_link_button.setVisible(False)
        if hasattr(self, "project_backup_link_button"):
            self.project_backup_link_button.setVisible(False)
        if hasattr(self, "project_development_group_button"):
            self.project_development_group_button.setVisible(False)
        if hasattr(self, "project_coordination_group_button"):
            self.project_coordination_group_button.setVisible(False)
        if getattr(self, "project_scope_value", "mine") == "mine":
            self.project_description.setText("当前没有你参与的项目。可以创建项目，或切到“全部项目”查看团队项目。")
        else:
            self.project_description.setText("创建项目后，可以继续维护成员、日报、周报和项目文档。")
        self._set_metric(self.metric_members, 0)
        self._set_metric(self.metric_todos, 0)
        self._set_metric(self.metric_daily, 0)
        self._set_metric(self.metric_weekly, 0)
        self._set_metric(self.metric_decks, 0)
        self._clear_layout(self.member_cards_layout)
        self.daily_member_label.setText("当前身份：自己")
        self.daily_editor.clear()
        self.daily_editor.setEnabled(False)
        if hasattr(self, "daily_todo_link"):
            self.daily_todo_link.clear()
            self.daily_todo_link.addItem("不关联代办", 0)
            self.daily_todo_link.setEnabled(False)
        self.save_daily_button.setEnabled(False)
        self.todo_panel.setVisible(False)
        if hasattr(self, "activity_forms_panel"):
            self.activity_forms_panel.setVisible(False)
        self.daily_form.setVisible(False)
        self.project_todo_input.clear()
        self.project_todo_input.setEnabled(False)
        self.add_todo_button.setEnabled(False)
        if hasattr(self, "assigned_todo_assignee"):
            self.assigned_todo_assignee.clear()
            self.assigned_todo_assignee.setVisible(False)
        if hasattr(self, "assigned_todo_deadline_row"):
            self.assigned_todo_deadline_row.setVisible(False)
        self.todo_count_label.setText("0 个待完成")
        self.todo_board.clear()
        self._add_todo_card(None, "选择项目后，这里会显示代办。", False)
        self.product_feed.clear()
        self.developer_feed.clear()
        empty_text = "当前没有你参与的项目。" if getattr(self, "project_scope_value", "mine") == "mine" else "还没有项目。"
        self._add_feed_card(self.product_feed, "", "项目", empty_text)
        self._add_feed_card(self.developer_feed, "", "日报", "还没有项目日报。")
        self.member_name.setEnabled(False)
        self.member_role.setEnabled(False)
        self.add_member_button.setEnabled(False)
        if hasattr(self, "project_owner_select"):
            self.project_owner_select.clear()
            self.project_owner_select.setEnabled(False)
        if hasattr(self, "save_project_owner_button"):
            self.save_project_owner_button.setEnabled(False)
        self.config_project_description.clear()
        self.config_project_description.setEnabled(False)
        self.config_project_name.clear()
        self.config_project_name.setEnabled(False)
        if hasattr(self, "config_project_link"):
            self.config_project_link.clear()
            self.config_project_link.setEnabled(False)
        if hasattr(self, "config_project_backup_link"):
            self.config_project_backup_link.clear()
            self.config_project_backup_link.setEnabled(False)
        self.config_development_group_link.clear()
        self.config_development_group_link.setEnabled(False)
        self.config_coordination_group_link.clear()
        self.config_coordination_group_link.setEnabled(False)
        if hasattr(self, "config_project_notes"):
            self.config_project_notes.clear()
            self.config_project_notes.setEnabled(False)
            self.config_project_notes.setVisible(True)
        if hasattr(self, "config_project_notes_label"):
            self.config_project_notes_label.setVisible(True)
        self.save_project_description_button.setEnabled(False)
        self.config_project_panel.setVisible(False)
        self.delete_project_button.setEnabled(False)
        self.weekly_form.setVisible(False)
        self.project_weekly_editor.setEnabled(False)
        self.project_weekly_editor.setVisible(True)
        self.save_project_weekly_button.setEnabled(False)
        self.save_project_weekly_button.setVisible(True)
        self.project_document_type.setEnabled(False)
        self.project_document_visibility.setEnabled(False)
        self.upload_deck_button.setEnabled(False)
        self.project_config_button.setEnabled(False)
        self.config_member_list.clear()

    def _current_project_member(self, project: Project, members: list[ProjectMember]) -> ProjectMember | None:
        for member in members:
            if self.db.is_current_user_name(member.name):
                return member
        if self.db.is_current_user_name(project.owner):
            return ProjectMember(
                0,
                project.id,
                self.db.display_name(),
                "产品经理",
                self.db.dingtalk_id_for_name(project.owner),
                project.created_at,
            )
        return None

    def _can_manage_project(self, project: Project, member: ProjectMember | None) -> bool:
        if self._is_super_admin():
            return True
        return self.db.is_current_user_name(project.owner)

    def _can_assign_todo(self, project: Project, member: ProjectMember | None) -> bool:
        if self._can_manage_project(project, member):
            return True
        if member is None:
            return False
        role = member.role.strip()
        return "产品" in role or "测试" in role

    def _member_is_product(self, member: ProjectMember | None) -> bool:
        return member is not None and "产品" in member.role.strip()

    def _member_is_developer(self, member: ProjectMember | None) -> bool:
        if member is None:
            return False
        role = member.role.strip()
        return any(keyword in role for keyword in ("开发", "前端", "后端", "数据", "运维", "算法"))

    def _member_is_designer(self, member: ProjectMember | None) -> bool:
        if member is None:
            return False
        role = member.role.strip().upper()
        return "UI" in role or "设计" in role

    def _project_member_by_name(self, members: list[ProjectMember], name: str) -> ProjectMember | None:
        for member in members:
            if self.db.is_current_user_name(member.name) and self.db.is_current_user_name(name):
                return member
            if member.name.strip() == name.strip():
                return member
        return None

    def _first_project_tester(self, members: list[ProjectMember], exclude_name: str = "") -> ProjectMember | None:
        for member in members:
            if member.name.strip() != exclude_name.strip() and "测试" in member.role.strip():
                return member
        return None

    def _first_project_designer(self, members: list[ProjectMember], exclude_name: str = "") -> ProjectMember | None:
        for member in members:
            if member.name.strip() != exclude_name.strip() and self._member_is_designer(member):
                return member
        return None

    def _can_upload_project_document(self, project: Project, member: ProjectMember | None, is_manager: bool | None = None) -> bool:
        can_manage = is_manager if is_manager is not None else self._can_manage_project(project, member)
        if can_manage:
            return True
        if member is None:
            return False
        return "测试" in member.role.strip() or self._member_is_designer(member)

    def _refresh_project_document_type_options(self, is_manager: bool, can_upload: bool) -> None:
        if not hasattr(self, "project_document_type"):
            return
        current = self.project_document_type.currentText().strip()
        options = DOCUMENT_TYPES
        if not is_manager:
            project = self._current_project()
            current_member = self._current_project_member(project, self.db.list_project_members(project.id)) if project is not None else None
            options = []
            if self._member_is_designer(current_member):
                options.append("设计图")
            if current_member is not None and "测试" in current_member.role.strip():
                options.append("测试文档")
            if not options:
                options = ["其他"]
        self.project_document_type.blockSignals(True)
        self.project_document_type.clear()
        if can_upload:
            self.project_document_type.addItems(options)
            if current in options:
                self.project_document_type.setCurrentText(current)
            elif "设计图" in options:
                self.project_document_type.setCurrentText("设计图")
            elif "测试文档" in options:
                self.project_document_type.setCurrentText("测试文档")
        self.project_document_type.blockSignals(False)

    def _refresh_assigned_todo_assignees(self, members: list[ProjectMember], can_assign: bool) -> None:
        if not hasattr(self, "assigned_todo_assignee"):
            return
        current = self.assigned_todo_assignee.currentData()
        self.assigned_todo_assignee.blockSignals(True)
        self.assigned_todo_assignee.clear()
        if can_assign:
            for member in members:
                self.assigned_todo_assignee.addItem(f"{member.name} · {member.role}", member.name)
        if current is not None:
            for index in range(self.assigned_todo_assignee.count()):
                if self.assigned_todo_assignee.itemData(index) == current:
                    self.assigned_todo_assignee.setCurrentIndex(index)
                    break
        self.assigned_todo_assignee.blockSignals(False)

    def _refresh_daily_todo_links(
        self,
        project: Project,
        current_member: ProjectMember | None,
        is_manager: bool,
        can_write_daily: bool,
    ) -> None:
        if not hasattr(self, "daily_todo_link"):
            return
        current = int(self.daily_todo_link.currentData() or 0)
        self.daily_todo_link.blockSignals(True)
        self.daily_todo_link.clear()
        self.daily_todo_link.addItem("不关联代办", 0)
        if can_write_daily:
            todos = self.db.list_project_todos(project.id)
            for todo in todos:
                if not self._can_link_daily_todo(todo, current_member, is_manager):
                    continue
                label = self._daily_todo_option_label(todo)
                self.daily_todo_link.addItem(label, todo.id)
        if current:
            for index in range(self.daily_todo_link.count()):
                if self.daily_todo_link.itemData(index) == current:
                    self.daily_todo_link.setCurrentIndex(index)
                    break
        self.daily_todo_link.setEnabled(can_write_daily and self.daily_todo_link.count() > 1)
        self.daily_todo_link.blockSignals(False)

    def _can_link_daily_todo(self, todo: ProjectTodo, current_member: ProjectMember | None, is_manager: bool) -> bool:
        if current_member is None or todo.status == "done":
            return False
        return todo.scope == "assigned" and self._todo_visible_to_current_user(todo)

    def _daily_todo_option_label(self, todo: ProjectTodo) -> str:
        title = todo.title.strip()
        if len(title) > 22:
            title = f"{title[:22]}..."
        return f"关联代办：{todo.assigned_by or todo.creator} · {title}"

    def _todos_for_current_view(self, project_id: int, is_manager: bool) -> list[ProjectTodo]:
        todos = [
            todo
            for todo in self.db.list_project_todos(project_id, scope=self.todo_view_mode)
            if todo.status != "done"
        ]
        if self.todo_view_mode == "personal":
            if is_manager:
                return todos
            return [todo for todo in todos if self.db.is_current_user_name(todo.creator)]
        if self.todo_view_mode == "assigned":
            return [
                todo
                for todo in todos
                if self._todo_visible_to_current_user(todo)
                or self.db.is_current_user_name(todo.assigned_by)
                or is_manager
            ]
        return todos

    def _todo_visible_to_current_user(self, todo: ProjectTodo) -> bool:
        if todo.workflow == "dev_test_accept":
            return self.db.is_current_user_name(todo.current_handler)
        return self.db.is_current_user_name(todo.assignee)

    def _todo_current_handler(self, todo: ProjectTodo) -> str:
        return todo.current_handler.strip() or todo.assignee.strip()

    def _todo_status_text(self, todo: ProjectTodo) -> str:
        return {
            "ui_todo": "待UI",
            "dev_todo": "待开发",
            "dev_doing": "开发中",
            "test_todo": "待测试",
            "accept_todo": "待验收",
            "done": "已完成",
            "todo": "待完成",
        }.get(todo.status, "进行中")

    def _todo_primary_action_text(self, todo: ProjectTodo) -> str:
        if todo.workflow != "dev_test_accept":
            return "完成"
        has_tester = self._first_project_tester(self.db.list_project_members(todo.project_id)) is not None
        return {
            "ui_todo": "提交开发",
            "dev_todo": "提交测试" if has_tester else "提交验收",
            "dev_doing": "提交测试" if has_tester else "提交验收",
            "test_todo": "测试通过",
            "accept_todo": "验收通过",
        }.get(todo.status, "完成")

    def _todo_can_start(self, todo: ProjectTodo) -> bool:
        if todo.workflow == "dev_test_accept":
            return todo.status == "dev_todo"
        return todo.started_at is None

    def _todo_can_record(self, todo: ProjectTodo) -> bool:
        if todo.workflow == "dev_test_accept":
            return todo.status in {"ui_todo", "dev_doing"}
        return todo.started_at is not None

    def _todo_can_reject(self, todo: ProjectTodo) -> bool:
        return todo.workflow == "dev_test_accept" and todo.status == "test_todo"

    def _todo_can_advance(self, todo: ProjectTodo) -> bool:
        if todo.status == "done":
            return False
        if todo.workflow == "dev_test_accept":
            return todo.status in {"ui_todo", "dev_doing", "test_todo", "accept_todo"}
        return True

    def _todo_can_skip_ui(self, todo: ProjectTodo) -> bool:
        return todo.workflow == "dev_test_accept" and todo.status == "ui_todo"

    def _can_complete_todo(
        self,
        todo: ProjectTodo,
        current_member: ProjectMember | None,
        is_manager: bool,
    ) -> bool:
        if current_member is None or todo.status == "done":
            return False
        if todo.scope == "project":
            return is_manager
        if todo.scope == "assigned":
            return self._todo_visible_to_current_user(todo)
        return True

    def _clear_layout(self, layout: QGridLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _is_super_admin(self) -> bool:
        return any(self.db.is_current_user_name(name) for name in SUPER_ADMIN_NAMES)

    def _refresh_project_owner_options(
        self,
        project: Project,
        members: list[ProjectMember],
        can_manage: bool,
    ) -> None:
        self.project_owner_select.blockSignals(True)
        self.project_owner_select.clear()
        names: list[str] = []
        for name in [project.owner, *(member.name for member in members)]:
            name = name.strip()
            if name and name not in names:
                names.append(name)
        for name in names:
            role = "负责人" if name == project.owner else self._project_member_role(members, name)
            self.project_owner_select.addItem(f"{name} · {role}" if role else name, name)
        for index in range(self.project_owner_select.count()):
            if self.project_owner_select.itemData(index) == project.owner:
                self.project_owner_select.setCurrentIndex(index)
                break
        self.project_owner_select.setEnabled(can_manage and bool(names))
        self.save_project_owner_button.setEnabled(can_manage and bool(names))
        self.project_owner_select.blockSignals(False)

    def _project_member_role(self, members: list[ProjectMember], name: str) -> str:
        for member in members:
            if member.name.strip() == name.strip():
                return member.role.strip()
        return ""

    def _save_project_owner(self) -> None:
        project = self._current_project()
        if project is None:
            return
        if not self._can_manage_project(project, None):
            QMessageBox.warning(self, "不能保存", "只有这个项目的负责人或最高权限用户可以更改负责人。")
            return
        owner = str(self.project_owner_select.currentData() or self.project_owner_select.currentText()).strip()
        if not owner:
            QMessageBox.information(self, "负责人为空", "先选择新的项目负责人。")
            return
        if owner == project.owner:
            return
        updated = self.db.update_project_owner(project.id, owner)
        if updated is None:
            QMessageBox.warning(self, "保存失败", "这个项目记录已经不存在。")
            self._load_projects()
            return
        self.current_project_id = updated.id
        self._load_projects()
        self._refresh_project_workspace()
        self._announce_presence()

    def _refresh_config_member_list(
        self,
        project: Project,
        members: list[ProjectMember],
        can_manage: bool,
    ) -> None:
        self.config_member_list.clear()
        if not members:
            item = QListWidgetItem("还没有成员。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.config_member_list.addItem(item)
            return
        for member in members:
            self._add_config_member_card(project, member, can_manage)

    def _add_config_member_card(self, project: Project, member: ProjectMember, can_manage: bool) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)

        card = QWidget()
        card.setObjectName("feedCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        text_box = QVBoxLayout()
        text_box.setSpacing(4)
        text_box.addWidget(self._name_with_chat(member.name))
        text_box.addWidget(_label(member.role, "muted"))
        layout.addLayout(text_box, 1)

        delete_button = QPushButton("删除")
        delete_button.setObjectName("smallButton")
        protected_member = (
            not self._is_super_admin()
            and (self.db.is_current_user_name(member.name) or member.name == project.owner)
        )
        delete_button.setEnabled(can_manage and not protected_member)
        delete_button.clicked.connect(lambda checked=False, selected=member: self._delete_project_member(selected))
        layout.addWidget(delete_button)

        item.setSizeHint(QSize(0, 74))
        self.config_member_list.addItem(item)
        self.config_member_list.setItemWidget(item, card)

    def _delete_project_member(self, member: ProjectMember) -> None:
        project = self._current_project()
        if project is None:
            return
        if not self._can_manage_project(project, None):
            QMessageBox.warning(self, "不能配置", "只有这个项目的负责人或最高权限用户可以删除成员。")
            return
        if not self._is_super_admin() and (self.db.is_current_user_name(member.name) or member.name == project.owner):
            QMessageBox.information(self, "不能删除", "负责人不能从项目成员里删除。")
            return
        message = f"确定从项目「{project.name}」删除成员「{member.name}」吗？"
        if QMessageBox.question(self, "删除成员", message) != QMessageBox.StandardButton.Yes:
            return
        if not self.db.delete_project_member(member.id):
            QMessageBox.warning(self, "删除失败", "这个成员记录已经不存在。")
            return
        self._refresh_project_workspace()

    def _delete_project_progress_item(self, payload: tuple[str, int, str]) -> None:
        project = self._current_project()
        if project is None:
            return
        if not self._can_manage_project(project, None):
            QMessageBox.warning(self, "不能删除", "只有这个项目的产品经理或最高权限用户可以删除项目进展。")
            return
        item_type, record_id, label = payload
        message = f"确定从项目进展流删除「{label}」吗？"
        if QMessageBox.question(self, "删除项目进展", message) != QMessageBox.StandardButton.Yes:
            return

        deleted = False
        if item_type == "member":
            deleted = self.db.delete_project_member(record_id)
        elif item_type == "project_weekly":
            deleted = self.db.delete_project_weekly_report(record_id)
        elif item_type == "document":
            deleted = self.db.delete_project_document(record_id)
        elif item_type == "todo":
            deleted = self.db.delete_project_todo(record_id)

        if not deleted:
            QMessageBox.warning(self, "删除失败", "这条项目进展已经不存在。")
            self._refresh_project_workspace()
            return
        self._refresh_project_workspace()
        self._refresh_document_library()
        self._refresh_badge_wall()
        self._announce_presence()

    def _add_member_card(self, member: ProjectMember) -> None:
        card = QWidget()
        card.setObjectName("compactMemberCard")
        card.setFixedHeight(66)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        avatar = _label((member.name[:1] or "?").upper(), "compactAvatar")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        name = self._name_with_chat(member.name)
        role = _label(member.role, "compactRoleBadge")
        role.setFixedWidth(82)
        text_box.addWidget(name)
        role_row = QHBoxLayout()
        role_row.setContentsMargins(0, 0, 0, 0)
        role_row.setSpacing(8)
        role_row.addWidget(role)
        daily_button = QPushButton("日报")
        daily_button.setObjectName("smallButton")
        daily_button.setFixedHeight(26)
        daily_button.setFixedWidth(58)
        daily_button.clicked.connect(lambda checked=False, selected=member: self._open_project_member_daily_reports(selected))
        role_row.addWidget(daily_button)
        role_row.addStretch()
        text_box.addLayout(role_row)

        layout.addWidget(avatar)
        layout.addLayout(text_box, 1)

        index = self.member_cards_layout.count()
        self.member_cards_layout.addWidget(card, index, 0)
        self.member_cards_layout.setRowStretch(index, 0)
        self.member_cards_layout.setRowStretch(index + 1, 1)

    def _add_todo_card(self, todo: ProjectTodo | None, title: str, can_complete: bool) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)

        card = QWidget()
        card.setObjectName("feedCard")
        if todo is not None:
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setToolTip("查看代办详情")
            card.mousePressEvent = lambda event, selected=todo: self._open_todo_detail(selected)  # type: ignore[method-assign]
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        body = QVBoxLayout()
        body.setSpacing(4)
        meta_text = "待完成"
        actor_name = ""
        if todo is not None:
            actor_name = todo.creator or "项目成员"
            meta_text = f"{todo.created_at.strftime('%m-%d %H:%M')}"
            if todo.scope == "assigned":
                actor_name = ""
                meta_text = f"{todo.created_at.strftime('%m-%d %H:%M')}"
            elif todo.scope == "project":
                actor_name = ""
                meta_text = f"{todo.created_at.strftime('%m-%d %H:%M')}  项目代办"
        if todo is not None and todo.scope == "assigned":
            meta_row = QHBoxLayout()
            meta_row.setContentsMargins(0, 0, 0, 0)
            meta_row.setSpacing(5)
            meta_row.addWidget(_label(f"{meta_text} · {self._todo_status_text(todo)}", "eyebrow"))
            meta_row.addWidget(self._name_with_chat(todo.assigned_by or todo.creator))
            meta_row.addWidget(_label("->", "eyebrow"))
            meta_row.addWidget(self._name_with_chat(self._todo_current_handler(todo) or todo.assignee))
            meta_row.addStretch()
            body.addLayout(meta_row)
            due_text = self._todo_due_text(todo)
            if due_text:
                body.addWidget(_label(due_text, "eyebrow"))
            started_text = self._todo_started_text(todo)
            if started_text:
                body.addWidget(_label(started_text, "eyebrow"))
        elif actor_name:
            meta_row = QHBoxLayout()
            meta_row.setContentsMargins(0, 0, 0, 0)
            meta_row.setSpacing(5)
            meta_row.addWidget(_label(meta_text, "eyebrow"))
            meta_row.addWidget(self._name_with_chat(actor_name))
            meta_row.addStretch()
            body.addLayout(meta_row)
        else:
            body.addWidget(_label(meta_text, "eyebrow"))
        body.addWidget(_label(title))
        if todo is not None:
            progress_text = self._todo_progress_text(todo)
            if progress_text:
                body.addWidget(_label(progress_text, "muted"))
        layout.addLayout(body, 1)

        if todo is not None:
            if todo.scope == "assigned" and self._todo_visible_to_current_user(todo) and self._todo_can_start(todo):
                start_button = QPushButton("开始开发" if todo.workflow == "dev_test_accept" else "开始")
                start_button.setObjectName("smallButton")
                start_button.clicked.connect(lambda checked=False, selected=todo: self._start_project_todo(selected))
                layout.addWidget(start_button)
            elif todo.scope == "assigned" and self._todo_visible_to_current_user(todo) and self._todo_can_record(todo):
                record_button = QPushButton("记录")
                record_button.setObjectName("smallButton")
                record_button.clicked.connect(lambda checked=False, selected=todo: self._record_todo_daily_report(selected))
                layout.addWidget(record_button)
            if self._todo_can_advance(todo):
                done_button = QPushButton("完成")
                done_button.setText(self._todo_primary_action_text(todo))
                done_button.setObjectName("smallButton")
                done_button.setEnabled(can_complete)
                done_button.clicked.connect(lambda checked=False, selected=todo: self._complete_project_todo(selected))
                layout.addWidget(done_button)
            if self._todo_can_reject(todo):
                reject_button = QPushButton("打回")
                reject_button.setObjectName("smallButton")
                reject_button.setEnabled(can_complete)
                reject_button.clicked.connect(lambda checked=False, selected=todo: self._reject_project_todo(selected))
                layout.addWidget(reject_button)
            if self._todo_can_skip_ui(todo):
                skip_button = QPushButton("跳过UI")
                skip_button.setObjectName("smallButton")
                skip_button.setEnabled(can_complete)
                skip_button.clicked.connect(lambda checked=False, selected=todo: self._skip_project_todo_ui(selected))
                layout.addWidget(skip_button)

        extra_lines = 0
        if todo is not None:
            if self._todo_due_text(todo):
                extra_lines += 1
            if self._todo_started_text(todo):
                extra_lines += 1
            if self._todo_progress_text(todo):
                extra_lines += 1
        item.setSizeHint(QSize(0, 72 + extra_lines * 24))
        self.todo_board.addItem(item)
        self.todo_board.setItemWidget(item, card)

    def _start_project_todo(self, todo: ProjectTodo) -> None:
        if not self._todo_visible_to_current_user(todo):
            QMessageBox.information(self, "不能开始", "只有当前处理人可以开始这条分配代办。")
            return
        updated = self.db.start_project_todo(todo.id, self.db.display_name())
        if updated is None:
            QMessageBox.information(self, "不能开始", "这个代办已经完成、不是分配代办，或已经不存在。")
            return
        self._refresh_project_workspace()
        self._refresh_my_panel()
        self._announce_presence()

    def _record_todo_daily_report(self, todo: ProjectTodo) -> None:
        latest = self.db.get_project_todo(todo.id) or todo
        project = self.db.get_project(latest.project_id)
        if project is None:
            QMessageBox.information(self, "项目不存在", "这条代办对应的项目已经不存在。")
            return
        if not self._todo_visible_to_current_user(latest):
            QMessageBox.information(self, "不能记录", "只有当前处理人可以记录这条代办的日报。")
            return
        current_member = self._current_project_member(project, self.db.list_project_members(project.id))
        if current_member is None:
            QMessageBox.information(self, "不能记录", "只有项目成员可以写日报。")
            return
        dialog = TodoDailyReportDialog(latest, project.name, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        content = dialog.content()
        if not content:
            QMessageBox.information(self, "日报为空", "先写一点代办进展。")
            return
        self.db.add_daily_report(project.id, current_member.name, current_member.role, content, todo_id=latest.id)
        self._refresh_project_workspace()
        self._refresh_my_panel()
        self._refresh_rest_calendar()
        self._refresh_badge_wall()
        self._nudge_after_late_record()
        self._announce_presence()

    def _add_feed_card(
        self,
        list_widget: QListWidget,
        time_text: str,
        kind: str,
        content: str,
        document: ProjectDocument | None = None,
        daily_report: DailyReport | None = None,
        progress_delete: tuple[str, int, str] | None = None,
        height: int | None = None,
        min_content_lines: int = 1,
        max_content_lines: int | None = 2,
        visual_chars_per_line: int = 32,
        person_name: str = "",
        person_dingtalk_id: str = "",
    ) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)

        card = QWidget()
        card.setObjectName("feedCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        body = QVBoxLayout()
        body.setSpacing(5)
        meta_text = f"{time_text}  {kind}".strip()
        meta = _label(meta_text, "eyebrow")
        meta.setWordWrap(False)
        text = _label(content)
        if max_content_lines is not None:
            text.setMaximumHeight(max_content_lines * 24)
        if person_name:
            meta_row = QHBoxLayout()
            meta_row.setContentsMargins(0, 0, 0, 0)
            meta_row.setSpacing(8)
            meta_row.addWidget(meta)
            meta_row.addWidget(self._name_with_chat(person_name, person_dingtalk_id))
            meta_row.addStretch()
            body.addLayout(meta_row)
        else:
            body.addWidget(meta)
        body.addWidget(text)
        layout.addLayout(body, 1)
        linked_todo = self._todo_for_daily_report(daily_report) if daily_report is not None else None

        if document is not None:
            actions = QHBoxLayout()
            actions.setSpacing(8)
            open_button = QPushButton("打开")
            open_button.setObjectName("smallButton")
            open_button.clicked.connect(lambda checked=False, selected=document: self._open_deck_file(selected))
            actions.addWidget(open_button)
            if progress_delete is not None:
                delete_button = QPushButton("删除")
                delete_button.setObjectName("smallButton")
                delete_button.clicked.connect(
                    lambda checked=False, payload=progress_delete: self._delete_project_progress_item(payload)
                )
                actions.addWidget(delete_button)
            elif self.db.is_current_user_name(document.uploader):
                delete_button = QPushButton("删除")
                delete_button.setObjectName("smallButton")
                delete_button.clicked.connect(lambda checked=False, selected=document: self._delete_project_document(selected))
                actions.addWidget(delete_button)
            layout.addLayout(actions)
        elif progress_delete is not None:
            actions = QHBoxLayout()
            actions.setSpacing(8)
            delete_button = QPushButton("删除")
            delete_button.setObjectName("smallButton")
            delete_button.clicked.connect(
                lambda checked=False, payload=progress_delete: self._delete_project_progress_item(payload)
            )
            actions.addWidget(delete_button)
            layout.addLayout(actions)
        elif daily_report is not None and (linked_todo is not None or self.db.is_current_user_name(daily_report.member_name)):
            actions = QHBoxLayout()
            actions.setSpacing(8)
            if self.db.is_current_user_name(daily_report.member_name):
                delete_button = QPushButton("删除")
                delete_button.setObjectName("smallButton")
                delete_button.clicked.connect(lambda checked=False, selected=daily_report: self._delete_daily_report(selected))
                actions.addWidget(delete_button)
            layout.addLayout(actions)

        if linked_todo is not None:
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setToolTip("查看代办详情")
            card.mousePressEvent = lambda event, selected=linked_todo: self._open_todo_detail(selected)  # type: ignore[method-assign]

        if height is None:
            height = self._feed_card_height(
                content,
                min_content_lines,
                max_content_lines,
                meta_text=meta_text,
                visual_chars_per_line=visual_chars_per_line,
            )
        item.setSizeHint(QSize(0, height))
        list_widget.addItem(item)
        list_widget.setItemWidget(item, card)

    def _daily_report_groups(self, reports: list[DailyReport]) -> list[list[DailyReport]]:
        groups: dict[tuple[date, str], list[DailyReport]] = {}
        for report in reports:
            key = (report.created_at.date(), " ".join(report.member_name.strip().split()).casefold())
            groups.setdefault(key, []).append(report)
        result = list(groups.values())
        for group in result:
            group.sort(key=lambda report: report.created_at)
        result.sort(key=lambda group: group[-1].created_at, reverse=True)
        return result

    def _add_daily_report_group_card(self, list_widget: QListWidget, reports: list[DailyReport]) -> None:
        if not reports:
            return
        latest = max(reports, key=lambda report: report.created_at)
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)

        card = QWidget()
        card.setObjectName("feedCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(_nowrap_label(f"{latest.created_at.strftime('%m-%d %H:%M')}  日报 · {latest.role}", "eyebrow"))
        header.addWidget(self._name_with_chat(latest.member_name, self.db.dingtalk_id_for_name(latest.member_name)))
        header.addStretch()
        layout.addLayout(header)

        row_widgets: list[QWidget] = []
        row_labels: list[QLabel] = []

        def measured_text_height(label: QLabel, width: int) -> int:
            document = QTextDocument()
            document.setDefaultFont(label.font())
            document.setDocumentMargin(0)
            document.setPlainText(label.text())
            document.setTextWidth(max(120, width))
            return int(document.size().height()) + 2

        def refresh_height() -> None:
            if not all(_is_qt_object_alive(obj) for obj in (list_widget, card, item)):
                return
            try:
                content_width = max(260, list_widget.viewport().width() - 64)
                for row_widget, row_label in zip(row_widgets, row_labels):
                    if not all(_is_qt_object_alive(obj) for obj in (row_widget, row_label)):
                        return
                    buttons = [button for button in row_widget.findChildren(QPushButton) if _is_qt_object_alive(button)]
                    button_width = sum(button.sizeHint().width() for button in buttons)
                    label_width = content_width - button_width - (12 if buttons else 0)
                    next_height = max(row_label.fontMetrics().height(), measured_text_height(row_label, label_width))
                    row_label.setFixedHeight(next_height)
                    row_widget.setFixedHeight(next_height + 12)
                height = card.sizeHint().height() + 2
                card.setFixedHeight(height)
                item.setSizeHint(QSize(0, height))
                list_widget.doItemsLayout()
            except RuntimeError:
                return

        for report in reports:
            row_box = QVBoxLayout()
            row_box.setContentsMargins(0, 0, 0, 0)
            row_box.setSpacing(0)

            content = report.content.strip() or "空日报"
            row_text = f"{report.created_at.strftime('%H:%M')}  {content}"
            linked_todo = self._todo_for_daily_report(report)
            row_widget = QWidget()
            row_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(12)
            row_label = _label(row_text)
            row_label.setWordWrap(True)
            row_layout.addWidget(row_label, 1)
            row_widgets.append(row_widget)
            row_labels.append(row_label)
            if self.db.is_current_user_name(report.member_name):
                delete_button = QPushButton("删除")
                delete_button.setObjectName("dailyReportDeleteButton")
                delete_button.clicked.connect(lambda checked=False, selected=report: self._delete_daily_report(selected))
                row_layout.addWidget(delete_button)
            row_box.addWidget(row_widget)
            row_widget.mousePressEvent = lambda event, selected=report: self._handle_daily_report_click(selected)  # type: ignore[method-assign]
            layout.addLayout(row_box)

        refresh_height()
        list_widget.addItem(item)
        list_widget.setItemWidget(item, card)
        QTimer.singleShot(0, refresh_height)

    def _handle_daily_report_click(self, report: DailyReport) -> None:
        linked_todo = self._todo_for_daily_report(report)
        if linked_todo is not None:
            self._open_todo_detail(linked_todo, highlight_report_id=report.id)
            return
        self._open_daily_report_detail(report)

    def _open_daily_report_detail(self, report: DailyReport) -> None:
        linked_todo = self._todo_for_daily_report(report)
        linked_text = self._daily_report_todo_text(report)
        dialog = DailyReportDetailDialog(
            report,
            linked_todo,
            linked_text,
            self.db.is_current_user_name(report.member_name),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.delete_requested:
            self._delete_daily_report(report)
            return
        if linked_todo is not None:
            self._open_todo_detail(linked_todo)

    def _feed_card_height(
        self,
        content: str,
        min_lines: int = 1,
        max_lines: int | None = 2,
        meta_text: str = "",
        visual_chars_per_line: int = 32,
    ) -> int:
        def visual_line_count(value: str) -> int:
            normalized_value = " ".join(value.strip().split())
            if not normalized_value:
                return 1
            explicit = len([line for line in value.splitlines() if line.strip()])
            width = sum(1 if ord(char) < 128 else 2 for char in normalized_value)
            return max(explicit, max(1, (width + visual_chars_per_line - 1) // visual_chars_per_line))

        normalized = " ".join(content.strip().split())
        if not normalized:
            line_count = min_lines
            return 42 + visual_line_count(meta_text) * 22 + line_count * 26
        content_lines = visual_line_count(content)
        line_count = max(min_lines, content_lines if max_lines is None else min(max_lines, content_lines))
        return 42 + visual_line_count(meta_text) * 22 + line_count * 26

    def _delete_daily_report(self, report: DailyReport) -> None:
        message = f"确定删除 {report.created_at.strftime('%m-%d %H:%M')} 的日报吗？"
        if QMessageBox.question(self, "删除日报", message) != QMessageBox.StandardButton.Yes:
            return
        if not self.db.delete_daily_report(report.id):
            QMessageBox.warning(self, "删除失败", "只能删除自己的日报，或这条日报已经不存在。")
            return
        self._refresh_project_workspace()
        self._refresh_rest_calendar()
        self._refresh_badge_wall()
        self._announce_presence()

    def _daily_feed_text(self, report: DailyReport) -> str:
        linked_todo = self._daily_report_todo_text(report)
        todo_line = f"\n关联代办：{linked_todo}" if linked_todo else ""
        return (
            f"{report.created_at.strftime('%m-%d %H:%M')}  日报 · {report.member_name} / {report.role}\n"
            f"{report.content}{todo_line}"
        )

    def _open_feed_item(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(payload, tuple) or len(payload) != 2:
            return
        kind, record_id = payload
        if kind == "deck" and isinstance(record_id, int):
            self._show_deck_detail(record_id)

    def _show_deck_detail(self, deck_id: int) -> None:
        document = self.db.get_project_document(deck_id)
        if document is None:
            QMessageBox.warning(self, "文件记录不存在", "这个文档记录已经不存在。")
            self._refresh_project_workspace()
            return
        self.selected_document_id = document.id
        self._render_deck_detail(document)
        self.project_content_stack.setCurrentIndex(1)

    def _render_deck_detail(self, document: ProjectDocument) -> None:
        source = _safe_local_path(document.file_path)
        exists = _path_exists_safely(source)
        status = "文件可用" if exists else "文件不在本机"
        visibility = "团队文档" if document.visibility == "team" else "本人文档"
        self.deck_detail_title.setText(document.title)
        self.deck_detail_meta.setText(
            f"{document.doc_type} · {visibility} · {document.uploader} · {document.created_at.strftime('%Y-%m-%d %H:%M')} · {status}"
        )
        self.deck_detail_path.setPlainText(str(source) if source is not None else str(document.file_path))
        self.open_deck_button.setEnabled(exists)

    def _show_project_overview(self) -> None:
        if hasattr(self, "project_content_stack"):
            self.project_content_stack.setCurrentIndex(0)

    def _selected_deck(self) -> ProjectDocument | None:
        if self.selected_document_id is None:
            return None
        return self.db.get_project_document(self.selected_document_id)

    def _open_selected_deck_file(self) -> None:
        deck = self._selected_deck()
        if deck is None:
            return
        self._open_deck_file(deck)

    def _open_deck_file(self, deck: ProjectDocument) -> None:
        source = _safe_local_path(deck.file_path)
        if not _path_exists_safely(source):
            QMessageBox.warning(self, "文件不在本机", "这个文档文件没有同步到当前电脑，或原文件已经被移动。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(source)))

    def _delete_project_document(self, document: ProjectDocument) -> None:
        if not self.db.is_current_user_name(document.uploader):
            QMessageBox.warning(self, "不能删除", "只有上传这个文档的人可以删除。")
            return
        message = f"确定删除文档「{document.title}」吗？"
        if QMessageBox.question(self, "删除文档", message) != QMessageBox.StandardButton.Yes:
            return
        if not self.db.delete_project_document(document.id, uploader=self.db.display_name()):
            QMessageBox.warning(self, "删除失败", "只能删除自己上传的文档，或这条文档记录已经不存在。")
            return
        self._refresh_project_workspace()
        self._refresh_document_library()
        self._announce_presence()

    def _weekly_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(34, 22, 34, 30)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title_box.addWidget(_label("周报", "sectionTitle"))
        header.addLayout(title_box)
        header.addStretch()
        mood_badge = _label("LOCAL AI", "eyebrow")
        mood_badge.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(mood_badge)
        outer.addLayout(header)

        splitter = QSplitter()
        outer.addWidget(splitter, 1)

        editor_panel = _panel()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(20, 20, 20, 20)
        editor_layout.setSpacing(14)
        weekly_record_header = QHBoxLayout()
        weekly_record_header.addWidget(_label("本周记录", "eyebrow"))
        weekly_record_header.addStretch()
        import_weekly_content = QPushButton("一键导入")
        import_weekly_content.setObjectName("smallButton")
        import_weekly_content.setToolTip("导入本周一至今天的项目内容")
        import_weekly_content.clicked.connect(self._import_current_week_project_content)
        weekly_record_header.addWidget(import_weekly_content)
        editor_layout.addLayout(weekly_record_header)
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("完成、变化、阻塞、下周。")
        weekly_actions = QHBoxLayout()
        self.weekly_ai_button = QPushButton("AI 整理")
        self.weekly_ai_button.clicked.connect(self._summarize_weekly_with_server)
        self.weekly_save_button = QPushButton("保存")
        self.weekly_save_button.setObjectName("primaryButton")
        self.weekly_save_button.clicked.connect(self._save_weekly_report)
        editor_layout.addWidget(self.editor)
        weekly_actions.addWidget(self.weekly_ai_button)
        weekly_actions.addWidget(self.weekly_save_button)
        editor_layout.addLayout(weekly_actions)

        result_panel = _panel()
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(20, 20, 20, 20)
        result_layout.setSpacing(14)
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setPlaceholderText("AI 总结会显示在这里")
        self.history = QListWidget()
        self.history.itemClicked.connect(self._show_history_item)
        self.history.currentItemChanged.connect(self._update_delete_weekly_enabled)
        self.delete_weekly_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.history)
        self.delete_weekly_shortcut.activated.connect(self._delete_selected_weekly_report)
        self.backspace_weekly_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self.history)
        self.backspace_weekly_shortcut.activated.connect(self._delete_selected_weekly_report)
        result_layout.addWidget(_label("AI 摘要", "eyebrow"))
        result_layout.addWidget(self.summary, 2)
        history_header = QHBoxLayout()
        history_header.addWidget(_label("历史记录", "eyebrow"))
        history_header.addStretch()
        self.delete_weekly_button = QPushButton("删除")
        self.delete_weekly_button.setObjectName("smallButton")
        self.delete_weekly_button.setEnabled(False)
        self.delete_weekly_button.clicked.connect(self._delete_selected_weekly_report)
        history_header.addWidget(self.delete_weekly_button)
        result_layout.addLayout(history_header)
        result_layout.addWidget(self.history, 1)

        splitter.addWidget(editor_panel)
        splitter.addWidget(result_panel)
        splitter.setSizes([600, 420])
        return page

    def _import_current_week_project_content(self) -> None:
        now = datetime.now()
        week_start = datetime.combine(now.date() - timedelta(days=now.weekday()), datetime.min.time())
        projects = {project.id: project for project in self.db.list_projects()}
        grouped: dict[int, dict[str, list[str]]] = {}

        def add(project_id: int, category: str, content: str) -> None:
            text = " ".join(content.strip().split())
            if not text or project_id not in projects:
                return
            categories = grouped.setdefault(project_id, {})
            values = categories.setdefault(category, [])
            if text not in values:
                values.append(text)

        for project_id in projects:
            for report in self.db.list_daily_reports(project_id, limit=1000):
                if week_start <= report.created_at <= now and self.db.is_current_user_name(report.member_name):
                    add(project_id, "日报", report.content)
            for report in self.db.list_project_weekly_reports(project_id, limit=1000):
                if week_start <= report.created_at <= now and self.db.is_current_user_name(report.author):
                    add(project_id, "记录", report.content)

        for todo in self.db.list_all_project_todos(include_completed=True):
            if (
                todo.completed_at is not None
                and week_start <= todo.completed_at <= now
                and self.db.is_current_user_name(todo.completed_by)
            ):
                add(todo.project_id, "完成代办", todo.title)
            if (
                week_start <= todo.created_at <= now
                and todo.scope == "assigned"
                and (
                    self.db.is_current_user_name(todo.assigned_by)
                    or self.db.is_current_user_name(todo.creator)
                )
            ):
                assignee = f"（安排给 {todo.assignee}）" if todo.assignee.strip() else ""
                add(todo.project_id, "安排代办", f"{todo.title}{assignee}")
            if not todo.flow_history.strip():
                continue
            try:
                flow_entries = json.loads(todo.flow_history)
            except json.JSONDecodeError:
                continue
            if not isinstance(flow_entries, list):
                continue
            for entry in flow_entries:
                if not isinstance(entry, dict) or not self.db.is_current_user_name(str(entry.get("actor", ""))):
                    continue
                try:
                    happened_at = datetime.fromisoformat(str(entry.get("time", "")))
                except ValueError:
                    continue
                if not week_start <= happened_at <= now:
                    continue
                action = str(entry.get("action", "记录")).strip() or "记录"
                handler = str(entry.get("handler", "")).strip()
                suffix = f" → {handler}" if handler else ""
                add(todo.project_id, "记录", f"{todo.title}：{action}{suffix}")

        category_order = ("日报", "记录", "完成代办", "安排代办")
        sections: list[str] = []
        for project in self.db.list_projects():
            categories = grouped.get(project.id)
            if not categories:
                continue
            lines = [f"【{project.name}】"]
            for category in category_order:
                values = categories.get(category, [])
                if not values:
                    continue
                lines.append(f"{category}：")
                lines.extend(f"- {value}" for value in values)
            sections.append("\n".join(lines))

        if not sections:
            QMessageBox.information(self, "没有可导入内容", "本周一到今天还没有找到你的项目内容。")
            return
        imported = "\n\n".join(sections)
        current = self.editor.toPlainText().strip()
        if imported in current:
            QMessageBox.information(self, "已经导入", "这些项目内容已经在本周记录中。")
            return
        self.editor.setPlainText(f"{current}\n\n{imported}" if current else imported)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)

    def _rest_calendar_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(42, 38, 42, 38)
        outer.setSpacing(24)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.addWidget(_label("日历", "sectionTitle"))
        title_box.addWidget(_label("按日期看自己的休息安排，也能回看当天自己的项目日报。", "muted"))
        header.addLayout(title_box)
        header.addStretch()
        self.rest_calendar_mode_button = QPushButton("休息日历")
        self.rest_calendar_mode_button.setCheckable(True)
        self.rest_calendar_mode_button.clicked.connect(lambda checked=False: self._select_calendar_mode("rest"))
        self.daily_calendar_mode_button = QPushButton("日报日历")
        self.daily_calendar_mode_button.setCheckable(True)
        self.daily_calendar_mode_button.clicked.connect(lambda checked=False: self._select_calendar_mode("daily"))
        previous_month = QPushButton("上月")
        previous_month.setObjectName("smallButton")
        previous_month.clicked.connect(lambda checked=False: self._move_rest_calendar_month(-1))
        next_month = QPushButton("下月")
        next_month.setObjectName("smallButton")
        next_month.clicked.connect(lambda checked=False: self._move_rest_calendar_month(1))
        self.rest_month_label = _label("", "sectionTitle")
        self.rest_month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.rest_calendar_mode_button)
        header.addWidget(self.daily_calendar_mode_button)
        export_daily = QPushButton("导出近一周")
        export_daily.setObjectName("smallButton")
        export_daily.clicked.connect(self._export_recent_week_daily_reports)
        header.addWidget(export_daily)
        header.addWidget(previous_month)
        header.addWidget(self.rest_month_label)
        header.addWidget(next_month)
        outer.addLayout(header)

        splitter = QSplitter()
        outer.addWidget(splitter)

        calendar_panel = _panel()
        calendar_layout = QVBoxLayout(calendar_panel)
        calendar_layout.setContentsMargins(20, 20, 20, 20)
        calendar_layout.setSpacing(14)
        self.rest_summary = _label("", "muted")
        self.rest_calendar_grid = QGridLayout()
        self.rest_calendar_grid.setSpacing(8)
        calendar_layout.addWidget(self.rest_summary)
        calendar_layout.addLayout(self.rest_calendar_grid)

        side_panel = _panel()
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(0, 0, 0, 0)
        self.calendar_side_stack = QStackedWidget()

        rest_side = QWidget()
        rest_layout = QVBoxLayout(rest_side)
        rest_layout.setContentsMargins(20, 20, 20, 20)
        rest_layout.setSpacing(14)
        rest_layout.addWidget(_label("选中日期", "eyebrow"))
        self.rest_selected_label = _label("", "memberName")
        self.rest_selected_detail = _label("", "muted")
        self.rest_note = QLineEdit()
        self.rest_note.setPlaceholderText("备注，例如：调休、年假、上午休息")
        self.rest_toggle_button = QPushButton("安排休息")
        self.rest_toggle_button.setObjectName("primaryButton")
        self.rest_toggle_button.clicked.connect(self._toggle_selected_rest_day)
        rest_layout.addWidget(self.rest_selected_label)
        rest_layout.addWidget(self.rest_selected_detail)
        rest_layout.addWidget(self.rest_note)
        rest_layout.addWidget(self.rest_toggle_button)
        rest_layout.addSpacing(16)
        next_week_header = QHBoxLayout()
        next_week_header.addWidget(_label("下一周", "eyebrow"))
        next_week_header.addStretch()
        all_next_week = QPushButton("全员下周")
        all_next_week.setObjectName("smallButton")
        all_next_week.clicked.connect(self._open_next_week_roster)
        next_week_header.addWidget(all_next_week)
        rest_layout.addLayout(next_week_header)
        self.next_week_layout = QVBoxLayout()
        self.next_week_layout.setSpacing(8)
        rest_layout.addLayout(self.next_week_layout)
        rest_layout.addStretch()

        daily_side = QWidget()
        daily_layout = QVBoxLayout(daily_side)
        daily_layout.setContentsMargins(20, 20, 20, 20)
        daily_layout.setSpacing(14)
        daily_layout.addWidget(_label("当日日报", "eyebrow"))
        self.daily_calendar_selected_label = _label("", "memberName")
        self.daily_calendar_summary = _label("", "muted")
        self.daily_calendar_list = QListWidget()
        self.daily_calendar_list.setObjectName("plainList")
        self.daily_calendar_list.setSpacing(8)
        daily_layout.addWidget(self.daily_calendar_selected_label)
        daily_layout.addWidget(self.daily_calendar_summary)
        daily_layout.addWidget(self.daily_calendar_list, 1)

        self.calendar_side_stack.addWidget(rest_side)
        self.calendar_side_stack.addWidget(daily_side)
        side_layout.addWidget(self.calendar_side_stack)

        splitter.addWidget(calendar_panel)
        splitter.addWidget(side_panel)
        splitter.setSizes([760, 360])
        self._select_calendar_mode("rest")
        return page

    def _refresh_rest_calendar(self) -> None:
        if not hasattr(self, "rest_calendar_grid"):
            return

        rest_days = self.db.list_rest_days()
        rest_by_day = {item.day: item for item in rest_days}
        daily_counts = self.db.daily_report_counts_by_day()
        today = date.today()
        month = self.rest_calendar_month
        if self.selected_rest_day is None:
            self.selected_rest_day = today

        self.rest_month_label.setText(month.strftime("%Y年%m月"))
        if self.calendar_mode == "daily":
            month_daily_count = sum(
                count for day, count in daily_counts.items()
                if day.year == month.year and day.month == month.month
            )
            selected_count = daily_counts.get(self.selected_rest_day, 0)
            self.rest_summary.setText(f"本月共记录 {month_daily_count} 篇日报。选中日期 {selected_count} 篇日报。")
        else:
            month_rest_count = sum(
                1 for item in rest_days
                if item.day.year == month.year and item.day.month == month.month
            )
            past_rest_count = sum(1 for item in rest_days if item.day <= today)
            self.rest_summary.setText(f"本月已安排 {month_rest_count} 天休息。今天之前含今天共记录 {past_rest_count} 天休息。")

        self._clear_layout(self.rest_calendar_grid)
        for column, text in enumerate(("一", "二", "三", "四", "五", "六", "日")):
            label = _label(text, "eyebrow")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rest_calendar_grid.addWidget(label, 0, column)

        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month)
        for row_index, week in enumerate(weeks, start=1):
            for column, day in enumerate(week):
                rest_day = rest_by_day.get(day)
                if self.calendar_mode == "daily":
                    button = QPushButton(self._daily_day_button_text(day, daily_counts.get(day, 0), today))
                    button.setObjectName(self._daily_day_object_name(day, daily_counts.get(day, 0), today, month))
                else:
                    button = QPushButton(self._rest_day_button_text(day, rest_day, today))
                    button.setObjectName(self._rest_day_object_name(day, rest_day, today, month))
                button.clicked.connect(lambda checked=False, selected=day: self._select_rest_day(selected))
                self.rest_calendar_grid.addWidget(button, row_index, column)

        if self.calendar_mode == "daily":
            self._update_daily_calendar_selection()
        else:
            self._refresh_next_week(rest_by_day)
            self._update_rest_selection(rest_by_day)

    def _select_calendar_mode(self, mode: str) -> None:
        self.calendar_mode = mode
        if hasattr(self, "calendar_side_stack"):
            self.calendar_side_stack.setCurrentIndex(1 if mode == "daily" else 0)
        for button, button_mode in (
            (getattr(self, "rest_calendar_mode_button", None), "rest"),
            (getattr(self, "daily_calendar_mode_button", None), "daily"),
        ):
            if button is None:
                continue
            active = mode == button_mode
            button.setChecked(active)
            button.setObjectName("primaryButton" if active else "smallButton")
            button.style().unpolish(button)
            button.style().polish(button)
        self._refresh_rest_calendar()

    def _rest_day_button_text(self, day: date, rest_day: RestDay | None, today: date) -> str:
        labels = [str(day.day)]
        if day == today:
            labels.append("今天")
        if rest_day is not None:
            labels.append("休息")
        elif self._is_next_week(day):
            labels.append("可安排")
        return "\n".join(labels)

    def _rest_day_object_name(
        self,
        day: date,
        rest_day: RestDay | None,
        today: date,
        month: date,
    ) -> str:
        if rest_day is not None:
            return "calendarRest"
        if day == today:
            return "calendarToday"
        if day.month != month.month:
            return "calendarMuted"
        return "calendarDay"

    def _daily_day_button_text(self, day: date, count: int, today: date) -> str:
        labels = [str(day.day)]
        if day == today:
            labels.append("今天")
        if count:
            labels.append(f"{count} 篇日报")
        return "\n".join(labels)

    def _daily_day_object_name(self, day: date, count: int, today: date, month: date) -> str:
        if count:
            return "calendarRest"
        if day == today:
            return "calendarToday"
        if day.month != month.month:
            return "calendarMuted"
        return "calendarDay"

    def _update_daily_calendar_selection(self) -> None:
        selected = self.selected_rest_day or date.today()
        reports = self.db.daily_reports_on_day(selected)
        self.daily_calendar_selected_label.setText(selected.strftime("%Y-%m-%d"))
        self.daily_calendar_summary.setText(f"这天你写了 {len(reports)} 篇项目日报。")
        self.daily_calendar_list.clear()
        if not reports:
            self._add_feed_card(
                self.daily_calendar_list,
                "",
                "当日日报",
                "这天你还没有写项目日报。",
            )
            return
        for item in reports:
            report = item["report"]
            meta = f"{item['created_at'].strftime('%H:%M')}  {item['project_name']} · {item['role']}"
            content = str(item["content"])
            if isinstance(report, DailyReport):
                linked_todo = self._daily_report_todo_text(report)
                if linked_todo:
                    content = f"{content}\n关联代办：{linked_todo}"
            self._add_feed_card(
                self.daily_calendar_list,
                meta,
                "日报",
                content,
                daily_report=report if isinstance(report, DailyReport) else None,
                height=self._feed_card_height(
                    content,
                    min_lines=2,
                    max_lines=None,
                    meta_text=f"{meta}  日报",
                    visual_chars_per_line=22,
                ) + 36,
                min_content_lines=1,
                max_content_lines=None,
                person_name=str(item["member_name"]),
            )

    def _export_recent_week_daily_reports(self) -> None:
        end_day = date.today()
        start_day = end_day - timedelta(days=6)
        reports = self.db.daily_reports_between(start_day, end_day, mine_only=False)
        if not reports:
            QMessageBox.information(self, "没有日报", "最近一周本机还没有同步到任何项目日报。")
            return
        default_name = str(Path.home() / "Downloads" / f"全员日报-{start_day:%Y%m%d}-{end_day:%Y%m%d}.pdf")
        target, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出最近一周全员日报",
            default_name,
            "PDF 文件 (*.pdf);;Word 文档 (*.docx)",
        )
        if not target:
            return
        target_path = Path(target)
        if "Word" in selected_filter and target_path.suffix.lower() != ".docx":
            target_path = target_path.with_suffix(".docx")
        elif "Word" not in selected_filter and target_path.suffix.lower() not in {".pdf", ".docx"}:
            target_path = target_path.with_suffix(".pdf")

        try:
            if target_path.suffix.lower() == ".docx":
                self._write_daily_report_docx(target_path, start_day, end_day, reports)
            else:
                self._write_daily_report_pdf(target_path, start_day, end_day, reports)
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", f"保存文件失败：{exc}")
            return
        QMessageBox.information(self, "导出完成", f"已导出：\n{target_path}")

    def _daily_export_title(self, start_day: date, end_day: date) -> str:
        return f"最近一周全员日报（{start_day:%Y-%m-%d} 至 {end_day:%Y-%m-%d}）"

    def _daily_reports_grouped_by_day(self, reports: list[dict[str, object]]) -> dict[date, list[dict[str, object]]]:
        grouped: dict[date, list[dict[str, object]]] = {}
        for report in reports:
            created_at = report.get("created_at")
            if not isinstance(created_at, datetime):
                continue
            grouped.setdefault(created_at.date(), []).append(report)
        return dict(sorted(grouped.items()))

    def _write_daily_report_pdf(
        self,
        target: Path,
        start_day: date,
        end_day: date,
        reports: list[dict[str, object]],
    ) -> None:
        title = self._daily_export_title(start_day, end_day)
        parts = [
            "<html><head><meta charset='utf-8'><style>",
            "body { font-family: 'Songti SC', 'PingFang SC', sans-serif; font-size: 11pt; color: #23241f; }",
            "h1 { font-size: 20pt; margin-bottom: 6px; }",
            "h2 { font-size: 14pt; margin-top: 18px; color: #34543a; }",
            ".meta { color: #596d5b; font-weight: 600; margin-top: 10px; }",
            ".content { white-space: pre-wrap; margin: 4px 0 12px 0; }",
            "</style></head><body>",
            f"<h1>{escape(title)}</h1>",
            f"<p>共 {len(reports)} 篇日报。本报告包含本机已同步的在线和非在线成员日报。</p>",
        ]
        for day, day_reports in self._daily_reports_grouped_by_day(reports).items():
            parts.append(f"<h2>{day:%Y-%m-%d}（{len(day_reports)} 篇）</h2>")
            for report in day_reports:
                created_at = report.get("created_at")
                time_text = created_at.strftime("%H:%M") if isinstance(created_at, datetime) else ""
                meta = " · ".join(
                    str(value)
                    for value in (
                        time_text,
                        report.get("project_name", "未知项目"),
                        report.get("member_name", ""),
                        report.get("role", ""),
                    )
                    if str(value).strip()
                )
                parts.append(f"<div class='meta'>{escape(meta)}</div>")
                parts.append(f"<div class='content'>{escape(str(report.get('content', '')))}</div>")
        parts.append("</body></html>")

        document = QTextDocument()
        document.setHtml("".join(parts))
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(target))
        document.print_(printer)

    def _write_daily_report_docx(
        self,
        target: Path,
        start_day: date,
        end_day: date,
        reports: list[dict[str, object]],
    ) -> None:
        paragraphs: list[tuple[str, str]] = [
            ("Title", self._daily_export_title(start_day, end_day)),
            ("Normal", f"共 {len(reports)} 篇日报。本报告包含本机已同步的在线和非在线成员日报。"),
        ]
        for day, day_reports in self._daily_reports_grouped_by_day(reports).items():
            paragraphs.append(("Heading1", f"{day:%Y-%m-%d}（{len(day_reports)} 篇）"))
            for report in day_reports:
                created_at = report.get("created_at")
                time_text = created_at.strftime("%H:%M") if isinstance(created_at, datetime) else ""
                meta = " · ".join(
                    str(value)
                    for value in (
                        time_text,
                        report.get("project_name", "未知项目"),
                        report.get("member_name", ""),
                        report.get("role", ""),
                    )
                    if str(value).strip()
                )
                paragraphs.append(("Heading2", meta))
                for line in str(report.get("content", "")).splitlines() or [""]:
                    paragraphs.append(("Normal", line))

        document_xml = self._docx_document_xml(paragraphs)
        content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
        rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
        document_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""
        styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>
</w:styles>"""
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", rels)
            archive.writestr("word/_rels/document.xml.rels", document_rels)
            archive.writestr("word/styles.xml", styles)
            archive.writestr("word/document.xml", document_xml)

    def _docx_document_xml(self, paragraphs: list[tuple[str, str]]) -> str:
        body_parts = []
        for style, text in paragraphs:
            style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style != "Normal" else ""
            body_parts.append(
                "<w:p>"
                f"{style_xml}"
                "<w:r><w:t xml:space=\"preserve\">"
                f"{escape(text)}"
                "</w:t></w:r></w:p>"
            )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            + "".join(body_parts)
            + "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1134\" w:right=\"1134\" w:bottom=\"1134\" w:left=\"1134\"/></w:sectPr>"
            "</w:body></w:document>"
        )

    def _refresh_next_week(self, rest_by_day: dict[date, RestDay]) -> None:
        self._clear_layout(self.next_week_layout)
        start = self._next_week_start(date.today())
        for offset in range(7):
            day = start + timedelta(days=offset)
            is_rest = day in rest_by_day
            label = f"{day.strftime('%m-%d')}  周{'一二三四五六日'[day.weekday()]}"
            button = QPushButton(f"{label}  {'取消休息' if is_rest else '安排休息'}")
            button.setObjectName("calendarRest" if is_rest else "smallButton")
            button.clicked.connect(lambda checked=False, selected=day: self._toggle_rest_day(selected))
            self.next_week_layout.addWidget(button)

    def _select_rest_day(self, day: date) -> None:
        self.selected_rest_day = day
        self._refresh_rest_calendar()

    def _update_rest_selection(self, rest_by_day: dict[date, RestDay]) -> None:
        selected = self.selected_rest_day or date.today()
        rest_day = rest_by_day.get(selected)
        self.rest_selected_label.setText(selected.strftime("%Y-%m-%d"))
        if rest_day is None:
            self.rest_selected_detail.setText("这天还没有安排休息。")
            self.rest_note.setText("")
            self.rest_toggle_button.setText("安排休息")
            self.rest_toggle_button.setObjectName("primaryButton")
        else:
            note = f" · {rest_day.note}" if rest_day.note else ""
            self.rest_selected_detail.setText(f"已安排休息{note}")
            self.rest_note.setText(rest_day.note)
            self.rest_toggle_button.setText("取消休息")
            self.rest_toggle_button.setObjectName("dangerButton")
        self.rest_toggle_button.style().unpolish(self.rest_toggle_button)
        self.rest_toggle_button.style().polish(self.rest_toggle_button)

    def _toggle_selected_rest_day(self) -> None:
        self._toggle_rest_day(self.selected_rest_day or date.today(), self.rest_note.text())

    def _toggle_rest_day(self, day: date, note: str = "") -> None:
        rest_by_day = {item.day: item for item in self.db.list_rest_days()}
        if day in rest_by_day:
            self.db.delete_rest_day(day)
        else:
            self.db.set_rest_day(day, note)
        central_sync = getattr(self, "central_sync", None)
        if central_sync is not None:
            central_sync.mark_local_dirty()
            central_sync.sync_now(push_first=True)
        self.selected_rest_day = day
        self.rest_calendar_month = day.replace(day=1)
        self._refresh_rest_calendar()

    def _open_next_week_roster(self) -> None:
        dialog = NextWeekRosterDialog(self.db, self)
        dialog.exec()

    def _move_rest_calendar_month(self, offset: int) -> None:
        month = self.rest_calendar_month
        month_index = month.month - 1 + offset
        year = month.year + month_index // 12
        new_month = month_index % 12 + 1
        self.rest_calendar_month = date(year, new_month, 1)
        self._refresh_rest_calendar()

    def _next_week_start(self, value: date) -> date:
        start_this_week = value - timedelta(days=value.weekday())
        return start_this_week + timedelta(days=7)

    def _is_next_week(self, value: date) -> bool:
        start = self._next_week_start(date.today())
        return start <= value < start + timedelta(days=7)

    def _clear_layout(self, layout: QGridLayout | QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_layout(child_layout)  # type: ignore[arg-type]

    def _lan_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(42, 38, 42, 38)
        outer.setSpacing(24)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.addWidget(_label("局域网", "sectionTitle"))
        self.lan_subtitle = _label("正在寻找同一网络里的数智中心。", "muted")
        title_box.addWidget(self.lan_subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.lan_peers_button = QPushButton("在线同事")
        self.lan_peers_button.setCheckable(True)
        self.lan_peers_button.setChecked(True)
        self.lan_peers_button.setObjectName("primaryButton")
        self.lan_peers_button.clicked.connect(lambda: self._set_lan_view("peers"))
        self.lan_logs_button = QPushButton("日志视角")
        self.lan_logs_button.setCheckable(True)
        self.lan_logs_button.clicked.connect(lambda: self._set_lan_view("logs"))
        header.addWidget(self.lan_peers_button)
        header.addWidget(self.lan_logs_button)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self._manual_lan_refresh)
        header.addWidget(refresh)
        outer.addLayout(header)

        panel = _panel()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(14)
        self.lan_panel_title = _label("在线同事", "eyebrow")
        panel_layout.addWidget(self.lan_panel_title)
        direct_peer_row = QHBoxLayout()
        direct_peer_row.setSpacing(8)
        self.lan_direct_peer_input = QLineEdit()
        self.lan_direct_peer_input.setPlaceholderText("跨网段同事 IP，例如 192.168.11.71")
        self.lan_direct_peer_input.returnPressed.connect(self._add_lan_direct_peer)
        add_direct_peer = QPushButton("添加直连")
        add_direct_peer.clicked.connect(self._add_lan_direct_peer)
        clear_direct_peer = QPushButton("清空")
        clear_direct_peer.clicked.connect(self._clear_lan_direct_peers)
        direct_peer_row.addWidget(self.lan_direct_peer_input, 1)
        direct_peer_row.addWidget(add_direct_peer)
        direct_peer_row.addWidget(clear_direct_peer)
        panel_layout.addLayout(direct_peer_row)
        self.lan_direct_peer_hint = _label("", "muted")
        panel_layout.addWidget(self.lan_direct_peer_hint)
        self._refresh_lan_direct_peer_hint()
        self.peer_list = QListWidget()
        self.peer_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.peer_list.itemClicked.connect(self._open_lan_log_item)
        panel_layout.addWidget(self.peer_list)
        outer.addWidget(panel)
        return page

    def _home_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(42, 38, 42, 38)
        layout.setSpacing(24)
        title = _label("成长履历", "sectionTitle")
        self.home_text = QTextEdit()
        self.home_text.setReadOnly(True)
        self.home_text.setText("先积累几篇周报，这里会慢慢长出入职、升职、项目月份线和个人成长总结。")
        layout.addWidget(title)
        layout.addWidget(self.home_text)
        return page

    def _feature_guide_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(42, 38, 42, 38)
        outer.setSpacing(22)

        header = QVBoxLayout()
        header.setSpacing(4)
        header.addWidget(_label("功能介绍", "sectionTitle"))
        header.addWidget(_label("各模块用途、常用操作和版本记录入口都集中在这里。", "muted"))
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_content = QWidget()
        grid = QGridLayout(scroll_content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)

        items = [
            (
                "我的面板",
                "每天先看这里。",
                "查看个人待办、项目动态和近期提醒，快速确认今天要处理的事。",
            ),
            (
                "项目面板",
                "项目协作主入口。",
                "创建和维护项目，管理成员、待办、日报、周报、项目进展和项目文档；顶部统计卡可点击查看明细。",
            ),
            (
                "个人周报",
                "沉淀个人工作记录。",
                "填写每周工作内容，系统生成摘要和状态，并同步沉淀到成长履历。",
            ),
            (
                "日历",
                "看节奏和安排。",
                "查看日期、休息日和记录情况，辅助安排项目汇报、周报和日常跟进。",
            ),
            (
                "局域网",
                "团队同步和更新。",
                "查看在线同事、同步团队数据、查看日志视角；发现同系统高版本安装包时可从这里更新。",
            ),
            (
                "成长履历",
                "回顾个人成长线。",
                "根据周报和项目记录汇总阶段成果，方便做个人复盘。",
            ),
            (
                "徽章墙",
                "记录习惯和贡献。",
                "展示工作节奏、记录习惯和项目贡献相关徽章，点击徽章可查看获得规则和明细。",
            ),
            (
                "文档库",
                "集中找项目资料。",
                "按本人文档、团队文档、项目和文档类型筛选资料，可上传、打开和删除自己上传的文档。",
            ),
            (
                "桌宠",
                "轻量提醒和互动。",
                "左下角入口可打开桌宠设置，切换形象、互动动作，或隐藏和重新显示桌宠。",
            ),
            (
                "名字/PIN",
                "维护个人身份。",
                "设置姓名、PIN 和钉钉号；姓名用于团队同步识别，PIN 用于保护设置和接管旧电脑身份。",
            ),
            (
                "版本",
                "查看功能日志。",
                "查看当前版本、本版更新和全部历史记录；后续新增功能继续同步更新版本号和日志。",
            ),
        ]

        for index, (title, summary, detail) in enumerate(items):
            card = _panel()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 16, 18, 16)
            card_layout.setSpacing(8)
            card_layout.addWidget(_label(title, "eyebrow"))
            card_layout.addWidget(_label(summary, "memberName"))
            detail_label = _label(detail, "muted")
            detail_label.setMinimumHeight(64)
            card_layout.addWidget(detail_label)
            card_layout.addStretch()
            grid.addWidget(card, index // 2, index % 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(scroll_content)
        outer.addWidget(scroll)
        return page

    def _docs_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(42, 38, 42, 38)
        outer.setSpacing(22)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.addWidget(_label("文档库", "sectionTitle"))
        title_box.addWidget(_label("按本人文档、团队文档和项目归档项目资料。", "muted"))
        header.addLayout(title_box)
        header.addStretch()
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self._refresh_document_library)
        header.addWidget(refresh)
        outer.addLayout(header)

        splitter = QSplitter()
        outer.addWidget(splitter)

        filters = _panel()
        filters.setMinimumWidth(270)
        filters.setMaximumWidth(340)
        filter_layout = QVBoxLayout(filters)
        filter_layout.setContentsMargins(18, 18, 18, 18)
        filter_layout.setSpacing(12)
        filter_layout.addWidget(_label("筛选", "eyebrow"))

        self.docs_scope = QComboBox()
        self.docs_scope.addItem("全部可见", "all")
        self.docs_scope.addItem("本人文档", "mine")
        self.docs_scope.addItem("团队文档", "team")
        self.docs_scope.currentIndexChanged.connect(self._refresh_document_library)

        self.docs_project = QComboBox()
        self.docs_project.currentIndexChanged.connect(self._refresh_document_library)

        self.docs_type = QComboBox()
        self.docs_type.addItem("全部类型", "")
        self.docs_type.addItems(DOCUMENT_TYPES)
        self.docs_type.currentIndexChanged.connect(self._refresh_document_library)

        upload = QPushButton("上传文档")
        upload.setObjectName("primaryButton")
        upload.clicked.connect(self._upload_document_from_library)

        filter_layout.addWidget(self.docs_scope)
        filter_layout.addWidget(self.docs_project)
        filter_layout.addWidget(self.docs_type)
        filter_layout.addWidget(upload)
        filter_layout.addStretch()

        list_panel = _panel()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(18, 18, 18, 18)
        list_layout.setSpacing(12)
        self.docs_count = _label("0 个文档", "eyebrow")
        self.docs_list = QListWidget()
        self.docs_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_layout.addWidget(self.docs_count)
        list_layout.addWidget(self.docs_list)

        splitter.addWidget(filters)
        splitter.addWidget(list_panel)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([300, 760])
        return page

    def _upload_document_from_library(self) -> None:
        project_id = self.docs_project.currentData()
        if not isinstance(project_id, int):
            QMessageBox.information(self, "没有项目", "先创建或选择一个项目。")
            return
        doc_type = self.docs_type.currentText().strip()
        if self.docs_type.currentIndex() == 0:
            doc_type = "项目汇报PPT"
        visibility = "personal" if self.docs_scope.currentData() == "mine" else "team"
        self._upload_project_document(project_id, doc_type, visibility)

    def _refresh_document_library(self) -> None:
        if not hasattr(self, "docs_list"):
            return
        current_project = self.docs_project.currentData()
        self.docs_project.blockSignals(True)
        self.docs_project.clear()
        self.docs_project.addItem("全部项目", None)
        for project in self.db.list_projects():
            self.docs_project.addItem(project.name, project.id)
        if isinstance(current_project, int):
            for index in range(self.docs_project.count()):
                if self.docs_project.itemData(index) == current_project:
                    self.docs_project.setCurrentIndex(index)
                    break
        self.docs_project.blockSignals(False)

        project_id = self.docs_project.currentData()
        if not isinstance(project_id, int):
            project_id = None
        scope = self.docs_scope.currentData() or "all"
        doc_type = None if self.docs_type.currentIndex() == 0 else self.docs_type.currentText().strip()
        documents = self.db.list_visible_project_documents(
            self.db.display_name(),
            project_id=project_id,
            scope=str(scope),
            doc_type=doc_type,
        )
        projects = {project.id: project.name for project in self.db.list_projects()}
        self.docs_list.clear()
        self.docs_count.setText(f"{len(documents)} 个文档")
        if not documents:
            self._add_document_card(None, "没有匹配的文档。", "", "", "")
            return
        for document in documents:
            self._add_document_card(
                document,
                document.title,
                projects.get(document.project_id, "未知项目"),
                document.doc_type,
                f"{'团队文档' if document.visibility == 'team' else '本人文档'} · {document.uploader} · {document.created_at.strftime('%Y-%m-%d %H:%M')}",
            )

    def _add_document_card(
        self,
        document: ProjectDocument | None,
        title: str,
        project_name: str,
        doc_type: str,
        meta_text: str,
    ) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        card = QWidget()
        card.setObjectName("feedCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        body = QVBoxLayout()
        body.setSpacing(5)
        heading = _label(title, "memberName")
        meta = _label("  ".join(part for part in (project_name, doc_type, meta_text) if part), "eyebrow")
        body.addWidget(heading)
        body.addWidget(meta)
        layout.addLayout(body, 1)

        if document is not None:
            actions = QHBoxLayout()
            actions.setSpacing(8)
            open_button = QPushButton("打开")
            open_button.setObjectName("smallButton")
            open_button.clicked.connect(lambda checked=False, selected=document: self._open_deck_file(selected))
            actions.addWidget(open_button)
            if self.db.is_current_user_name(document.uploader):
                delete_button = QPushButton("删除")
                delete_button.setObjectName("smallButton")
                delete_button.clicked.connect(lambda checked=False, selected=document: self._delete_project_document(selected))
                actions.addWidget(delete_button)
            layout.addLayout(actions)

        item.setSizeHint(QSize(0, 82))
        self.docs_list.addItem(item)
        self.docs_list.setItemWidget(item, card)

    def _summarize_weekly_with_server(self) -> None:
        content = self.editor.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "还没写", "先写一点周报内容。")
            return
        central_sync = getattr(self, "central_sync", None)
        if central_sync is None or not getattr(central_sync, "server_url", ""):
            QMessageBox.information(self, "服务器未连接", "尚未发现中央数据服务器，暂时不能使用 AI 整理。")
            return
        if self._weekly_ai_worker is not None and self._weekly_ai_worker.isRunning():
            return
        self.editor.setReadOnly(True)
        self.weekly_ai_button.setEnabled(False)
        self.weekly_save_button.setEnabled(False)
        self.weekly_ai_button.setText("AI 整理中…")
        worker = WeeklyAIWorker(central_sync, content)
        self._weekly_ai_worker = worker
        worker.completed.connect(self._weekly_ai_completed)
        worker.failed.connect(self._weekly_ai_failed)
        worker.finished.connect(self._weekly_ai_finished)
        worker.start()

    def _weekly_ai_completed(self, content: str) -> None:
        self.editor.setPlainText(content)
        self.editor.setReadOnly(False)
        self.weekly_ai_button.setEnabled(True)
        self.weekly_save_button.setEnabled(True)
        self.weekly_ai_button.setText("AI 整理")

    def _weekly_ai_failed(self, message: str) -> None:
        self.editor.setReadOnly(False)
        self.weekly_ai_button.setEnabled(True)
        self.weekly_save_button.setEnabled(True)
        self.weekly_ai_button.setText("AI 整理")
        QMessageBox.warning(self, "AI 整理失败", f"服务器没有完成整理：{message}")

    def _weekly_ai_finished(self) -> None:
        self._weekly_ai_worker = None

    def _save_weekly_report(self) -> None:
        content = self.editor.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "还没写", "先写一点周报内容。")
            return

        mood = self.summarizer.infer_mood(content)
        report = self.db.add_weekly_report(content, content, mood)
        self.summary.setMarkdown(content)
        self.pet.set_mood(mood)
        self.editor.clear()
        self._prepend_report(report)
        self._refresh_home()
        self._refresh_badge_wall()
        self._nudge_after_late_record()

    def _load_reports(self) -> None:
        self.history.clear()
        for report in self.db.list_weekly_reports():
            self._append_report(report)
        self._update_delete_weekly_enabled()
        self._refresh_home()

    def _prepend_report(self, report: WeeklyReport) -> None:
        item = self._make_report_item(report)
        self.history.insertItem(0, item)

    def _append_report(self, report: WeeklyReport) -> None:
        self.history.addItem(self._make_report_item(report))

    def _make_report_item(self, report: WeeklyReport) -> QListWidgetItem:
        item = QListWidgetItem(f"{report.created_at.strftime('%Y-%m-%d %H:%M')}  {report.mood}")
        item.setData(Qt.ItemDataRole.UserRole, report)
        return item

    def _show_history_item(self, item: QListWidgetItem) -> None:
        report = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(report, WeeklyReport):
            self.summary.setMarkdown(report.summary)
            self.pet.set_mood(report.mood)

    def _update_delete_weekly_enabled(self, *_args: object) -> None:
        if hasattr(self, "delete_weekly_button"):
            self.delete_weekly_button.setEnabled(self.history.currentItem() is not None)

    def _delete_selected_weekly_report(self) -> None:
        item = self.history.currentItem()
        if item is None:
            return
        report = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(report, WeeklyReport):
            return

        reply = QMessageBox.question(
            self,
            "删除周报",
            f"确定删除 {report.created_at.strftime('%Y-%m-%d %H:%M')} 的个人周报吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not self.db.delete_weekly_report(report.id):
            QMessageBox.warning(self, "删除失败", "没有找到这条周报，或当前用户不能删除它。")
            return

        row = self.history.row(item)
        self.history.takeItem(row)
        if self.summary.toPlainText() == report.summary:
            self.summary.clear()
        self._update_delete_weekly_enabled()
        self._refresh_home()
        self._refresh_badge_wall()

    def _refresh_home(self) -> None:
        reports = self.db.list_weekly_reports(limit=100)
        if not reports:
            self.home_text.setPlainText("先积累几篇周报，这里会慢慢长出入职、升职、项目月份线和个人成长总结。")
            return
        happy = sum(1 for item in reports if item.mood == "happy")
        tired = sum(1 for item in reports if item.mood == "tired")
        self.home_text.setPlainText(
            f"已记录 {len(reports)} 篇周报。\n\n"
            f"高光周报：{happy} 篇\n"
            f"压力/阻塞周报：{tired} 篇\n\n"
            "最近一次成长摘要：\n"
            f"{reports[0].summary}"
        )

    def _open_settings(self) -> None:
        peers = self.discovery.sorted_peers() if self.discovery is not None else []
        dialog = SettingsDialog(self.db, peers)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self._refresh_identity()
            central_sync = getattr(self, "central_sync", None)
            if central_sync is not None:
                central_sync.mark_local_dirty()
                central_sync.sync_now(push_first=True)
            if self.discovery is not None:
                self.discovery.set_display_name(self.db.display_name())
                self.discovery.announce_burst()
                self.discovery.request_peer_snapshot_refresh()
                self._refresh_peers(self.discovery.sorted_peers())

    def _open_pet(self) -> None:
        self.db.record_activity("打开桌宠")
        self.pet.move_to_bottom_right()
        self.pet.show_manually()
        dialog = PetDialog(self.db, self.pet)
        dialog.exec()
        self._refresh_badge_wall()
        self._announce_presence()

    def _open_version(self) -> None:
        dialog = VersionDialog()
        dialog.exec()

    def _refresh_identity(self) -> None:
        name = self.db.display_name()
        self.app_title.setText(name)
        self.app_title.setToolTip(name)
        self.setWindowTitle(f"{name} - 数智中心")

    def _announce_presence(self) -> None:
        if self.discovery is not None:
            self.discovery.announce_burst()

    def _load_lan_direct_peers(self) -> list[str]:
        raw = self.db.get_setting("lan_direct_peers") or "[]"
        try:
            values = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(values, list):
            return []
        addresses: list[str] = []
        for value in values:
            address = str(value).strip()
            try:
                ipaddress.ip_address(address)
            except ValueError:
                continue
            if address not in addresses:
                addresses.append(address)
        return addresses

    def _save_lan_direct_peers(self) -> None:
        self.db.set_setting("lan_direct_peers", json.dumps(self.lan_direct_peers), save=True)
        if self.discovery is not None:
            self.discovery.set_direct_peer_addresses(self.lan_direct_peers)
        self._refresh_lan_direct_peer_hint()

    def _refresh_lan_direct_peer_hint(self) -> None:
        if not hasattr(self, "lan_direct_peer_hint"):
            return
        if self.lan_direct_peers:
            self.lan_direct_peer_hint.setText(f"直连 IP：{', '.join(self.lan_direct_peers)}")
        else:
            self.lan_direct_peer_hint.setText("跨网段时，可添加一位同事的 IP 来辅助发现。")

    def _add_lan_direct_peer(self) -> None:
        address = self.lan_direct_peer_input.text().strip()
        try:
            ipaddress.ip_address(address)
        except ValueError:
            QMessageBox.information(self, "IP 无效", "请输入完整的 IPv4 或 IPv6 地址。")
            return
        if address not in self.lan_direct_peers:
            self.lan_direct_peers.append(address)
            self._save_lan_direct_peers()
        self.lan_direct_peer_input.clear()
        self._manual_lan_refresh()

    def _clear_lan_direct_peers(self) -> None:
        if not self.lan_direct_peers:
            return
        self.lan_direct_peers = []
        self._save_lan_direct_peers()

    def _manual_lan_refresh(self) -> None:
        if self.discovery is None:
            self.lan_subtitle.setText("局域网发现没有启动。")
            return
        central_sync = getattr(self, "central_sync", None)
        if central_sync is not None:
            central_sync.sync_now(push_first=True)
        self.discovery.announce_burst()
        started_count = self.discovery.request_peer_snapshot_refresh()
        self._refresh_after_lan_sync()
        self._refresh_peers(self.discovery.sorted_peers())
        if started_count:
            self.lan_subtitle.setText(f"已开始后台同步 {started_count} 位同事，完成后会自动刷新。")
        elif central_sync is not None:
            self.lan_subtitle.setText("已请求中央数据服务同步，完成后会自动刷新。")
        else:
            self.lan_subtitle.setText("刷新完成，没有发现比本机更新的数据。")

    def _refresh_after_lan_sync(self) -> None:
        project_page_locked = self._project_page_has_edit_focus()
        if project_page_locked:
            self._update_project_sync_hint("服务器数据已同步，当前编辑页暂不刷新")
        else:
            self._load_projects()
        self._load_reports()
        self._refresh_rest_calendar()
        self._refresh_document_library()
        self._refresh_home()
        self._refresh_badge_wall()
        if self.lan_view_mode == "logs":
            self._refresh_lan_logs(self.current_lan_peers)

    def _set_lan_view(self, mode: str) -> None:
        self.lan_view_mode = "logs" if mode == "logs" else "peers"
        if self.lan_view_mode != "logs":
            self._lan_logs_signature = None
        self.lan_peers_button.setChecked(self.lan_view_mode == "peers")
        self.lan_logs_button.setChecked(self.lan_view_mode == "logs")
        self.lan_peers_button.setObjectName("primaryButton" if self.lan_view_mode == "peers" else "")
        self.lan_logs_button.setObjectName("primaryButton" if self.lan_view_mode == "logs" else "")
        for button in (self.lan_peers_button, self.lan_logs_button):
            button.style().unpolish(button)
            button.style().polish(button)
        self._refresh_peers(self.current_lan_peers)

    def _refresh_peers(self, peers: list[LanPeer]) -> None:
        if not hasattr(self, "peer_list"):
            return
        self.current_lan_peers = peers
        self._check_lan_update_reminder()
        if self.lan_view_mode == "logs":
            self._refresh_lan_logs(peers)
            return
        scrollbar = self.peer_list.verticalScrollBar()
        scroll_value = scrollbar.value()
        was_at_bottom = scrollbar.maximum() > 0 and scroll_value >= scrollbar.maximum() - 4
        self._lan_peer_scroll_generation += 1
        scroll_generation = self._lan_peer_scroll_generation
        self.peer_list.setUpdatesEnabled(False)
        self.peer_list.clear()
        self.lan_panel_title.setText("在线同事")
        if self.discovery is not None and not self.discovery.is_bound:
            self.lan_subtitle.setText("局域网发现没有启动。请检查系统网络权限或端口占用。")
            item = QListWidgetItem("UDP 45454 端口未能绑定。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.peer_list.addItem(item)
            self.peer_list.setUpdatesEnabled(True)
            self._schedule_lan_peer_scroll_restore(scroll_value, was_at_bottom, scroll_generation)
            return
        self.lan_subtitle.setText(f"我的名字：{self.db.display_name()}。发现 {len(peers)} 位在线同事。")
        if not peers:
            item = QListWidgetItem("暂时没有发现其他人。确认大家在同一局域网，并且都打开了数智中心。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.peer_list.addItem(item)
            self.peer_list.setUpdatesEnabled(True)
            self._schedule_lan_peer_scroll_restore(scroll_value, was_at_bottom, scroll_generation)
            return
        for peer in peers:
            seen = peer.last_seen.strftime("%H:%M:%S")
            self._add_peer_card(peer, seen)
        self.peer_list.setUpdatesEnabled(True)
        self._schedule_lan_peer_scroll_restore(scroll_value, was_at_bottom, scroll_generation)

    def _schedule_lan_peer_scroll_restore(self, value: int, was_at_bottom: bool, generation: int) -> None:
        self._restore_lan_peer_scroll(value, was_at_bottom, generation)
        QTimer.singleShot(
            0,
            lambda saved=value, bottom=was_at_bottom, current=generation: self._restore_lan_peer_scroll(
                saved,
                bottom,
                current,
            ),
        )

    def _restore_lan_peer_scroll(self, value: int, was_at_bottom: bool, generation: int) -> None:
        if (
            not hasattr(self, "peer_list")
            or self.lan_view_mode != "peers"
            or generation != self._lan_peer_scroll_generation
        ):
            return
        scrollbar = self.peer_list.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum() if was_at_bottom else min(value, scrollbar.maximum()))

    def _refresh_lan_logs(self, peers: list[LanPeer]) -> None:
        self.lan_panel_title.setText("今日项目日志")
        if self.discovery is not None and not self.discovery.is_bound:
            self._lan_logs_signature = None
            self.lan_subtitle.setText("局域网发现没有启动。请检查系统网络权限或端口占用。")
            self.peer_list.clear()
            item = QListWidgetItem("UDP 45454 端口未能绑定。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.peer_list.addItem(item)
            return
        today = date.today().strftime("%Y-%m-%d")
        people = [
            (self.db.display_name(), self.db.today_project_logs(), True),
            *[
                (
                    peer.name,
                    [item for item in peer.today_project_logs if isinstance(item, dict)],
                    version_tuple(peer.app_version) >= version_tuple("0.1.24"),
                )
                for peer in peers
            ],
        ]
        done_count = sum(1 for _, logs, _ in people if logs)
        missing_count = sum(1 for _, logs, supports in people if supports and not logs)
        self.lan_subtitle.setText(
            f"日志视角：{today}。共 {len(people)} 人，已写 {done_count} 人，未写 {missing_count} 人。"
        )
        signature = self._lan_logs_signature_for(today, people)
        if signature == self._lan_logs_signature:
            return
        self._lan_logs_signature = signature
        scrollbar = self.peer_list.verticalScrollBar()
        scroll_value = scrollbar.value()
        was_at_bottom = scrollbar.maximum() > 0 and scroll_value >= scrollbar.maximum() - 4
        self.peer_list.setUpdatesEnabled(False)
        self.peer_list.clear()
        self._add_lan_log_card(
            self.db.display_name(),
            "本机",
            people[0][1],
            supports_logs=True,
            member_name=self.db.display_name(),
        )
        for peer, (_, logs, supports_logs) in zip(peers, people[1:]):
            self._add_lan_log_card(
                peer.name,
                f"{peer.address} · {peer.last_seen.strftime('%H:%M:%S')}",
                logs,
                supports_logs=supports_logs,
                member_name=peer.name,
            )
        self.peer_list.setUpdatesEnabled(True)
        QTimer.singleShot(0, lambda value=scroll_value, bottom=was_at_bottom: self._restore_lan_log_scroll(value, bottom))

    def _lan_logs_signature_for(
        self,
        today: str,
        people: list[tuple[str, list[dict[str, object]], bool]],
    ) -> tuple[object, ...]:
        rows: list[object] = [today]
        for name, logs, supports_logs in people:
            log_rows = tuple(
                (
                    str(log.get("created_at", "")),
                    str(log.get("project_name", "")),
                    str(log.get("role", "")),
                    str(log.get("content", "")),
                )
                for log in logs
            )
            rows.append((name, supports_logs, log_rows))
        return tuple(rows)

    def _restore_lan_log_scroll(self, value: int, was_at_bottom: bool) -> None:
        if not hasattr(self, "peer_list") or self.lan_view_mode != "logs":
            return
        scrollbar = self.peer_list.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum() if was_at_bottom else min(value, scrollbar.maximum()))

    def _add_lan_log_card(
        self,
        name: str,
        meta_text: str,
        logs: list[dict[str, object]],
        supports_logs: bool,
        member_name: str,
    ) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setData(Qt.ItemDataRole.UserRole, ("project_logs", member_name))
        card = QWidget()
        card.setObjectName("feedCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.addWidget(self._name_with_chat(name))
        title_box.addWidget(_label(meta_text, "muted"))
        header.addLayout(title_box, 1)
        status = "已写" if logs else ("未写" if supports_logs else "未共享")
        count = f"{len(logs)} 条" if logs else "0 条"
        status_label = _label(f"{status} · {count}", "roleBadge")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_label.setFixedWidth(92)
        header.addWidget(status_label)
        history_button = QPushButton("全部日志")
        history_button.setObjectName("smallButton")
        history_button.clicked.connect(lambda checked=False, selected=member_name: self._open_lan_member_logs(selected))
        header.addWidget(history_button)
        layout.addLayout(header)

        if logs:
            for log in logs:
                layout.addWidget(self._lan_log_line(log))
        else:
            message = "今天还没有项目日志。" if supports_logs else "对方版本暂未共享日志状态。"
            layout.addWidget(_label(message, "muted"))

        logs_height = sum(self._lan_log_line_height(str(log.get("content", ""))) for log in logs)
        item.setSizeHint(QSize(0, 82 + (logs_height if logs else 58)))
        self.peer_list.addItem(item)
        self.peer_list.setItemWidget(item, card)

    def _open_lan_member_logs(self, member_name: str) -> None:
        logs = self.db.project_logs_for_member(member_name)
        projects = self._projects_with_notes_for_current_user(self.db.projects_for_member(member_name))
        dialog = ProjectLogHistoryDialog(member_name, logs, projects, self)
        dialog.exec()

    def _open_lan_log_item(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple) or len(data) != 2 or data[0] != "project_logs":
            return
        self._open_lan_member_logs(str(data[1]))

    def _lan_log_line(self, log: dict[str, object]) -> QWidget:
        row = QWidget()
        row.setObjectName("compactMemberCard")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        created_at = self._format_lan_log_time(str(log.get("created_at", "")))
        project_name = str(log.get("project_name", "未知项目"))
        role = str(log.get("role", "")).strip()
        meta = " · ".join(part for part in (created_at, project_name, role) if part)
        content = str(log.get("content", "")).strip() or "空日志"
        content_label = _label(content)
        layout.addWidget(_label(meta, "eyebrow"))
        layout.addWidget(content_label)
        return row

    def _lan_log_line_height(self, content: str) -> int:
        normalized = " ".join(content.strip().split())
        explicit_lines = len([line for line in content.splitlines() if line.strip()])
        visual_width = sum(1 if ord(char) < 128 else 2 for char in normalized)
        visual_lines = max(1, (visual_width + 39) // 40)
        return 44 + max(1, explicit_lines, visual_lines) * 24

    def _format_lan_log_time(self, value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%H:%M")
        except ValueError:
            return ""

    def _add_peer_card(self, peer: LanPeer, seen: str) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        card = QWidget()
        card.setObjectName("feedCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        body = QVBoxLayout()
        body.setSpacing(5)
        body.addWidget(self._name_with_chat(peer.name))
        body.addWidget(_label(self._peer_list_text(peer, seen), "muted"))
        layout.addLayout(body, 1)

        if self._peer_has_lan_update(peer):
            download = QPushButton("下载更新")
            download.setObjectName("primaryButton")
            download.clicked.connect(lambda checked=False, selected=peer: self._download_lan_update(selected))
            layout.addWidget(download)
        elif (
            peer.platform == sys.platform
            and bool(peer.app_version)
            and version_tuple(peer.app_version) > version_tuple(APP_VERSION)
        ):
            unavailable = QPushButton("无安装包")
            unavailable.setEnabled(False)
            layout.addWidget(unavailable)

        item.setSizeHint(QSize(0, 92))
        self.peer_list.addItem(item)
        self.peer_list.setItemWidget(item, card)

    def _peer_has_lan_update(self, peer: LanPeer) -> bool:
        package_version = self._peer_update_package_version(peer)
        return self._peer_has_downloadable_package(peer) and version_tuple(package_version) > version_tuple(APP_VERSION)

    def _peer_has_downloadable_package(self, peer: LanPeer) -> bool:
        package = peer.update_package
        try:
            package_size = int(package.get("size", 0) or 0) if isinstance(package, dict) else 0
        except (TypeError, ValueError):
            package_size = 0
        return (
            peer.platform == sys.platform
            and isinstance(package, dict)
            and bool(package)
            and package_size > 0
            and bool(self._peer_update_package_version(peer))
        )

    def _peer_update_package_version(self, peer: LanPeer) -> str:
        if not isinstance(peer.update_package, dict):
            return ""
        return str(peer.update_package.get("version") or peer.app_version or "").strip()

    def _download_lan_update(self, peer: LanPeer) -> None:
        if self.discovery is None:
            return
        if QMessageBox.question(
            self,
            "下载局域网更新",
            self._lan_update_message(peer),
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            target = self.discovery.download_update_package(peer, _desktop_path())
        except Exception as exc:
            QMessageBox.warning(self, "下载失败", str(exc))
            return
        if sys.platform == "win32" and target.suffix.lower() == ".exe":
            result = QProcess.startDetached(str(target), ["--update-restart"])
            started = result[0] if isinstance(result, tuple) else bool(result)
        else:
            started = QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        if not started:
            QMessageBox.warning(self, "无法打开更新", f"安装包已保存到桌面，但未能自动打开：\n{target}")
            return
        QApplication.quit()

    def _lan_update_message(self, peer: LanPeer) -> str:
        package = peer.update_package
        package_version = self._peer_update_package_version(peer) or peer.app_version
        notes = str(package.get("notes", "")).strip()
        history = package.get("changelog")
        history_text = ""
        if isinstance(history, list):
            lines: list[str] = []
            for entry in history[:5]:
                if not isinstance(entry, dict):
                    continue
                version = str(entry.get("version", "")).strip()
                note = str(entry.get("notes", "")).strip()
                if version and note:
                    lines.append(f"v{version}：{note}")
            if lines:
                history_text = "\n\n全部历史记录：\n" + "\n".join(lines)
        notes_text = f"\n\n更新内容：\n{notes}" if notes else ""
        return (
            f"从 {peer.name} 下载 v{package_version} 安装包吗？"
            f"{notes_text}"
            f"{history_text}"
            "\n\n下载后需要手动关闭当前程序并运行安装包。"
        )

    def _peer_list_text(self, peer: LanPeer, seen: str) -> str:
        platform = self._platform_label(peer.platform)
        version = f"v{peer.app_version}" if peer.app_version else "版本未知"
        status = ""
        if peer.platform == sys.platform:
            if self._peer_has_lan_update(peer):
                status = " · 可局域网更新"
            elif peer.app_version and version_tuple(peer.app_version) > version_tuple(APP_VERSION):
                status = " · 高版本但未共享安装包"
            elif peer.app_version and version_tuple(peer.app_version) < version_tuple(APP_VERSION):
                status = " · 对方版本较低"
            elif self._peer_has_downloadable_package(peer):
                status = " · 本机已是同版本"
        elif peer.platform and peer.platform != sys.platform:
            status = " · 不同系统"
        package = peer.update_package
        package_text = ""
        if package:
            package_text = f" · {package.get('name', '安装包')} · {self._format_size(int(package.get('size', 0) or 0))}"
        return f"{peer.address} · {platform} · {version} · {seen}{status}{package_text}"

    def _format_size(self, size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return f"{size} B"

    def _platform_label(self, platform: str) -> str:
        if platform == "win32":
            return "Windows"
        if platform == "darwin":
            return "macOS"
        if platform.startswith("linux"):
            return "Linux"
        return platform or "系统未知"
