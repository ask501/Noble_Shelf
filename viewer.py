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

try:
    import py7zr
    HAS_PY7ZR = True
except ImportError:
    HAS_PY7ZR = False

try:
    import rarfile
    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False

from PIL import Image
import io
import zipfile
import config
from theme import apply_dark_titlebar

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
        elif ext in (".zip", ".cbz"):
            return ZipReader(path)
        elif ext in (".7z", ".cb7"):
            return SevenZipReader(path)
        elif ext in (".rar", ".cbr"):
            return RarReader(path)
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


class ZipReader(BookReader):
    def __init__(self, path: str):
        self._zf = zipfile.ZipFile(path, "r")
        self._files = sorted(
            n for n in self._zf.namelist()
            if os.path.splitext(n)[1].lower() in IMAGE_EXTS
            and not os.path.basename(n).startswith(".")
        )

    def page_count(self):
        return len(self._files)

    def read_page(self, idx: int) -> Image.Image:
        data = self._zf.read(self._files[idx])
        return Image.open(io.BytesIO(data)).convert("RGB")

    def close(self):
        self._zf.close()


class SevenZipReader(BookReader):
    def __init__(self, path: str):
        if not HAS_PY7ZR:
            raise ImportError("py7zr が必要です: pip install py7zr")
        self._path = path
        with py7zr.SevenZipFile(path, "r") as zf:
            self._files = sorted(
                n for n in zf.getnames()
                if os.path.splitext(n)[1].lower() in IMAGE_EXTS
            )

    def page_count(self):
        return len(self._files)

    def read_page(self, idx: int) -> Image.Image:
        with py7zr.SevenZipFile(self._path, "r") as zf:
            target = self._files[idx]
            data = zf.read([target])[target].read()
        return Image.open(io.BytesIO(data)).convert("RGB")


class RarReader(BookReader):
    def __init__(self, path: str):
        if not HAS_RARFILE:
            raise ImportError("rarfile が必要です: pip install rarfile")
        self._rf = rarfile.RarFile(path)
        self._files = sorted(
            n for n in self._rf.namelist()
            if os.path.splitext(n)[1].lower() in IMAGE_EXTS
        )

    def page_count(self):
        return len(self._files)

    def read_page(self, idx: int) -> Image.Image:
        data = self._rf.read(self._files[idx])
        return Image.open(io.BytesIO(data)).convert("RGB")

    def close(self):
        self._rf.close()


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
        self.setStyleSheet("background: #111111;")
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
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        iw, ih = self._pixmap.width(), self._pixmap.height()

        # キャンバスに収まるベースサイズを計算
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
        self.resize(900, 700)
        self.setWindowState(Qt.WindowMaximized)
        self.setStyleSheet("background: #111111;")
        # メインウィンドウの操作をブロックしない
        self.setWindowModality(Qt.NonModal)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self.path     = path
        self._reader: BookReader | None = None
        self.index    = 0
        self.dual     = False

        self._load_source(path)
        self._setup_ui()
        self._show_page()
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
        elif ext in (".zip", ".cbz"):
            return ZipReader(path)
        elif ext in (".7z", ".cb7"):
            return SevenZipReader(path)
        elif ext in (".rar", ".cbr"):
            return RarReader(path)
        elif ext == ".pdf":
            return PdfReader(path)
        else:
            raise ValueError(f"非対応形式: {ext}")    

    def _load_source(self, path: str):
        try:
            self._reader = BookReader.open(path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._reader = None

    @property
    def images(self) -> list:
        """page_count分のダミーリスト（後方互換用）"""
        if self._reader is None:
            return []
        return list(range(self._reader.page_count()))

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── ツールバー（タイトルバー代わりの上端。ダブルクリックで最大化するためフィルターを付ける）
        self._toolbar = QWidget()
        self._toolbar.setFixedHeight(36)
        self._toolbar.setStyleSheet("background: #1a1a1a;")
        tb_layout = QHBoxLayout(self._toolbar)
        tb_layout.setContentsMargins(6, 4, 6, 4)
        tb_layout.setSpacing(4)

        btn_style = f"""
            QPushButton {{
                background: #2a2a2a; color: #cccccc;
                border: 1px solid #444; border-radius: 4px;
                padding: 2px 10px; font-size: {config.FONT_SIZE_VIEWER_UI}px;
            }}
            QPushButton:hover {{ background: #3a3a3a; }}
            QPushButton:pressed {{ background: #9A7FFF; color: #fff; }}
        """

        self._btn_1p = QPushButton("1P")
        self._btn_2p = QPushButton("2P")
        self._btn_fs = QPushButton("全画面")
        self._page_label = QLabel("")
        self._page_label.setStyleSheet(f"color: #aaaaaa; font-size: {config.FONT_SIZE_VIEWER_UI}px;")

        for btn in (self._btn_1p, self._btn_2p, self._btn_fs):
            btn.setStyleSheet(btn_style)
            btn.setFixedHeight(26)

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
        seekbar_widget.setFixedHeight(32)
        seekbar_widget.setStyleSheet("background: #1a1a1a;")
        sb_layout = QHBoxLayout(seekbar_widget)
        sb_layout.setContentsMargins(10, 4, 10, 4)

        n = max(1, len(self.images) - 1)
        self._seekbar = QSlider(Qt.Horizontal)
        self._seekbar.setRange(0, n)
        self._seekbar.setValue(0)
        self._seekbar.valueChanged.connect(self._on_seek)
        self._seekbar.installEventFilter(self)
        self._seekbar.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #444; border-radius: 2px; }
            QSlider::handle:horizontal {
                background: #9A7FFF; width: 14px; height: 14px;
                border-radius: 7px; margin: -5px 0;
            }
            QSlider::sub-page:horizontal { background: #9A7FFF; border-radius: 2px; }
        """)

        self._seek_label = QLabel("")
        self._seek_label.setStyleSheet(f"color: #aaaaaa; font-size: {config.FONT_SIZE_VIEWER_SEEK}px;")
        self._seek_label.setFixedWidth(80)
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

    def _get_page_pixmap(self, idx: int) -> QPixmap:
        if self._reader is None:
            return QPixmap()
        try:
            img = self._reader.read_page(idx)
            return _pil_to_qpixmap(img)
        except Exception as e:
            return QPixmap()

    def _render_single(self) -> tuple[QPixmap, str]:
        pix  = self._get_page_pixmap(self.index)
        text = f"{self.index + 1} / {len(self.images)}"
        return pix, text

    def _render_dual(self) -> tuple[QPixmap, str]:
        if self.index + 1 >= len(self.images):
            return self._render_single()
        p1 = self._get_page_pixmap(self.index)
        p2 = self._get_page_pixmap(self.index + 1)
        h  = min(p1.height(), p2.height())
        # 同じ高さにスケール
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
            if event.pos().x() < self._canvas.width() // 2:
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
        if key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Space):
            self._next()
        elif key in (Qt.Key_Left, Qt.Key_Up):
            self._prev()
        elif key == Qt.Key_Escape:
            if self.isFullScreen():
                self.showMaximized()
                self._btn_fs.setText("全画面")
            else:
                self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        parent = self.parent()
        if parent and hasattr(parent, "_open_viewers") and self in parent._open_viewers:
            parent._open_viewers.remove(self)
        if self._reader:
            try:
                self._reader.close()
            except Exception:
                pass
        super().closeEvent(event)
