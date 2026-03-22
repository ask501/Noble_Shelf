from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, QThreadPool
from PySide6.QtGui import QPixmap

import config
import db
from .roles import *  # noqa: F403
from .thumb import ThumbSignals, ThumbWorker, _cache_path

# ページ数カウントに使用する拡張子
PAGE_COUNT_EXTS = (".jpg", ".jpeg", ".png", ".webp")

class BookListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._books: list[dict] = []
        self._thumbs: dict[str, QPixmap] = {}
        self._pending: set[str] = set()
        self._pool = QThreadPool.globalInstance()
        self._card_w = config.CARD_WIDTH_BASE
        self._bookmarks: dict[str, int] = {}

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._books)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._books):
            return None
        b = self._books[index.row()]
        if role == ROLE_COVER:  # noqa: F405
            return b.get("cover", "")
        if role == ROLE_TITLE:  # noqa: F405
            return b.get("title", "") or b.get("name", "")
        if role == ROLE_CIRCLE:  # noqa: F405
            return b.get("circle", "")
        if role == ROLE_PAGES:  # noqa: F405
            self._ensure_meta_cached(b)
            pages = b.get("pages", 0) or 0
            if pages > 0:
                return pages

            path = b.get("path", "") or ""
            if not path:
                return 0

            # フォルダ内画像ファイル枚数をカウント（再帰なし）
            if os.path.isdir(path):
                try:
                    count = sum(1 for name in os.listdir(path) if os.path.splitext(name)[1].lower() in PAGE_COUNT_EXTS)
                except Exception:
                    count = 0
                b["pages"] = count
                return count

            return 0
        if role == ROLE_PATH:  # noqa: F405
            return b.get("path", "")
        if role == ROLE_RATING:  # noqa: F405
            # お気に入りテーブル由来の評価を優先して返す
            path = b.get("path", "") or ""
            if path:
                rating = self._bookmarks.get(path, 0)
                b["rating"] = rating
                return rating
            return b.get("rating", 0)
        if role == ROLE_META_ST:  # noqa: F405
            # 0=未取得, 1=取得済み
            self._ensure_meta_cached(b)
            return b.get("meta_status", 0)
        if role == ROLE_THUMB:  # noqa: F405
            cover = b.get("cover", "")
            if cover in self._thumbs:
                return self._thumbs[cover]
            self._request_thumb(cover, index)
            return None
        if role == Qt.SizeHintRole:
            return QSize(self._card_w + config.CARD_MIN_GAP, config.CARD_HEIGHT_BASE + config.CARD_MIN_GAP)
        return None

    def set_books(self, books: list[dict]):
        self.beginResetModel()
        self._books = books
        self.endResetModel()
        # メタキャッシュをリセット
        for b in self._books:
            b.pop("_meta_cached", None)
            b.pop("meta_status", None)
        # お気に入り（評価）情報を一括取得してキャッシュ
        try:
            self._bookmarks = db.get_all_bookmarks()
        except Exception:
            self._bookmarks = {}

    def _ensure_meta_cached(self, b: dict):
        """book dict にメタ情報由来の補助データをキャッシュする。"""
        if b.get("_meta_cached"):
            return
        b["_meta_cached"] = True

        path = b.get("path", "")
        if not path:
            return
        try:
            meta = db.get_book_meta(path)
        except Exception:
            return
        if not meta:
            return

        # ページ数（あればキャッシュ）
        m_pages = meta.get("pages") or 0
        if m_pages > 0:
            b["pages"] = m_pages

        # メタ取得済みフラグ
        has_meta = bool(
            meta.get("dlsite_id")
            or meta.get("author")
            or meta.get("series")
            or (meta.get("characters") or [])
            or (meta.get("tags") or [])
        )
        if has_meta:
            b["meta_status"] = 1

    def set_card_width(self, w: int):
        self._card_w = w
        self.layoutChanged.emit()

    def _request_thumb(self, cover: str, index: QModelIndex):
        if not cover or cover in self._pending:
            return
        if len(self._pending) >= 16:
            return
        self._pending.add(cover)
        w = ThumbWorker(cover)
        w.signals.done.connect(self._on_thumb_done)
        self._pool.start(w)

    def _on_thumb_done(self, cover: str, pix: QPixmap):
        self._pending.discard(cover)
        self._thumbs[cover] = pix
        for row, b in enumerate(self._books):
            if b.get("cover") == cover:
                idx = self.index(row)
                self.dataChanged.emit(idx, idx, [ROLE_THUMB])  # noqa: F405
                break

    def invalidate_thumb(self, cover: str) -> None:
        """特定coverのメモリ・ディスクキャッシュを破棄して再描画をトリガーする"""
        if not cover:
            return
        self._thumbs.pop(cover, None)
        self._pending.discard(cover)
        cp = _cache_path(cover)
        if os.path.exists(cp):
            os.remove(cp)
        for i, b in enumerate(self._books):
            if b.get("cover") == cover:
                idx = self.index(i)
                self.dataChanged.emit(idx, idx, [ROLE_THUMB])  # noqa: F405
                break

    def invalidate_thumbs(self):
        self._thumbs.clear()
        self._pending.clear()

    def preload_thumbs_for_books(self, books: list[dict]):
        """CACHE_DIR 内 .png が存在するものだけ同期ロードして _thumbs に詰める。"""
        for b in books:
            cover = b.get("cover") or ""
            if not cover:
                continue
            try:
                cp = _cache_path(cover)
                if not os.path.exists(cp):
                    continue
                pix = QPixmap(cp)
                if pix.isNull():
                    continue
                self._thumbs[cover] = pix
            except Exception:
                continue

