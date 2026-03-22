"""
searchbar.py - 検索バー（PySide6版）
- テキスト入力でタイトル・サークル・作者をリアルタイム絞り込み
- Ctrl+F で表示/非表示トグル
- 将来: チップUI・フィールド指定・スマートモード
"""
from __future__ import annotations
import os
import unicodedata

from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
)
from PySide6.QtCore import Qt, QRectF, QSize, Signal, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QTransform,
)

import db
import config
import paths
from theme import THEME_COLORS


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower() if s else ""


class _SearchInput(QLineEdit):
    """検索バー用QLineEdit"""
    pass


class _SearchCapsuleFrame(QFrame):
    """検索カプセル外枠。QSS の border-radius が効かない環境向けに角丸を自前描画する。"""

    def __init__(self, radius_px: int, border_px: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._radius = float(radius_px)
        self._border_px = float(border_px)
        self.setObjectName("SearchCapsule")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("")

    def _capsule_outer_path(self) -> QPainterPath:
        """カプセル外周（塗り・線・右ボタンの setClipPath と同一パス）。"""
        w, h = self.width(), self.height()
        path = QPainterPath()
        if w <= 0 or h <= 0:
            return path
        rf = QRectF(0, 0, float(w), float(h))
        rw = min(self._radius, rf.width() / 2.0, rf.height() / 2.0)
        path.addRoundedRect(rf, rw, rw)
        return path

    def paintEvent(self, event):
        path = self._capsule_outer_path()
        if path.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bw = self._border_px

        # 塗り・枠線とも _capsule_outer_path と同一パス
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(THEME_COLORS["bg_widget"])))
        painter.fillPath(path, QBrush(QColor(THEME_COLORS["bg_widget"])))

        pen = QPen(QColor(THEME_COLORS["border"]))
        pen.setWidthF(bw)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.strokePath(path, pen)


class _SearchCapsuleRightButton(QPushButton):
    """
    右端がカプセル外周に沿う検索ボタン。
    QWidget.setMask(QRegion) は多角形近似のため角がギザつく → 親マスクは使わず、
    paint 時に同一 QPainterPath で setClipPath する（アンチエイリアス付き）。
    """

    def __init__(self, capsule: _SearchCapsuleFrame):
        super().__init__(capsule)
        self._capsule = capsule
        self.setAutoFillBackground(False)
        self.setStyleSheet("")

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.update()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cap_path = self._capsule._capsule_outer_path()
        if not cap_path.isEmpty():
            local = QTransform.fromTranslate(
                -float(self.x()), -float(self.y())
            ).map(cap_path)
            painter.setClipPath(
                local, Qt.ClipOperation.IntersectClip
            )

        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        st = opt.state
        if st & QStyle.StateFlag.State_Sunken:
            bg_key = "accent_hover"
        elif st & QStyle.StateFlag.State_MouseOver:
            bg_key = "accent"
        else:
            bg_key = "hover"
        painter.fillRect(self.rect(), QColor(THEME_COLORS[bg_key]))

        if not self.icon().isNull():
            cr = self.style().subElementRect(
                QStyle.SubElement.SE_PushButtonContents, opt, self
            )
            self.icon().paint(painter, cr, Qt.AlignmentFlag.AlignCenter)


class SearchBar(QWidget):
    """検索バー本体"""

    searchChanged = Signal(str)   # 検索テキスト変更 → app.pyがフィルタリング
    cleared       = Signal()      # クリアボタン

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(config.SEARCHBAR_HEIGHT)
        # 親レイアウトで横方向に領域を確保し、内部の stretch でカプセルを中央寄せする
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        # 背景は app.py のメインツールバー側で塗る（透明のまま）
        self.setStyleSheet("")
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(config.SEARCHBAR_DEBOUNCE_MS)    # 入力後に検索発火
        self._debounce_timer.timeout.connect(self._emit_search)
        self._setup_ui()

    def _setup_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(*config.SEARCHBAR_OUTER_MARGINS)
        outer.setSpacing(config.LAYOUT_SPACING_ZERO)

        cap_h = config.SEARCHBAR_HEIGHT - config.SEARCHBAR_CAPSULE_HEIGHT_INSET
        radius = config.SEARCHBAR_CAPSULE_RADIUS
        _bw = config.BORDER_WIDTH
        _inner_h = cap_h - 2 * _bw
        _inner_r = max(0, radius - _bw)

        capsule = _SearchCapsuleFrame(radius, _bw)
        capsule.setFixedHeight(cap_h)
        capsule.setMinimumWidth(config.SEARCHBAR_CAPSULE_MIN_WIDTH)
        capsule.setMaximumWidth(config.SEARCHBAR_MAX_WIDTH)
        capsule.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        cap_layout = QHBoxLayout(capsule)
        # 枠線・角丸の内側に子を収める（子の矩形が外周角を潰さない）
        cap_layout.setContentsMargins(_bw, _bw, _bw, _bw)
        cap_layout.setSpacing(config.LAYOUT_SPACING_ZERO)

        self._input = _SearchInput()
        self._input.setFixedHeight(_inner_h)
        self._input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._input.setPlaceholderText("検索")
        self._input.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # 左はカプセル角丸に合わせる。背景は透明でカプセル塗りを透かす。
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background-color: transparent;
                color: {THEME_COLORS['text_main']};
                border: none;
                border-top-left-radius: {_inner_r}px;
                border-bottom-left-radius: {_inner_r}px;
                border-top-right-radius: 0;
                border-bottom-right-radius: 0;
                padding: {config.SEARCHBAR_INPUT_PADDING_Y}px {config.SEARCHBAR_INPUT_PADDING_X}px;
                font-size: {config.FONT_SIZE_SEARCH_INPUT}px;
            }}
            QLineEdit:focus {{
                outline: none;
            }}
        """)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._emit_search)

        self._btn_search = _SearchCapsuleRightButton(capsule)
        self._btn_search.setFixedSize(
            config.SEARCHBAR_CAPSULE_BTN_WIDTH, _inner_h
        )
        self._btn_search.setToolTip("検索を実行")
        self._btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        _search_btn_icon_path = paths.ICON_SEARCH
        if os.path.isfile(_search_btn_icon_path):
            self._btn_search.setIcon(QIcon(_search_btn_icon_path))
            self._btn_search.setIconSize(
                QSize(
                    config.SEARCHBAR_SEARCH_BTN_ICON_SIZE,
                    config.SEARCHBAR_SEARCH_BTN_ICON_SIZE,
                )
            )
        # 入力とボタンの間は直線の縦線（border-left だとカプセル角丸と相まって「(🔍」に見えやすい）
        _div_w = config.SEARCHBAR_BTN_DIVIDER_WIDTH
        divider = QWidget()
        divider.setFixedWidth(_div_w)
        divider.setFixedHeight(_inner_h)
        divider.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        divider.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        divider.setStyleSheet(
            f"background-color: {THEME_COLORS['border']}; border: none;"
        )

        # 背景・角丸は _SearchCapsuleRightButton.paintEvent（setClipPath）で描画
        self._btn_search.clicked.connect(self._emit_search)

        cap_layout.addWidget(self._input, stretch=1)
        cap_layout.addWidget(divider)
        cap_layout.addWidget(self._btn_search)

        outer.addWidget(capsule, stretch=1)
        outer.setAlignment(capsule, Qt.AlignmentFlag.AlignHCenter)

    def _on_text_changed(self, _text: str):
        self._debounce_timer.start()

    def _emit_search(self):
        self.searchChanged.emit(self._input.text())

    def clear_search(self):
        self._input.clear()
        self.cleared.emit()

    def focus_input(self):
        self._input.setFocus()
        self._input.selectAll()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.clear_search()
        else:
            super().keyPressEvent(event)


# ── 検索用haystackキャッシュ ──────────────────────────────
_haystack_cache: dict[str, str] = {}


def build_haystack_cache(books: list[dict]):
    """
    起動時・スキャン完了後に一度だけ呼ぶ。
    path → 検索用文字列のキャッシュを構築。
    """
    global _haystack_cache
    _haystack_cache = {}
    try:
        all_metas = db.get_all_book_metas()  # {path: meta_dict}
    except Exception:
        all_metas = {}

    for book in books:
        path = book.get("path", "")
        base = _nfkc(" ".join([
            book.get("title",  "") or "",
            book.get("name",   "") or "",
            book.get("circle", "") or "",
        ]))
        meta = all_metas.get(path, {})
        if meta and meta.get("author"):
            base += " " + _nfkc(meta["author"])
        _haystack_cache[path] = base


# ── フィルタリングロジック ─────────────────────────────────

def filter_books(books: list[dict], query: str) -> list[dict]:
    """
    books をクエリでフィルタリングして返す。
    キャッシュ済みhaystackを使うので高速。
    """
    if not query.strip():
        return books

    words = [_nfkc(w) for w in query.split() if w]
    if not words:
        return books

    result = []
    for book in books:
        path = book.get("path", "")
        haystack = _haystack_cache.get(path) or _nfkc(" ".join([
            book.get("title",  "") or "",
            book.get("name",   "") or "",
            book.get("circle", "") or "",
        ]))
        if all(w in haystack for w in words):
            result.append(book)

    return result
