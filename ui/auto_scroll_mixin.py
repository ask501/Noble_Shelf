from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QListWidget

import config


def _apply_dead_zone(value: int | float, zone: int) -> float:
    """デッドゾーンを適用した有効な差分を返す。"""
    if zone <= 0:
        return float(value)
    if value > zone:
        return float(value - zone)
    if value < -zone:
        return float(value + zone)
    return 0.0


class AutoScrollMixin:
    """中クリックオートスクロールMixin。"""

    def _init_auto_scroll(self):
        self._auto_scroll_active = False
        self._auto_scroll_origin = QPoint()
        self._auto_scroll_dx = 0
        self._auto_scroll_dy = 0
        self._auto_scroll_press_pos = None
        self._auto_scroll_timer = QTimer(self)
        self._auto_scroll_timer.setInterval(config.AUTO_SCROLL_TIMER_MS)
        self._auto_scroll_timer.timeout.connect(self._on_auto_scroll_tick)

        self._auto_scroll_pixmap = None
        icon_path = os.path.join(config.APP_BASE, "assets", "auto_scroll.png")
        pix = QPixmap(icon_path)
        if not pix.isNull():
            self._auto_scroll_pixmap = pix.scaled(
                config.AUTO_SCROLL_ICON_SIZE,
                config.AUTO_SCROLL_ICON_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

    def _start_auto_scroll(self, origin: QPoint):
        self._auto_scroll_active = True
        self._auto_scroll_origin = origin
        self._auto_scroll_dx = 0
        self._auto_scroll_dy = 0
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._auto_scroll_timer.start()
        self.viewport().update()

    def _stop_auto_scroll(self):
        print("[DEBUG] _stop_auto_scroll called")
        self._auto_scroll_active = False
        self._auto_scroll_timer.stop()
        self.unsetCursor()
        self.viewport().update()
        print(f"[DEBUG] after stop: active={self._auto_scroll_active}, timer={self._auto_scroll_timer.isActive()}")

    def _on_auto_scroll_tick(self):
        if not self._auto_scroll_active:
            return

        zone = config.AUTO_SCROLL_DEAD_ZONE
        max_speed = config.AUTO_SCROLL_MAX_SPEED

        eff_dx = _apply_dead_zone(self._auto_scroll_dx, zone)
        eff_dy = _apply_dead_zone(self._auto_scroll_dy, zone)
        if eff_dx == 0 and eff_dy == 0:
            return

        denom = zone * 4
        speed_x = (eff_dx / denom) * max_speed if denom else 0
        speed_y = (eff_dy / denom) * max_speed if denom else 0
        speed_x = max(-max_speed, min(max_speed, speed_x))
        speed_y = max(-max_speed, min(max_speed, speed_y))

        vbar = self.verticalScrollBar()
        hbar = self.horizontalScrollBar()
        if vbar is not None:
            vbar.setValue(vbar.value() + int(speed_y))
        if hbar is not None:
            hbar.setValue(hbar.value() + int(speed_x))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._auto_scroll_press_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            if self._auto_scroll_press_pos is not None:
                current = event.globalPosition().toPoint()
                dx = abs(current.x() - self._auto_scroll_press_pos.x())
                dy = abs(current.y() - self._auto_scroll_press_pos.y())
                th = config.AUTO_SCROLL_DRAG_THRESHOLD
                if dx >= th or dy >= th:
                    self._stop_auto_scroll()
                else:
                    if self._auto_scroll_active:
                        self._stop_auto_scroll()
                    else:
                        self._start_auto_scroll(self._auto_scroll_press_pos)
                self._auto_scroll_press_pos = None
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self._auto_scroll_active:
            cur = event.globalPosition().toPoint()
            self._auto_scroll_dx = cur.x() - self._auto_scroll_origin.x()
            self._auto_scroll_dy = cur.y() - self._auto_scroll_origin.y()
        elif self._auto_scroll_press_pos is not None:
            current = event.globalPosition().toPoint()
            dx = abs(current.x() - self._auto_scroll_press_pos.x())
            dy = abs(current.y() - self._auto_scroll_press_pos.y())
            th = config.AUTO_SCROLL_DRAG_THRESHOLD
            if dx >= th or dy >= th:
                self._start_auto_scroll(self._auto_scroll_press_pos)
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._auto_scroll_active:
            self._stop_auto_scroll()
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if self._auto_scroll_active:
            self._stop_auto_scroll()
        super().focusOutEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._auto_scroll_active:
            return
        if self._auto_scroll_pixmap is None:
            return

        vp = self.viewport()
        origin_in_viewport = vp.mapFromGlobal(self._auto_scroll_origin)
        pw = self._auto_scroll_pixmap.width()
        ph = self._auto_scroll_pixmap.height()
        draw_x = origin_in_viewport.x() - pw // 2
        draw_y = origin_in_viewport.y() - ph // 2

        painter = QPainter(self.viewport())
        painter.drawPixmap(draw_x, draw_y, self._auto_scroll_pixmap)
        painter.end()


class AutoScrollListWidget(AutoScrollMixin, QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_auto_scroll()
