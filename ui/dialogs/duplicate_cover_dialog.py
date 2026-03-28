"""
duplicate_cover_dialog.py - cover_hash 一致時の重複確認ダイアログ
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

import config
from theme import apply_dark_titlebar


class DuplicateCoverDialog(QDialog):
    """
    cover_hash 一致時の重複確認ダイアログ。
    既存・新規のサムネを左右に並べて表示し、ユーザーが処理を選択する。

    result_action:
        "new"     → 別作品として新規登録
        "cancel"  → 登録中止
    """

    def __init__(
        self,
        existing: dict,  # db.get_book_by_cover_hash の返り値
        new_name: str,  # 新規フォルダ名
        new_cover_abs: str,  # 新規フォルダの先頭画像絶対パス
        existing_cover_abs: str,  # 既存エントリのカバー絶対パス
        parent=None,
    ):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.setWindowModality(Qt.ApplicationModal)
        self.result_action: str = "cancel"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*config.META_APPLY_LAYOUT_MARGINS)
        layout.setSpacing(config.META_APPLY_LAYOUT_SPACING)

        # タイトル
        title_lbl = QLabel("似た作品が既に登録されています")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # サムネ比較行
        thumb_row = QHBoxLayout()

        def _make_thumb_col(cover_abs: str, label_text: str, sub_text: str) -> QVBoxLayout:
            col = QVBoxLayout()
            thumb = QLabel()
            thumb.setFixedSize(*config.DUPLICATE_COVER_THUMB_SIZE)
            thumb.setAlignment(Qt.AlignCenter)
            if cover_abs and os.path.isfile(cover_abs):
                pix = QPixmap(cover_abs).scaled(
                    config.DUPLICATE_COVER_THUMB_SIZE[0],
                    config.DUPLICATE_COVER_THUMB_SIZE[1],
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                thumb.setPixmap(pix)
            else:
                thumb.setText("なし")
            col.addWidget(thumb)
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setFixedWidth(config.DUPLICATE_COVER_THUMB_SIZE[0])
            col.addWidget(lbl)
            sub = QLabel(sub_text)
            sub.setAlignment(Qt.AlignCenter)
            sub.setFixedWidth(config.DUPLICATE_COVER_THUMB_SIZE[0])
            col.addWidget(sub)
            return col

        existing_name = existing.get("name") or existing.get("path") or "既存"
        registered_at = (existing.get("updated_at") or "")[:10]  # YYYY-MM-DD
        sub_existing = f"登録日: {registered_at}" if registered_at else ""

        thumb_row.addLayout(_make_thumb_col(existing_cover_abs, existing_name, sub_existing))
        thumb_row.addSpacing(config.DUPLICATE_COVER_THUMB_SPACING)
        thumb_row.addLayout(_make_thumb_col(new_cover_abs, new_name, "新規"))
        layout.addLayout(thumb_row)

        # ボタン行
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_new = QPushButton("別作品として登録")
        btn_cancel = QPushButton("キャンセル")

        btn_new.clicked.connect(self._on_new)
        btn_cancel.clicked.connect(self._on_cancel)

        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self.adjustSize()

    def _on_new(self) -> None:
        self.result_action = "new"
        self.accept()

    def _on_cancel(self) -> None:
        self.result_action = "cancel"
        self.reject()
