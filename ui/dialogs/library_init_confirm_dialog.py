"""
library_init_confirm_dialog.py - ライブラリ初期化前の整理内容確認ダイアログ
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import config
from theme import apply_dark_titlebar
from scanners import SCANNERS


class LibraryInitConfirmDialog(QDialog):
    """
    scan_for_organize() の結果を受け取り、移動内容をユーザーに提示する。
    OK → accepted、キャンセル → rejected。
    """

    def __init__(self, folder: str, scan_result: dict, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.LIBRARY_INIT_CONFIRM_DIALOG_TITLE)
        self.setMinimumSize(*config.LIBRARY_INIT_CONFIRM_DIALOG_MIN_SIZE)
        self.resize(*config.LIBRARY_INIT_CONFIRM_DIALOG_SIZE)

        root = QVBoxLayout(self)
        root.setContentsMargins(*config.THUMB_CROP_LAYOUT_MARGINS)
        root.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)

        # ヘッダー
        header = QLabel(config.LIBRARY_INIT_CONFIRM_HEADER.format(folder=folder))
        header.setWordWrap(True)
        root.addWidget(header)

        # スクロールエリア
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        layout.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)
        scroll.setWidget(container)
        root.addWidget(scroll)

        by_type = scan_result.get("by_type") or {}
        skipped = scan_result.get("skipped") or []
        has_content = False

        # メディアタイプごとのセクション（by_typeをループ → 将来のスキャナ追加に自動対応）
        for media_type, scanner_cls in SCANNERS.items():
            info = by_type.get(media_type)
            if not info:
                continue
            targets = info.get("targets") or []
            dest = info.get("dest") or ""
            if not targets:
                continue
            has_content = True

            display_name = getattr(scanner_cls, "display_name_ja", "") or media_type

            section_label = QLabel(
                f"【{config.LIBRARY_INIT_CONFIRM_SECTION_MOVE}】"
                f" {display_name} → {os.path.basename(dest)}/"
            )
            section_label.setWordWrap(True)
            layout.addWidget(section_label)

            for path in targets:
                name = os.path.basename(path)
                suffix = "/" if os.path.isdir(path) else ""
                lbl = QLabel(f"　{name}{suffix}")
                lbl.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
                )
                layout.addWidget(lbl)

        # 整理対象外セクション
        if skipped:
            has_content = True
            layout.addWidget(QLabel(f"【{config.LIBRARY_INIT_CONFIRM_SECTION_SKIP}】"))
            for path in skipped:
                name = os.path.basename(path)
                suffix = "/" if os.path.isdir(path) else ""
                lbl = QLabel(f"　{name}{suffix}")
                lbl.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
                )
                layout.addWidget(lbl)

        if not has_content:
            layout.addWidget(QLabel(config.LIBRARY_INIT_CONFIRM_EMPTY))

        layout.addStretch()

        # ボタン
        buttons = QDialogButtonBox()
        buttons.addButton(
            config.LIBRARY_INIT_CONFIRM_BTN_OK,
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        buttons.addButton(
            config.LIBRARY_INIT_CONFIRM_BTN_CANCEL,
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
