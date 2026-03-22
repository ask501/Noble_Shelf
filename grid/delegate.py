from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

import config
import db
import paths
from .roles import *  # noqa: F403
from theme import (
    THEME_COLORS,
    CARD_BADGE_OVERLAY_ALPHA,
    CARD_RATING_BG_ALPHA,
    CARD_SHADOW_ALPHA,
    CARD_TITLE_SHADOW_ALPHA,
)

# ── 定数（view.py 側はここから import する）─────────────────
CARD_W = config.CARD_WIDTH_BASE
CARD_H = config.CARD_HEIGHT_BASE
MIN_GAP = config.CARD_MIN_GAP
RADIUS = config.BORDER_RADIUS
BADGE_H = config.BADGE_HEIGHT
BADGE_PAD = config.PAGE_BADGE_PAD
BADGE_BG_OVERLAY = config.PAGE_BADGE_BG_OVERLAY
CARD_BADGE_OFFSET_X = config.CARD_BADGE_OFFSET_X
CARD_BADGE_OFFSET_Y = config.CARD_BADGE_OFFSET_Y
BADGE_ICON_PAD = config.BADGE_ICON_PAD
BADGE_ICON_HEIGHT = config.BADGE_ICON_HEIGHT
STAR_FONT_SZ = 8

C_BG = QColor(THEME_COLORS["card_bg"])
C_SEL_BORDER = QColor(THEME_COLORS["accent"])
C_PLACEHOLDER = QColor(THEME_COLORS["card_placeholder"])
C_STAR_ON = QColor(THEME_COLORS["card_star_on"])
C_CHECK_OK = QColor(THEME_COLORS["check_ok"])
C_CHECK_MAN = QColor(THEME_COLORS["check_man"])

# DMM/DLSite ビュアー形式（ページ数の代わりにバッジアイコンを表示）
STORE_FILE_EXTS_DMM = (".dmmb", ".dmme", ".dmmr")
STORE_FILE_EXT_DLSITE = ".dlst"


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
        self._badge_dmm_pix = _load_badge_icon(paths.ICON_DMM_BADGE)
        self._badge_dlsite_pix = _load_badge_icon(paths.ICON_DLSITE_BADGE)
        self._font_title = QFont(config.FONT_FAMILY, config.FONT_SIZE_CARD_TITLE)
        self._font_badge = QFont(config.FONT_FAMILY, config.FONT_SIZE_CARD_BADGE, QFont.Bold)
        self._font_circle = QFont(config.FONT_FAMILY, config.FONT_SIZE_CARD_CIRCLE)
        self._font_star = QFont(config.FONT_FAMILY_SYMBOL, STAR_FONT_SZ)
        self._font_check = QFont(config.FONT_FAMILY_SYMBOL, 9, QFont.Bold)
        self._show_meta_badge = True
        self._show_pages_badge = True
        self._show_star = True
        self._sub_info = "circle"
        self._show_store_icon = True

    def set_display_settings(self, show_meta_badge: bool, show_pages_badge: bool, show_star: bool, sub_info: str, show_store_icon: bool = True):
        self._show_meta_badge = show_meta_badge
        self._show_pages_badge = show_pages_badge
        self._show_star = show_star
        self._sub_info = sub_info
        self._show_store_icon = show_store_icon

    def set_card_size(self, w: int, h: int):
        self._card_w = w
        self._card_h = h

    def _get_sub_info_text(self, index):
        if self._sub_info == "none":
            return ""
        if self._sub_info == "circle":
            return index.data(ROLE_CIRCLE) or ""  # noqa: F405
        path = index.data(ROLE_PATH) or ""  # noqa: F405
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

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        r = option.rect
        cx = r.x() + (r.width() - self._card_w) // 2
        cy = r.y() + (r.height() - self._card_h) // 2
        card_rect = QRect(cx, cy, self._card_w, self._card_h)
        thumb_h = self._card_h - config.CARD_TEXT_HEIGHT_FIXED
        thumb_rect = QRect(cx, cy, self._card_w, thumb_h)

        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = bool(option.state & QStyle.State_MouseOver)

        # ── カード背景 ──
        if is_selected:
            bg_color = QColor(THEME_COLORS["accent"]).darker(200)
            bg_color.setAlpha(220)
        elif is_hovered:
            bg_color = QColor(THEME_COLORS["hover"])
        else:
            bg_color = C_BG
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(card_rect, RADIUS, RADIUS)

        # ── サムネイル ──
        pix: Optional[QPixmap] = index.data(ROLE_THUMB)  # noqa: F405
        if pix and not pix.isNull():
            scaled = pix.scaled(thumb_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            ox = thumb_rect.x() + (thumb_rect.width() - scaled.width()) // 2
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

        # ── 左上: メタデータ取得状態 ──
        if self._show_meta_badge:
            meta_st = index.data(ROLE_META_ST) or 0  # noqa: F405
            if meta_st >= 1:
                badge_size = config.CARD_META_BADGE_SIZE
                inset = config.CARD_INSET
                bx = cx + inset
                by = cy + inset
                badge_rect = QRect(bx, by, badge_size, badge_size)

                shadow_rect = badge_rect.translated(1, 2)
                shadow_color = QColor(0, 0, 0, CARD_SHADOW_ALPHA)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(shadow_color))
                painter.drawRoundedRect(shadow_rect, config.CARD_META_BADGE_RADIUS, config.CARD_META_BADGE_RADIUS)

                bg = QColor(C_CHECK_OK if meta_st == 1 else C_CHECK_MAN)
                painter.setBrush(QBrush(bg))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(badge_rect, config.CARD_META_BADGE_RADIUS, config.CARD_META_BADGE_RADIUS)

                painter.setPen(QPen(Qt.white))
                painter.drawText(badge_rect, Qt.AlignCenter, "✓")

        # ── 右上: ページ数バッジ or ストアアイコン ──
        path = (index.data(ROLE_PATH) or "") or ""  # noqa: F405
        ext = os.path.splitext(path)[1].lower() if path else ""

        use_icon = None
        if self._show_store_icon:
            if ext in STORE_FILE_EXTS_DMM and self._badge_dmm_pix and not self._badge_dmm_pix.isNull():
                use_icon = self._badge_dmm_pix
            elif ext == STORE_FILE_EXT_DLSITE and self._badge_dlsite_pix and not self._badge_dlsite_pix.isNull():
                use_icon = self._badge_dlsite_pix

        if use_icon is not None:
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
        elif self._show_pages_badge:
            pages = index.data(ROLE_PAGES) or 0  # noqa: F405
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

        # ── 左下: 星レーティング ──
        if self._show_star:
            rating = index.data(ROLE_RATING) or 0  # noqa: F405
            if rating > 0:
                painter.setFont(self._font_star)
                fm_s = QFontMetrics(painter.font())
                star_w = fm_s.horizontalAdvance("★") + 1
                stars_to_draw = min(5, rating)

                badge_w = stars_to_draw * (star_w + 1) + config.CARD_STAR_BADGE_PADDING
                badge_h = BADGE_H
                bx = cx + config.CARD_INSET
                by = cy + thumb_h - badge_h - config.CARD_INSET
                rating_rect = QRect(bx, by, badge_w, badge_h)

                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(0, 0, 0, CARD_RATING_BG_ALPHA)))
                painter.drawRoundedRect(rating_rect, config.CARD_BADGE_RADIUS, config.CARD_BADGE_RADIUS)

                for i in range(stars_to_draw):
                    sx = bx + 3 + i * (star_w + 1)
                    painter.setPen(QPen(C_STAR_ON))
                    painter.drawText(QRect(sx, by, star_w + 2, badge_h), Qt.AlignLeft | Qt.AlignVCenter, "★")

        # ── テキスト（タイトル + サブ情報） ──
        text_inset = config.CARD_INSET
        line_h = config.CARD_TEXT_HEIGHT_FIXED // 2
        title_rect = QRect(
            cx + text_inset,
            cy + thumb_h + 2,
            self._card_w - text_inset * 2,
            line_h - 2 if self._sub_info != "none" else config.CARD_TEXT_HEIGHT_FIXED - 4,
        )
        title = index.data(ROLE_TITLE) or ""  # noqa: F405
        painter.setFont(self._font_title)
        fm_t = QFontMetrics(painter.font())
        elided = fm_t.elidedText(title, Qt.ElideRight, title_rect.width())
        painter.setPen(QPen(QColor(0, 0, 0, CARD_TITLE_SHADOW_ALPHA)))
        painter.drawText(title_rect.translated(1, 1), Qt.AlignLeft | Qt.AlignVCenter, elided)
        painter.setPen(QPen(QColor(THEME_COLORS["card_title_fg"])))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, elided)

        if self._sub_info != "none":
            sub_rect = QRect(cx + text_inset, cy + thumb_h + 2 + line_h, self._card_w - text_inset * 2, line_h - 2)
            sub_text = self._get_sub_info_text(index)
            if sub_text:
                painter.setFont(self._font_circle if self._sub_info == "circle" else self._font_badge)
                fm_s = QFontMetrics(painter.font())
                elided_sub = fm_s.elidedText(sub_text, Qt.ElideRight, sub_rect.width())
                painter.setPen(QPen(QColor(THEME_COLORS["card_sub_fg"])))
                painter.drawText(sub_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_sub)

        # ── 選択ボーダー ──
        if is_selected:
            painter.setPen(QPen(C_SEL_BORDER, 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(card_rect.adjusted(1, 1, -1, -1), RADIUS, RADIUS)

        painter.restore()

