"""tab_card.py - 設定ダイアログ「カード表示」タブ"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QComboBox,
    QFrame,
    QScrollArea,
)
from PySide6.QtGui import (
    QPainter,
    QColor,
    QBrush,
    QPen,
    QFont,
    QFontMetrics,
    QLinearGradient,
)
from PySide6.QtCore import Qt, QRect, QSize

import db
import config
from theme import (
    SETTINGS_CARD_PREVIEW_THUMB_BG,
    SETTINGS_CARD_PREVIEW_META_OK_BG,
    COLOR_BG_WIDGET,
    COLOR_BORDER,
    COLOR_STAR_ACTIVE,
    COLOR_CARD_TITLE_FG,
    COLOR_CARD_SUB_FG,
    CARD_BADGE_OVERLAY_ALPHA,
    CARD_RATING_BG_ALPHA,
)

CARD_W, CARD_H = config.THUMB_WIDTH_BASE, config.THUMB_HEIGHT_BASE
THUMB_H = int(CARD_H * 0.80)
TEXT_H = CARD_H - THUMB_H

SUB_INFO_OPTIONS = [
    ("none", "なし"),
    ("circle", "サークル"),
    ("author", "作者"),
    ("series", "シリーズ"),
    ("character", "キャラクター"),
    ("tag", "タグ"),
]
SUB_SAMPLE_TEXT = {
    "none": "",
    "circle": "サークル名サンプル",
    "author": "作者名サンプル",
    "series": "シリーズ名サンプル",
    "character": "キャラクター名",
    "tag": "タグA・タグB・タグC…",
}


class _CardPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(
            CARD_W + config.SETTINGS_CARD_PREVIEW_OUTER_PAD * 2,
            CARD_H + config.SETTINGS_CARD_PREVIEW_OUTER_PAD * 2,
        )
        self.show_meta = True
        self.show_pages = True
        self.show_star = True
        self.show_store_icon = True
        self.sub_info = "circle"
        self.sub_text = "サークル名サンプル"

    def sizeHint(self):
        return QSize(
            CARD_W + config.SETTINGS_CARD_PREVIEW_OUTER_PAD * 2,
            CARD_H + config.SETTINGS_CARD_PREVIEW_OUTER_PAD * 2,
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        cx, cy = config.SETTINGS_CARD_PREVIEW_OUTER_PAD, config.SETTINGS_CARD_PREVIEW_OUTER_PAD

        p.setBrush(QBrush(QColor(COLOR_BG_WIDGET)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRect(cx, cy, CARD_W, CARD_H), config.BORDER_RADIUS, config.BORDER_RADIUS)

        p.setBrush(QBrush(QColor(SETTINGS_CARD_PREVIEW_THUMB_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRect(cx, cy, CARD_W, THUMB_H))

        grad = QLinearGradient(
            0,
            cy + THUMB_H - config.CARD_GRADIENT_HEIGHT,
            0,
            cy + THUMB_H,
        )
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(COLOR_BG_WIDGET))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRect(cx, cy + THUMB_H - config.CARD_GRADIENT_HEIGHT, CARD_W, config.CARD_GRADIENT_HEIGHT))

        if self.show_meta:
            p.setBrush(QBrush(QColor(SETTINGS_CARD_PREVIEW_META_OK_BG)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(
                QRect(
                    cx + config.CARD_INSET,
                    cy + config.CARD_INSET,
                    config.CARD_META_BADGE_SIZE,
                    config.CARD_META_BADGE_SIZE,
                ),
                config.CARD_META_BADGE_RADIUS,
                config.CARD_META_BADGE_RADIUS,
            )
            p.setPen(QPen(Qt.GlobalColor.white))
            f = QFont(config.FONT_FAMILY)
            f.setPointSize(config.FONT_SIZE_CARD_BADGE)
            f.setBold(True)
            p.setFont(f)
            p.drawText(
                QRect(
                    cx + config.CARD_INSET,
                    cy + config.CARD_INSET,
                    config.CARD_META_BADGE_SIZE,
                    config.CARD_META_BADGE_SIZE,
                ),
                Qt.AlignmentFlag.AlignCenter,
                "✓",
            )

        if self.show_pages:
            f = QFont(config.FONT_FAMILY)
            f.setPointSize(config.FONT_SIZE_CARD_BADGE)
            p.setFont(f)
            fm = QFontMetrics(f)
            badge_text = "148P"
            bw = fm.horizontalAdvance(badge_text) + (config.PAGE_BADGE_PAD * 2)
            p.setBrush(QBrush(QColor(0, 0, 0, CARD_BADGE_OVERLAY_ALPHA)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(
                QRect(
                    cx + CARD_W - bw - config.CARD_INSET,
                    cy + config.CARD_INSET,
                    bw,
                    config.BADGE_HEIGHT,
                ),
                config.CARD_BADGE_RADIUS,
                config.CARD_BADGE_RADIUS,
            )
            p.setPen(QPen(Qt.GlobalColor.white))
            p.drawText(
                QRect(
                    cx + CARD_W - bw - config.CARD_INSET,
                    cy + config.CARD_INSET,
                    bw,
                    config.BADGE_HEIGHT,
                ),
                Qt.AlignmentFlag.AlignCenter,
                badge_text,
            )

        if self.show_star:
            f = QFont(config.FONT_FAMILY)
            f.setPointSize(config.FONT_SIZE_CARD_BADGE)
            p.setFont(f)
            fm = QFontMetrics(f)
            stars = "★★★"
            sw = fm.horizontalAdvance(stars) + (config.PAGE_BADGE_PAD * 2)
            p.setBrush(QBrush(QColor(0, 0, 0, CARD_RATING_BG_ALPHA)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(
                QRect(
                    cx + config.CARD_INSET,
                    cy + THUMB_H - config.CARD_GRADIENT_HEIGHT,
                    sw,
                    config.BADGE_HEIGHT,
                ),
                config.CARD_BADGE_RADIUS,
                config.CARD_BADGE_RADIUS,
            )
            p.setPen(QPen(QColor(COLOR_STAR_ACTIVE)))
            p.drawText(
                QRect(
                    cx + config.CARD_INSET,
                    cy + THUMB_H - config.CARD_GRADIENT_HEIGHT,
                    sw,
                    config.BADGE_HEIGHT,
                ),
                Qt.AlignmentFlag.AlignCenter,
                stars,
            )

        line_h = (TEXT_H - 2) // 2

        f = QFont(config.FONT_FAMILY)
        f.setPointSize(config.FONT_SIZE_CARD_TITLE)
        p.setFont(f)
        fm = QFontMetrics(f)
        title = config.APP_TITLE
        elided = fm.elidedText(title, Qt.TextElideMode.ElideRight, CARD_W - 8)
        p.setPen(QPen(QColor(COLOR_CARD_TITLE_FG)))
        p.drawText(
            QRect(cx + 4, cy + THUMB_H + 2, CARD_W - 8, line_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )

        if self.sub_info != "none" and self.sub_text:
            f2 = QFont(config.FONT_FAMILY)
            f2.setPointSize(config.FONT_SIZE_CARD_BADGE)
            p.setFont(f2)
            fm2 = QFontMetrics(f2)
            elided_sub = fm2.elidedText(self.sub_text, Qt.TextElideMode.ElideRight, CARD_W - 8)
            p.setPen(QPen(QColor(COLOR_CARD_SUB_FG)))
            p.drawText(
                QRect(cx + 4, cy + THUMB_H + 2 + line_h, CARD_W - 8, line_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elided_sub,
            )

        p.end()


class TabCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._preview: _CardPreview | None = None
        self._setup_ui()

    def _setup_ui(self):
        page = QWidget()
        root = QHBoxLayout(page)
        root.setContentsMargins(*config.SETTINGS_DIALOG_MARGINS)
        root.setSpacing(config.SETTINGS_CARD_TAB_ROOT_SPACING)

        left = QVBoxLayout()
        left.setSpacing(config.SETTINGS_CARD_TAB_LEFT_SPACING)

        section_badge = QLabel("バッジ・レーティング")
        section_badge.setStyleSheet(
            f"font-weight: bold; color: {COLOR_CARD_SUB_FG}; font-size: {config.SETTINGS_SECTION_LABEL_FONT_SIZE_PX}px;"
        )
        left.addWidget(section_badge)

        self._chk_meta_badge = QCheckBox("メタデータバッジ（✓）を表示")
        self._chk_pages_badge = QCheckBox("ページ数バッジを表示")
        self._chk_star = QCheckBox("星レーティング（★）を表示")
        self._chk_store_icon = QCheckBox("ストアアイコンを表示（DLSite / DMM）")
        for chk in (self._chk_meta_badge, self._chk_pages_badge, self._chk_star, self._chk_store_icon):
            left.addWidget(chk)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {COLOR_BORDER};")
        left.addWidget(sep)

        section_sub = QLabel("カード下部のサブ情報")
        section_sub.setStyleSheet(
            f"font-weight: bold; color: {COLOR_CARD_SUB_FG}; font-size: {config.SETTINGS_SECTION_LABEL_FONT_SIZE_PX}px;"
        )
        left.addWidget(section_sub)

        sub_row = QHBoxLayout()
        sub_label = QLabel("表示する情報：")
        self._combo_sub_info = QComboBox()
        for key, label in SUB_INFO_OPTIONS:
            self._combo_sub_info.addItem(label, key)
        sub_row.addWidget(sub_label)
        sub_row.addWidget(self._combo_sub_info)
        sub_row.addStretch()
        left.addLayout(sub_row)
        left.addStretch()

        right = QVBoxLayout()
        right.setSpacing(config.SETTINGS_CARD_TAB_RIGHT_SPACING)
        preview_label = QLabel("プレビュー")
        preview_label.setStyleSheet(
            f"color: {COLOR_CARD_SUB_FG}; font-size: {config.SETTINGS_SECTION_LABEL_FONT_SIZE_PX}px;"
        )
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        preview = _CardPreview()
        self._preview = preview
        right.addStretch()
        right.addWidget(preview_label, 0, Qt.AlignmentFlag.AlignHCenter)
        right.addWidget(preview, 0, Qt.AlignmentFlag.AlignHCenter)
        right.addStretch()

        root.addLayout(left, 1)
        root.addLayout(right, 0)

        self._chk_meta_badge.stateChanged.connect(self._update_preview)
        self._chk_pages_badge.stateChanged.connect(self._update_preview)
        self._chk_star.stateChanged.connect(self._update_preview)
        self._chk_store_icon.stateChanged.connect(self._update_preview)
        self._combo_sub_info.currentIndexChanged.connect(self._update_preview)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner_widget = QWidget()
        inner_layout = QVBoxLayout(inner_widget)
        inner_layout.addWidget(page)
        inner_layout.addStretch()
        scroll.setWidget(inner_widget)
        outer.addWidget(scroll)

    def _update_preview(self):
        if self._preview is None:
            return
        preview = self._preview
        preview.show_meta = self._chk_meta_badge.isChecked()
        preview.show_pages = self._chk_pages_badge.isChecked()
        preview.show_star = self._chk_star.isChecked()
        preview.show_store_icon = self._chk_store_icon.isChecked()
        key = self._combo_sub_info.currentData()
        preview.sub_info = key
        preview.sub_text = SUB_SAMPLE_TEXT.get(key, "")
        preview.update()

    def load(self) -> None:
        def _b(key, default="1"):
            v = db.get_setting(key)
            return v != "0" if v is not None else (default == "1")

        self._chk_meta_badge.setChecked(_b(config.CARD_SETTING_META_BADGE))
        self._chk_pages_badge.setChecked(_b(config.CARD_SETTING_PAGES_BADGE))
        self._chk_star.setChecked(_b(config.CARD_SETTING_STAR))
        self._chk_store_icon.setChecked(_b(config.CARD_SETTING_STORE_ICON))
        saved_sub = db.get_setting(config.CARD_SETTING_SUB_INFO) or config.CARD_SETTING_SUB_INFO_DEFAULT
        for i in range(self._combo_sub_info.count()):
            if self._combo_sub_info.itemData(i) == saved_sub:
                self._combo_sub_info.setCurrentIndex(i)
                break
        self._update_preview()

    def save(self) -> None:
        db.set_setting(config.CARD_SETTING_META_BADGE, "1" if self._chk_meta_badge.isChecked() else "0")
        db.set_setting(config.CARD_SETTING_PAGES_BADGE, "1" if self._chk_pages_badge.isChecked() else "0")
        db.set_setting(config.CARD_SETTING_STAR, "1" if self._chk_star.isChecked() else "0")
        db.set_setting(config.CARD_SETTING_STORE_ICON, "1" if self._chk_store_icon.isChecked() else "0")
        db.set_setting(config.CARD_SETTING_SUB_INFO, self._combo_sub_info.currentData())
