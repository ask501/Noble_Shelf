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

from ui.dialogs.viewer._reader import BookReader, FolderReader, PdfReader, IMAGE_EXTS
from ui.dialogs.viewer._reader_utils import read_page_concurrent
from ui.dialogs.viewer._utils import _pil_to_qpixmap
from ui.dialogs.viewer._canvas import PageCanvas, _OriginalPixmapRunnable
from ui.dialogs.viewer._overlay import ThumbnailOverlay, _OverlayThumbRunnable
from ui.dialogs.viewer._strip import (
    _ThumbStripScrollArea, _ThumbStripEmitter,
    _ThumbStripRunnable, _StripThumbCell,
)


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
        self._overlay_pool.setMaxThreadCount(config.VIEWER_OVERLAY_POOL_MAX_THREADS)
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

        btn_br = config.VIEWER_TOOLBAR_BTN_BORDER_RADIUS
        btn_style = f"""
            QPushButton {{
                background: {VIEWER_BTN_BG}; color: {VIEWER_BTN_FG};
                border: 1px solid {VIEWER_BTN_BORDER}; border-radius: {btn_br}px;
                padding: {config.VIEWER_TOOLBAR_BTN_PADDING_Y}px {config.VIEWER_TOOLBAR_BTN_PADDING_X}px;
                font-size: {config.FONT_SIZE_VIEWER_UI}px;
            }}
            QPushButton:hover {{ background: {VIEWER_BTN_HOVER_BG}; }}
            QPushButton:pressed {{ background: {VIEWER_BTN_PRESSED_BG}; color: {VIEWER_BTN_PRESSED_FG}; }}
        """

        self._btn_dual = QPushButton()
        self._btn_dual.setCheckable(True)
        self._btn_dual.setChecked(self.dual)
        self._btn_dual.setIcon(QIcon(paths.ICON_VIEWER_2P))
        ic_dual = config.VIEWER_TOOLBAR_ICON_SIZE
        self._btn_dual.setIconSize(QSize(ic_dual, ic_dual))
        self._btn_dual.setToolTip(config.VIEWER_TOOLTIP_2P_MODE)
        dual_btn_style = f"""
            QPushButton {{
                background: {VIEWER_BTN_BG}; color: {VIEWER_BTN_FG};
                border: 1px solid {VIEWER_BTN_BORDER}; border-radius: {btn_br}px;
                padding: {config.VIEWER_TOOLBAR_BTN_PADDING_Y}px {config.VIEWER_TOOLBAR_BTN_PADDING_X}px;
            }}
            QPushButton:hover {{ background: {VIEWER_BTN_HOVER_BG}; }}
            QPushButton:pressed {{ background: {VIEWER_BTN_PRESSED_BG}; color: {VIEWER_BTN_PRESSED_FG}; }}
            QPushButton:checked {{ background: {VIEWER_BTN_PRESSED_BG}; color: {VIEWER_BTN_PRESSED_FG}; }}
        """
        self._btn_dual.setStyleSheet(dual_btn_style)
        self._btn_dual.setFixedHeight(config.VIEWER_TOOLBAR_BTN_HEIGHT)
        self._btn_dual.toggled.connect(self._on_dual_toggled)

        self._btn_page_offset = QPushButton()
        self._btn_page_offset.setCheckable(False)
        self._btn_page_offset.setIcon(QIcon(paths.ICON_VIEWER_NEXT_PAGE))
        self._btn_page_offset.setIconSize(QSize(ic_dual, ic_dual))
        self._btn_page_offset.setToolTip(config.VIEWER_TOOLTIP_PAGE_OFFSET)
        self._btn_page_offset.setStyleSheet(dual_btn_style)
        self._btn_page_offset.setFixedHeight(config.VIEWER_TOOLBAR_BTN_HEIGHT)
        self._btn_page_offset.setVisible(True)
        self._btn_page_offset.clicked.connect(self._on_page_offset_clicked)

        self._btn_fs = QPushButton("全画面")
        self._page_label = QLabel("")
        self._page_label.setVisible(False)
        self._page_label.setStyleSheet(f"color: {VIEWER_TEXT_SUB}; font-size: {config.FONT_SIZE_VIEWER_UI}px;")

        self._btn_fs.setStyleSheet(btn_style)
        self._btn_fs.setFixedHeight(config.VIEWER_TOOLBAR_BTN_HEIGHT)

        self._btn_fs.clicked.connect(self._toggle_fullscreen)

        tb_layout.addWidget(self._btn_dual)
        tb_layout.addWidget(self._btn_page_offset)
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
        tsb.setInvertedAppearance(False)
        tsb.setInvertedControls(self.rtl)

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
            if strip_vis:
                QTimer.singleShot(0, self._thumb_strip_on_first_show)
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
        tsb.setInvertedAppearance(False)
        tsb.setInvertedControls(self.rtl)
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
            + config.VIEWER_THUMB_STRIP_PAGE_LABEL_HEIGHT
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
        vp_w = self._thumb_scroll.viewport().width()
        x_cell = self._strip_cell_x(idx)
        cell_w = cell.width()
        center_cell = x_cell + cell_w // 2
        sb = self._thumb_scroll.horizontalScrollBar()
        target = center_cell - vp_w // 2
        target = max(sb.minimum(), min(sb.maximum(), target))
        sb.setValue(target)
        QTimer.singleShot(0, self._schedule_strip_thumbs)

    def _get_page_pixmap(self, idx: int, canvas_w: int, canvas_h: int) -> QPixmap:
        if self._reader is None:
            return QPixmap()
        try:
            if isinstance(self._reader, FolderReader):
                img = read_page_concurrent(self._reader, self._reader_lock, idx)
            else:
                with self._reader_lock:
                    img = read_page_concurrent(self._reader, self._reader_lock, idx)

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
        base = self.index
        if base + 1 >= len(self.images):
            return self._render_single()
        cw = self._canvas.width() // 2
        ch = self._canvas.height()
        if self.rtl:
            left_idx = base + 1
            right_idx = base
        else:
            left_idx = base
            right_idx = base + 1
        p1 = self._get_page_pixmap(left_idx, cw, ch)
        p2 = self._get_page_pixmap(right_idx, cw, ch)
        h  = min(p1.height(), p2.height())
        p1s = p1.scaledToHeight(h, Qt.SmoothTransformation)
        p2s = p2.scaledToHeight(h, Qt.SmoothTransformation)
        combined = QPixmap(p1s.width() + p2s.width(), h)
        combined.fill(Qt.black)
        painter = QPainter(combined)
        painter.drawPixmap(0,           0, p1s)
        painter.drawPixmap(p1s.width(), 0, p2s)
        painter.end()
        end = min(base + 2, len(self.images))
        if self.rtl:
            text = f"{base + 1}-{end} / {len(self.images)}"
        else:
            text = f"{end} - {base + 1} / {len(self.images)}"
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

    def _on_dual_toggled(self, checked: bool) -> None:
        if checked:
            self._set_dual()
        else:
            self._set_single()

    def _on_page_offset_clicked(self) -> None:
        step = config.VIEWER_SINGLE_PAGE_STEP
        if self.index + step < len(self.images):
            self.index += step
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
