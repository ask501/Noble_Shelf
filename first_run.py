"""
first_run.py - 初回起動用オーバーレイ

ライブラリフォルダが未設定のときに、グリッド中央に
「ライブラリフォルダを設定」ボタンを出すための薄いウィジェット。
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PySide6.QtCore import Qt, Signal

import config
from theme import THEME_COLORS


class LibrarySetupOverlay(QWidget):
    """ライブラリ未設定時に中央に表示するボタンだけのオーバーレイ。"""

    setupClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()

        self._btn = QPushButton("ライブラリフォルダを設定")
        # おおよそ縦2cm×横4cm程度（96DPI想定でやや大きめに）
        self._btn.setFixedSize(180, 80)
        self._btn.clicked.connect(self.setupClicked)

        accent = THEME_COLORS.get("accent", "#2d6a2d")
        accent_hover = THEME_COLORS.get("accent_hover", accent)
        text_main = THEME_COLORS.get("text_main", "#ffffff")

        self._btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {accent};
                color: {text_main};
                border: none;
                border-radius: 16px;
                font-family: {config.FONT_FAMILY};
                font-size: {config.FONT_SIZE_SORT_LABEL}px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {accent};
                opacity: 0.9;
            }}
            """
        )

        layout.addWidget(self._btn, 0, Qt.AlignHCenter)
        layout.addStretch()

