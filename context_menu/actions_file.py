from __future__ import annotations

import os
from typing import Callable

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

import config
import db
from theme import THEME_COLORS, apply_dark_titlebar, COLOR_WHITE


class DeleteConfirmDialog(QDialog):
    def __init__(self, book: dict, parent, on_done: Callable[[], None] | None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self._book = book
        self._on_done = on_done
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle(config.APP_TITLE)
        self.setMinimumSize(config.DELETE_CONFIRM_MIN_WIDTH, 0)
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {THEME_COLORS["bg_panel"]};
                color: {THEME_COLORS["text_main"]};
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*config.DELETE_CONFIRM_MARGINS)
        layout.setSpacing(config.DELETE_CONFIRM_SPACING)

        name = self._book.get("name", "")
        lbl = QLabel(
            f"「{name}」を完全に削除しますか？\n\n"
            "ライブラリから削除するだけでなく、元のファイル（またはフォルダ）もディスクから削除されます。\n"
            "この操作は元に戻せません。"
        )
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(config.DELETE_CONFIRM_LABEL_MIN_WIDTH)
        lbl.setMinimumHeight(config.DELETE_CONFIRM_LABEL_MIN_HEIGHT)
        layout.addWidget(lbl)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("削除")
        btn_cancel = QPushButton("キャンセル")
        btn_ok.setStyleSheet(f"QPushButton {{ background-color: {THEME_COLORS['delete']}; color: {COLOR_WHITE}; }}")
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._apply)

    def _apply(self):
        import shutil

        path = self._book.get("path", "")
        if not path:
            return
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
                # Windows 等で rmtree 後に空フォルダが残ることがあるため、フォルダごと確実に削除
                if os.path.exists(path) and os.path.isdir(path):
                    try:
                        os.rmdir(path)
                    except Exception:
                        pass
            else:
                os.remove(path)
                # その本が入っていた親フォルダがライブラリ直下で空なら削除する
                parent_dir = os.path.dirname(path)
                lib_folder = (db.get_setting("library_folder") or "").strip()
                if (
                    parent_dir
                    and lib_folder
                    and os.path.isdir(parent_dir)
                    and os.path.normpath(parent_dir).startswith(os.path.normpath(lib_folder))
                    and not os.listdir(parent_dir)
                ):
                    shutil.rmtree(parent_dir)
            db.delete_book(path)
            if self._on_done:
                self._on_done()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "削除エラー", str(e))


def delete_book(book: dict, parent_window, on_done: Callable[[], None] | None) -> None:
    """DeleteConfirmDialog を生成して exec() するだけ"""
    dlg = DeleteConfirmDialog(book, parent_window, on_done)
    dlg.exec()

