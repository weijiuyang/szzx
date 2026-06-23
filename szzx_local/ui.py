from __future__ import annotations

import calendar
import shutil
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from PySide6.QtCore import QThread, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .ai import LocalSummarizer
from .changelog import changelog_text, current_release_notes
from .database import APP_DIR, Database
from .lan import LanDiscovery, LanPeer
from .models import DailyReport, Project, ProjectDocument, ProjectMember, ProjectTodo, RestDay, WeeklyReport
from .pet import DesktopPet, PET_ACTIONS, PET_KINDS
from .updater import check_for_update, configured_update_url, version_tuple
from .version import APP_VERSION


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
"""


DOCUMENT_TYPES = [
    "产品原型图",
    "项目汇报PPT",
    "交接文档",
    "调研/可行性报告",
    "竞品调研报告",
    "会议纪要",
    "其他",
]
PROJECT_HERO_HEIGHT = 300


def _label(text: str, object_name: str | None = None) -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(True)
    return label


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
        setup_hint = _label("进入后请在左下角「名字/PIN」修改名字和 PIN。", "muted")
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

        layout = QFormLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        self.display_name: QLineEdit | None = None
        if self.db.display_name_locked():
            locked_name = _label(self.db.display_name(), "memberName")
            locked_name.setToolTip("名字已经锁定")
            layout.addRow("名字", locked_name)
        else:
            self.display_name = QLineEdit()
            self.display_name.setMaxLength(32)
            self.display_name.setText(self.db.display_name())
            self.display_name.setPlaceholderText("显示给局域网同事的名字")
            layout.addRow("名字", self.display_name)

        self.new_pin = QLineEdit()
        self.new_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pin.setMaxLength(12)
        self.new_pin.setPlaceholderText("本地密码，留空则不修改")

        save = QPushButton("保存")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save)

        layout.addRow("本地密码", self.new_pin)
        layout.addRow("", save)

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

        show_pet = QPushButton("显示桌宠")
        show_pet.setObjectName("primaryButton")
        show_pet.clicked.connect(self._show_pet_bottom_right)
        layout.addWidget(show_pet)

    def _select_pet(self, kind: str) -> None:
        self.db.set_pet_kind(kind)
        self.pet.set_kind(kind)
        for button_kind, button in self.pet_buttons.items():
            button.setChecked(button_kind == kind)
        self._show_pet_bottom_right()

    def _play_action(self, action: str) -> None:
        self.pet.set_mood(action)
        self._show_pet_bottom_right()

    def _show_pet_bottom_right(self) -> None:
        self.pet.move_to_bottom_right()
        self.pet.show()


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


class ProjectLogHistoryDialog(QDialog):
    def __init__(self, member_name: str, logs: list[dict[str, object]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{member_name} 的项目日志")
        self.resize(820, 620)
        self.setStyleSheet(APP_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(_label(f"{member_name} 的全部项目日志", "sectionTitle"))
        layout.addWidget(_label(f"按日期倒序排列，共 {len(logs)} 条。", "muted"))

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

    def _add_log_card(self, log: dict[str, object]) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        card = QWidget()
        card.setObjectName("feedCard")
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

    def _format_log_time(self, value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value

    def _history_card_height(self, content: str) -> int:
        normalized = " ".join(content.strip().split())
        visual_width = sum(1 if ord(char) < 128 else 2 for char in normalized)
        lines = max(1, min(7, (visual_width // 72) + 1))
        return 66 + lines * 24


class NextWeekRosterDialog(QDialog):
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
        names = self.db.known_display_names()
        rest_days = self.db.list_rest_days(mine_only=False)
        rest_lookup = {(item.author, item.day) for item in rest_days}
        rows: list[list[str]] = []
        for name in names:
            row = [name]
            for day in self.days:
                row.append("休" if (name, day) in rest_lookup else "早班")
            rows.append(row)
        return rows

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
        self._notified_update_version: str | None = None
        self.lan_view_mode = "peers"
        self.current_lan_peers: list[LanPeer] = []
        self.rest_calendar_month = date.today().replace(day=1)
        self.selected_rest_day: date | None = None

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

        self.stack.addWidget(self._project_tab())
        self.stack.addWidget(self._weekly_tab())
        self.stack.addWidget(self._rest_calendar_tab())
        self.stack.addWidget(self._lan_tab())
        self.stack.addWidget(self._home_tab())
        self.stack.addWidget(self._docs_tab())
        shell_layout.addWidget(self.stack, 1)

        self.setCentralWidget(shell)
        self._select_page(0)

        if self.discovery is not None:
            self.discovery.peers_changed.connect(self._refresh_peers)
            self.discovery.data_synced.connect(self._refresh_after_lan_sync)
            self.discovery.start()
            self._refresh_peers(self.discovery.sorted_peers())

        self._load_projects()
        self._load_reports()
        self._refresh_rest_calendar()
        self._refresh_document_library()
        self._start_update_timer()

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

        for index, text in enumerate(("项目面板", "个人周报", "休息日历", "局域网", "成长履历", "文档库")):
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=index: self._select_page(page))
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch()
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
        refresh.clicked.connect(self._load_projects)
        header.addWidget(refresh)
        outer.addLayout(header)

        splitter = QSplitter()
        outer.addWidget(splitter)

        left = _panel()
        left.setMinimumWidth(230)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(12)
        left_layout.addWidget(_label("项目", "eyebrow"))
        self.project_list = QListWidget()
        self.project_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.project_list.setFixedHeight(260)
        self.project_list.itemClicked.connect(self._select_project_item)
        left_layout.addWidget(self.project_list)
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
        self.project_title = _label("选择一个项目", "heroTitle")
        self.project_description = _label("项目负责人可以在这里查看所有日报、维护项目周报，并归档项目文档。", "muted")
        hero_layout.addWidget(self.project_status)
        hero_layout.addWidget(self.project_title)
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
        progress_panel.setMinimumHeight(620)
        progress_layout = QVBoxLayout(progress_panel)
        progress_layout.setContentsMargins(18, 18, 18, 18)
        progress_layout.setSpacing(12)
        feed_split = QSplitter(Qt.Orientation.Vertical)

        product_feed_panel = QWidget()
        product_feed_layout = QVBoxLayout(product_feed_panel)
        product_feed_layout.setContentsMargins(0, 0, 0, 0)
        product_feed_layout.setSpacing(8)
        product_feed_layout.addWidget(_label("项目进展流", "eyebrow"))
        self.product_feed = QListWidget()
        self.product_feed.setMinimumHeight(410)
        product_feed_layout.addWidget(self.product_feed)

        developer_feed_panel = QWidget()
        developer_feed_layout = QVBoxLayout(developer_feed_panel)
        developer_feed_layout.setContentsMargins(0, 0, 0, 0)
        developer_feed_layout.setSpacing(8)
        developer_feed_layout.addWidget(_label("日报流", "eyebrow"))
        self.developer_feed = QListWidget()
        self.developer_feed.setMinimumHeight(410)
        developer_feed_layout.addWidget(self.developer_feed)

        feed_split.addWidget(product_feed_panel)
        feed_split.addWidget(developer_feed_panel)
        feed_split.setChildrenCollapsible(False)
        feed_split.setSizes([430, 430])
        progress_layout.addWidget(feed_split)

        self.config_project_panel = _panel()
        self.config_project_panel.setFixedHeight(260)
        config_project_layout = QVBoxLayout(self.config_project_panel)
        config_project_layout.setContentsMargins(18, 18, 18, 18)
        config_project_layout.setSpacing(12)
        config_project_layout.addWidget(_label("项目简介", "eyebrow"))
        self.config_project_description = QTextEdit()
        self.config_project_description.setPlaceholderText("项目目标、范围、当前进展或待办。")
        self.config_project_description.setFixedHeight(130)
        self.save_project_description_button = QPushButton("保存项目简介")
        self.save_project_description_button.setObjectName("primaryButton")
        self.save_project_description_button.clicked.connect(self._save_project_description)
        config_project_layout.addWidget(self.config_project_description)
        config_project_layout.addWidget(self.save_project_description_button)
        self.config_project_panel.setVisible(False)

        overview_layout.addWidget(progress_panel)
        overview_layout.addWidget(self.config_project_panel)
        overview_layout.addStretch()
        self.project_content_stack.addWidget(overview_page)
        self.project_content_stack.addWidget(self._deck_detail_page())

        self.project_side_stack = QStackedWidget()
        self.project_side_stack.setMinimumWidth(260)
        self.project_side_stack.setMaximumWidth(340)

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
        self.member_role.addItems(["前端开发", "后端开发", "测试", "产品经理", "设计", "运维"])
        self.add_member_button = QPushButton("添加成员")
        self.add_member_button.clicked.connect(self._add_project_member)
        member_form_layout.addWidget(self.member_name)
        member_form_layout.addWidget(self.member_role)
        member_form_layout.addWidget(self.add_member_button)

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
        todo_layout = QVBoxLayout(todo_panel)
        todo_layout.setContentsMargins(18, 18, 18, 18)
        todo_layout.setSpacing(10)
        todo_header = QHBoxLayout()
        todo_header.addWidget(_label("代办看板", "eyebrow"))
        todo_header.addStretch()
        self.todo_count_label = _label("0 个待完成", "muted")
        todo_header.addWidget(self.todo_count_label)
        todo_layout.addLayout(todo_header)
        todo_input_row = QHBoxLayout()
        todo_input_row.setSpacing(8)
        self.project_todo_input = QLineEdit()
        self.project_todo_input.setPlaceholderText("新增一个 todo")
        self.add_todo_button = QPushButton("添加")
        self.add_todo_button.clicked.connect(self._add_project_todo)
        todo_input_row.addWidget(self.project_todo_input, 1)
        todo_input_row.addWidget(self.add_todo_button)
        todo_layout.addLayout(todo_input_row)
        self.todo_board = QListWidget()
        self.todo_board.setMinimumHeight(168)
        self.todo_board.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        todo_layout.addWidget(self.todo_board)

        self.daily_form = _panel()
        daily_form = self.daily_form
        daily_form.setFixedHeight(265)
        daily_layout = QVBoxLayout(daily_form)
        daily_layout.setContentsMargins(18, 18, 18, 18)
        daily_layout.setSpacing(10)
        daily_layout.addWidget(_label("日报", "eyebrow"))
        self.daily_member_label = _label("当前身份：自己", "muted")
        self.daily_editor = QTextEdit()
        self.daily_editor.setFixedHeight(118)
        self.daily_editor.setPlaceholderText("今天完成了什么、遇到什么阻塞、明天准备做什么。")
        self.save_daily_button = QPushButton("保存日报")
        self.save_daily_button.setObjectName("primaryButton")
        self.save_daily_button.clicked.connect(self._save_daily_report)
        daily_layout.addWidget(self.daily_member_label)
        daily_layout.addWidget(self.daily_editor)
        daily_layout.addWidget(self.save_daily_button)

        self.weekly_form = _panel()
        weekly_form = self.weekly_form
        weekly_form.setFixedHeight(390)
        weekly_layout = QVBoxLayout(weekly_form)
        weekly_layout.setContentsMargins(18, 18, 18, 18)
        weekly_layout.setSpacing(10)
        weekly_layout.addWidget(_label("负责人周报 / 文档", "eyebrow"))
        self.project_weekly_editor = QTextEdit()
        self.project_weekly_editor.setFixedHeight(118)
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

        display_side_layout.addWidget(member_panel, 0, Qt.AlignmentFlag.AlignTop)
        display_side_layout.addWidget(todo_panel, 0, Qt.AlignmentFlag.AlignTop)
        display_side_layout.addWidget(daily_form, 0, Qt.AlignmentFlag.AlignTop)
        display_side_layout.addWidget(weekly_form, 0, Qt.AlignmentFlag.AlignTop)
        display_side_layout.addStretch()
        config_side_layout.addWidget(member_form)
        config_side_layout.addWidget(config_member_panel)
        config_side_layout.addWidget(project_danger)
        config_side_layout.addStretch()
        self.project_side_stack.addWidget(display_side)
        self.project_side_stack.addWidget(config_side)

        splitter.addWidget(left)
        splitter.addWidget(middle)
        splitter.addWidget(self.project_side_stack)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([260, 590, 300])
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
        self.download_deck_button = QPushButton("下载文档")
        self.download_deck_button.clicked.connect(self._download_selected_deck)
        actions.addWidget(self.open_deck_button)
        actions.addWidget(self.download_deck_button)
        actions.addStretch()
        detail_layout.addLayout(actions)

        layout.addWidget(hero)
        layout.addWidget(detail)
        layout.addStretch()
        return page

    def _metric_card(self, title: str, value: str) -> QWidget:
        card = _soft_panel()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)
        value_label = _label(value, "metricValue")
        title_label = _label(title, "muted")
        layout.addWidget(value_label)
        layout.addWidget(title_label)
        self._metric_labels[title] = value_label
        card.setProperty("metricTitle", title)
        return card

    def _set_metric(self, card: QWidget, value: int) -> None:
        title = card.property("metricTitle")
        label = self._metric_labels.get(str(title))
        if label is not None:
            label.setText(str(value))

    def _load_projects(self) -> None:
        if not hasattr(self, "project_list"):
            return
        self.project_list.clear()
        projects = self._visible_projects()
        for project in projects:
            item = QListWidgetItem(f"{project.name}\n负责人 {project.owner}\n{project.status}")
            item.setData(Qt.ItemDataRole.UserRole, project.id)
            item.setSizeHint(QSize(0, 78))
            self.project_list.addItem(item)
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

    def _visible_projects(self) -> list[Project]:
        projects = self.db.list_projects()
        if getattr(self, "project_scope_value", "mine") == "all":
            return projects
        return [project for project in projects if self._project_involves_current_user(project)]

    def _project_involves_current_user(self, project: Project) -> bool:
        if self.db.is_current_user_name(project.owner):
            return True
        return any(
            self.db.is_current_user_name(member.name)
            for member in self.db.list_project_members(project.id)
        )

    def _select_project_item(self, item: QListWidgetItem) -> None:
        project_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(project_id, int):
            self.current_project_id = project_id
            self._show_project_overview()
            self._refresh_project_workspace()

    def _select_project_mode(self, index: int) -> None:
        if index == 1:
            project = self._current_project()
            if project is None or not self._can_manage_project(project, None):
                QMessageBox.information(self, "不能配置", "只有这个项目的负责人可以配置成员。")
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
            QMessageBox.warning(self, "不能配置", "只有这个项目的负责人可以添加成员。")
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
            QMessageBox.warning(self, "不能保存", "只有这个项目的负责人可以编辑项目简介。")
            return
        description = self.config_project_description.toPlainText().strip()
        if not description:
            QMessageBox.information(self, "简介为空", "先写一点项目简介。")
            return
        updated = self.db.update_project_description(project.id, description)
        if updated is None:
            QMessageBox.warning(self, "保存失败", "这个项目记录已经不存在。")
            self._load_projects()
            return
        self._refresh_project_workspace()

    def _delete_current_project(self) -> None:
        project = self._current_project()
        if project is None:
            return
        if not self._can_manage_project(project, None):
            QMessageBox.warning(self, "不能删除", "只有这个项目的负责人可以删除项目。")
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
        self.db.add_daily_report(project.id, current_member.name, current_member.role, content)
        self.daily_editor.clear()
        self._refresh_project_workspace()
        self._announce_presence()

    def _add_project_todo(self) -> None:
        project = self._current_project()
        if project is None:
            return
        members = self.db.list_project_members(project.id)
        current_member = self._current_project_member(project, members)
        if current_member is None:
            QMessageBox.information(self, "不能添加", "只有项目成员可以添加代办。")
            return
        title = self.project_todo_input.text().strip()
        if not title:
            QMessageBox.information(self, "代办为空", "先写一个 todo。")
            return
        self.db.add_project_todo(project.id, title, self.db.display_name())
        self.project_todo_input.clear()
        self._refresh_project_workspace()

    def _complete_project_todo(self, todo: ProjectTodo) -> None:
        project = self._current_project()
        if project is None:
            return
        members = self.db.list_project_members(project.id)
        current_member = self._current_project_member(project, members)
        if current_member is None:
            QMessageBox.information(self, "不能完成", "只有项目成员可以完成代办。")
            return
        report = self.db.complete_project_todo(todo.id, current_member.name, current_member.role)
        if report is None:
            QMessageBox.information(self, "已完成", "这个代办已经被完成。")
        self._refresh_project_workspace()
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

    def _upload_project_deck(self) -> None:
        project = self._current_project()
        if project is None:
            return
        doc_type = self.project_document_type.currentText().strip() or "其他"
        visibility = self.project_document_visibility.currentData() or "team"
        self._upload_project_document(project.id, doc_type, str(visibility))

    def _upload_project_document(self, project_id: int, doc_type: str, visibility: str = "team") -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择项目文档",
            "",
            "Documents (*.ppt *.pptx *.doc *.docx *.pdf *.xls *.xlsx *.png *.jpg *.jpeg *.fig *.zip *.txt *.md);;All Files (*)",
        )
        if not file_path:
            return
        source = Path(file_path)
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
        stem = source.stem or "document"
        suffix = source.suffix
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        target = target_dir / f"{stem}-{timestamp}{suffix}"
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
        members = self.db.list_project_members(project.id)
        daily_reports = self.db.list_daily_reports(project.id)
        weekly_reports = self.db.list_project_weekly_reports(project.id)
        documents = self.db.list_visible_project_documents(self.db.display_name(), project.id)
        todos = self.db.list_project_todos(project.id)
        completed_todos = [
            todo
            for todo in self.db.list_project_todos(project.id, include_completed=True)
            if todo.status == "done" and todo.completed_at is not None
        ]

        self.project_status.setText(f"{project.status} · 负责人 {project.owner}")
        self.project_title.setText(project.name)
        self.project_description.setText(project.description)
        self.config_project_description.setPlainText(project.description)
        self._set_metric(self.metric_members, len(members))
        self._set_metric(self.metric_todos, len(todos))
        self._set_metric(self.metric_daily, len(daily_reports))
        self._set_metric(self.metric_weekly, len(weekly_reports))
        self._set_metric(self.metric_decks, len(documents))

        self._clear_layout(self.member_cards_layout)
        current_member = self._current_project_member(project, members)
        is_manager = self._can_manage_project(project, current_member)
        if hasattr(self, "project_config_button"):
            self.project_config_button.setEnabled(is_manager)
        if not is_manager and self.project_side_stack.currentIndex() == 1:
            self._select_project_mode(0)
        can_update_todos = current_member is not None
        self.todo_panel.setVisible(can_update_todos)
        self.daily_form.setVisible(can_update_todos)
        self.project_todo_input.setEnabled(can_update_todos)
        self.add_todo_button.setEnabled(can_update_todos)
        self.daily_editor.setEnabled(can_update_todos)
        self.save_daily_button.setEnabled(can_update_todos)
        self.daily_member_label.setText(
            f"当前身份：{current_member.name} · {current_member.role}" if current_member is not None else "当前身份：非项目成员"
        )
        self.member_name.setEnabled(is_manager)
        self.member_role.setEnabled(is_manager)
        self.add_member_button.setEnabled(is_manager)
        self.config_project_description.setEnabled(is_manager)
        self.save_project_description_button.setEnabled(is_manager)
        self.delete_project_button.setEnabled(is_manager)
        self.weekly_form.setVisible(is_manager)
        self.project_weekly_editor.setEnabled(is_manager)
        self.save_project_weekly_button.setEnabled(is_manager)
        self.project_document_type.setEnabled(is_manager)
        self.project_document_visibility.setEnabled(is_manager)
        self.upload_deck_button.setEnabled(is_manager)
        for member in members:
            self._add_member_card(member)
        self._refresh_config_member_list(project, members, is_manager)

        self.todo_board.clear()
        self.todo_count_label.setText(f"{len(todos)} 个待完成")
        if not todos:
            self._add_todo_card(None, "当前没有待完成 todo。", False)
        for todo in todos:
            self._add_todo_card(todo, todo.title, can_update_todos)

        self.product_feed.clear()
        product_items: list[tuple[str, str, str, str, ProjectDocument | None]] = []
        if is_manager:
            for member in members:
                product_items.append(
                    (
                        member.created_at.isoformat(),
                        member.created_at.strftime("%m-%d %H:%M"),
                        "成员配置",
                        f"{member.name} · {member.role}",
                        None,
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
                    )
                )
        for todo in completed_todos:
            if not is_manager and not self.db.is_current_user_name(todo.completed_by):
                continue
            completed_at = todo.completed_at
            product_items.append(
                (
                    completed_at.isoformat(),
                    completed_at.strftime("%m-%d %H:%M"),
                    f"完成代办 · {todo.completed_by or '项目成员'}",
                    todo.title,
                    None,
                )
            )
        if product_items:
            for _, time_text, kind, content, document in sorted(product_items, reverse=True)[:5]:
                self._add_feed_card(self.product_feed, time_text, kind, content, document)
        else:
            self._add_feed_card(
                self.product_feed,
                "",
                "权限说明",
                "仅产品经理可查看项目周报、成员配置和汇报材料。",
            )

        self.developer_feed.clear()
        visible_daily_reports = daily_reports if is_manager else [
            report for report in daily_reports if self.db.is_current_user_name(report.member_name)
        ]
        if not visible_daily_reports:
            empty_text = "还没有日报。" if is_manager else "你还没有写过日报。"
            self._add_feed_card(self.developer_feed, "", "日报", empty_text)
        for report in visible_daily_reports[:5]:
            self._add_feed_card(
                self.developer_feed,
                report.created_at.strftime("%m-%d %H:%M"),
                f"日报 · {report.member_name} / {report.role}",
                report.content,
                daily_report=report,
            )

    def _clear_project_workspace(self) -> None:
        if not hasattr(self, "project_title"):
            return
        self.project_status.setText("暂无项目")
        self.project_title.setText("创建一个项目")
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
        self.save_daily_button.setEnabled(False)
        self.todo_panel.setVisible(False)
        self.daily_form.setVisible(False)
        self.project_todo_input.clear()
        self.project_todo_input.setEnabled(False)
        self.add_todo_button.setEnabled(False)
        self.todo_count_label.setText("0 个待完成")
        self.todo_board.clear()
        self._add_todo_card(None, "选择项目后，这里会显示 todo。", False)
        self.product_feed.clear()
        self.developer_feed.clear()
        empty_text = "当前没有你参与的项目。" if getattr(self, "project_scope_value", "mine") == "mine" else "还没有项目。"
        self._add_feed_card(self.product_feed, "", "项目", empty_text)
        self._add_feed_card(self.developer_feed, "", "日报", "还没有项目日报。")
        self.member_name.setEnabled(False)
        self.member_role.setEnabled(False)
        self.add_member_button.setEnabled(False)
        self.config_project_description.clear()
        self.config_project_description.setEnabled(False)
        self.save_project_description_button.setEnabled(False)
        self.config_project_panel.setVisible(False)
        self.delete_project_button.setEnabled(False)
        self.weekly_form.setVisible(False)
        self.project_weekly_editor.setEnabled(False)
        self.save_project_weekly_button.setEnabled(False)
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
            return ProjectMember(0, project.id, self.db.display_name(), "产品经理", project.created_at)
        return None

    def _can_manage_project(self, project: Project, member: ProjectMember | None) -> bool:
        return self.db.is_current_user_name(project.owner)

    def _clear_layout(self, layout: QGridLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

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
        text_box.addWidget(_label(member.name, "memberName"))
        text_box.addWidget(_label(member.role, "muted"))
        layout.addLayout(text_box, 1)

        delete_button = QPushButton("删除")
        delete_button.setObjectName("smallButton")
        delete_button.setEnabled(can_manage and not self.db.is_current_user_name(member.name) and member.name != project.owner)
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
            QMessageBox.warning(self, "不能配置", "只有这个项目的负责人可以删除成员。")
            return
        if self.db.is_current_user_name(member.name) or member.name == project.owner:
            QMessageBox.information(self, "不能删除", "负责人不能从项目成员里删除。")
            return
        message = f"确定从项目「{project.name}」删除成员「{member.name}」吗？"
        if QMessageBox.question(self, "删除成员", message) != QMessageBox.StandardButton.Yes:
            return
        if not self.db.delete_project_member(member.id):
            QMessageBox.warning(self, "删除失败", "这个成员记录已经不存在。")
            return
        self._refresh_project_workspace()

    def _add_member_card(self, member: ProjectMember) -> None:
        card = QWidget()
        card.setObjectName("compactMemberCard")
        card.setFixedHeight(64)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        avatar = _label((member.name[:1] or "?").upper(), "compactAvatar")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        name = _label(member.name, "memberName")
        role = _label(member.role, "compactRoleBadge")
        role.setFixedWidth(82)
        text_box.addWidget(name)
        role_row = QHBoxLayout()
        role_row.setContentsMargins(0, 0, 0, 0)
        role_row.setSpacing(0)
        role_row.addWidget(role)
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
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        body = QVBoxLayout()
        body.setSpacing(4)
        meta_text = "待完成"
        if todo is not None:
            meta_text = f"{todo.created_at.strftime('%m-%d %H:%M')}  {todo.creator or '项目成员'}"
        body.addWidget(_label(meta_text, "eyebrow"))
        body.addWidget(_label(title))
        layout.addLayout(body, 1)

        if todo is not None:
            done_button = QPushButton("完成")
            done_button.setObjectName("smallButton")
            done_button.setEnabled(can_complete)
            done_button.clicked.connect(lambda checked=False, selected=todo: self._complete_project_todo(selected))
            layout.addWidget(done_button)

        item.setSizeHint(QSize(0, 72))
        self.todo_board.addItem(item)
        self.todo_board.setItemWidget(item, card)

    def _add_feed_card(
        self,
        list_widget: QListWidget,
        time_text: str,
        kind: str,
        content: str,
        document: ProjectDocument | None = None,
        daily_report: DailyReport | None = None,
        height: int | None = None,
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
        meta = _label(f"{time_text}  {kind}".strip(), "eyebrow")
        text = _label(content)
        text.setMaximumHeight(42)
        body.addWidget(meta)
        body.addWidget(text)
        layout.addLayout(body, 1)

        if document is not None:
            actions = QHBoxLayout()
            actions.setSpacing(8)
            open_button = QPushButton("打开")
            open_button.setObjectName("smallButton")
            open_button.clicked.connect(lambda checked=False, selected=document: self._open_deck_file(selected))
            download_button = QPushButton("下载")
            download_button.setObjectName("smallButton")
            download_button.clicked.connect(lambda checked=False, selected=document: self._download_deck(selected))
            actions.addWidget(open_button)
            actions.addWidget(download_button)
            layout.addLayout(actions)
        elif daily_report is not None and self.db.is_current_user_name(daily_report.member_name):
            actions = QHBoxLayout()
            actions.setSpacing(8)
            delete_button = QPushButton("删除")
            delete_button.setObjectName("smallButton")
            delete_button.clicked.connect(lambda checked=False, selected=daily_report: self._delete_daily_report(selected))
            actions.addWidget(delete_button)
            layout.addLayout(actions)

        if height is None:
            height = self._feed_card_height(content)
        item.setSizeHint(QSize(0, height))
        list_widget.addItem(item)
        list_widget.setItemWidget(item, card)

    def _feed_card_height(self, content: str) -> int:
        normalized = " ".join(content.strip().split())
        if not normalized:
            return 78
        explicit_lines = len([line for line in content.splitlines() if line.strip()])
        visual_width = sum(1 if ord(char) < 128 else 2 for char in normalized)
        needs_two_lines = explicit_lines > 1 or visual_width > 48
        return 104 if needs_two_lines else 78

    def _delete_daily_report(self, report: DailyReport) -> None:
        message = f"确定删除 {report.created_at.strftime('%m-%d %H:%M')} 的日报吗？"
        if QMessageBox.question(self, "删除日报", message) != QMessageBox.StandardButton.Yes:
            return
        if not self.db.delete_daily_report(report.id):
            QMessageBox.warning(self, "删除失败", "只能删除自己的日报，或这条日报已经不存在。")
            return
        self._refresh_project_workspace()
        self._announce_presence()

    def _daily_feed_text(self, report: DailyReport) -> str:
        return (
            f"{report.created_at.strftime('%m-%d %H:%M')}  日报 · {report.member_name} / {report.role}\n"
            f"{report.content}"
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
        source = Path(document.file_path)
        status = "文件可用" if source.exists() else "原文件找不到"
        visibility = "团队文档" if document.visibility == "team" else "本人文档"
        self.deck_detail_title.setText(document.title)
        self.deck_detail_meta.setText(
            f"{document.doc_type} · {visibility} · {document.uploader} · {document.created_at.strftime('%Y-%m-%d %H:%M')} · {status}"
        )
        self.deck_detail_path.setPlainText(str(source))
        self.open_deck_button.setEnabled(source.exists())
        self.download_deck_button.setEnabled(source.exists())

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
        source = Path(deck.file_path)
        if not source.exists():
            QMessageBox.warning(self, "文件不存在", "这个文档文件找不到，可能被移动或删除了。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(source)))

    def _download_selected_deck(self) -> None:
        deck = self._selected_deck()
        if deck is None:
            return
        self._download_deck(deck)

    def _download_deck(self, deck: ProjectDocument) -> None:
        source = Path(deck.file_path)
        if not source.exists():
            QMessageBox.warning(self, "文件不存在", "这个文档文件找不到，暂时不能下载。")
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "下载文档",
            str(Path.home() / "Downloads" / source.name),
            "All Files (*)",
        )
        if not target:
            return
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            QMessageBox.warning(self, "下载失败", f"保存文件失败：{exc}")
            return
        QMessageBox.information(self, "下载完成", f"文档已保存到：\n{target}")

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
        editor_layout.addWidget(_label("本周记录", "eyebrow"))
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("完成、变化、阻塞、下周。")
        submit = QPushButton("整理并保存")
        submit.setObjectName("primaryButton")
        submit.clicked.connect(self._summarize_and_save)
        editor_layout.addWidget(self.editor)
        editor_layout.addWidget(submit)

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

    def _rest_calendar_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(42, 38, 42, 38)
        outer.setSpacing(24)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.addWidget(_label("休息日历", "sectionTitle"))
        title_box.addWidget(_label("看见已经休息的日子，也把下一周先安排好。", "muted"))
        header.addLayout(title_box)
        header.addStretch()
        previous_month = QPushButton("上月")
        previous_month.setObjectName("smallButton")
        previous_month.clicked.connect(lambda checked=False: self._move_rest_calendar_month(-1))
        next_month = QPushButton("下月")
        next_month.setObjectName("smallButton")
        next_month.clicked.connect(lambda checked=False: self._move_rest_calendar_month(1))
        self.rest_month_label = _label("", "sectionTitle")
        self.rest_month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        side_layout.setContentsMargins(20, 20, 20, 20)
        side_layout.setSpacing(14)
        side_layout.addWidget(_label("选中日期", "eyebrow"))
        self.rest_selected_label = _label("", "memberName")
        self.rest_selected_detail = _label("", "muted")
        self.rest_note = QLineEdit()
        self.rest_note.setPlaceholderText("备注，例如：调休、年假、上午休息")
        self.rest_toggle_button = QPushButton("安排休息")
        self.rest_toggle_button.setObjectName("primaryButton")
        self.rest_toggle_button.clicked.connect(self._toggle_selected_rest_day)
        side_layout.addWidget(self.rest_selected_label)
        side_layout.addWidget(self.rest_selected_detail)
        side_layout.addWidget(self.rest_note)
        side_layout.addWidget(self.rest_toggle_button)
        side_layout.addSpacing(16)
        next_week_header = QHBoxLayout()
        next_week_header.addWidget(_label("下一周", "eyebrow"))
        next_week_header.addStretch()
        all_next_week = QPushButton("全员下周")
        all_next_week.setObjectName("smallButton")
        all_next_week.clicked.connect(self._open_next_week_roster)
        next_week_header.addWidget(all_next_week)
        side_layout.addLayout(next_week_header)
        self.next_week_layout = QVBoxLayout()
        self.next_week_layout.setSpacing(8)
        side_layout.addLayout(self.next_week_layout)
        side_layout.addStretch()

        splitter.addWidget(calendar_panel)
        splitter.addWidget(side_panel)
        splitter.setSizes([760, 360])
        return page

    def _refresh_rest_calendar(self) -> None:
        if not hasattr(self, "rest_calendar_grid"):
            return

        rest_days = self.db.list_rest_days()
        rest_by_day = {item.day: item for item in rest_days}
        today = date.today()
        month = self.rest_calendar_month
        if self.selected_rest_day is None:
            self.selected_rest_day = today

        self.rest_month_label.setText(month.strftime("%Y年%m月"))
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
                button = QPushButton(self._rest_day_button_text(day, rest_day, today))
                button.setObjectName(self._rest_day_object_name(day, rest_day, today, month))
                button.clicked.connect(lambda checked=False, selected=day: self._select_rest_day(selected))
                self.rest_calendar_grid.addWidget(button, row_index, column)

        self._refresh_next_week(rest_by_day)
        self._update_rest_selection(rest_by_day)

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
        refresh.clicked.connect(self._announce_presence)
        header.addWidget(refresh)
        outer.addLayout(header)

        panel = _panel()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(14)
        self.lan_panel_title = _label("在线同事", "eyebrow")
        panel_layout.addWidget(self.lan_panel_title)
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
            download_button = QPushButton("下载")
            download_button.setObjectName("smallButton")
            download_button.clicked.connect(lambda checked=False, selected=document: self._download_deck(selected))
            actions.addWidget(open_button)
            actions.addWidget(download_button)
            layout.addLayout(actions)

        item.setSizeHint(QSize(0, 82))
        self.docs_list.addItem(item)
        self.docs_list.setItemWidget(item, card)

    def _summarize_and_save(self) -> None:
        content = self.editor.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "还没写", "先写一点周报内容。")
            return

        result = self.summarizer.summarize(content)
        report = self.db.add_weekly_report(content, result.summary, result.mood)
        self.summary.setPlainText(result.summary)
        self.pet.set_mood(result.mood)
        self.pet.move_to_bottom_right()
        self.pet.show()
        self.editor.clear()
        self._prepend_report(report)
        self._refresh_home()

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
            self.summary.setPlainText(report.summary)
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
            if self.discovery is not None:
                self.discovery.set_display_name(self.db.display_name())
                self._refresh_peers(self.discovery.sorted_peers())

    def _open_pet(self) -> None:
        self.pet.move_to_bottom_right()
        self.pet.show()
        dialog = PetDialog(self.db, self.pet)
        dialog.exec()

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
            self.discovery.announce()
            self.discovery.broadcast_database()

    def _refresh_after_lan_sync(self) -> None:
        self._load_projects()
        self._load_reports()
        self._refresh_rest_calendar()
        self._refresh_document_library()
        self._refresh_home()
        if self.lan_view_mode == "logs":
            self._refresh_lan_logs(self.current_lan_peers)

    def _set_lan_view(self, mode: str) -> None:
        self.lan_view_mode = "logs" if mode == "logs" else "peers"
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
        if self.lan_view_mode == "logs":
            self._refresh_lan_logs(peers)
            return
        self.peer_list.clear()
        self.lan_panel_title.setText("在线同事")
        if self.discovery is not None and not self.discovery.is_bound:
            self.lan_subtitle.setText("局域网发现没有启动。请检查系统网络权限或端口占用。")
            item = QListWidgetItem("UDP 45454 端口未能绑定。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.peer_list.addItem(item)
            return
        self.lan_subtitle.setText(f"我的名字：{self.db.display_name()}。发现 {len(peers)} 位在线同事。")
        if not peers:
            item = QListWidgetItem("暂时没有发现其他人。确认大家在同一局域网，并且都打开了数智中心。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.peer_list.addItem(item)
            return
        for peer in peers:
            seen = peer.last_seen.strftime("%H:%M:%S")
            self._add_peer_card(peer, seen)

    def _refresh_lan_logs(self, peers: list[LanPeer]) -> None:
        self.peer_list.clear()
        self.lan_panel_title.setText("今日项目日志")
        if self.discovery is not None and not self.discovery.is_bound:
            self.lan_subtitle.setText("局域网发现没有启动。请检查系统网络权限或端口占用。")
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
        title_box.addWidget(_label(name, "memberName"))
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

        item.setSizeHint(QSize(0, 82 + max(1, len(logs)) * 58))
        self.peer_list.addItem(item)
        self.peer_list.setItemWidget(item, card)

    def _open_lan_member_logs(self, member_name: str) -> None:
        logs = self.db.project_logs_for_member(member_name)
        dialog = ProjectLogHistoryDialog(member_name, logs, self)
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
        content_label.setMaximumHeight(42)
        layout.addWidget(_label(meta, "eyebrow"))
        layout.addWidget(content_label)
        return row

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
        body.addWidget(_label(peer.name, "memberName"))
        body.addWidget(_label(self._peer_list_text(peer, seen), "muted"))
        layout.addLayout(body, 1)

        if self._peer_has_lan_update(peer):
            download = QPushButton("下载更新")
            download.setObjectName("primaryButton")
            download.clicked.connect(lambda checked=False, selected=peer: self._download_lan_update(selected))
            layout.addWidget(download)
        elif peer.platform == sys.platform and peer.app_version and version_tuple(peer.app_version) > version_tuple(APP_VERSION):
            unavailable = QPushButton("无安装包")
            unavailable.setEnabled(False)
            layout.addWidget(unavailable)

        item.setSizeHint(QSize(0, 92))
        self.peer_list.addItem(item)
        self.peer_list.setItemWidget(item, card)

    def _peer_has_lan_update(self, peer: LanPeer) -> bool:
        return (
            peer.platform == sys.platform
            and bool(peer.update_package)
            and bool(peer.app_version)
            and version_tuple(peer.app_version) > version_tuple(APP_VERSION)
        )

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
            target = self.discovery.download_update_package(peer, Path.home() / "Downloads")
        except Exception as exc:
            QMessageBox.warning(self, "下载失败", str(exc))
            return
        message = f"安装包已保存到：\n{target}\n\n是否现在打开？"
        if QMessageBox.question(self, "下载完成", message) == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _lan_update_message(self, peer: LanPeer) -> str:
        package = peer.update_package
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
            f"从 {peer.name} 下载 v{peer.app_version} 安装包吗？"
            f"{notes_text}"
            f"{history_text}"
            "\n\n下载后需要手动关闭当前程序并运行安装包。"
        )

    def _peer_list_text(self, peer: LanPeer, seen: str) -> str:
        platform = self._platform_label(peer.platform)
        version = f"v{peer.app_version}" if peer.app_version else "版本未知"
        status = ""
        if peer.platform == sys.platform and peer.app_version:
            if version_tuple(peer.app_version) > version_tuple(APP_VERSION):
                status = " · 可局域网更新" if peer.update_package else " · 高版本但未共享安装包"
            elif version_tuple(peer.app_version) < version_tuple(APP_VERSION):
                status = " · 对方版本较低"
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
