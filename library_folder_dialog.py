from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

import config
from theme import THEME_COLORS, apply_dark_titlebar


def _default_library_path() -> str:
    """ライブラリの推奨パス（OS 依存の動的値）。"""
    return os.path.join(os.path.expanduser("~"), "Documents", "NobleShelf")


class LibraryFolderDialog(QDialog):
    """テキスト入力と参照でライブラリフォルダを選ぶ／新規作成するダイアログ。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self._selected_path: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle(config.LIBRARY_FOLDER_DIALOG_TITLE)
        self.resize(*config.LIBRARY_FOLDER_DIALOG_SIZE)
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {THEME_COLORS["bg_panel"]};
                color: {THEME_COLORS["text_main"]};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(*config.RENAME_DIALOG_MARGINS)
        root.setSpacing(config.RENAME_DIALOG_SPACING)

        row = QHBoxLayout()
        row.setSpacing(config.RENAME_DIALOG_SPACING)
        self._line_edit = QLineEdit(_default_library_path())
        self._line_edit.setMinimumHeight(config.DIALOG_BUTTON_HEIGHT)
        self._browse_btn = QPushButton("参照...")
        self._browse_btn.setFixedHeight(config.DIALOG_BUTTON_HEIGHT)
        self._browse_btn.setMinimumWidth(config.DIALOG_FETCH_BTN_WIDTH)
        row.addWidget(self._line_edit, stretch=1)
        row.addWidget(self._browse_btn, stretch=0)
        root.addLayout(row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._ok_btn = QPushButton("OK")
        self._cancel_btn = QPushButton("キャンセル")
        self._ok_btn.setFixedHeight(config.DIALOG_BUTTON_HEIGHT)
        self._cancel_btn.setFixedHeight(config.DIALOG_BUTTON_HEIGHT)
        btn_row.addWidget(self._ok_btn)
        btn_row.addWidget(self._cancel_btn)
        root.addLayout(btn_row)

        self._browse_btn.clicked.connect(self._on_browse)
        self._ok_btn.clicked.connect(self._on_ok)
        self._cancel_btn.clicked.connect(self.reject)

    @staticmethod
    def _normalize_path(raw: str) -> str:
        t = raw.strip()
        if not t:
            return ""
        return os.path.normpath(os.path.expanduser(t))

    def _on_browse(self) -> None:
        start = self._normalize_path(self._line_edit.text())
        if os.path.isdir(start):
            browse_start = start
        else:
            parent_dir = os.path.dirname(start) if start else ""
            browse_start = (
                parent_dir
                if parent_dir and os.path.isdir(parent_dir)
                else _default_library_path()
            )
        chosen = QFileDialog.getExistingDirectory(
            self,
            "ライブラリフォルダを選択",
            browse_start,
        )
        if chosen:
            self._line_edit.setText(chosen)

    def _on_ok(self) -> None:
        path = self._normalize_path(self._line_edit.text())
        if not path:
            return
        if os.path.isdir(path):
            self._selected_path = path
            self.accept()
            return
        if os.path.exists(path):
            QMessageBox.critical(
                self,
                config.LIBRARY_FOLDER_DIALOG_TITLE,
                "選択したパスはフォルダではありません。",
            )
            return
        reply = QMessageBox.question(
            self,
            config.LIBRARY_FOLDER_DIALOG_TITLE,
            "フォルダが存在しません。新規作成しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        os.makedirs(path, exist_ok=True)
        self._selected_path = path
        self.accept()

    @property
    def selected_path(self) -> str:
        """OK 確定後のパス（未確定時は空文字）。"""
        return self._selected_path
