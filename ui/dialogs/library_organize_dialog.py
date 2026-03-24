"""
library_organize_dialog.py - ライブラリ整理でスキップされた項目の手動移動
"""
from __future__ import annotations

import os
import shutil

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import config
from theme import THEME_COLORS, apply_dark_titlebar


class LibraryOrganizeDialog(QDialog):
    """整理対象外だったパスを dest へ手動移動する。"""

    def __init__(self, skipped_paths: list[str], dest: str, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.LIBRARY_ORGANIZE_DIALOG_TITLE)
        self.setMinimumSize(*config.LIBRARY_ORGANIZE_DIALOG_MIN_SIZE)
        self.resize(*config.LIBRARY_ORGANIZE_DIALOG_SIZE)
        self._dest = os.path.normpath(dest)
        self._paths: list[str] = list(skipped_paths)

        root = QVBoxLayout(self)
        root.setContentsMargins(*config.THUMB_CROP_LAYOUT_MARGINS)
        root.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)

        self._message = QLabel("")
        root.addWidget(self._message)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._container = QWidget(self._scroll)
        self._rows = QVBoxLayout(self._container)
        self._rows.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        self._rows.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)
        self._scroll.setWidget(self._container)
        root.addWidget(self._scroll)

        self._refresh_list()

    def _refresh_list(self) -> None:
        old = self._scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self._container = QWidget()
        self._rows = QVBoxLayout(self._container)
        self._rows.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        self._rows.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)
        self._scroll.setWidget(self._container)

        visible = [p for p in self._paths if os.path.exists(p)]
        self._paths = visible

        if not visible:
            self._message.setText("手動移動の対象はありません")
            return

        self._message.setText(
            f"{len(visible)} 件は自動整理の対象外です。必要なら「移動」で次のフォルダへ移せます:\n{self._dest}"
        )
        for path in visible:
            self._rows.addWidget(self._build_row(path))
        self._rows.addStretch()

    def _build_row(self, path: str) -> QWidget:
        row = QWidget(self)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        lay.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)

        name = os.path.basename(path) + ("/" if os.path.isdir(path) else "")
        lbl = QLabel(name)
        lbl.setStyleSheet(f"color: {THEME_COLORS['text_main']};")
        lay.addWidget(lbl, 1)

        btn_move = QPushButton("移動")
        btn_move.setFixedHeight(config.DIALOG_BUTTON_HEIGHT)
        btn_move.clicked.connect(lambda _=False, p=path: self._on_move(p))
        lay.addWidget(btn_move)

        btn_open = QPushButton("エクスプローラーで開く")
        btn_open.setFixedHeight(config.DIALOG_BUTTON_HEIGHT)
        btn_open.clicked.connect(lambda _=False, p=path: self._on_open_in_explorer(p))
        lay.addWidget(btn_open)

        return row

    def _on_move(self, path: str) -> None:
        if not os.path.exists(path):
            self._paths = [p for p in self._paths if p != path]
            self._refresh_list()
            return
        try:
            os.makedirs(self._dest, exist_ok=True)
            dest_path = os.path.join(self._dest, os.path.basename(path))
            shutil.move(path, dest_path)
        except Exception as exc:
            QMessageBox.warning(self, config.APP_TITLE, f"移動に失敗しました:\n{exc}")
            return
        self._paths = [p for p in self._paths if p != path]
        self._refresh_list()

    def _on_open_in_explorer(self, path: str) -> None:
        if os.path.exists(path):
            os.startfile(path)
