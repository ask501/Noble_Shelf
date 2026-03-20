"""
thumbnail_crop_dialog.py - サムネイル切り抜きダイアログ（QGraphicsView）
- 画像を表示し、中央の赤枠（カード比）が切り抜き範囲
- ホイールでズーム・ドラッグでパン。スクロールバーで端まで移動可能
"""
from __future__ import annotations

import os
import hashlib

from PySide6.QtCore import Qt, QRectF, QRect, QTimer
from PySide6.QtGui import QPixmap, QWheelEvent, QPainter, QPen, QColor, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QSlider,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
)

import config
from theme import (
    apply_dark_titlebar,
    COLOR_WHITE,
    THUMB_CROP_HINT_FG,
    THUMB_CROP_VIEW_BG,
    THUMB_CROP_BTN_FG,
    THUMB_CROP_FRAME_COLOR,
    THUMB_CROP_FRAME_PEN_W,
    THUMB_CROP_BTN_CROP_BG,
    THUMB_CROP_BTN_CROP_BORDER,
    THUMB_CROP_BTN_CROP_PAD_Y,
    THUMB_CROP_BTN_CROP_PAD_X,
    THUMB_CROP_OVERLAY_COLOR,
    THUMB_CROP_BTN_LOCK_ON_BG,
    THUMB_CROP_BTN_LOCK_ON_FG,
)

CROP_ASPECT_W = getattr(config, "CARD_WIDTH_BASE", 150)
CROP_ASPECT_H = getattr(config, "CARD_HEIGHT_BASE", 220)


def _download_image(url: str) -> QPixmap | None:
    """URLから画像をダウンロードしてQPixmapで返す"""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=config.THUMB_CROP_DOWNLOAD_TIMEOUT_SEC) as res:
            data = res.read()
        pix = QPixmap()
        if not pix.loadFromData(data):
            return None
        return pix
    except Exception:
        return None


class CropGraphicsView(QGraphicsView):
    """ズーム・パン可能。中央にカード比の赤枠をオーバーレイ。シーン＝画像のみでスクロールは端まで可。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(self.palette().color(self.backgroundRole()))
        self._zoom = 1.0
        self._lock_horizontal = False
        self.set_horizontal_lock(False)

    def _crop_frame_viewport_rect(self) -> QRect:
        """ビューポート上でカード比の赤枠（中央）の矩形"""
        vp = self.viewport().rect()
        vw, vh = vp.width(), vp.height()
        if vw <= 0 or vh <= 0:
            return vp
        frame_aspect = CROP_ASPECT_W / CROP_ASPECT_H
        view_aspect = vw / vh
        if view_aspect >= frame_aspect:
            fh = vh
            fw = int(fh * frame_aspect)
        else:
            fw = vw
            fh = int(fw / frame_aspect)
        x = (vw - fw) // 2
        y = (vh - fh) // 2
        return QRect(x, y, fw, fh)

    def paintEvent(self, event):
        super().paintEvent(event)
        r = self._crop_frame_viewport_rect()
        if r.width() <= 0 or r.height() <= 0:
            return
        vp = self.viewport().rect()
        vw, vh = vp.width(), vp.height()
        painter = QPainter(self.viewport())
        overlay = QColor(*THUMB_CROP_OVERLAY_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(overlay)
        painter.drawRect(QRect(0, 0, vw, r.top()))
        painter.drawRect(QRect(0, r.bottom(), vw, vh - r.bottom()))
        painter.drawRect(QRect(0, r.top(), r.left(), r.height()))
        painter.drawRect(QRect(r.right(), r.top(), vw - r.right(), r.height()))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(*THUMB_CROP_FRAME_COLOR), THUMB_CROP_FRAME_PEN_W, Qt.PenStyle.SolidLine))
        painter.drawRect(r)
        painter.end()

    def set_horizontal_lock(self, locked: bool) -> None:
        self._lock_horizontal = locked
        cursor = (
            Qt.CursorShape.SizeHorCursor if locked else Qt.CursorShape.OpenHandCursor
        )
        self.viewport().setCursor(cursor)
        if locked:
            r = self._image_scene_rect()
            if not r.isEmpty():
                current_x = self.mapToScene(self.viewport().rect().center()).x()
                self.centerOn(current_x, r.center().y())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last_pos = event.position().toPoint()
            cursor = (
                Qt.CursorShape.SizeHorCursor
                if self._lock_horizontal
                else Qt.CursorShape.ClosedHandCursor
            )
            self.viewport().setCursor(cursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(
            self, "_drag_last_pos"
        ):
            delta = event.position().toPoint() - self._drag_last_pos
            self._drag_last_pos = event.position().toPoint()
            if self._lock_horizontal:
                delta.setY(0)
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            cursor = (
                Qt.CursorShape.SizeHorCursor
                if self._lock_horizontal
                else Qt.CursorShape.OpenHandCursor
            )
            self.viewport().setCursor(cursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        angle = event.angleDelta().y()
        zf = config.THUMB_CROP_WHEEL_ZOOM_FACTOR
        factor = zf if angle > 0 else 1 / zf
        self._zoom *= factor
        self._zoom = max(
            config.THUMB_CROP_ZOOM_MIN,
            min(config.THUMB_CROP_ZOOM_MAX, self._zoom),
        )
        self.scale(factor, factor)
        if self._lock_horizontal:
            r = self._image_scene_rect()
            if not r.isEmpty():
                self.centerOn(r.center().x(), r.center().y())
        p = self.parent()
        if p is not None and hasattr(p, "_zoom_slider"):
            p._zoom_slider.blockSignals(True)
            p._zoom_slider.setValue(int(self._zoom * 1000))
            p._zoom_slider.blockSignals(False)

    def _image_scene_rect(self) -> QRectF:
        """画像アイテムのシーン座標矩形（原点基準・余白は含まない）"""
        sc = self.scene()
        if not sc:
            return QRectF()
        for it in sc.items():
            if isinstance(it, QGraphicsPixmapItem):
                return it.sceneBoundingRect()
        return QRectF()

    def fit_image_to_crop_frame(self, img_w: int, img_h: int) -> None:
        """画像を赤枠に収まるように表示"""
        frame_vp = self._crop_frame_viewport_rect()
        if frame_vp.width() <= 0 or frame_vp.height() <= 0 or img_w <= 0 or img_h <= 0:
            return
        scale = min(frame_vp.width() / img_w, frame_vp.height() / img_h)
        scale = max(
            config.THUMB_CROP_ZOOM_MIN,
            min(config.THUMB_CROP_ZOOM_MAX, scale),
        )
        self.resetTransform()
        self._zoom = scale
        self.scale(scale, scale)
        r = self._image_scene_rect()
        QTimer.singleShot(0, lambda: self.centerOn(r.center()))

    def fit_height_to_viewport(self, img_h: int) -> None:
        """画像の高さをビューポートの高さに合わせる"""
        vh = self.viewport().rect().height()
        if vh <= 0 or img_h <= 0:
            return
        scale = max(
            config.THUMB_CROP_ZOOM_MIN,
            min(config.THUMB_CROP_ZOOM_MAX, vh / img_h),
        )
        self.resetTransform()
        self._zoom = scale
        self.scale(scale, scale)
        r = self._image_scene_rect()
        QTimer.singleShot(0, lambda: self.centerOn(r.center()))

    def fit_width_to_crop_frame(self, img_w: int) -> None:
        frame_vp = self._crop_frame_viewport_rect()
        vp = self.viewport().rect()
        if frame_vp.width() <= 0 or img_w <= 0:
            return
        scale = max(
            config.THUMB_CROP_ZOOM_MIN,
            min(config.THUMB_CROP_ZOOM_MAX, frame_vp.width() / img_w),
        )
        self.resetTransform()
        self._zoom = scale
        self.scale(scale, scale)
        # scaleの確定を待たずに直接centerOnを呼ぶ
        r = self._image_scene_rect()
        self.centerOn(r.center())


class ThumbnailCropDialog(QDialog):
    """画像を表示し、赤枠内を切り抜きして保存"""

    def __init__(self, image_source: str, book_path: str, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.setMinimumSize(*config.THUMB_CROP_DIALOG_MIN_SIZE)
        self.resize(*config.THUMB_CROP_DIALOG_SIZE)

        self._book_path = book_path
        self._source_path_or_url = image_source
        self._pixmap: QPixmap | None = None
        self.result_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*config.THUMB_CROP_LAYOUT_MARGINS)
        layout.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)

        lbl = QLabel("赤枠がカードの表示比率です。ホイールで拡大縮小・ドラッグで位置を調整し、「切り抜き」で赤枠内を保存します。")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {THUMB_CROP_HINT_FG}; font-size: {config.FONT_SIZE_PROP_HINT}px;")
        layout.addWidget(lbl)

        self._scene = QGraphicsScene(self)
        self._view = CropGraphicsView(self)
        self._view.setScene(self._scene)
        self._view.setStyleSheet(f"background: {THUMB_CROP_VIEW_BG}; border-radius: {config.PROP_ACTION_BTN_RADIUS}px;")
        layout.addWidget(self._view)
        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setMinimum(int(config.THUMB_CROP_ZOOM_MIN * 1000))
        self._zoom_slider.setMaximum(int(config.THUMB_CROP_ZOOM_MAX * 1000))
        self._zoom_slider.setValue(int(self._view._zoom * 1000))
        self._zoom_slider.setToolTip("ズーム")
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        layout.addWidget(self._zoom_slider)

        btn_row = QHBoxLayout()
        btn_fit_h = QPushButton("縦フィット")
        btn_fit_h.setStyleSheet(f"color: {THUMB_CROP_BTN_FG};")
        btn_fit_h.setToolTip("画像の高さをビューに合わせます")
        btn_fit_h.clicked.connect(
            lambda: self._view.fit_height_to_viewport(self._pixmap.height())
            if self._pixmap
            else None
        )
        btn_fit_w = QPushButton("横フィット")
        btn_fit_w.setStyleSheet(f"color: {THUMB_CROP_BTN_FG};")
        btn_fit_w.setToolTip("画像の幅を赤枠の幅に合わせます")
        btn_fit_w.clicked.connect(
            lambda: self._view.fit_width_to_crop_frame(self._pixmap.width())
            if self._pixmap
            else None
        )
        btn_row.addWidget(btn_fit_h)
        btn_row.addWidget(btn_fit_w)
        self._btn_lock = QPushButton("横固定")
        self._btn_lock.setCheckable(True)
        self._btn_lock.setStyleSheet(f"color: {THUMB_CROP_BTN_FG};")
        self._btn_lock.toggled.connect(self._on_lock_toggled)
        btn_row.addWidget(self._btn_lock)
        btn_row.addStretch()
        btn_crop = QPushButton("切り抜き")
        btn_crop.setStyleSheet(
            f"""
            QPushButton {{ background: {THUMB_CROP_BTN_CROP_BG}; color: {COLOR_WHITE}; border: 1px solid {THUMB_CROP_BTN_CROP_BORDER}; border-radius: {config.PROP_ACTION_BTN_RADIUS}px; padding: {THUMB_CROP_BTN_CROP_PAD_Y}px {THUMB_CROP_BTN_CROP_PAD_X}px; }}
            QPushButton:hover {{ background: {THUMB_CROP_BTN_CROP_BORDER}; }}
        """
        )
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setStyleSheet(f"color: {THUMB_CROP_BTN_FG};")
        btn_crop.clicked.connect(self._do_crop)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_crop)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self._load_image()

    def _on_lock_toggled(self, checked: bool) -> None:
        self._view.set_horizontal_lock(checked)
        if checked:
            self._btn_lock.setStyleSheet(
                f"QPushButton {{ background: {THUMB_CROP_BTN_LOCK_ON_BG}; color: {THUMB_CROP_BTN_LOCK_ON_FG}; "
                f"border-radius: {config.PROP_ACTION_BTN_RADIUS}px; "
                f"padding: {THUMB_CROP_BTN_CROP_PAD_Y}px {THUMB_CROP_BTN_CROP_PAD_X}px; }}"
            )
        else:
            self._btn_lock.setStyleSheet(f"color: {THUMB_CROP_BTN_FG};")

    def _on_zoom_slider_changed(self, value: int) -> None:
        scale = value / 1000.0
        current_x = self._view.mapToScene(self._view.viewport().rect().center()).x()
        self._view.resetTransform()
        self._view._zoom = scale
        self._view.scale(scale, scale)
        r = self._view._image_scene_rect()
        if not r.isEmpty():
            self._view.centerOn(current_x, r.center().y())

    def _load_image(self):
        source = self._source_path_or_url
        if not source:
            return
        if source.startswith("http://") or source.startswith("https://"):
            self._pixmap = _download_image(source)
        else:
            self._pixmap = QPixmap(source) if os.path.isfile(source) else None
        if self._pixmap is None or self._pixmap.isNull():
            return
        self._scene.clear()
        margin_x = self._pixmap.width()
        margin_y = self._pixmap.height()
        self._scene.setSceneRect(
            -margin_x,
            -margin_y,
            self._pixmap.width() + margin_x * 2,
            self._pixmap.height() + margin_y * 2,
        )
        item = QGraphicsPixmapItem(self._pixmap)
        self._scene.addItem(item)
        self._view._zoom = 1.0
        QTimer.singleShot(config.THUMB_CROP_FIT_DELAY_MS, self._apply_initial_image_fit)

    def _apply_initial_image_fit(self) -> None:
        """読み込み直後：長辺をビューに合わせる初期表示"""
        if self._pixmap is None or self._pixmap.isNull():
            return
        w, h = self._pixmap.width(), self._pixmap.height()
        if w > h:
            self._view.fit_width_to_crop_frame(w)
        else:
            self._view.fit_height_to_viewport(h)
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(int(self._view._zoom * 1000))
        self._zoom_slider.blockSignals(False)

    def _do_crop(self):
        if self._pixmap is None or self._pixmap.isNull():
            self.reject()
            return
        # 赤枠のビューポート矩形をシーン座標に変換して切り抜き範囲に
        frame_vp = self._view._crop_frame_viewport_rect()
        top_left = self._view.mapToScene(frame_vp.topLeft())
        bottom_right = self._view.mapToScene(frame_vp.bottomRight())
        x1 = max(0, min(top_left.x(), bottom_right.x()))
        y1 = max(0, min(top_left.y(), bottom_right.y()))
        x2 = min(self._pixmap.width(), max(top_left.x(), bottom_right.x()))
        y2 = min(self._pixmap.height(), max(top_left.y(), bottom_right.y()))
        if x2 <= x1 or y2 <= y1:
            self.reject()
            return
        cropped = self._pixmap.copy(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
        if cropped.isNull():
            self.reject()
            return
        cover_dir = config.COVER_CACHE_DIR
        os.makedirs(cover_dir, exist_ok=True)
        key = hashlib.md5(self._book_path.encode()).hexdigest()
        out_path = os.path.join(cover_dir, f"{key}_custom.jpg")
        if not cropped.save(out_path, "JPEG", quality=config.THUMB_CROP_JPEG_QUALITY):
            self.reject()
            return
        self.result_path = out_path
        self.accept()
