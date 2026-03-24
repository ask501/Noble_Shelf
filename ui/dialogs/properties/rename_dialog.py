from __future__ import annotations

import os
from typing import Callable

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

import config
import db
from ui.dialogs.properties._utils import _is_library_root, _safe_from_db_path
from theme import THEME_COLORS, apply_dark_titlebar


class RenameDialog(QDialog):
    """context_menu から呼び出す単純な名前変更ダイアログ"""

    def __init__(self, book: dict, parent=None, on_renamed: Callable[[], None] | None = None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self._book = book
        self._on_renamed = on_renamed
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle(config.APP_TITLE)
        self.setFixedSize(*config.RENAME_DIALOG_SIZE)
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {THEME_COLORS["bg_panel"]};
                color: {THEME_COLORS["text_main"]};
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*config.RENAME_DIALOG_MARGINS)
        layout.setSpacing(config.RENAME_DIALOG_SPACING)

        name = self._book.get("name", "")
        parsed_circle, parsed_title = db.parse_display_name(name)
        circle_init = parsed_circle or self._book.get("circle", "") or ""
        title_init = parsed_title or self._book.get("title", "") or name

        layout.addWidget(QLabel("サークル名"))
        self._circle_edit = QLineEdit(circle_init)
        layout.addWidget(self._circle_edit)

        layout.addWidget(QLabel("作品名"))
        self._title_edit = QLineEdit(title_init)
        layout.addWidget(self._title_edit)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("変更")
        btn_cancel = QPushButton("キャンセル")
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._apply)

    def _apply(self):
        path = _safe_from_db_path(self._book.get("path", ""))
        cover = self._book.get("cover", "")
        circle_old = self._book.get("circle", "")
        title_old = self._book.get("title", "")

        new_circle = self._circle_edit.text().strip()
        new_title = self._title_edit.text().strip()
        if not new_title or not path:
            return
        new_name = db.format_book_name(new_circle, new_title)

        try:
            if os.path.isdir(path):
                if _is_library_root(path):
                    QMessageBox.critical(self, "リネーム不可", "ライブラリフォルダ自体の名前は変更できません。")
                    return
                base_dir = os.path.dirname(path)
                new_path = os.path.join(base_dir, new_name)
                os.rename(path, new_path)
            else:
                parent_dir = os.path.dirname(path)
                if _is_library_root(parent_dir):
                    # ライブラリ直下のファイル（ストアファイル等）→ ファイル自体をリネーム
                    ext = os.path.splitext(path)[1]
                    new_path = os.path.join(parent_dir, new_name + ext)
                    if new_path != path:
                        os.rename(path, new_path)
                else:
                    # サブフォルダ内のファイル → 親フォルダをリネーム
                    grand = os.path.dirname(parent_dir)
                    new_parent = os.path.join(grand, new_name)
                    os.rename(parent_dir, new_parent)
                    new_path = os.path.join(new_parent, os.path.basename(path))

            new_cover = cover
            if cover:
                if os.path.isdir(path) and cover.startswith(path):
                    new_cover = cover.replace(path, new_path, 1)
                elif not os.path.isdir(path) and cover.startswith(path):
                    new_cover = new_path if path == cover else cover.replace(path, new_path, 1)
                else:
                    parent_dir_old = os.path.dirname(path)
                    if cover.startswith(parent_dir_old):
                        new_cover = cover.replace(parent_dir_old, os.path.dirname(new_path), 1)

            db.rename_book(path, new_path, new_name, new_circle, new_title, new_cover or "")

            if (circle_old != new_circle or title_old != new_title) and self._on_renamed:
                self._on_renamed()

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))

