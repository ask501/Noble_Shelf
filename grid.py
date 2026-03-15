"""
grid.py - サムネイルグリッド（カード表示リファイン版）
- 左上: メタデータ取得状態チェックマーク
- 右上: ページ数バッジ
- 左下: 星レーティング
- ホバー: 枠ハイライト / 選択: アクセントカラー枠
- Shift/Ctrl複数選択
- テキスト: 1行すっきり表示
"""
from __future__ import annotations

import os
import hashlib
import zipfile
from typing import Optional

from PySide6.QtWidgets import (
    QListView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QAbstractItemView,
    QStyle,
)
from PySide6.QtCore import (
    Qt,
    QSize,
    QRect,
    QModelIndex,
    QAbstractListModel,
    Signal,
    QObject,
    QRunnable,
    QThreadPool,
)
from PySide6.QtGui import (
    QPainter,
    QPixmap,
    QColor,
    QFont,
    QPen,
    QBrush,
    QFontMetrics,
    QLinearGradient,
)
from PIL import Image

import config
import db
from theme import (
    THEME_COLORS,
    CARD_BADGE_OVERLAY_ALPHA,
    CARD_SHADOW_ALPHA,
    CARD_RATING_BG_ALPHA,
    CARD_TITLE_SHADOW_ALPHA,
)

# ── 定数 ─────────────────────────────────────────────────
CARD_W        = config.CARD_WIDTH_BASE
CARD_H        = config.CARD_HEIGHT_BASE
CACHE_DIR     = config.CACHE_DIR
MIN_GAP       = config.CARD_MIN_GAP
RADIUS        = config.BORDER_RADIUS
BADGE_H            = config.BADGE_HEIGHT
BADGE_PAD          = config.PAGE_BADGE_PAD   # ページ数バッジ(XXP)内のテキスト左右余白
BADGE_BG_OVERLAY   = config.PAGE_BADGE_BG_OVERLAY  # ページ数バッジ背景の上下左右オーバーレイ(px)
CARD_BADGE_OFFSET_X = config.CARD_BADGE_OFFSET_X
CARD_BADGE_OFFSET_Y = config.CARD_BADGE_OFFSET_Y
BADGE_ICON_PAD     = config.BADGE_ICON_PAD   # DMM/DLSite画像時の左右・上下余白
BADGE_ICON_HEIGHT = config.BADGE_ICON_HEIGHT  # DMM/DLSiteバッジの表示高さ(px)
TEXT_H        = 22
STAR_FONT_SZ  = 8

C_BG           = QColor(THEME_COLORS["card_bg"])
C_HOVER_BORDER = QColor(THEME_COLORS["card_hover_border"])
C_SEL_BORDER   = QColor(THEME_COLORS["accent"])
C_TEXT         = QColor(THEME_COLORS["text_main"])
C_BADGE_BG     = QColor(THEME_COLORS["badge_bg"])
C_BADGE_FG     = QColor(THEME_COLORS["badge_fg"])
C_PLACEHOLDER  = QColor(THEME_COLORS["card_placeholder"])
C_STAR_ON      = QColor(THEME_COLORS["card_star_on"])
C_STAR_OFF     = QColor(THEME_COLORS["card_star_off"])
C_CHECK_OK     = QColor(THEME_COLORS["check_ok"])
C_CHECK_MAN    = QColor(THEME_COLORS["check_man"])

# ページ数カウントに使用する拡張子
PAGE_COUNT_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# アーカイブ拡張子（Zip等の圧縮ファイル内ファイル数をページ数表示する）
ARCHIVE_EXTS = (".zip", ".cbz", ".7z", ".cb7", ".rar", ".cbr")

# DMM/DLSite ビュアー形式（ページ数の代わりにバッジアイコンを表示）
STORE_FILE_EXTS_DMM = (".dmmb", ".dmme", ".dmmr")
STORE_FILE_EXT_DLSITE = ".dlst"


def _archive_page_count(path: str) -> int:
    """Zip等のアーカイブ内の画像ファイル数（ページ数）を返す。取得失敗時は0。"""
    if not path or not os.path.isfile(path):
        return 0
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".zip", ".cbz"):
            with zipfile.ZipFile(path, "r") as zf:
                return sum(
                    1
                    for n in zf.namelist()
                    if os.path.splitext(n)[1].lower() in PAGE_COUNT_EXTS
                    and not os.path.basename(n).startswith(".")
                )
        if ext in (".7z", ".cb7"):
            try:
                import py7zr
            except ImportError:
                return 0
            with py7zr.SevenZipFile(path, "r") as zf:
                return sum(
                    1
                    for n in zf.getnames()
                    if os.path.splitext(n)[1].lower() in PAGE_COUNT_EXTS
                )
        if ext in (".rar", ".cbr"):
            try:
                import rarfile
            except ImportError:
                return 0
            with rarfile.RarFile(path) as rf:
                return sum(
                    1
                    for n in rf.namelist()
                    if os.path.splitext(n)[1].lower() in PAGE_COUNT_EXTS
                )
    except Exception:
        return 0
    return 0


# ══════════════════════════════════════════════════════════
#  サムネイル非同期ロード
# ══════════════════════════════════════════════════════════

def _cache_path(cover: str) -> str:
    h = hashlib.md5(cover.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.png")


def _load_thumb_sync(cover: str) -> Optional[QPixmap]:
    try:
        cp = _cache_path(cover)
        tw, th = config.THUMB_CACHE_WIDTH, config.THUMB_CACHE_HEIGHT
        if os.path.exists(cp):
            pix = QPixmap(cp)
            if not pix.isNull():
                return pix
        if not os.path.exists(cover):
            return None
        with Image.open(cover) as im:
            im = im.convert("RGB")
            im.thumbnail((tw, th), Image.BILINEAR)
            os.makedirs(CACHE_DIR, exist_ok=True)
            im.save(cp, "PNG", optimize=False)
        pix = QPixmap(cp)
        return pix if not pix.isNull() else None
    except Exception:
        return None


class ThumbSignals(QObject):
    done = Signal(str, QPixmap)


class ThumbWorker(QRunnable):
    def __init__(self, cover: str):
        super().__init__()
        self.cover   = cover
        self.signals = ThumbSignals()
        self.setAutoDelete(True)

    def run(self):
        pix = _load_thumb_sync(self.cover)
        if pix:
            self.signals.done.emit(self.cover, pix)


# ══════════════════════════════════════════════════════════
#  カスタムロール
# ══════════════════════════════════════════════════════════
ROLE_COVER   = Qt.UserRole + 1
ROLE_TITLE   = Qt.UserRole + 2
ROLE_CIRCLE  = Qt.UserRole + 3
ROLE_PAGES   = Qt.UserRole + 4
ROLE_PATH    = Qt.UserRole + 5
ROLE_THUMB   = Qt.UserRole + 6
ROLE_RATING  = Qt.UserRole + 7
ROLE_META_ST = Qt.UserRole + 8   # 0=未取得 1=取得済 2=手動


# ══════════════════════════════════════════════════════════
#  データモデル
# ══════════════════════════════════════════════════════════

class BookListModel(QAbstractListModel):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._books: list[dict] = []
        self._thumbs: dict[str, QPixmap] = {}
        self._pending: set[str] = set()
        self._pool = QThreadPool.globalInstance()
        self._card_w = CARD_W
        self._bookmarks: dict[str, int] = {}

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._books)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._books):
            return None
        b = self._books[index.row()]
        if role == ROLE_COVER:   return b.get("cover", "")
        if role == ROLE_TITLE:   return b.get("title", "") or b.get("name", "")
        if role == ROLE_CIRCLE:  return b.get("circle", "")
        if role == ROLE_PAGES:
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
                    count = sum(
                        1
                        for name in os.listdir(path)
                        if os.path.splitext(name)[1].lower() in PAGE_COUNT_EXTS
                    )
                except Exception:
                    count = 0
                b["pages"] = count
                return count

            # Zip等のアーカイブ内の画像ファイル数をページ数として表示
            if os.path.isfile(path) and os.path.splitext(path)[1].lower() in ARCHIVE_EXTS:
                count = _archive_page_count(path)
                if count > 0:
                    b["pages"] = count
                    return count

            return 0
        if role == ROLE_PATH:
            return b.get("path", "")
        if role == ROLE_RATING:
            # お気に入りテーブル由来の評価を優先して返す
            path = b.get("path", "") or ""
            if path:
                rating = self._bookmarks.get(path, 0)
                b["rating"] = rating
                return rating
            return b.get("rating", 0)
        if role == ROLE_META_ST:
            # 0=未取得, 1=取得済み
            self._ensure_meta_cached(b)
            return b.get("meta_status", 0)
        if role == ROLE_THUMB:
            cover = b.get("cover", "")
            if cover in self._thumbs:
                return self._thumbs[cover]
            self._request_thumb(cover, index)
            return None
        if role == Qt.SizeHintRole:
            return QSize(self._card_w + MIN_GAP, CARD_H + MIN_GAP)
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
        """book dict にメタ情報由来の補助データをキャッシュする。
        - pages: メタデータ上のページ数があれば設定
        - meta_status: 作品ID・作者・シリーズ・タグ・キャラのいずれかがあれば 1（取得済み）
        """
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
        if isinstance(m_pages, int) and m_pages > 0:
            b.setdefault("pages", m_pages)

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
                self.dataChanged.emit(idx, idx, [ROLE_THUMB])
                break

    def invalidate_thumbs(self):
        self._thumbs.clear()
        self._pending.clear()

    def preload_thumbs_for_books(self, books: list[dict]):
        """
        事前にサムネキャッシュ（CACHE_DIR 内 .png）が存在するものだけ
        QPixmap を同期ロードして _thumbs に詰めておく。
        """
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

# ══════════════════════════════════════════════════════════
#  デリゲート（カード描画）
# ══════════════════════════════════════════════════════════

def _load_badge_icon(path: str) -> Optional[QPixmap]:
    """バッジ用アイコンを読み込む。失敗時は None。"""
    if not path or not os.path.isfile(path):
        return None
    pix = QPixmap(path)
    return pix if not pix.isNull() else None


class BookCardDelegate(QStyledItemDelegate):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._card_w = CARD_W
        self._card_h = CARD_H
        # DMM/DLSite バッジアイコン（assets に dmm_badge.png / dlsite_badge.png があれば使用）
        self._badge_dmm_pix = _load_badge_icon(getattr(config, "BADGE_ICON_DMM_PATH", ""))
        self._badge_dlsite_pix = _load_badge_icon(getattr(config, "BADGE_ICON_DLSITE_PATH", ""))
        # カードタイトル・バッジ・サークルのフォント（セマンティック定数で管理）
        self._font_title  = QFont(config.FONT_FAMILY, config.FONT_SIZE_CARD_TITLE)
        self._font_badge  = QFont(config.FONT_FAMILY, config.FONT_SIZE_CARD_BADGE, QFont.Bold)
        self._font_circle = QFont(config.FONT_FAMILY, config.FONT_SIZE_CARD_CIRCLE)
        self._font_star   = QFont(config.FONT_FAMILY_SYMBOL, STAR_FONT_SZ)
        self._font_check = QFont(config.FONT_FAMILY_SYMBOL, 9, QFont.Bold)
        # カード表示設定（デフォルト値。set_display_settings() で上書き）
        self._show_meta_badge  = True
        self._show_pages_badge = True
        self._show_star        = True
        self._sub_info         = "circle"   # "none"/"circle"/"author"/"series"/"character"/"tag"
        self._show_store_icon  = True

    def set_display_settings(self, show_meta_badge: bool, show_pages_badge: bool,
                             show_star: bool, sub_info: str, show_store_icon: bool = True):
        self._show_meta_badge  = show_meta_badge
        self._show_pages_badge = show_pages_badge
        self._show_star        = show_star
        self._sub_info         = sub_info
        self._show_store_icon  = show_store_icon

    def set_card_size(self, w: int, h: int):
        self._card_w = w
        self._card_h = h

    def _get_sub_info_text(self, index: QModelIndex) -> str:
        """サブ情報フィールドに表示するテキストを返す"""
        if self._sub_info == "none":
            return ""
        if self._sub_info == "circle":
            return index.data(ROLE_CIRCLE) or ""
        path = index.data(ROLE_PATH) or ""
        if not path:
            return ""
        try:
            meta = db.get_book_meta(path)
        except Exception:
            return ""
        if not meta:
            return ""
        if self._sub_info == "author":
            return meta.get("author", "") or ""
        if self._sub_info == "series":
            return meta.get("series", "") or ""
        if self._sub_info == "character":
            return meta.get("character", "") or ""
        if self._sub_info == "tag":
            tags = meta.get("tags", "") or ""
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            if not tag_list:
                return ""
            result = ""
            for i, tag in enumerate(tag_list):
                candidate = (result + "・" + tag) if result else tag
                if i >= 3:
                    result = result + "…"
                    break
                result = candidate
            return result
        return ""

    def sizeHint(self, option, index) -> QSize:
        return QSize(self._card_w + MIN_GAP, self._card_h + MIN_GAP)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        r  = option.rect
        cx = r.x() + (r.width()  - self._card_w) // 2
        cy = r.y() + (r.height() - self._card_h) // 2
        card_rect  = QRect(cx, cy, self._card_w, self._card_h)
        # thumb_h は常に2行分テキスト領域を確保した固定値
        thumb_h = self._card_h - config.CARD_TEXT_HEIGHT_FIXED
        # サムネ領域: カード上端からthumb_h分（背景色の余白が上下に自然に出る）
        thumb_rect = QRect(cx, cy, self._card_w, thumb_h)

        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered  = bool(option.state & QStyle.State_MouseOver)

        # ── カード背景（ホバー・選択で色変化） ───────────
        if is_selected:
            bg_color = QColor(THEME_COLORS["accent"]).darker(200)  # 暗めのアクセント
            bg_color.setAlpha(220)
        elif is_hovered:
            bg_color = QColor(THEME_COLORS["hover"])
        else:
            bg_color = C_BG
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(card_rect, RADIUS, RADIUS)

        # ── サムネイル ────────────────────────────────────
        pix: Optional[QPixmap] = index.data(ROLE_THUMB)
        if pix and not pix.isNull():
            # KeepAspectRatio: 領域に収まるよう縮小（はみ出さない）
            scaled = pix.scaled(thumb_rect.size(), Qt.KeepAspectRatio,
                                Qt.SmoothTransformation)
            # 中央配置（上下左右に背景色の余白）
            ox = thumb_rect.x() + (thumb_rect.width()  - scaled.width())  // 2
            oy = thumb_rect.y() + (thumb_rect.height() - scaled.height()) // 2
            painter.drawPixmap(ox, oy, scaled)
            painter.setClipping(False)
        else:
            painter.setBrush(QBrush(C_PLACEHOLDER))
            painter.setPen(Qt.NoPen)
            painter.drawRect(thumb_rect)
            half = config.CARD_PLACEHOLDER_CROSS_HALF
            lx = thumb_rect.x() + thumb_rect.width() // 2 - half
            rx = thumb_rect.x() + thumb_rect.width() // 2 + half
            ty = thumb_rect.y() + thumb_rect.height() // 2 - half * 2
            by = thumb_rect.y() + thumb_rect.height() // 2 + half * 2
            painter.setPen(QPen(QColor(THEME_COLORS["card_star_off"]), 2))
            painter.drawLine(lx, ty, lx, by)
            painter.drawLine(rx, ty, rx, by)
            painter.drawLine(lx, ty, rx, ty)
            painter.drawLine(lx, by, rx, by)

        # サムネイル下端グラデーション
        grad_h = config.CARD_GRADIENT_HEIGHT
        grad_rect = QRect(cx, cy + thumb_h - grad_h, self._card_w, grad_h)
        grad = QLinearGradient(0, grad_rect.top(), 0, grad_rect.bottom())
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(THEME_COLORS["card_bg"]))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.setClipping(False)
        painter.drawRect(grad_rect)

        # ── 左上: メタデータ取得状態 ──────────────────────
        if self._show_meta_badge:
            meta_st = index.data(ROLE_META_ST) or 0
            if meta_st >= 1:
                # バッジの矩形
                badge_size = config.CARD_META_BADGE_SIZE
                inset = config.CARD_INSET
                bx = cx + inset
                by = cy + inset
                badge_rect = QRect(bx, by, badge_size, badge_size)

                # ドロップシャドウ風の影
                shadow_rect = badge_rect.translated(1, 2)
                shadow_color = QColor(0, 0, 0, CARD_SHADOW_ALPHA)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(shadow_color))
                painter.drawRoundedRect(shadow_rect, config.CARD_META_BADGE_RADIUS, config.CARD_META_BADGE_RADIUS)

                # 本体バッジ
                bg_color = QColor(C_CHECK_OK if meta_st == 1 else C_CHECK_MAN)
                painter.setBrush(QBrush(bg_color))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(badge_rect, config.CARD_META_BADGE_RADIUS, config.CARD_META_BADGE_RADIUS)

                # 白抜きチェックマーク
                painter.setPen(QPen(Qt.white))
                painter.drawText(badge_rect, Qt.AlignCenter, "✓")

        # ── 右上: ページ数バッジ または DMM/DLSite アイコン ──────────────────────────
        if self._show_pages_badge:
            path = (index.data(ROLE_PATH) or "") or ""
            ext = os.path.splitext(path)[1].lower() if path else ""
            use_icon = None
            if self._show_store_icon:
                if ext in STORE_FILE_EXTS_DMM and self._badge_dmm_pix and not self._badge_dmm_pix.isNull():
                    use_icon = self._badge_dmm_pix
                elif ext == STORE_FILE_EXT_DLSITE and self._badge_dlsite_pix and not self._badge_dlsite_pix.isNull():
                    use_icon = self._badge_dlsite_pix

            if use_icon is not None:
                # アイコンバッジ（高さ・余白は config で管理、幅は画像のアスペクト比に合わせる）
                icon_h = BADGE_ICON_HEIGHT
                orig_w = use_icon.width()
                orig_h = use_icon.height()
                icon_w = int(icon_h * orig_w / orig_h) if orig_h > 0 else icon_h
                pad = BADGE_ICON_PAD
                bw, bh = icon_w + pad * 2, icon_h + pad * 2
                badge_rect = QRect(cx + self._card_w - bw - CARD_BADGE_OFFSET_X, cy + CARD_BADGE_OFFSET_Y, bw, bh)
                bg_rect = badge_rect.adjusted(-BADGE_BG_OVERLAY, -BADGE_BG_OVERLAY, BADGE_BG_OVERLAY, BADGE_BG_OVERLAY)
                bg = QColor(0, 0, 0, CARD_BADGE_OVERLAY_ALPHA)
                painter.setBrush(QBrush(bg))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(bg_rect, config.CARD_BADGE_RADIUS, config.CARD_BADGE_RADIUS)
                scaled = use_icon.scaled(QSize(icon_w, icon_h), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                ix = badge_rect.x() + pad + (icon_w - scaled.width()) // 2
                iy = badge_rect.y() + pad + (icon_h - scaled.height()) // 2
                painter.drawPixmap(ix, iy, scaled)
            else:
                # 従来のページ数テキスト（config の FONT_SIZE_CARD_BADGE を反映）。0Pの場合は "--"
                pages = index.data(ROLE_PAGES) or 0
                badge_text = f"{pages}P" if pages > 0 else "--"
                painter.setFont(self._font_badge)
                fm = QFontMetrics(painter.font())
                bw = fm.horizontalAdvance(badge_text) + BADGE_PAD * 2
                badge_rect = QRect(cx + self._card_w - bw - CARD_BADGE_OFFSET_X, cy + CARD_BADGE_OFFSET_Y, bw, BADGE_H)
                bg_rect = badge_rect.adjusted(-BADGE_BG_OVERLAY, -BADGE_BG_OVERLAY, BADGE_BG_OVERLAY, BADGE_BG_OVERLAY)
                bg = QColor(0, 0, 0, CARD_BADGE_OVERLAY_ALPHA)
                painter.setBrush(QBrush(bg))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(bg_rect, config.CARD_BADGE_RADIUS, config.CARD_BADGE_RADIUS)
                painter.setPen(QPen(Qt.white))
                painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

        # ── 左下: 星レーティング ──────────────────────────
        if self._show_star:
            rating = index.data(ROLE_RATING) or 0
            if rating > 0:
                painter.setFont(self._font_star)
                fm_s = QFontMetrics(painter.font())
                star_w = fm_s.horizontalAdvance("★") + 1
                stars_to_draw = min(5, rating)

                # 背景バッジ（左下）
                badge_w = stars_to_draw * (star_w + 1) + config.CARD_STAR_BADGE_PADDING
                badge_h = BADGE_H
                bx = cx + config.CARD_INSET
                by = cy + thumb_h - badge_h - config.CARD_INSET
                rating_rect = QRect(bx, by, badge_w, badge_h)

                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(0, 0, 0, CARD_RATING_BG_ALPHA)))
                painter.drawRoundedRect(rating_rect, config.CARD_BADGE_RADIUS, config.CARD_BADGE_RADIUS)

                # ★描画
                for i in range(stars_to_draw):
                    sx = bx + 3 + i * (star_w + 1)
                    painter.setPen(QPen(C_STAR_ON))
                    painter.drawText(
                        QRect(sx, by, star_w + 2, badge_h),
                        Qt.AlignLeft | Qt.AlignVCenter,
                        "★",
                    )

        # ── テキスト1行目: タイトル（固定） ──
        text_inset = config.CARD_INSET
        line_h = config.CARD_TEXT_HEIGHT_FIXED // 2
        # サブ情報なし時はテキスト領域全体を使って縦中央
        title_rect = QRect(cx + text_inset, cy + thumb_h + 2, self._card_w - text_inset * 2,
                           line_h - 2 if self._sub_info != "none" else config.CARD_TEXT_HEIGHT_FIXED - 4)
        title = index.data(ROLE_TITLE) or ""
        painter.setFont(self._font_title)
        fm_t = QFontMetrics(painter.font())
        elided = fm_t.elidedText(title, Qt.ElideRight, title_rect.width())
        painter.setPen(QPen(QColor(0, 0, 0, CARD_TITLE_SHADOW_ALPHA)))
        painter.drawText(title_rect.translated(1, 1), Qt.AlignLeft | Qt.AlignVCenter, elided)
        painter.setPen(QPen(QColor(THEME_COLORS["card_title_fg"])))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, elided)

        # ── テキスト2行目: サブ情報（サークル時は FONT_SIZE_CARD_CIRCLE、それ以外は FONT_SIZE_CARD_BADGE） ──
        if self._sub_info != "none":
            sub_rect = QRect(cx + text_inset, cy + thumb_h + 2 + line_h, self._card_w - text_inset * 2, line_h - 2)
            sub_text = self._get_sub_info_text(index)
            if sub_text:
                painter.setFont(self._font_circle if self._sub_info == "circle" else self._font_badge)
                fm_s = QFontMetrics(painter.font())
                elided_sub = fm_s.elidedText(sub_text, Qt.ElideRight, sub_rect.width())
                painter.setPen(QPen(QColor(THEME_COLORS["card_sub_fg"])))
                painter.drawText(sub_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_sub)

        # ── ホバー・選択ボーダー（背景色で識別済み、選択時のみ細枠で補強） ──
        if is_selected:
            painter.setPen(QPen(C_SEL_BORDER, 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(card_rect.adjusted(1, 1, -1, -1), RADIUS, RADIUS)

        painter.restore()


# ══════════════════════════════════════════════════════════
#  グリッドビュー本体
# ══════════════════════════════════════════════════════════

class BookGridView(QListView):

    bookOpened   = Signal(str)
    bookSelected = Signal(dict)
    ctrlWheelZoom = Signal(int)   # Ctrl+ホイール: delta (+/-)

    def __init__(self, parent=None, app_callbacks: dict | None = None):
        super().__init__(parent)
        self._card_w = CARD_W
        self._card_h = CARD_H
        self._app_callbacks: dict | None = app_callbacks

        self._model    = BookListModel(self)
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

        show_meta       = _b(config.CARD_SETTING_META_BADGE)
        show_pages      = _b(config.CARD_SETTING_PAGES_BADGE)
        show_star       = _b(config.CARD_SETTING_STAR)
        sub_info        = db.get_setting(config.CARD_SETTING_SUB_INFO) or config.CARD_SETTING_SUB_INFO_DEFAULT
        show_store_icon = _b(config.CARD_SETTING_STORE_ICON)

        self._delegate.set_display_settings(show_meta, show_pages, show_star, sub_info, show_store_icon)
        self.viewport().update()

    def _on_click(self, index: QModelIndex):
        book = self._book_from_index(index)
        if book:
            self.bookSelected.emit(book)

    def _on_double_click(self, index: QModelIndex):
        # 複数選択対応：現在選択されている本をまとめて開く。ストアファイルは専用ビュアーのみ。
        from PySide6.QtWidgets import QMessageBox
        from context_menu import open_book

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
            ret = QMessageBox.question(
                self,
                "確認",
                f"{count}冊を同時に開きますか？",
                QMessageBox.Yes | QMessageBox.No,
            )
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
            "path":   index.data(ROLE_PATH),
            "title":  index.data(ROLE_TITLE),
            "circle": index.data(ROLE_CIRCLE),
            "pages":  index.data(ROLE_PAGES),
            "cover":  index.data(ROLE_COVER),
            "rating": index.data(ROLE_RATING),
            "name":   index.data(ROLE_TITLE),
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
            from context_menu import BookContextMenu
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
