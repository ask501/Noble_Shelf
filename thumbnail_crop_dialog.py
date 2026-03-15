"""
thumbnail_crop_dialog.py - サムネイル切り抜きダイアログ（QGraphicsView）
- 画像を表示し、中央の赤枠（カード比）が切り抜き範囲
- ホイールでズーム・ドラッグでパン。スクロールバーで端まで移動可能
"""
from __future__ import annotations

import os
import hashlib

from PySide6.QtCore import Qt, QRectF, QRect, QTimer
from PySide6.QtGui import QPixmap, QWheelEvent, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
)

import config
from theme import apply_dark_titlebar

CROP_ASPECT_W = getattr(config, "CARD_WIDTH_BASE", 150)
CROP_ASPECT_H = getattr(config, "CARD_HEIGHT_BASE", 220)


def _download_image(url: str) -> QPixmap | None:
    """URLから画像をダウンロードしてQPixmapで返す"""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as res:
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
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setBackgroundBrush(self.palette().color(self.backgroundRole()))
        self._zoom = 1.0

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
        painter = QPainter(self.viewport())
        painter.setPen(QPen(QColor(255, 80, 80), 2, Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)
        painter.end()

    def wheelEvent(self, event: QWheelEvent):
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else 1 / 1.15
        self._zoom *= factor
        self._zoom = max(0.2, min(10.0, self._zoom))
        self.scale(factor, factor)

    def _image_scene_rect(self) -> QRectF:
        """シーン上の画像矩形（scene の sceneRect）"""
        if not self.scene():
            return QRectF()
        return self.scene().sceneRect()

    def fit_image_to_crop_frame(self):
        """画像を赤枠に収まるように表示"""
        frame_vp = self._crop_frame_viewport_rect()
        if frame_vp.width() <= 0 or frame_vp.height() <= 0:
            return
        r = self._image_scene_rect()
        if r.isEmpty():
            return
        sx = frame_vp.width() / r.width()
        sy = frame_vp.height() / r.height()
        scale = min(sx, sy)
        self.resetTransform()
        self._zoom = scale
        self.scale(scale, scale)
        self.centerOn(r.center())

    def fit_height_to_crop_frame(self):
        """画像の高さを赤枠の高さに合わせる"""
        frame_vp = self._crop_frame_viewport_rect()
        if frame_vp.height() <= 0:
            return
        r = self._image_scene_rect()
        if r.isEmpty() or r.height() <= 0:
            return
        scale = max(0.2, min(10.0, frame_vp.height() / r.height()))
        self.resetTransform()
        self._zoom = scale
        self.scale(scale, scale)
        self.centerOn(r.center())

    def fit_width_to_crop_frame(self):
        """画像の幅を赤枠の幅に合わせる"""
        frame_vp = self._crop_frame_viewport_rect()
        if frame_vp.width() <= 0:
            return
        r = self._image_scene_rect()
        if r.isEmpty() or r.width() <= 0:
            return
        scale = max(0.2, min(10.0, frame_vp.width() / r.width()))
        self.resetTransform()
        self._zoom = scale
        self.scale(scale, scale)
        self.centerOn(r.center())


class ThumbnailCropDialog(QDialog):
    """画像を表示し、赤枠内を切り抜きして保存"""

    def __init__(self, image_source: str, book_path: str, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.setMinimumSize(640, 480)
        self.resize(800, 600)

        self._book_path = book_path
        self._source_path_or_url = image_source
        self._pixmap: QPixmap | None = None
        self.result_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl = QLabel("赤枠がカードの表示比率です。ホイールで拡大縮小・ドラッグで位置を調整し、「切り抜き」で赤枠内を保存します。")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: #aaa; font-size: {config.FONT_SIZE_PROP_HINT}px;")
        layout.addWidget(lbl)

        self._scene = QGraphicsScene(self)
        self._view = CropGraphicsView(self)
        self._view.setScene(self._scene)
        self._view.setStyleSheet("background: #1a1a1a; border-radius: 4px;")
        layout.addWidget(self._view)

        btn_row = QHBoxLayout()
        btn_fit_h = QPushButton("縦フィット")
        btn_fit_h.setStyleSheet("color: #aaa;")
        btn_fit_h.setToolTip("画像の高さを赤枠の高さに合わせます")
        btn_fit_h.clicked.connect(self._view.fit_height_to_crop_frame)
        btn_fit_w = QPushButton("横フィット")
        btn_fit_w.setStyleSheet("color: #aaa;")
        btn_fit_w.setToolTip("画像の幅を赤枠の幅に合わせます")
        btn_fit_w.clicked.connect(self._view.fit_width_to_crop_frame)
        btn_row.addWidget(btn_fit_h)
        btn_row.addWidget(btn_fit_w)
        btn_row.addStretch()
        btn_crop = QPushButton("切り抜き")
        btn_crop.setStyleSheet("""
            QPushButton { background: #2d6a2d; color: #fff; border: 1px solid #3a8a3a; border-radius: 4px; padding: 6px 16px; }
            QPushButton:hover { background: #3a8a3a; }
        """)
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setStyleSheet("color: #aaa;")
        btn_crop.clicked.connect(self._do_crop)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_crop)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self._load_image()

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
        item = QGraphicsPixmapItem(self._pixmap)
        self._scene.addItem(item)
        self._scene.setSceneRect(QRectF(self._pixmap.rect()))
        self._view._zoom = 1.0
        QTimer.singleShot(50, self._view.fit_image_to_crop_frame)

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
        if not cropped.save(out_path, "JPEG", quality=90):
            self.reject()
            return
        self.result_path = out_path
        self.accept()
