from __future__ import annotations

import logging
from functools import partial

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

import config
import db
from theme import THEME_COLORS, apply_dark_titlebar, COLOR_WHITE, BOOKMARK_STAR_ON_FG, BOOKMARK_STAR_OFF_FG, BOOKMARK_SAVE_BG


def edit_bookmark(book: dict, parent_window) -> None:
    """BookContextMenu._on_bookmark の星ダイアログ部分をそのまま移動"""
    path = (book or {}).get("path", "")
    if not path:
        return

    dlg = QDialog(parent_window)
    dlg.setWindowTitle(config.APP_TITLE)
    dlg.setModal(True)
    dlg.setFixedSize(*config.BOOKMARK_DIALOG_SIZE)
    apply_dark_titlebar(dlg)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(*config.BOOKMARK_DIALOG_MARGINS)
    layout.setSpacing(config.BOOKMARK_DIALOG_SPACING)

    # タイトル
    title = (book or {}).get("title", "") or (book or {}).get("name", "")
    lbl = QLabel(title)
    font = lbl.font()
    font.setBold(True)
    lbl.setFont(font)
    layout.addWidget(lbl)

    # 星ボタン行
    try:
        bookmarks = db.get_all_bookmarks()
        current = bookmarks.get(path, 0)
    except Exception:
        current = 0

    star_buttons: list[QPushButton] = []

    star_row = QHBoxLayout()
    star_row.setSpacing(config.BOOKMARK_STAR_ROW_SPACING)
    star_row.addStretch()

    def _update_stars(rating: int):
        for i, btn in enumerate(star_buttons, start=1):
            btn.setText("★")
            btn.setStyleSheet(
                f"color: {BOOKMARK_STAR_ON_FG}; background: transparent; border: none; font-size: {config.FONT_SIZE_BTN_STAR}px;"
                if i <= rating
                else f"color: {BOOKMARK_STAR_OFF_FG}; background: transparent; border: none; font-size: {config.FONT_SIZE_BTN_STAR}px;"
            )

    def _set_rating(rating: int):
        nonlocal current
        current = rating
        _update_stars(current)

    for i in range(1, 6):
        btn = QPushButton("★")
        btn.setFixedSize(*config.BOOKMARK_STAR_BTN_SIZE)
        btn.setFlat(True)
        btn.clicked.connect(partial(_set_rating, i))
        star_buttons.append(btn)
        star_row.addWidget(btn)

    star_row.addStretch()
    layout.addLayout(star_row)
    _update_stars(current)

    # ボタン行：保存・削除・キャンセル
    btn_row = QHBoxLayout()
    btn_row.addStretch()

    btn_save = QPushButton("保存")
    btn_save.setFixedWidth(config.BOOKMARK_BTN_WIDTH)
    btn_save.setStyleSheet(
        f"background-color: {BOOKMARK_SAVE_BG}; color: {COLOR_WHITE}; border: none; "
        f"border-radius: {config.BOOKMARK_BTN_RADIUS}px; padding: {config.BOOKMARK_BTN_PADDING_Y}px {config.BOOKMARK_BTN_PADDING_X}px;"
    )

    btn_delete = QPushButton("削除")
    btn_delete.setFixedWidth(config.BOOKMARK_BTN_WIDTH)
    btn_delete.setStyleSheet(
        f"background-color: {THEME_COLORS['delete']}; color: {COLOR_WHITE}; border: none; "
        f"border-radius: {config.BOOKMARK_BTN_RADIUS}px; padding: {config.BOOKMARK_BTN_PADDING_Y}px {config.BOOKMARK_BTN_PADDING_X}px;"
    )

    btn_cancel = QPushButton("キャンセル")
    btn_cancel.setFixedWidth(config.BOOKMARK_CANCEL_BTN_WIDTH)

    btn_row.addWidget(btn_save)
    btn_row.addWidget(btn_delete)
    btn_row.addWidget(btn_cancel)
    layout.addLayout(btn_row)

    def _apply_and_close():
        try:
            db.set_bookmark(path, current)
        except Exception as e:
            logging.debug("[actions_bookmark] set_bookmark（保存）失敗: %s", e)
        on_updated = getattr(parent_window, "on_book_updated", None)
        if callable(on_updated):
            on_updated(path)
        dlg.accept()

    def _delete_and_close():
        try:
            db.set_bookmark(path, 0)
        except Exception as e:
            logging.debug("[actions_bookmark] set_bookmark（削除）失敗: %s", e)
        on_updated = getattr(parent_window, "on_book_updated", None)
        if callable(on_updated):
            on_updated(path)
        dlg.accept()

    btn_save.clicked.connect(_apply_and_close)
    btn_delete.clicked.connect(_delete_and_close)
    btn_cancel.clicked.connect(dlg.reject)

    dlg.exec()

