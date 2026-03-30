from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel

import config
from theme import THEME_COLORS


class ToastWidget(QLabel):
    def __init__(self, parent, message: str, on_click=None):
        super().__init__(message, parent)
        self._on_click = on_click
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor if on_click else Qt.ArrowCursor)
        self.setStyleSheet(
            f"""
            background-color: {THEME_COLORS['accent']};
            color: {THEME_COLORS['text_main']};
            border-radius: {config.TOAST_BORDER_RADIUS}px;
            padding: {config.TOAST_PADDING_Y}px {config.TOAST_PADDING_X}px;
            font-size: {config.FONT_SIZE_TOAST}px;
        """
        )
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        QTimer.singleShot(config.TOAST_DURATION_MS, self.deleteLater)

    def _reposition(self):
        if not self.parent():
            return
        pw = self.parent().width()
        ph = self.parent().height()
        x = pw - self.width() - config.TOAST_MARGIN_RIGHT
        y = ph - self.height() - config.TOAST_MARGIN_BOTTOM
        self.move(x, y)

    def mousePressEvent(self, event):
        if self._on_click:
            self._on_click()
        try:
            self.deleteLater()
        except RuntimeError:
            pass
