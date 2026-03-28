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
import os
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QWidget, QSizePolicy
)
from PySide6.QtCore import Qt, QRect, QPoint, QSize, QEvent
from PySide6.QtGui import (
    QPainter, QPixmap, QImage, QKeyEvent,
    QWheelEvent, QMouseEvent, QResizeEvent,
)

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

from PIL import Image
import config
import db
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
        self._zoom   = 1.0
        self._pan    = QPoint(0, 0)
        self._last_mid = QPoint(0, 0)
        self.setMouseTracking(True)

    def set_pixmap(self, pix: Optional[QPixmap]):
        self._pixmap = pix
        self._zoom   = 1.0
        self._pan    = QPoint(0, 0)
        self.update()

    def paintEvent(self, _):
        if not self._pixmap:
            return
        painter = QPainter(self)
        w, h = self.width(), self.height()
        iw, ih = self._pixmap.width(), self._pixmap.height()
        scale = min(w / iw, h / ih) if iw > 0 and ih > 0 else 1.0
        pw = int(iw * scale * self._zoom)
        ph = int(ih * scale * self._zoom)
        x  = (w - pw) // 2 + self._pan.x()
        y  = (h - ph) // 2 + self._pan.y()
        painter.drawPixmap(x, y, pw, ph, self._pixmap)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom = min(self._zoom + 0.1, 5.0)
        else:
            self._zoom = max(self._zoom - 0.1, 1.0)
            if self._zoom == 1.0:
                self._pan = QPoint(0, 0)
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

        self._load_source(path)
        self._setup_ui()
        from PySide6.QtCore import QTimer
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
        tb_layout.addWidget(self._btn_fs)
        layout.addWidget(self._toolbar)
        self._toolbar.installEventFilter(self)

        # ── キャンバス
        self._canvas = PageCanvas()
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 左クリック→次、右クリック→前
        self._canvas.mousePressEvent = self._canvas_click
        layout.addWidget(self._canvas)

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

        self._seek_label = QLabel("")
        self._seek_label.setStyleSheet(f"color: {VIEWER_TEXT_SUB}; font-size: {config.FONT_SIZE_VIEWER_SEEK}px;")
        self._seek_label.setFixedWidth(config.VIEWER_SEEKBAR_LABEL_WIDTH)
        self._seek_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        sb_layout.addWidget(self._seekbar)
        sb_layout.addWidget(self._seek_label)
        layout.addWidget(seekbar_widget)

        # 初期フォーカスをキャンバスに（方向キーがシークバーに奪われないようにする）
        self._canvas.setFocusPolicy(Qt.StrongFocus)
        self._canvas.setFocus()
        self._canvas.installEventFilter(self)

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

    # ── ページ表示 ────────────────────────────────────
    def _show_page(self):
        if not self.images:
            return
        if self.dual:
            pix, text = self._render_dual()
        else:
            pix, text = self._render_single()

        self._canvas.set_pixmap(pix)
        self._page_label.setText(text)
        self._seek_label.setText(text)
        self._seekbar.blockSignals(True)
        self._seekbar.setValue(self.index)
        self._seekbar.blockSignals(False)

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
                img = img.resize((nw, nh), Image.BICUBIC)

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
        parent = self.parent()
        if parent and hasattr(parent, "_open_viewers") and self in parent._open_viewers:
            parent._open_viewers.remove(self)
        if self._reader:
            try:
                self._reader.close()
            except Exception as e:
                logging.debug("[viewer] リーダーclose失敗: %s", e)
        super().closeEvent(event)
