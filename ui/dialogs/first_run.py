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
        layout.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        layout.setSpacing(config.LAYOUT_SPACING_ZERO)
        layout.addStretch()

        self._btn = QPushButton("ライブラリフォルダを設定")
        # おおよそ縦2cm×横4cm程度（96DPI想定でやや大きめに）
        self._btn.setFixedSize(*config.FIRST_RUN_SETUP_BTN_SIZE)
        self._btn.clicked.connect(self.setupClicked)

        # fallback は theme 側の既定カラーと同値（見た目維持）
        # THEME_COLORS にキーが無い場合でも、旧来の見た目を崩さないために直書きで残す
        accent = THEME_COLORS.get("accent", "#2d6a2d")
        accent_hover = THEME_COLORS.get("accent_hover", accent)
        # THEME_COLORS にキーが無い場合でも、旧来の見た目を崩さないために直書きで残す
        text_main = THEME_COLORS.get("text_main", "#ffffff")

        self._btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {accent};
                color: {text_main};
                border: none;
                border-radius: {config.FIRST_RUN_SETUP_BTN_RADIUS}px;
                font-family: {config.FONT_FAMILY};
                font-size: {config.FONT_SIZE_SORT_LABEL}px;
                padding: {config.FIRST_RUN_SETUP_BTN_PADDING[0]}px {config.FIRST_RUN_SETUP_BTN_PADDING[1]}px;
            }}
            QPushButton:hover {{
                background-color: {accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {accent};
                opacity: {config.FIRST_RUN_SETUP_BTN_PRESSED_OPACITY};
            }}
            """
        )

        layout.addWidget(self._btn, 0, Qt.AlignHCenter)
        layout.addStretch()

