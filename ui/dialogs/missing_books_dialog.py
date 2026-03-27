from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import config
import db
from theme import apply_dark_titlebar


class MissingBooksDialog(QDialog):
    """missing_since_date が付いた本を一覧・削除するダイアログ。"""

    # 操作列のインデックス（行クリックで削除確認するのはこの列以外）
    _COL_ACTION = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle("見つからない本")
        self.resize(*config.LIBRARY_CHECK_DIALOG_SIZE)
        self.setMinimumSize(*config.LIBRARY_CHECK_DIALOG_MIN_SIZE)

        root = QVBoxLayout(self)
        root.setContentsMargins(*config.THUMB_CROP_LAYOUT_MARGINS)
        root.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)

        self._message = QLabel("")
        root.addWidget(self._message)

        self._table = QTableWidget(self)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["タイトル", "パス", "missing開始", "残り日数", "操作"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.cellClicked.connect(self._on_cell_clicked)
        root.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        self._btn_delete_all = QPushButton("すべて削除")
        self._btn_close = QPushButton("閉じる")
        btn_row.addStretch(1)
        btn_row.addWidget(self._btn_delete_all)
        btn_row.addWidget(self._btn_close)
        root.addLayout(btn_row)

        self._btn_delete_all.clicked.connect(self._on_delete_all)
        self._btn_close.clicked.connect(self.accept)

        self._rows: list[dict] = []
        self._reload()

    def _calc_remaining_days(self, missing_since: str) -> int:
        try:
            since = datetime.fromisoformat((missing_since or "").strip())
            elapsed = (datetime.utcnow() - since).days
            return max(config.MISSING_BOOK_TTL_DAYS - elapsed, 0)
        except Exception:
            return 0

    def _confirm_delete_one(self, title: str, path: str) -> bool:
        """削除確認。True なら削除してよい。"""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(config.APP_TITLE)
        box.setText(
            config.MISSING_BOOKS_DIALOG_ROW_DELETE_TEXT_TEMPLATE.format(title=title))
        box.setInformativeText(config.MISSING_BOOKS_DIALOG_ROW_DELETE_INFO)
        btn_delete = box.addButton(
            config.MISSING_BOOKS_DIALOG_BTN_DELETE,
            QMessageBox.ButtonRole.DestructiveRole,
        )
        btn_cancel = box.addButton(
            config.MISSING_BOOKS_DIALOG_BTN_CANCEL,
            QMessageBox.ButtonRole.RejectRole,
        )
        box.setDefaultButton(btn_cancel)
        box.exec()
        return box.clickedButton() == btn_delete

    def _reload(self) -> None:
        self._rows = db.get_missing_books()
        self._table.setRowCount(len(self._rows))
        self._message.setText(f"{len(self._rows)} 件の見つからない本")
        for i, row in enumerate(self._rows):
            title = (row.get("title") or row.get("name") or "").strip()
            path = (row.get("path") or "").strip()
            missing_since = (row.get("missing_since_date") or "").strip()
            remain = self._calc_remaining_days(missing_since)

            self._table.setItem(i, 0, QTableWidgetItem(title))
            self._table.setItem(i, 1, QTableWidgetItem(path))
            self._table.setItem(i, 2, QTableWidgetItem(missing_since))
            self._table.setItem(i, 3, QTableWidgetItem(str(remain)))

            btn = QPushButton("今すぐ削除")
            btn.clicked.connect(lambda _=False, t=title, p=path: self._on_delete_one(t, p))
            holder = QWidget(self._table)
            lay = QHBoxLayout(holder)
            lay.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
            lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
            self._table.setCellWidget(i, self._COL_ACTION, holder)

        self._table.resizeColumnsToContents()
        self._btn_delete_all.setEnabled(bool(self._rows))

    def _on_cell_clicked(self, row: int, column: int) -> None:
        """タイトル〜残り日数列のクリックで削除確認（操作列はボタン専用）。"""
        if column == self._COL_ACTION:
            return
        if row < 0 or row >= len(self._rows):
            return
        r = self._rows[row]
        title = (r.get("title") or r.get("name") or "").strip()
        path = (r.get("path") or "").strip()
        if not path:
            return
        if self._confirm_delete_one(title or path, path):
            db.delete_books_by_paths([path])
            self._reload()

    def _on_delete_one(self, title: str, path: str) -> None:
        if not path:
            return
        if not self._confirm_delete_one(title or path, path):
            return
        db.delete_books_by_paths([path])
        self._reload()

    def _on_delete_all(self) -> None:
        paths = [(r.get("path") or "").strip() for r in self._rows]
        paths = [p for p in paths if p]
        if not paths:
            return
        if QMessageBox.question(
            self,
            config.APP_TITLE,
            f"{len(paths)} 件のレコードを削除しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        db.delete_books_by_paths(paths)
        self._reload()
