from __future__ import annotations

import logging
import math
import threading
import time
from typing import Callable

from PySide6.QtCore import (
    Qt, QRect, QPoint, QSize, QRunnable, QTimer,
    QMetaObject, Q_ARG, Slot, QPropertyAnimation,
)
from PySide6.QtGui import (
    QPainter, QPixmap, QImage, QMouseEvent,
    QFont, QFontMetrics, QPen, QColor,
    QWheelEvent, QResizeEvent, QKeyEvent,
)
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect

import cv2
import numpy as np

import config
from theme import (
    VIEWER_OVERLAY_HIGHLIGHT_BORDER,
    VIEWER_OVERLAY_HIGHLIGHT_BG,
    VIEWER_OVERLAY_PLACEHOLDER_BG,
    COLOR_WHITE,
)
from ui.dialogs.viewer._reader import BookReader, FolderReader
from ui.dialogs.viewer._reader_utils import read_page_concurrent


class _OverlayThumbRunnable(QRunnable):
    """オーバーレイ用サムネ生成（read_page・メインへ QMetaObject.invokeMethod）"""

    def __init__(
        self,
        reader: "BookReader",
        reader_lock: threading.Lock,
        idx: int,
        is_high: bool,
        job_serial: int,
        serial_getter: Callable[[], int],
        overlay: "ThumbnailOverlay",
    ) -> None:
        super().__init__()
        self._reader = reader
        self._reader_lock = reader_lock
        self._idx = idx
        self._is_high = is_high
        self._job_serial = job_serial
        self._serial_getter = serial_getter
        self._overlay = overlay

    def run(self) -> None:
        if self._serial_getter() != self._job_serial:
            return
        if self._reader is None:
            QMetaObject.invokeMethod(
                self._overlay,
                "_on_thumb_failed",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(int, self._idx),
                Q_ARG(bool, self._is_high),
                Q_ARG(int, self._job_serial),
            )
            return
        try:
            if isinstance(self._reader, FolderReader):
                if self._serial_getter() != self._job_serial:
                    return
            else:
                with self._reader_lock:
                    if self._serial_getter() != self._job_serial:
                        return
            pil = read_page_concurrent(
                self._reader, self._reader_lock, self._idx
            )
            tw, th = (
                config.VIEWER_OVERLAY_THUMB_SIZE
                if self._is_high
                else config.VIEWER_OVERLAY_THUMB_LOW_SIZE
            )
            arr_in = np.asarray(pil)
            h_orig, w_orig = int(arr_in.shape[0]), int(arr_in.shape[1])
            scale = min(tw / w_orig, th / h_orig)
            bpp = config.VIEWER_OVERLAY_THUMB_RGB_BYTES_PER_PIXEL
            new_w = max(1, int(w_orig * scale))
            new_h = max(1, int(h_orig * scale))
            arr = cv2.resize(
                arr_in,
                (new_w, new_h),
                interpolation=config.VIEWER_OVERLAY_THUMB_CV2_INTERPOLATION,
            )
            arr = np.ascontiguousarray(arr, dtype=np.uint8)
            stride = new_w * bpp
            qimg = QImage(
                arr.data,
                new_w,
                new_h,
                stride,
                QImage.Format.Format_RGB888,
            ).copy()
            # 外部バッファ参照の QImage を copy() で複製し、arr が GC されても安全にする
            pm = QPixmap.fromImage(qimg)
            if self._serial_getter() == self._job_serial:
                QMetaObject.invokeMethod(
                    self._overlay,
                    "_on_thumb_ready",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(int, self._idx),
                    Q_ARG(QPixmap, pm),
                    Q_ARG(bool, self._is_high),
                    Q_ARG(int, self._job_serial),
                )
        except Exception:
            logging.debug(
                "[viewer] overlay thumb idx=%s high=%s",
                self._idx,
                self._is_high,
                exc_info=True,
            )
            if self._serial_getter() == self._job_serial:
                QMetaObject.invokeMethod(
                    self._overlay,
                    "_on_thumb_failed",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(int, self._idx),
                    Q_ARG(bool, self._is_high),
                    Q_ARG(int, self._job_serial),
                )


class ThumbnailOverlay(QWidget):
    """PageCanvas 上に重ねる全画面サムネグリッド（paintEvent で可視セルのみ描画）"""

    def __init__(self, viewer: "Viewer") -> None:
        super().__init__()
        self._viewer = viewer
        self._thumb_low: dict[int, QPixmap] = {}
        self._thumb_high: dict[int, QPixmap] = {}
        self._loading: set[int] = set()
        self._high_res_done: set[int] = set()
        self._scroll_y: int = 0
        self._cols: int = 1
        self._count: int = 0
        self._hover_idx: int = -1
        self._current: int = 0
        self._num_pixmap_cache: dict[int, QPixmap] = {}
        self._fade_in_anim: QPropertyAnimation | None = None
        self._fade_out_anim: QPropertyAnimation | None = None
        self._press_pos: QPoint | None = None

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.hide()

        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._schedule_overlay_loads)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._on_preview_debounce_fire)
        self._preview_pending_idx: int = -1

    def _cancel_overlay_anims(self) -> None:
        for anim in (self._fade_in_anim, self._fade_out_anim):
            if anim is not None and anim.state() == QPropertyAnimation.State.Running:
                anim.stop()

    def show_overlay(self) -> None:
        """オーバーレイを開く（スクロール初期位置・フェードイン・読み込みキュー）"""
        _t0 = time.perf_counter()
        try:
            self._cancel_overlay_anims()
            self._count = len(self._viewer.images)
            if self._count <= 0:
                self._viewer._sync_overlay_button_checked(False)
                return
            self._current = self._viewer.index
            tw, th = config.VIEWER_OVERLAY_THUMB_SIZE
            gap = config.VIEWER_OVERLAY_THUMB_GAP
            self._cols = max(1, self.width() // (tw + gap))
            row_h = th + gap
            index_row = self._current // self._cols
            target = index_row * row_h - self.height() // 2
            self._scroll_y = max(0, min(target, self._max_scroll()))

            self.setEnabled(True)
            self.show()
            self._opacity_effect.setOpacity(0.0)
            anim = QPropertyAnimation(self._opacity_effect, b"opacity")
            anim.setDuration(config.VIEWER_OVERLAY_FADE_IN_MS)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.start()
            self._fade_in_anim = anim
            self.setFocus()
            self.update()
            self._schedule_overlay_loads()
        finally:
            logging.debug(
                "[perf:new] show_overlay elapsed=%.3fs",
                time.perf_counter() - _t0,
            )

    def _close(self) -> None:
        if (
            self._fade_out_anim is not None
            and self._fade_out_anim.state() == QPropertyAnimation.State.Running
        ):
            return
        self._cancel_overlay_anims()
        self._viewer._sync_overlay_button_checked(False)
        self._viewer._overlay_gen_serial += 1
        self._preview_timer.stop()
        self._preview_pending_idx = -1
        self.setEnabled(False)
        anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        anim.setDuration(config.VIEWER_OVERLAY_FADE_OUT_MS)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self._on_fade_out_finished)
        anim.start()
        self._fade_out_anim = anim

    def _on_fade_out_finished(self) -> None:
        self.hide()
        self.setEnabled(True)
        self._viewer._canvas.setFocus()

    def sync_current_page(self, idx: int) -> None:
        """ビューワーのページ変更に追随（オーバーレイ表示中のみ）"""
        if not self.isVisible():
            return
        self._current = idx
        self.update()

    def _max_scroll(self) -> int:
        thumb_h = config.VIEWER_OVERLAY_THUMB_SIZE[1]
        gap = config.VIEWER_OVERLAY_THUMB_GAP
        rows = math.ceil(self._count / max(1, self._cols))
        content_h = rows * (thumb_h + gap)
        return max(0, content_h - self.height())

    def _idx_to_rect(self, idx: int) -> QRect:
        thumb_w, thumb_h = config.VIEWER_OVERLAY_THUMB_SIZE
        gap = config.VIEWER_OVERLAY_THUMB_GAP
        col = idx % self._cols
        row = idx // self._cols
        x = col * (thumb_w + gap)
        y = row * (thumb_h + gap) - self._scroll_y
        return QRect(x, y, thumb_w, thumb_h)

    def _pos_to_idx(self, pos: QPoint) -> int:
        thumb_w, thumb_h = config.VIEWER_OVERLAY_THUMB_SIZE
        gap = config.VIEWER_OVERLAY_THUMB_GAP
        col = pos.x() // (thumb_w + gap)
        if col < 0 or col >= self._cols:
            return -1
        row = (pos.y() + self._scroll_y) // (thumb_h + gap)
        if row < 0:
            return -1
        idx = row * self._cols + col
        if idx < 0 or idx >= self._count:
            return -1
        # ギャップ帯のクリックは背景扱い
        lx = pos.x() - col * (thumb_w + gap)
        ly = (pos.y() + self._scroll_y) - row * (thumb_h + gap)
        if lx > thumb_w or ly > thumb_h:
            return -1
        return idx

    def _get_num_pixmap(self, idx: int) -> QPixmap:
        if idx in self._num_pixmap_cache:
            return self._num_pixmap_cache[idx]
        text = str(idx + 1)
        pad = 4
        f = QFont(config.FONT_FAMILY, config.VIEWER_OVERLAY_PAGE_NUM_FONT_SIZE)
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(text) + pad * 2
        th = fm.height() + pad
        pm = QPixmap(max(1, tw), max(1, th))
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setFont(f)
        p.setPen(QColor(COLOR_WHITE))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, text)
        p.end()
        self._num_pixmap_cache[idx] = pm
        return pm

    def _overlay_priority_indices(self) -> list[int]:
        thumb_w, thumb_h = config.VIEWER_OVERLAY_THUMB_SIZE
        gap = config.VIEWER_OVERLAY_THUMB_GAP
        cell_h = thumb_h + gap
        cols = max(1, self._cols)
        row_current = self._current // cols
        first_row = max(0, self._scroll_y // cell_h)
        last_row = (self._scroll_y + self.height()) // cell_h + 1
        preload = config.VIEWER_OVERLAY_PRELOAD_ROWS
        seen: set[int] = set()
        out: list[int] = []

        for c in range(cols):
            idx = row_current * cols + c
            if 0 <= idx < self._count and idx not in seen:
                seen.add(idx)
                out.append(idx)

        for r in range(first_row, last_row + 1):
            for c in range(cols):
                idx = r * cols + c
                if 0 <= idx < self._count and idx not in seen:
                    seen.add(idx)
                    out.append(idx)

        for dr in range(1, preload + 1):
            for r in (first_row - dr, last_row + dr):
                if r < 0:
                    continue
                for c in range(cols):
                    idx = r * cols + c
                    if 0 <= idx < self._count and idx not in seen:
                        seen.add(idx)
                        out.append(idx)

        for idx in range(self._count):
            if idx not in seen:
                out.append(idx)
        return out

    def _throttled_reload(self) -> None:
        if self._scroll_timer.isActive():
            return
        self._scroll_timer.start(config.VIEWER_OVERLAY_SCROLL_THROTTLE_MS)

    def _schedule_overlay_loads(self) -> None:
        if not self.isVisible() or self._count <= 0:
            return
        job_serial = self._viewer._overlay_gen_serial
        started = 0
        batch = config.VIEWER_OVERLAY_SCHEDULE_BATCH
        for idx in self._overlay_priority_indices():
            if started >= batch:
                break
            if idx in self._loading:
                continue
            if idx not in self._thumb_low:
                self._loading.add(idx)
                self._viewer._overlay_pool.start(
                    _OverlayThumbRunnable(
                        self._viewer._reader,
                        self._viewer._reader_lock,
                        idx,
                        False,
                        job_serial,
                        lambda: self._viewer._overlay_gen_serial,
                        self,
                    )
                )
                started += 1
            elif idx not in self._high_res_done:
                self._loading.add(idx)
                self._viewer._overlay_pool.start(
                    _OverlayThumbRunnable(
                        self._viewer._reader,
                        self._viewer._reader_lock,
                        idx,
                        True,
                        job_serial,
                        lambda: self._viewer._overlay_gen_serial,
                        self,
                    )
                )
                started += 1

    @Slot(int, QPixmap, bool, int)
    def _on_thumb_ready(self, idx: int, pix: QPixmap, is_high: bool, job_serial: int) -> None:
        if job_serial != self._viewer._overlay_gen_serial:
            return
        self._loading.discard(idx)
        if is_high:
            if idx in self._high_res_done:
                return
            self._thumb_high[idx] = pix
            self._high_res_done.add(idx)
        else:
            self._thumb_low[idx] = pix
        self.update(self._idx_to_rect(idx))
        self._schedule_overlay_loads()

    @Slot(int, bool, int)
    def _on_thumb_failed(self, idx: int, is_high: bool, job_serial: int) -> None:
        if job_serial != self._viewer._overlay_gen_serial:
            return
        self._loading.discard(idx)
        self._schedule_overlay_loads()

    def _on_preview_debounce_fire(self) -> None:
        idx = self._preview_pending_idx
        self._preview_pending_idx = -1
        if idx < 0:
            return
        self._viewer.index = idx
        self._viewer._show_page()
        self._current = idx

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, config.VIEWER_OVERLAY_BG_ALPHA))

        if self._count <= 0:
            return

        thumb_w, thumb_h = config.VIEWER_OVERLAY_THUMB_SIZE
        gap = config.VIEWER_OVERLAY_THUMB_GAP
        cell_h = thumb_h + gap
        first_row = max(0, self._scroll_y // cell_h)
        last_row = (self._scroll_y + self.height()) // cell_h + 1
        cols = max(1, self._cols)
        start = first_row * cols
        end = min(self._count, (last_row + 1) * cols)

        ph = QColor(VIEWER_OVERLAY_PLACEHOLDER_BG)
        hb = QColor(VIEWER_OVERLAY_HIGHLIGHT_BG)
        hp = QPen(QColor(VIEWER_OVERLAY_HIGHLIGHT_BORDER))
        hp.setWidth(config.VIEWER_OVERLAY_BORDER_WIDTH)

        for idx in range(start, end):
            rect = self._idx_to_rect(idx)
            if not rect.intersects(self.rect()):
                continue
            if idx == self._current:
                painter.fillRect(rect, hb)
            pm = self._thumb_high.get(idx) or self._thumb_low.get(idx)
            if pm is not None and not pm.isNull():
                scaled = pm.scaled(
                    QSize(thumb_w, thumb_h),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                dx = rect.x() + (thumb_w - scaled.width()) // 2
                dy = rect.y() + (thumb_h - scaled.height()) // 2
                painter.drawPixmap(dx, dy, scaled)
            else:
                painter.fillRect(rect, ph)
            if idx == self._current:
                painter.setPen(hp)
                painter.drawRect(rect.adjusted(1, 1, -1, -1))
            npm = self._get_num_pixmap(idx)
            painter.drawPixmap(
                rect.right() - npm.width(),
                rect.bottom() - npm.height(),
                npm,
            )

    def wheelEvent(self, event: QWheelEvent) -> None:
        div = max(1, config.VIEWER_OVERLAY_WHEEL_DIVISOR)
        self._scroll_y -= event.angleDelta().y() // div
        self._scroll_y = max(0, min(self._scroll_y, self._max_scroll()))
        self.update()
        self._throttled_reload()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        tw, th = config.VIEWER_OVERLAY_THUMB_SIZE
        gap = config.VIEWER_OVERLAY_THUMB_GAP
        self._cols = max(1, self.width() // (tw + gap))
        self._scroll_y = min(self._scroll_y, self._max_scroll())
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._press_pos is not None:
            release_pos = event.pos()
            if (
                (release_pos - self._press_pos).manhattanLength()
                > config.DRAG_THRESHOLD_PX
            ):
                self._press_pos = None
                super().mouseReleaseEvent(event)
                return
            idx = self._pos_to_idx(release_pos)
            self._press_pos = None
            if idx == -1:
                self._close()
                super().mouseReleaseEvent(event)
                return
            self._preview_pending_idx = idx
            self._preview_timer.start(config.VIEWER_OVERLAY_PREVIEW_DEBOUNCE_MS)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._preview_timer.stop()
        self._preview_pending_idx = -1
        self._close()
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        idx = self._pos_to_idx(event.pos())
        if idx != self._hover_idx:
            self._hover_idx = idx
        new_shape = (
            Qt.CursorShape.PointingHandCursor
            if idx >= 0
            else Qt.CursorShape.ArrowCursor
        )
        if self.cursor().shape() != new_shape:
            self.setCursor(new_shape)
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self._close()
            return
        super().keyPressEvent(event)
