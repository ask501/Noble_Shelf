from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from PySide6.QtCore import Qt, QPoint, QRunnable
from PySide6.QtGui import QPainter, QPixmap, QWheelEvent, QMouseEvent
from PySide6.QtWidgets import QWidget

import config
from theme import VIEWER_BG

from ui.dialogs.viewer._reader import BookReader, FolderReader
from ui.dialogs.viewer._reader_utils import read_page_concurrent
from ui.dialogs.viewer._utils import _pil_to_qpixmap


# ══════════════════════════════════════════════════════════
#  ページキャンバス
# ══════════════════════════════════════════════════════════

class PageCanvas(QWidget):
    """ページ画像を描画するキャンバス"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {VIEWER_BG};")
        self._pixmap: Optional[QPixmap] = None
        self._original_pixmap: Optional[QPixmap] = None
        self._zoom   = 1.0
        self._pan    = QPoint(0, 0)
        self._last_mid = QPoint(0, 0)
        self.setMouseTracking(True)

    def set_pixmap(
        self,
        pix: Optional[QPixmap],
        original: Optional[QPixmap] = None,
        *,
        reset_view: bool = True,
    ) -> None:
        self._pixmap = pix
        self._original_pixmap = original
        if reset_view:
            self._zoom = 1.0
            self._pan = QPoint(0, 0)
        self.update()

    def paintEvent(self, _):
        src = (
            self._original_pixmap
            if self._zoom > config.VIEWER_CANVAS_ZOOM_BASE
            and self._original_pixmap is not None
            else self._pixmap
        )
        if not src:
            return
        painter = QPainter(self)
        w, h = self.width(), self.height()
        iw, ih = src.width(), src.height()
        scale = min(w / iw, h / ih) if iw > 0 and ih > 0 else 1.0
        pw = int(iw * scale * self._zoom)
        ph = int(ih * scale * self._zoom)
        x  = (w - pw) // 2 + self._pan.x()
        y  = (h - ph) // 2 + self._pan.y()
        if src is self._original_pixmap and self._original_pixmap is not None:
            scaled = src.scaled(
                pw,
                ph,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(x, y, scaled)
        else:
            painter.drawPixmap(x, y, pw, ph, src)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        old_zoom = self._zoom
        if delta > 0:
            self._zoom = min(self._zoom + 0.1, 5.0)
        else:
            self._zoom = max(self._zoom - 0.1, 1.0)
        if self._zoom == 1.0:
            self._pan = QPoint(0, 0)
        elif self._zoom != old_zoom:
            ratio = self._zoom / old_zoom
            pos = event.position()
            mx = pos.x()
            my = pos.y()
            d = config.VIEWER_CANVAS_WIDGET_CENTER_DIVISOR
            self._pan = QPoint(
                int((self._pan.x() + self.width() / d - mx) * ratio + mx - self.width() / d),
                int((self._pan.y() + self.height() / d - my) * ratio + my - self.height() / d),
            )
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            self._last_mid = event.pos()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.MiddleButton:
            delta = event.pos() - self._last_mid
            self._pan += delta
            self._last_mid = event.pos()
            self.update()

    def reset_view(self):
        self._zoom = 1.0
        self._pan  = QPoint(0, 0)
        self.update()


# ══════════════════════════════════════════════════════════
#  全画面サムネイルオーバーレイ（仮想グリッド・専用 QRunnable）
# ══════════════════════════════════════════════════════════


class _OriginalPixmapRunnable(QRunnable):
    """1P 用フル解像度 pixmap をバックグラウンド生成（完了は callback で通知）"""

    def __init__(
        self,
        reader: "BookReader",
        reader_lock: threading.Lock,
        idx: int,
        serial: int,
        serial_getter: Callable[[], int],
        callback: Callable[[int, QPixmap, int], None],
    ) -> None:
        super().__init__()
        self._reader = reader
        self._reader_lock = reader_lock
        self._idx = idx
        self._serial = serial
        self._serial_getter = serial_getter
        self._callback = callback

    def run(self) -> None:
        if self._serial_getter() != self._serial:
            return
        if self._reader is None:
            return
        try:
            if isinstance(self._reader, FolderReader):
                if self._serial_getter() != self._serial:
                    return
            else:
                with self._reader_lock:
                    if self._serial_getter() != self._serial:
                        return
            img = read_page_concurrent(
                self._reader, self._reader_lock, self._idx
            )
            pm = _pil_to_qpixmap(img)
            if self._serial_getter() == self._serial:
                self._callback(self._idx, pm, self._serial)
        except Exception:
            logging.debug(
                "[viewer] original pixmap idx=%s", self._idx, exc_info=True
            )
