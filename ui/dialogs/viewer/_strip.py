from __future__ import annotations

import logging
import threading
from typing import Callable

from PySide6.QtCore import Qt, QObject, QRunnable, Signal, QSize
from PySide6.QtGui import QImage, QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from PIL import Image
import config
from theme import (
    VIEWER_THUMB_STRIP_CURRENT_PAGE_BORDER,
    VIEWER_THUMB_STRIP_SELECTED_BG,
    VIEWER_TEXT_SUB,
    VIEWER_OVERLAY_PLACEHOLDER_BG,
    COLOR_UI_TRANSPARENT,
)

from ui.dialogs.viewer._reader import BookReader, FolderReader
from ui.dialogs.viewer._reader_utils import read_page_concurrent


# ══════════════════════════════════════════════════════════
#  サムネイルストリップ（バックグラウンド生成・遅延セル）
# ══════════════════════════════════════════════════════════


class _ThumbStripScrollArea(QScrollArea):
    """縦ホイールで横方向のみスクロール（ページ送りはしない）"""

    def __init__(self, viewer: "Viewer") -> None:
        super().__init__(viewer)
        self._viewer = viewer

    def wheelEvent(self, event: QWheelEvent) -> None:
        dy = event.angleDelta().y()
        if dy != 0:
            sb = self.horizontalScrollBar()
            notch = config.VIEWER_THUMB_STRIP_WHEEL_ANGLE_PER_NOTCH
            notches = dy // notch if notch else 0
            if notches == 0:
                notches = 1 if dy > 0 else -1
            step = config.VIEWER_THUMB_STRIP_WHEEL_HSCROLL_STEP
            # 上回転（正）→左へ、下回転（負）→右へ
            sb.setValue(sb.value() - notches * step)
            event.accept()
            return
        super().wheelEvent(event)


class _ThumbStripEmitter(QObject):
    """ワーカーからメインスレッドへサムネ QImage を渡す"""

    thumb_ready = Signal(int, QImage)
    thumb_failed = Signal(int)


class _ThumbStripRunnable(QRunnable):
    """read_page でサムネ用 QImage を生成（QThreadPool で実行）"""

    def __init__(
        self,
        reader: "BookReader",
        reader_lock: threading.Lock,
        idx: int,
        serial: int,
        serial_getter: Callable[[], int],
        emitter: "_ThumbStripEmitter",
    ) -> None:
        super().__init__()
        self._reader = reader
        self._reader_lock = reader_lock
        self._idx = idx
        self._serial = serial
        self._serial_getter = serial_getter
        self._emitter = emitter

    def run(self) -> None:
        if self._reader is None:
            self._emitter.thumb_failed.emit(self._idx)
            return
        try:
            if isinstance(self._reader, FolderReader):
                if self._serial_getter() != self._serial:
                    return
            else:
                with self._reader_lock:
                    if self._serial_getter() != self._serial:
                        return
            pil = read_page_concurrent(
                self._reader, self._reader_lock, self._idx
            )
            tw, th = config.VIEWER_THUMB_STRIP_SIZE
            pil.thumbnail((tw, th), Image.Resampling.BILINEAR)
            data = pil.tobytes("raw", "RGB")
            qimg = QImage(
                data,
                pil.width,
                pil.height,
                pil.width * 3,
                QImage.Format.Format_RGB888,
            ).copy()
            if self._serial_getter() == self._serial:
                self._emitter.thumb_ready.emit(self._idx, qimg)
        except Exception:
            logging.debug("[viewer] thumb strip idx=%s", self._idx, exc_info=True)
            if self._serial_getter() == self._serial:
                self._emitter.thumb_failed.emit(self._idx)


class _StripThumbCell(QWidget):
    """1ページ分のサムネ枠（クリックでジャンプ）"""

    def __init__(self, viewer: "Viewer", idx: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._viewer = viewer
        self._idx = idx
        ow = viewer._strip_cell_outer_width()
        oh = viewer._strip_cell_outer_height()
        self.setFixedSize(ow, oh)
        self.setObjectName("StripThumbCellRoot")
        self._thumb_label: QLabel | None = None
        lay = QVBoxLayout(self)
        # 枠(border)＋サムネ周りの内側余白（QLabel は VIEWER_THUMB_STRIP_SIZE 固定でこの内側に収める）
        m = config.VIEWER_THUMB_STRIP_BORDER_WIDTH + config.VIEWER_THUMB_STRIP_INNER_MARGIN
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(config.LAYOUT_SPACING_ZERO)
        self._page_label = QLabel(str(idx + 1))
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setFixedHeight(config.VIEWER_THUMB_STRIP_PAGE_LABEL_HEIGHT)
        fs = config.VIEWER_THUMB_STRIP_PAGE_LABEL_FONT_SIZE
        self._page_label.setStyleSheet(
            f"color: {VIEWER_TEXT_SUB}; background: transparent; font-size: {fs}px;"
        )
        self.set_selected(False)
        lbl = self._ensure_label()
        r = config.VIEWER_THUMB_STRIP_PLACEHOLDER_BORDER_RADIUS
        lbl.setStyleSheet(
            f"background: {VIEWER_OVERLAY_PLACEHOLDER_BG}; border-radius: {r}px;"
        )
        lay.addWidget(self._page_label)

    def _ensure_label(self) -> QLabel:
        if self._thumb_label is None:
            self._thumb_label = QLabel()
            self._thumb_label.setFixedSize(*config.VIEWER_THUMB_STRIP_SIZE)
            self._thumb_label.setStyleSheet(
                f"background: {COLOR_UI_TRANSPARENT};"
            )
            self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout().addWidget(self._thumb_label, 0, Qt.AlignmentFlag.AlignCenter)
        return self._thumb_label

    def set_pixmap_from_image(self, qimg: QImage) -> None:
        lbl = self._ensure_label()
        pm = QPixmap.fromImage(qimg).scaled(
            QSize(*config.VIEWER_THUMB_STRIP_SIZE),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        lbl.setPixmap(pm)

    def set_selected(self, on: bool) -> None:
        bw = config.VIEWER_THUMB_STRIP_BORDER_WIDTH
        r = config.VIEWER_THUMB_STRIP_BORDER_RADIUS
        if on:
            self.setStyleSheet(
                f"QWidget#StripThumbCellRoot {{ border: {bw}px solid {VIEWER_THUMB_STRIP_CURRENT_PAGE_BORDER}; "
                f"background-color: {VIEWER_THUMB_STRIP_SELECTED_BG}; "
                f"border-radius: {r}px; }}"
            )
        else:
            self.setStyleSheet(
                f"QWidget#StripThumbCellRoot {{ border: {bw}px solid {COLOR_UI_TRANSPARENT}; "
                f"background-color: {COLOR_UI_TRANSPARENT}; "
                f"border-radius: {r}px; }}"
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._viewer.index = self._idx
            self._viewer._show_page()
        else:
            super().mousePressEvent(event)
