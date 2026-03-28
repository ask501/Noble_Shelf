from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from send2trash import send2trash

import config
import db
from drop_handler import handle_drop
from theme import THEME_COLORS, apply_dark_titlebar
from ui.dialogs.library_checker import scan_unregistered


class LibraryCheckDialog(QDialog):
    """ライブラリ直下の未登録アイテムを確認・操作する。"""

    def __init__(self, library_path: str, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle("ライブラリ整合性チェック")
        self.setMinimumSize(*config.LIBRARY_CHECK_DIALOG_MIN_SIZE)
        self.resize(*config.LIBRARY_CHECK_DIALOG_SIZE)
        self._library_path = library_path
        self._items: list[dict] = scan_unregistered(self._library_path, db)

        root = QVBoxLayout(self)
        root.setContentsMargins(*config.THUMB_CROP_LAYOUT_MARGINS)
        root.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)

        self._chk_show_hidden = QCheckBox("非表示を含めて表示")
        self._chk_show_hidden.toggled.connect(self._refresh_list)
        root.addWidget(self._chk_show_hidden)

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
        # 古いコンテナを破棄して新規作成
        old = self._scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self._container = QWidget()
        self._rows = QVBoxLayout(self._container)
        self._rows.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        self._rows.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)
        self._scroll.setWidget(self._container)

        show_hidden = self._chk_show_hidden.isChecked()
        visible = [
            item for item in self._items
            if show_hidden or not item.get("hidden", False)
        ]

        if not visible:
            self._message.setText("未登録のアイテムはありません")
            return

        self._message.setText(f"{len(visible)} 件の未登録アイテム")
        for item in visible:
            self._rows.addWidget(self._build_row(item, show_hidden))
        self._rows.addStretch()

    def _build_row(self, item: dict, show_hidden: bool) -> QWidget:
        row = QWidget(self)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        lay.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)

        name = item["name"] + ("/" if item["is_dir"] else "")
        lbl = QLabel(name)
        if item.get("hidden") and show_hidden:
            # text_muted / text_disabled は未定義のため text_sub → menu_disabled（theme.THEME_COLORS）
            _muted = THEME_COLORS.get(
                "text_muted",
                THEME_COLORS.get("text_sub", THEME_COLORS["menu_disabled"]),
            )
            lbl.setStyleSheet(f"color: {_muted};")
        lay.addWidget(lbl, 1)

        btn_register = QPushButton("登録")
        btn_register.clicked.connect(lambda _=False, p=item["path"]: self._on_register(p))
        lay.addWidget(btn_register)

        btn_open = QPushButton("エクスプローラーで開く")
        btn_open.clicked.connect(lambda _=False, p=item["path"]: self._on_open_in_explorer(p))
        lay.addWidget(btn_open)

        if item.get("hidden") and show_hidden:
            btn_unhide = QPushButton("再表示")
            btn_unhide.clicked.connect(lambda _=False, p=item["path"]: self._on_unhide(p))
            lay.addWidget(btn_unhide)
        else:
            btn_hide = QPushButton("非表示")
            btn_hide.clicked.connect(lambda _=False, p=item["path"]: self._on_hide(p))
            lay.addWidget(btn_hide)

        btn_delete = QPushButton("削除")
        btn_delete.clicked.connect(lambda _=False, p=item["path"]: self._on_delete(p))
        lay.addWidget(btn_delete)
        return row

    def _on_register(self, path: str) -> None:
        handle_drop(
            paths=[path],
            library_folder=self._library_path,
            parent=self,
            on_done=self._on_register_done,
        )

    def _on_register_done(self) -> None:
        self._items = scan_unregistered(self._library_path, db)
        self._refresh_list()
        parent = self.parent()
        if parent is not None and hasattr(parent, "_on_drop_done"):
            parent._on_drop_done()

    def _on_open_in_explorer(self, path: str) -> None:
        if os.path.exists(path):
            os.startfile(path)

    def _on_hide(self, path: str) -> None:
        db.add_hidden_path(path)
        self._items = scan_unregistered(self._library_path, db)
        self._refresh_list()

    def _on_unhide(self, path: str) -> None:
        db.remove_hidden_path(path)
        self._items = scan_unregistered(self._library_path, db)
        self._refresh_list()

    def _on_delete(self, path: str) -> None:
        reply = QMessageBox.question(
            self,
            config.APP_TITLE,
            f"次の項目をゴミ箱へ移動しますか？\n{path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            send2trash(path)
        except Exception as exc:
            QMessageBox.warning(self, config.APP_TITLE, f"削除に失敗しました:\n{exc}")
            return
        self._items = scan_unregistered(self._library_path, db)
        self._refresh_list()

