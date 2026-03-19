from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QModelIndex, Qt, Signal, QSize
from PySide6.QtWidgets import QAbstractItemView, QListView, QMessageBox

import config
import db
from ui.auto_scroll_mixin import AutoScrollMixin
from .delegate import BookCardDelegate, CARD_H, CARD_W, MIN_GAP
from .model import BookListModel
from .roles import ROLE_CIRCLE, ROLE_COVER, ROLE_PAGES, ROLE_PATH, ROLE_RATING, ROLE_TITLE


class BookGridView(AutoScrollMixin, QListView):
    bookOpened = Signal(str)
    bookSelected = Signal(dict)
    ctrlWheelZoom = Signal(int)  # Ctrl+ホイール: delta (+/-)

    def __init__(self, parent=None, app_callbacks: dict | None = None):
        super().__init__(parent)
        self._init_auto_scroll()
        self._card_w = CARD_W
        self._card_h = CARD_H
        self._app_callbacks: dict | None = app_callbacks

        self._model = BookListModel(self)
        self._delegate = BookCardDelegate(self)

        self.setModel(self._model)
        self.setItemDelegate(self._delegate)

        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(True)
        self.setSpacing(MIN_GAP // 2)
        self.setGridSize(QSize(self._card_w + MIN_GAP, self._card_h + MIN_GAP))

        # Shift/Ctrl複数選択
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(config.GRID_SCROLL_SINGLE_STEP)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setMovement(QListView.Static)
        self.setLayoutMode(QListView.Batched)
        self.setBatchSize(50)

        self.doubleClicked.connect(self._on_double_click)
        self.clicked.connect(self._on_click)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu_requested)

    def wheelEvent(self, event):
        """Ctrl+ホイールはズーム、それ以外は通常スクロール"""
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            self.ctrlWheelZoom.emit(delta)
            event.accept()
        else:
            super().wheelEvent(event)

    def load_books(self, books: list[dict]):
        self._model.set_books(books)

    def scroll_to_path(self, path: str):
        """指定pathのカードが見えるようにスクロール"""
        books = self._model._books
        for i, book in enumerate(books):
            if book.get("path") == path:
                index = self._model.index(i, 0)
                self.scrollTo(index, QAbstractItemView.PositionAtCenter)
                self.setCurrentIndex(index)
                break

    def preload_thumbs_for_books(self, books: list[dict]):
        self._model.preload_thumbs_for_books(books)

    def set_card_width(self, w: int):
        ratio = CARD_H / CARD_W
        self._card_w = w
        self._card_h = int(w * ratio)
        self._delegate.set_card_size(self._card_w, self._card_h)
        self._model.set_card_width(w)
        self.setGridSize(QSize(self._card_w + MIN_GAP, self._card_h + MIN_GAP))

    def apply_display_settings(self):
        """DBから表示設定を読み込んでDelegateに反映し再描画"""
        def _b(key, default="1"):
            return db.get_setting(key) != "0" if db.get_setting(key) is not None else (default == "1")

        show_meta = _b(config.CARD_SETTING_META_BADGE)
        show_pages = _b(config.CARD_SETTING_PAGES_BADGE)
        show_star = _b(config.CARD_SETTING_STAR)
        sub_info = db.get_setting(config.CARD_SETTING_SUB_INFO) or config.CARD_SETTING_SUB_INFO_DEFAULT
        show_store_icon = _b(config.CARD_SETTING_STORE_ICON)

        self._delegate.set_display_settings(show_meta, show_pages, show_star, sub_info, show_store_icon)
        self.viewport().update()

    def _on_click(self, index: QModelIndex):
        book = self._book_from_index(index)
        if book:
            self.bookSelected.emit(book)

    def _on_double_click(self, index: QModelIndex):
        # 複数選択対応：現在選択されている本をまとめて開く。ストアファイルは専用ビュアーのみ。
        from context_menu import open_book  # 遅延 import を維持

        selected_indexes = self.selectedIndexes()
        books: list[dict] = []
        for idx in selected_indexes:
            path = idx.data(ROLE_PATH)
            if path and os.path.exists(path):
                books.append({"path": path})

        if not books:
            path = index.data(ROLE_PATH)
            if not path or not os.path.exists(path):
                QMessageBox.warning(
                    self,
                    "ファイルが見つかりません",
                    f"以下のパスが存在しません。\n{path}\n\nライブラリを再スキャンしてください。",
                )
                return
            books = [{"path": path}]

        count = len(books)
        if count >= 5:
            ret = QMessageBox.question(self, "確認", f"{count}冊を同時に開きますか？", QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return

        parent_win = self.window()
        for b in books:
            path = b["path"]
            self.bookOpened.emit(path)
            if not open_book(path, parent_win, modal=False):
                break

    def _book_from_index(self, index: QModelIndex) -> Optional[dict]:
        if not index.isValid():
            return None
        return {
            "path": index.data(ROLE_PATH),
            "title": index.data(ROLE_TITLE),
            "circle": index.data(ROLE_CIRCLE),
            "pages": index.data(ROLE_PAGES),
            "cover": index.data(ROLE_COVER),
            "rating": index.data(ROLE_RATING),
            "name": index.data(ROLE_TITLE),
        }

    def _on_context_menu_requested(self, pos):
        """右クリックでコンテキストメニュー表示（CustomContextMenu で確実に発火させる）"""
        main = self.window()
        if main is not None:
            vb = self.verticalScrollBar()
            hb = self.horizontalScrollBar()
            v_val = vb.value() if vb else 0
            h_val = hb.value() if hb else 0
            main._context_menu_scroll = (v_val, h_val)

        index = self.indexAt(pos)
        try:
            from context_menu import BookContextMenu  # 遅延 import を維持
        except Exception:
            return

        if index.isValid():
            book = self._book_from_index(index) or {}
        else:
            book = {}

        selected_indexes = self.selectedIndexes()
        if index.isValid() and selected_indexes and any(idx == index for idx in selected_indexes):
            selected_books = []
            for idx in selected_indexes:
                b = self._book_from_index(idx)
                if b and b.get("path"):
                    selected_books.append(b)
            selected_books = selected_books if len(selected_books) > 1 else None
        else:
            selected_books = [book] if (book and book.get("path")) else None

        try:
            menu = BookContextMenu(book, self.window(), self._app_callbacks or {}, selected_books=selected_books)
        except Exception:
            return
        global_pos = self.mapToGlobal(pos)
        menu.exec(global_pos)

