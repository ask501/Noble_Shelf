"""
viewer.py - 同人誌ビューワー（PySide6版）
- フォルダ内画像 / PDF 両対応
- 1P / 2P表示
- ホイールズーム・中ボタンパン
- 下部シークバー
- 全画面
- キーボード操作（方向キー・スペースでページ送り、Escapeで全画面解除/閉じる）
"""
from __future__ import annotations
import logging
import math
import os
import threading
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QWidget, QSizePolicy, QScrollArea, QFrame,
    QStackedLayout, QGraphicsOpacityEffect,
)
from PySide6.QtCore import (
    Qt, QRect, QPoint, QSize, QEvent, QObject, Signal, QRunnable, QThreadPool, QTimer,
    QPropertyAnimation, QMetaObject, Q_ARG, Slot,
)
from PySide6.QtGui import (
    QPainter, QPixmap, QImage, QKeyEvent,
    QWheelEvent, QMouseEvent, QResizeEvent, QIcon,
    QColor, QPen, QFont, QFontMetrics,
)

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

from PIL import Image
import config
import db
import paths
from theme import (
    VIEWER_BG,
    VIEWER_TOOLBAR_BG,
    VIEWER_BTN_BG,
    VIEWER_BTN_FG,
    VIEWER_BTN_BORDER,
    VIEWER_BTN_HOVER_BG,
    VIEWER_BTN_PRESSED_BG,
    VIEWER_BTN_PRESSED_FG,
    VIEWER_TEXT_SUB,
    VIEWER_SLIDER_GROOVE_BG,
    VIEWER_THUMB_STRIP_SELECTED_BG,
    VIEWER_THUMB_STRIP_CURRENT_PAGE_BORDER,
    VIEWER_OVERLAY_HIGHLIGHT_BORDER,
    VIEWER_OVERLAY_HIGHLIGHT_BG,
    VIEWER_OVERLAY_PLACEHOLDER_BG,
    COLOR_WHITE,
    COLOR_UI_TRANSPARENT,
    apply_dark_titlebar,
)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


# ══════════════════════════════════════════════════════════
#  BookReader アダプター
# ══════════════════════════════════════════════════════════

class BookReader:
    """形式ごとの読み込みを統一するアダプター基底クラス"""

    def page_count(self) -> int:
        raise NotImplementedError

    def read_page(self, idx: int) -> Image.Image:
        raise NotImplementedError

    def close(self):
        pass

    @staticmethod
    def open(path: str) -> "BookReader":
        ext = os.path.splitext(path)[1].lower()
        if os.path.isdir(path):
            return FolderReader(path)
        elif ext == ".pdf":
            return PdfReader(path)
        else:
            raise ValueError(f"非対応形式: {ext}")


class FolderReader(BookReader):
    def __init__(self, path: str):
        self._path = path
        self._files = sorted(
            f for f in os.listdir(path)
            if f.lower().endswith(IMAGE_EXTS)
        )

    def page_count(self):
        return len(self._files)

    def read_page(self, idx: int) -> Image.Image:
        return Image.open(os.path.join(self._path, self._files[idx])).convert("RGB")


class PdfReader(BookReader):
    def __init__(self, path: str):
        if not HAS_PYMUPDF:
            raise ImportError("PyMuPDF が必要です: pip install pymupdf")
        self._doc = fitz.open(path)

    def page_count(self):
        return len(self._doc)

    def read_page(self, idx: int) -> Image.Image:
        page = self._doc[idx]
        mat  = fitz.Matrix(2.0, 2.0)
        pix  = page.get_pixmap(matrix=mat)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    def close(self):
        self._doc.close()


# ══════════════════════════════════════════════════════════
#  画像読み込みユーティリティ
# ══════════════════════════════════════════════════════════

def _pil_to_qpixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGB")
    data = img.tobytes("raw", "RGB")
    qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)


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
            with self._reader_lock:
                if self._serial_getter() != self._serial:
                    return
                if isinstance(self._reader, FolderReader):
                    img = Image.open(
                        os.path.join(self._reader._path, self._reader._files[self._idx])
                    )
                else:
                    img = self._reader.read_page(self._idx)
            img = img.convert("RGB")
            pm = _pil_to_qpixmap(img)
            if self._serial_getter() == self._serial:
                self._callback(self._idx, pm, self._serial)
        except Exception:
            logging.debug(
                "[viewer] original pixmap idx=%s", self._idx, exc_info=True
            )


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
            with self._reader_lock:
                if self._serial_getter() != self._job_serial:
                    return
                pil = self._reader.read_page(self._idx)
            pil = pil.convert("RGB")
            tw, th = (
                config.VIEWER_OVERLAY_THUMB_SIZE
                if self._is_high
                else config.VIEWER_OVERLAY_THUMB_LOW_SIZE
            )
            pil.thumbnail((tw, th), Image.Resampling.LANCZOS)
            data = pil.tobytes("raw", "RGB")
            qimg = QImage(
                data,
                pil.width,
                pil.height,
                pil.width * 3,
                QImage.Format.Format_RGB888,
            ).copy()
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
            with self._reader_lock:
                if self._serial_getter() != self._serial:
                    return
                pil = self._reader.read_page(self._idx)
            pil = pil.convert("RGB")
            tw, th = config.VIEWER_THUMB_STRIP_SIZE
            iw, ih = pil.size
            scale = min(tw / max(iw, 1), th / max(ih, 1))
            if scale < 1.0:
                nw = max(1, int(iw * scale))
                nh = max(1, int(ih * scale))
                pil = pil.resize((nw, nh), Image.Resampling.LANCZOS)
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
        self.set_selected(False)

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


# ══════════════════════════════════════════════════════════
#  ビューワー本体
# ══════════════════════════════════════════════════════════

class Viewer(QDialog):
    def __init__(self, parent, path: str):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.resize(config.VIEWER_INIT_WIDTH, config.VIEWER_INIT_HEIGHT)
        self.setWindowState(Qt.WindowMaximized)
        self.setStyleSheet(f"background: {VIEWER_BG};")
        # メインウィンドウの操作をブロックしない
        self.setWindowModality(Qt.NonModal)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self.path     = path
        self._reader: BookReader | None = None
        self.index    = 0
        self.dual     = False
        direction = db.get_setting(config.VIEWER_DIRECTION_SETTING_KEY) or config.VIEWER_DIRECTION_DEFAULT
        self.rtl = (direction == config.VIEWER_DIRECTION_DATA_RTL)

        self._reader_lock = threading.Lock()
        self._strip_gen_serial = 0
        self._thumb_pool = QThreadPool(self)
        self._thumb_pool.setMaxThreadCount(1)
        self._strip_cells: dict[int, _StripThumbCell] = {}
        self._strip_thumb_done: set[int] = set()
        self._strip_thumb_in_flight: set[int] = set()
        self._strip_pending_pixmaps: dict[int, QImage] = {}
        self._thumb_emitter = _ThumbStripEmitter(self)
        self._overlay_gen_serial = 0
        self._overlay_pool = QThreadPool(self)
        self._overlay_pool.setMaxThreadCount(2)
        self._original_gen_serial: int = 0
        self._original_cache: dict[int, QPixmap] = {}

        self._load_source(path)
        self._setup_ui()
        QTimer.singleShot(0, self._show_page)
        if parent and hasattr(parent, "_open_viewers"):
            parent._open_viewers.append(self)

    @staticmethod
    def open(path: str) -> "BookReader":
        ext = os.path.splitext(path)[1].lower()
        if os.path.isdir(path):
            # フォルダ内にPDFがあればPdfReaderで開く
            pdfs = sorted(
                f for f in os.listdir(path)
                if f.lower().endswith(".pdf")
            )
            if pdfs:
                return PdfReader(os.path.join(path, pdfs[0]))
            return FolderReader(path)
        elif ext == ".pdf":
            return PdfReader(path)
        else:
            raise ValueError(f"非対応形式: {ext}")    

    def _load_source(self, path: str):
        try:
            self._reader = BookReader.open(path)
        except Exception as e:
            self._reader = None

    @property
    def images(self) -> list:
        """page_count分のダミーリスト（後方互換用）"""
        if self._reader is None:
            return []
        return list(range(self._reader.page_count()))

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        layout.setSpacing(config.LAYOUT_SPACING_ZERO)

        # ── ツールバー（タイトルバー代わりの上端。ダブルクリックで最大化するためフィルターを付ける）
        self._toolbar = QWidget()
        self._toolbar.setFixedHeight(config.VIEWER_TOOLBAR_HEIGHT)
        self._toolbar.setStyleSheet(f"background: {VIEWER_TOOLBAR_BG};")
        tb_layout = QHBoxLayout(self._toolbar)
        tb_layout.setContentsMargins(*config.VIEWER_TOOLBAR_MARGIN)
        tb_layout.setSpacing(config.VIEWER_TOOLBAR_SPACING)

        btn_style = f"""
            QPushButton {{
                background: {VIEWER_BTN_BG}; color: {VIEWER_BTN_FG};
                border: 1px solid {VIEWER_BTN_BORDER}; border-radius: 4px;
                padding: {config.VIEWER_TOOLBAR_BTN_PADDING_Y}px {config.VIEWER_TOOLBAR_BTN_PADDING_X}px;
                font-size: {config.FONT_SIZE_VIEWER_UI}px;
            }}
            QPushButton:hover {{ background: {VIEWER_BTN_HOVER_BG}; }}
            QPushButton:pressed {{ background: {VIEWER_BTN_PRESSED_BG}; color: {VIEWER_BTN_PRESSED_FG}; }}
        """

        self._btn_1p = QPushButton("1P")
        self._btn_2p = QPushButton("2P")
        self._btn_fs = QPushButton("全画面")
        self._page_label = QLabel("")
        self._page_label.setStyleSheet(f"color: {VIEWER_TEXT_SUB}; font-size: {config.FONT_SIZE_VIEWER_UI}px;")

        for btn in (self._btn_1p, self._btn_2p, self._btn_fs):
            btn.setStyleSheet(btn_style)
            btn.setFixedHeight(config.VIEWER_TOOLBAR_BTN_HEIGHT)

        self._btn_1p.clicked.connect(self._set_single)
        self._btn_2p.clicked.connect(self._set_dual)
        self._btn_fs.clicked.connect(self._toggle_fullscreen)

        tb_layout.addWidget(self._btn_1p)
        tb_layout.addWidget(self._btn_2p)
        tb_layout.addWidget(self._page_label)
        tb_layout.addStretch()

        thumb_btn_style = btn_style + f"""
            QPushButton:checked {{
                background: {VIEWER_BTN_PRESSED_BG};
                color: {VIEWER_BTN_PRESSED_FG};
            }}
        """
        ic_sz = config.VIEWER_THUMB_STRIP_TOOLBAR_ICON_SIZE

        # 9マスグリッドアイコン → 全画面サムネオーバーレイ（thumb_strip.svg・紫トグル）
        self._btn_overlay_grid = QPushButton()
        self._btn_overlay_grid.setToolTip("全画面サムネイル")
        self._btn_overlay_grid.setStyleSheet(thumb_btn_style)
        self._btn_overlay_grid.setFixedHeight(config.VIEWER_TOOLBAR_BTN_HEIGHT)
        self._btn_overlay_grid.setCheckable(True)
        self._btn_overlay_grid.setIcon(QIcon(paths.ICON_VIEWER_OVERLAY_GRID))
        self._btn_overlay_grid.setIconSize(QSize(ic_sz, ic_sz))

        # 下段3サムネ風アイコン → 横ストリップ表示トグル（boxicons.svg）
        self._btn_thumb_strip = QPushButton()
        self._btn_thumb_strip.setToolTip("サムネイルストリップ")
        self._btn_thumb_strip.setStyleSheet(thumb_btn_style)
        self._btn_thumb_strip.setFixedHeight(config.VIEWER_TOOLBAR_BTN_HEIGHT)
        self._btn_thumb_strip.setCheckable(True)
        self._btn_thumb_strip.setIcon(QIcon(paths.ICON_VIEWER_THUMB_STRIP))
        self._btn_thumb_strip.setIconSize(QSize(ic_sz, ic_sz))

        # 左: 全画面グリッド／右: ストリップトグル
        tb_layout.addWidget(self._btn_overlay_grid)
        tb_layout.addWidget(self._btn_thumb_strip)
        tb_layout.addWidget(self._btn_fs)
        layout.addWidget(self._toolbar)
        self._toolbar.installEventFilter(self)

        # ── キャンバス + 全画面サムネオーバーレイ（StackAll で重ねる）
        self._canvas = PageCanvas()
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._canvas.mousePressEvent = self._canvas_click

        self._overlay = ThumbnailOverlay(self)

        stack_host = QWidget()
        stack_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        stack = QStackedLayout(stack_host)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        stack.setSpacing(config.LAYOUT_SPACING_ZERO)
        stack.addWidget(self._canvas)
        stack.addWidget(self._overlay)
        layout.addWidget(stack_host)

        # ── サムネイルストリップ（PageCanvas とシークバーの間・横スクロールのみ）
        self._thumb_scroll = _ThumbStripScrollArea(self)
        self._thumb_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._thumb_scroll.setWidgetResizable(False)
        self._thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._thumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._thumb_scroll.setFixedHeight(config.VIEWER_THUMB_STRIP_HEIGHT)
        self._thumb_scroll.setStyleSheet(f"background: {VIEWER_TOOLBAR_BG};")

        self._thumb_strip_inner = QWidget()
        self._thumb_strip_inner.setStyleSheet(f"background: {VIEWER_TOOLBAR_BG};")
        self._thumb_strip_inner.setFixedHeight(config.VIEWER_THUMB_STRIP_HEIGHT)
        self._thumb_scroll.setWidget(self._thumb_strip_inner)
        tsb = self._thumb_scroll.horizontalScrollBar()
        tsb.setInvertedAppearance(not self.rtl)
        tsb.setInvertedControls(not self.rtl)

        layout.addWidget(self._thumb_scroll)

        # ── シークバー
        seekbar_widget = QWidget()
        seekbar_widget.setFixedHeight(config.VIEWER_SEEKBAR_HEIGHT)
        seekbar_widget.setStyleSheet(f"background: {VIEWER_TOOLBAR_BG};")
        sb_layout = QHBoxLayout(seekbar_widget)
        sb_layout.setContentsMargins(*config.VIEWER_SEEKBAR_MARGIN)

        n = max(1, len(self.images) - 1)
        self._seekbar = QSlider(Qt.Horizontal)
        self._seekbar.setInvertedAppearance(self.rtl)
        self._seekbar.setInvertedControls(self.rtl)
        self._seekbar.setRange(0, n)
        self._seekbar.setValue(0)
        self._seekbar.valueChanged.connect(self._on_seek)
        self._seekbar.installEventFilter(self)
        self._apply_seekbar_direction_style()

        self._seek_label = QLabel("")
        self._seek_label.setStyleSheet(f"color: {VIEWER_TEXT_SUB}; font-size: {config.FONT_SIZE_VIEWER_SEEK}px;")
        self._seek_label.setFixedWidth(config.VIEWER_SEEKBAR_LABEL_WIDTH)
        self._seek_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        sb_layout.addWidget(self._seekbar)
        sb_layout.addWidget(self._seek_label)
        layout.addWidget(seekbar_widget)

        self._thumb_emitter.thumb_ready.connect(self._on_strip_thumb_ready)
        self._thumb_emitter.thumb_failed.connect(self._on_strip_thumb_failed)
        self._thumb_scroll.horizontalScrollBar().valueChanged.connect(self._thumb_strip_on_scroll)

        if not self.images:
            self._btn_overlay_grid.setEnabled(False)
            self._btn_thumb_strip.setEnabled(False)

        if self.images:
            vis_raw = db.get_setting(config.VIEWER_THUMB_STRIP_SETTING_KEY)
            strip_vis = vis_raw == "1"
            self._thumb_scroll.setVisible(strip_vis)
            self._btn_thumb_strip.blockSignals(True)
            self._btn_thumb_strip.setChecked(strip_vis)
            self._btn_thumb_strip.blockSignals(False)
            self._btn_overlay_grid.blockSignals(True)
            self._btn_overlay_grid.setChecked(False)
            self._btn_overlay_grid.blockSignals(False)
        else:
            self._thumb_scroll.setVisible(False)
            self._btn_thumb_strip.setEnabled(False)
            self._btn_thumb_strip.setChecked(False)
            self._btn_overlay_grid.setChecked(False)

        self._btn_thumb_strip.toggled.connect(self._thumb_strip_on_toggled)
        self._btn_overlay_grid.toggled.connect(self._thumb_overlay_on_toggled)

        # 初期フォーカスをキャンバスに（方向キーがシークバーに奪われないようにする）
        self._canvas.setFocusPolicy(Qt.StrongFocus)
        self._canvas.setFocus()
        self._canvas.installEventFilter(self)

    def _apply_seekbar_direction_style(self) -> None:
        """綴じ方向に応じたシークバー QSS（add-page / sub-page の色割り当て）"""
        if self.rtl:
            active_page = "add-page"
            inactive_page = "sub-page"
        else:
            active_page = "sub-page"
            inactive_page = "add-page"
        self._seekbar.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: {config.VIEWER_SLIDER_GROOVE_H}px;
                background: {VIEWER_SLIDER_GROOVE_BG};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {VIEWER_BTN_PRESSED_BG};
                width: {config.VIEWER_SLIDER_HANDLE_SIZE}px;
                height: {config.VIEWER_SLIDER_HANDLE_SIZE}px;
                border-radius: {config.VIEWER_SLIDER_HANDLE_RADIUS}px;
                margin: {config.VIEWER_SLIDER_HANDLE_MARGIN_Y}px 0;
            }}
            QSlider::{active_page}:horizontal {{
                background: {VIEWER_BTN_PRESSED_BG};
                border-radius: 2px;
            }}
            QSlider::{inactive_page}:horizontal {{
                background: {VIEWER_SLIDER_GROOVE_BG};
                border-radius: 2px;
            }}
        """)

    def _refresh_viewer_direction_from_settings(self) -> None:
        """DB の綴じ方向を再読み込みし、シークバー・ストリップスクロール・セル配置を反映する"""
        direction = db.get_setting(config.VIEWER_DIRECTION_SETTING_KEY) or config.VIEWER_DIRECTION_DEFAULT
        new_rtl = direction == config.VIEWER_DIRECTION_DATA_RTL
        if new_rtl == self.rtl:
            return
        self.rtl = new_rtl
        self._seekbar.setInvertedAppearance(self.rtl)
        self._seekbar.setInvertedControls(self.rtl)
        self._apply_seekbar_direction_style()
        tsb = self._thumb_scroll.horizontalScrollBar()
        tsb.setInvertedAppearance(not self.rtl)
        tsb.setInvertedControls(not self.rtl)
        y = (config.VIEWER_THUMB_STRIP_HEIGHT - self._strip_cell_outer_height()) // 2
        for idx, cell in self._strip_cells.items():
            cell.move(self._strip_cell_x(idx), y)
        self._thumb_strip_update_highlights()
        if self._thumb_scroll.isVisible() and self.images:
            QTimer.singleShot(0, self._thumb_strip_scroll_to_current)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.WindowActivate:
            self._refresh_viewer_direction_from_settings()
        super().changeEvent(event)

    def eventFilter(self, obj, event):
        # ツールバー（上端）ダブルクリックで最大化/元に戻す
        if event.type() == QEvent.Type.MouseButtonDblClick and obj is self._toolbar:
            if event.button() == Qt.LeftButton:
                self._toggle_maximize()
                return True
        # キャンバス・シークバーどちらにフォーカスがあっても方向キー・スペースでページ送り（現在のページから1回目で正しく反応）
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if obj is self._canvas or obj is self._seekbar:
                if self.rtl:
                    if key in (Qt.Key_Right, Qt.Key_Up):
                        self._prev()
                        return True
                    if key in (Qt.Key_Left, Qt.Key_Down, Qt.Key_Space):
                        self._next()
                        return True
                else:
                    if key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Space):
                        self._next()
                        return True
                    if key in (Qt.Key_Left, Qt.Key_Up):
                        self._prev()
                        return True
                if key == Qt.Key_Escape:
                    if self.isFullScreen():
                        self.showMaximized()
                        self._btn_fs.setText("全画面")
                    else:
                        self.close()
                    return True
        return super().eventFilter(obj, event)

    @Slot(int, QPixmap, int)
    def _on_original_ready(self, idx: int, pm: QPixmap, serial: int) -> None:
        if serial != self._original_gen_serial:
            return
        self._original_cache[idx] = pm
        if idx == self.index:
            self._canvas.set_pixmap(self._canvas._pixmap, pm, reset_view=False)

    def _schedule_original_loads(self) -> None:
        if self._reader is None or self.dual:
            return
        serial = self._original_gen_serial
        preload = config.VIEWER_ORIGINAL_PRELOAD_RADIUS_1P
        indices: list[int] = []
        for d in range(-preload, preload + 1):
            idx = self.index + d
            if 0 <= idx < len(self.images) and idx not in self._original_cache:
                indices.append(idx)
        indices.sort(key=lambda i: abs(i - self.index))
        for idx in indices:
            self._overlay_pool.start(
                _OriginalPixmapRunnable(
                    self._reader,
                    self._reader_lock,
                    idx,
                    serial,
                    lambda: self._original_gen_serial,
                    self._on_original_ready,
                )
            )

    # ── ページ表示 ────────────────────────────────────
    def _show_page(self) -> None:
        if not self.images:
            return
        self._original_gen_serial += 1
        self._original_cache.clear()
        if self.dual:
            pix, text = self._render_dual()
            self._canvas.set_pixmap(pix, None)
        else:
            pix, text = self._render_single()
            cached = self._original_cache.get(self.index)
            self._canvas.set_pixmap(pix, cached)
        self._page_label.setText(text)
        self._seek_label.setText(text)
        self._seekbar.blockSignals(True)
        self._seekbar.setValue(self.index)
        self._seekbar.blockSignals(False)
        self._thumb_strip_on_page_changed()
        self._overlay.sync_current_page(self.index)
        self._schedule_original_loads()

    def _sync_overlay_button_checked(self, on: bool) -> None:
        """全画面サムネボタンの checked をシグナルなしで合わせる（オーバーレイを別経路で閉じたとき用）"""
        self._btn_overlay_grid.blockSignals(True)
        self._btn_overlay_grid.setChecked(on)
        self._btn_overlay_grid.blockSignals(False)

    def _thumb_overlay_on_toggled(self, checked: bool) -> None:
        if not self.images:
            return
        o = self._overlay
        if checked:
            o.show_overlay()
            o.raise_()
        else:
            o._close()

    def _strip_cell_outer_width(self) -> int:
        return (
            config.VIEWER_THUMB_STRIP_SIZE[0]
            + 2 * config.VIEWER_THUMB_STRIP_INNER_MARGIN
            + 2 * config.VIEWER_THUMB_STRIP_BORDER_WIDTH
        )

    def _strip_cell_outer_height(self) -> int:
        return (
            config.VIEWER_THUMB_STRIP_SIZE[1]
            + 2 * config.VIEWER_THUMB_STRIP_INNER_MARGIN
            + 2 * config.VIEWER_THUMB_STRIP_BORDER_WIDTH
        )

    def _strip_cell_pitch(self) -> int:
        return self._strip_cell_outer_width() + config.VIEWER_THUMB_STRIP_CELL_SPACING

    def _strip_cell_x(self, idx: int) -> int:
        """綴じ方向に応じたセル左端 X。右綴じ(rtl)は先頭ページを右側に並べる。"""
        n = len(self.images)
        if n <= 0:
            return 0
        pitch = self._strip_cell_pitch()
        if self.rtl:
            return (n - 1 - idx) * pitch
        return idx * pitch

    def _thumb_strip_inner_width(self) -> int:
        n = len(self.images)
        if n <= 0:
            return 0
        return n * self._strip_cell_pitch() - config.VIEWER_THUMB_STRIP_CELL_SPACING

    def _thumb_strip_ensure_inner_size(self) -> None:
        self._thumb_strip_inner.setMinimumWidth(self._thumb_strip_inner_width())
        self._thumb_strip_inner.setFixedHeight(config.VIEWER_THUMB_STRIP_HEIGHT)

    @staticmethod
    def _thumb_strip_priority_order(center: int, n: int) -> list[int]:
        if n <= 0:
            return []
        order: list[int] = [center]
        for d in range(1, n + 1):
            for sign in (-1, 1):
                j = center + sign * d
                if 0 <= j < n:
                    order.append(j)
        return order

    def _thumb_strip_ensure_cell(self, idx: int) -> _StripThumbCell:
        if idx in self._strip_cells:
            return self._strip_cells[idx]
        cell = _StripThumbCell(self, idx, self._thumb_strip_inner)
        x = self._strip_cell_x(idx)
        y = (config.VIEWER_THUMB_STRIP_HEIGHT - self._strip_cell_outer_height()) // 2
        cell.move(x, y)
        cell.show()
        self._strip_cells[idx] = cell
        cell.set_selected(idx == self.index)
        if idx in self._strip_pending_pixmaps:
            qimg = self._strip_pending_pixmaps.pop(idx)
            cell.set_pixmap_from_image(qimg)
        return cell

    def _thumb_strip_ensure_around_index(self, center: int) -> None:
        n = len(self.images)
        if n <= 0:
            return
        rad = config.VIEWER_THUMB_STRIP_ENSURE_PAGE_RADIUS
        lo = max(0, center - rad)
        hi = min(n - 1, center + rad)
        for i in range(lo, hi + 1):
            self._thumb_strip_ensure_cell(i)

    def _thumb_strip_visible_index_range(self) -> tuple[int, int]:
        n = len(self.images)
        if n <= 0:
            return 0, 0
        ow = self._strip_cell_outer_width()
        sb = self._thumb_scroll.horizontalScrollBar()
        x0 = sb.value()
        vpw = self._thumb_scroll.viewport().width()
        x1 = x0 + vpw
        extra = config.VIEWER_THUMB_STRIP_ENSURE_PAGE_RADIUS
        lo_idx = n
        hi_idx = -1
        for idx in range(n):
            cx = self._strip_cell_x(idx)
            if cx + ow > x0 and cx < x1:
                lo_idx = min(lo_idx, idx)
                hi_idx = max(hi_idx, idx)
        if hi_idx < 0:
            return 0, n - 1
        lo = max(0, lo_idx - extra)
        hi = min(n - 1, hi_idx + extra)
        return lo, hi

    def _thumb_strip_on_scroll(self, _value: int) -> None:
        if not self._thumb_scroll.isVisible() or not self.images:
            return
        lo, hi = self._thumb_strip_visible_index_range()
        for i in range(lo, hi + 1):
            self._thumb_strip_ensure_cell(i)
        self._schedule_strip_thumbs()

    def _schedule_strip_thumbs(self) -> None:
        if not self._thumb_scroll.isVisible() or not self.images:
            return
        n = len(self.images)
        order = self._thumb_strip_priority_order(self.index, n)
        serial = self._strip_gen_serial
        for idx in order:
            if idx in self._strip_thumb_done or idx in self._strip_thumb_in_flight:
                continue
            if idx not in self._strip_cells:
                continue
            self._strip_thumb_in_flight.add(idx)
            self._thumb_pool.start(
                _ThumbStripRunnable(
                    self._reader,
                    self._reader_lock,
                    idx,
                    serial,
                    lambda: self._strip_gen_serial,
                    self._thumb_emitter,
                )
            )

    def _on_strip_thumb_ready(self, idx: int, qimg: QImage) -> None:
        self._strip_thumb_in_flight.discard(idx)
        self._strip_thumb_done.add(idx)
        if idx in self._strip_cells:
            self._strip_cells[idx].set_pixmap_from_image(qimg)
        else:
            self._strip_pending_pixmaps[idx] = qimg

    def _on_strip_thumb_failed(self, idx: int) -> None:
        self._strip_thumb_in_flight.discard(idx)

    def _thumb_strip_on_toggled(self, checked: bool) -> None:
        if not self.images:
            return
        self._thumb_scroll.setVisible(checked)
        db.set_setting(
            config.VIEWER_THUMB_STRIP_SETTING_KEY,
            "1" if checked else "0",
        )
        if checked:
            self._thumb_strip_on_first_show()

    def _thumb_strip_on_first_show(self) -> None:
        if not self.images:
            return
        self._thumb_strip_ensure_inner_size()
        self._thumb_strip_ensure_around_index(self.index)
        lo, hi = self._thumb_strip_visible_index_range()
        for i in range(lo, hi + 1):
            self._thumb_strip_ensure_cell(i)
        self._thumb_strip_update_highlights()
        self._schedule_strip_thumbs()
        QTimer.singleShot(0, self._thumb_strip_scroll_to_current)

    def _thumb_strip_on_page_changed(self) -> None:
        if not self.images:
            return
        self._thumb_strip_update_highlights()
        if not self._thumb_scroll.isVisible():
            return
        self._thumb_strip_ensure_inner_size()
        self._thumb_strip_ensure_around_index(self.index)
        self._schedule_strip_thumbs()
        QTimer.singleShot(0, self._thumb_strip_scroll_to_current)

    def _thumb_strip_update_highlights(self) -> None:
        cur = self.index
        for idx, cell in self._strip_cells.items():
            cell.set_selected(idx == cur)

    def _thumb_strip_scroll_to_current(self) -> None:
        if not self._thumb_scroll.isVisible() or not self.images:
            return
        idx = self.index
        if idx not in self._strip_cells:
            return
        cell = self._strip_cells[idx]
        m = config.VIEWER_THUMB_STRIP_SCROLL_ENSURE_MARGIN
        self._thumb_scroll.ensureWidgetVisible(cell, m, 0)
        vp_w = self._thumb_scroll.viewport().width()
        x_cell = self._strip_cell_x(idx)
        cell_w = cell.width()
        center_cell = x_cell + cell_w // 2
        sb = self._thumb_scroll.horizontalScrollBar()
        target = center_cell - vp_w // 2
        target = max(sb.minimum(), min(sb.maximum(), target))
        sb.setValue(target)

    def _get_page_pixmap(self, idx: int, canvas_w: int, canvas_h: int) -> QPixmap:
        if self._reader is None:
            return QPixmap()
        try:
            if isinstance(self._reader, FolderReader):
                path = os.path.join(self._reader._path, self._reader._files[idx])
                img = Image.open(path)
            else:
                img = self._reader.read_page(idx)

            # キャンバスサイズに収まるよう事前にLANCZOSでリサイズ
            iw, ih = img.size
            scale = min(canvas_w / iw, canvas_h / ih)
            if scale < 1.0:  # 縮小時のみ
                nw = int(iw * scale)
                nh = int(ih * scale)
                img = img.resize((nw, nh), Image.Resampling.LANCZOS)

            return _pil_to_qpixmap(img)
        except Exception:
            return QPixmap()

    def _render_single(self) -> tuple[QPixmap, str]:
        pix  = self._get_page_pixmap(self.index, self._canvas.width(), self._canvas.height())
        text = f"{self.index + 1} / {len(self.images)}"
        return pix, text

    def _render_dual(self) -> tuple[QPixmap, str]:
        if self.index + 1 >= len(self.images):
            return self._render_single()
        cw = self._canvas.width() // 2
        ch = self._canvas.height()
        p1 = self._get_page_pixmap(self.index,     cw, ch)
        p2 = self._get_page_pixmap(self.index + 1, cw, ch)
        h  = min(p1.height(), p2.height())
        p1s = p1.scaledToHeight(h, Qt.SmoothTransformation)
        p2s = p2.scaledToHeight(h, Qt.SmoothTransformation)
        combined = QPixmap(p1s.width() + p2s.width(), h)
        combined.fill(Qt.black)
        painter = QPainter(combined)
        painter.drawPixmap(0,           0, p1s)
        painter.drawPixmap(p1s.width(), 0, p2s)
        painter.end()
        end  = min(self.index + 2, len(self.images))
        text = f"{self.index + 1}-{end} / {len(self.images)}"
        return combined, text

    # ── ナビ ─────────────────────────────────────────
    def _next(self):
        step = 2 if self.dual else 1
        if self.index < len(self.images) - 1:
            self.index = min(len(self.images) - 1, self.index + step)
            self._show_page()

    def _prev(self):
        step = 2 if self.dual else 1
        if self.index > 0:
            self.index = max(0, self.index - step)
            self._show_page()

    def _set_single(self):
        self.dual = False
        self._show_page()

    def _set_dual(self):
        self.dual = True
        self._show_page()

    def _on_seek(self, value: int):
        self.index = value
        self._show_page()

    def _canvas_click(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            mid_x = self._canvas.width() // 2
            on_left = event.pos().x() < mid_x
            if self.rtl:
                if on_left:
                    self._next()
                else:
                    self._prev()
            else:
                if on_left:
                    self._prev()
                else:
                    self._next()
        elif event.button() == Qt.RightButton:
            self._prev()
        # 中ボタンはPageCanvas本来の処理に渡す
        elif event.button() == Qt.MiddleButton:
            PageCanvas.mousePressEvent(self._canvas, event)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
            self._btn_fs.setText("全画面")
        else:
            self.showFullScreen()
            self._btn_fs.setText("× 通常")

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        # タイトルバー（ツールバー上端）ダブルクリックで最大化/元に戻す
        if event.button() == Qt.LeftButton and event.pos().y() < 36:
            self._toggle_maximize()
            return
        super().mouseDoubleClickEvent(event)

    # ── キーボード（方向キー・スペースでページ送り） ─────────────────
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if self.rtl:
            if key in (Qt.Key_Right, Qt.Key_Up):
                self._prev()
                return
            if key in (Qt.Key_Left, Qt.Key_Down, Qt.Key_Space):
                self._next()
                return
        else:
            if key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Space):
                self._next()
                return
            if key in (Qt.Key_Left, Qt.Key_Up):
                self._prev()
                return
        if key == Qt.Key_Escape:
            if self.isFullScreen():
                self.showMaximized()
                self._btn_fs.setText("全画面")
            else:
                self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self._strip_gen_serial += 1
        self._overlay_gen_serial += 1
        self._thumb_pool.clear()
        self._overlay_pool.clear()
        if hasattr(self, "_overlay"):
            self._overlay._cancel_overlay_anims()
            self._overlay.hide()
        self._sync_overlay_button_checked(False)
        parent = self.parent()
        if parent and hasattr(parent, "_open_viewers") and self in parent._open_viewers:
            parent._open_viewers.remove(self)
        if self._reader:
            try:
                self._reader.close()
            except Exception as e:
                logging.debug("[viewer] リーダーclose失敗: %s", e)
        super().closeEvent(event)
