"""
searchbar.py - 検索バー（PySide6版）
- テキスト入力でタイトル・サークル・作者をリアルタイム絞り込み
- Ctrl+F で表示/非表示トグル
- 将来: チップUI・フィールド指定・スマートモード
"""
from __future__ import annotations
import unicodedata

from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QLineEdit, QPushButton
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QKeyEvent

import db
from theme import THEME_COLORS


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower() if s else ""


class _SearchInput(QLineEdit):
    """検索バー用QLineEdit"""
    pass


class SearchBar(QWidget):
    """検索バー本体"""

    searchChanged = Signal(str)   # 検索テキスト変更 → app.pyがフィルタリング
    cleared       = Signal()      # クリアボタン

    def __init__(self, parent=None):
        super().__init__(parent)
        from config import SEARCHBAR_HEIGHT

        self.setFixedHeight(SEARCHBAR_HEIGHT)
        self.setStyleSheet(f"background: {THEME_COLORS['bg_panel']}; border-bottom: 1px solid {THEME_COLORS['sep']};")
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(50)    # 50ms後に検索発火
        self._debounce_timer.timeout.connect(self._emit_search)
        self._setup_ui()

    def _setup_ui(self):
        import config
        from config import SEARCHBAR_HEIGHT, SEARCH_INPUT_MAX_WIDTH

        outer = QHBoxLayout(self)
        # スペースは検索フィールドの外に配置（中は詰める）
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(0)

        cap_h = SEARCHBAR_HEIGHT - 8
        radius = 14
        # 検索バーと検索ボタンをひとつの角丸枠で囲む（QFrameで枠を確実に表示）
        capsule = QFrame()
        capsule.setObjectName("SearchCapsule")
        capsule.setFixedHeight(cap_h)
        capsule.setFixedWidth(SEARCH_INPUT_MAX_WIDTH + 44)
        capsule.setFrameShape(QFrame.NoFrame)
        capsule.setStyleSheet(f"""
            #SearchCapsule {{
                background: {THEME_COLORS['bg_widget']};
                border: 1px solid {THEME_COLORS['border']};
                border-radius: {radius}px;
            }}
        """)
        cap_layout = QHBoxLayout(capsule)
        cap_layout.setContentsMargins(0, 0, 0, 0)
        cap_layout.setSpacing(0)

        # テキスト入力（configで幅指定・枠はカプセルで表示）
        self._input = _SearchInput()
        self._input.setMaximumWidth(SEARCH_INPUT_MAX_WIDTH)
        self._input.setPlaceholderText("検索")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {THEME_COLORS['bg_widget']};
                color: {THEME_COLORS['text_main']};
                border: none;
                border-top-left-radius: {radius - 1}px;
                border-bottom-left-radius: {radius - 1}px;
                padding: 6px 12px;
                font-size: {config.FONT_SIZE_SEARCH_INPUT}px;
            }}
            QLineEdit:focus {{
                outline: none;
            }}
        """)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._emit_search)
        cap_layout.addWidget(self._input)

        # 検索ボタン（右側・縦線で区切り・枠の右端の角丸）
        self._btn_search = QPushButton("🔍")
        self._btn_search.setFixedSize(44, cap_h)
        self._btn_search.setToolTip("検索を実行")
        self._btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_search.setStyleSheet(f"""
            QPushButton {{
                background: {THEME_COLORS['hover']};
                color: {THEME_COLORS['text_main']};
                border: none;
                border-left: 1px solid {THEME_COLORS['border']};
                border-top-right-radius: {radius - 1}px;
                border-bottom-right-radius: {radius - 1}px;
                padding: 0;
                margin: 0;
                font-size: {config.FONT_SIZE_SEARCHBAR_BTN}px;
            }}
            QPushButton:hover {{
                background: {THEME_COLORS['accent']};
                color: white;
            }}
        """)
        self._btn_search.clicked.connect(self._emit_search)
        cap_layout.addWidget(self._btn_search)

        outer.addWidget(capsule, alignment=Qt.AlignmentFlag.AlignHCenter)

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
