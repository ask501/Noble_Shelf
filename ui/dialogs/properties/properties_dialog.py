from __future__ import annotations

import logging
import os
import re
from typing import Callable, Optional

from PySide6.QtCore import Qt, QThread, Signal, QObject, QEvent
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import config
import db
from book_updater import BookUpdateError, rename_book as bu_rename_book
from ui.dialogs.properties._utils import (
    BTN_CANCEL_STYLE,
    BTN_FETCH_STYLE,
    BTN_SAVE_STYLE,
    MULTI_PLACEHOLDER,
    PropertyFormContext,
    _auto_kana,
    _is_library_root,
    _safe_from_db_path,
    _needs_kana_conversion,
    _parse_multi,
)
from ui.dialogs.properties.meta_apply_dialog import MetaApplyDialog
from ui.dialogs.properties.meta_search_dialog import MetaSearchDialog
from theme import (
    THEME_COLORS,
    apply_dark_titlebar,
    COLOR_STAR_ACTIVE,
    PROPERTY_BULK_HINT_FG,
    PROPERTY_BORDER,
    PROPERTY_THUMB_BG,
    PROPERTY_FOLDER_BG,
    PROPERTY_FOLDER_FG,
    PROPERTY_FOLDER_HOVER_BORDER,
    PROPERTY_STAR_OFF_FG,
)

# _setup_ui(): 下部ボタン列の固定幅（元の直書き互換）
BTN_W = 80


class _ComboMultiSelectFilter(QObject):
    """editable QComboBox のドロップダウンで Ctrl+クリック時に項目を追記し、ポップアップを閉じないようにする"""

    def __init__(self, combo: QComboBox, parent=None):
        super().__init__(parent)
        self._combo = combo

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.MouseButtonRelease:
            return super().eventFilter(obj, event)
        if event.button() != Qt.MouseButton.LeftButton:
            return super().eventFilter(obj, event)
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            return super().eventFilter(obj, event)
        view = self._combo.view()
        if obj != view.viewport():
            return super().eventFilter(obj, event)
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        idx = view.indexAt(pos)
        if not idx.isValid():
            return super().eventFilter(obj, event)
        text = self._combo.itemText(idx.row())
        if not text:
            return super().eventFilter(obj, event)
        le = self._combo.lineEdit()
        if le is None:
            return super().eventFilter(obj, event)
        cur = le.text().strip()
        new_text = (cur + ", " + text) if cur else text
        le.setText(new_text)
        return True  # イベント消費 → ポップアップは閉じない


class PropertyDialog(QDialog):
    def __init__(self, book_or_books: dict | list[dict], parent=None, on_saved: Callable[[str | None], None] | None = None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        if isinstance(book_or_books, list) and len(book_or_books) > 1:
            self._books = list(book_or_books)
            self._book = self._books[0]
            self._bulk = True
        else:
            b = book_or_books if isinstance(book_or_books, dict) else (book_or_books[0] if book_or_books else {})
            self._books = [b]
            self._book = b
            self._bulk = False
        self._on_saved = on_saved

        self._path: str = _safe_from_db_path(self._book.get("path", ""))
        self._name: str = self._book.get("name", "")
        self._title: str = self._book.get("title", "") or self._name
        self._circle: str = self._book.get("circle", "")
        self._cover: str = db.resolve_cover_stored_value(self._book.get("cover", "") or "")
        self._folder_edit_value: str = self._name
        self._folder_manually_edited: bool = False  # フォルダ名ポップアップで手動変更した場合のみ True

        self._new_cover_path: Optional[str] = None

        self._meta = db.get_book_meta(self._path)
        self._excluded = db.is_excluded(self._path)
        bookmarks = db.get_all_bookmarks()
        self._rating = bookmarks.get(self._path, 0)

        # 一括編集時: 選択作品間で値が異なる項目を記録（赤表示・保存時はプレースホルダーのままなら元の値を保持）
        self._multi_fields: set[str] = set()
        self._rating_edited = False
        self._rating_initial = 0
        if self._bulk:
            self._collect_multi_fields()

        self.setFocusPolicy(Qt.ClickFocus)

        self._setup_ui()
        self._load_initial_values()

    def _property_save_perf_cancel_if(self) -> None:
        """保存失敗で MainWindow の計測起点だけクリアする。"""
        parent = self.parent()
        _c = getattr(parent, "_property_save_perf_cancel", None)
        if callable(_c):
            _c()

    def _collect_multi_fields(self):
        """一括編集時、選択作品間で値が異なる項目を self._multi_fields に集める。"""
        for key, getter in [
            ("circle", lambda b: (b.get("circle") or "").strip()),
            ("title", lambda b: (b.get("title") or b.get("name") or "").strip()),
        ]:
            vals = {getter(b) for b in self._books}
            if len(vals) > 1:
                self._multi_fields.add(key)
        all_metas = [db.get_book_meta(_safe_from_db_path(b.get("path", ""))) or {} for b in self._books]
        for key, getter in [
            ("author", lambda m: (m.get("author") or "").strip()),
            ("series", lambda m: (m.get("series") or "").strip()),
            ("tags", lambda m: ", ".join(m.get("tags") or [])),
            ("characters", lambda m: ", ".join(m.get("characters") or [])),
            ("pages", lambda m: str(m.get("pages") or "")),
            ("release_date", lambda m: (m.get("release_date") or "").strip()),
            ("price", lambda m: str(m.get("price") or "")),
            ("dlsite_id", lambda m: (m.get("dlsite_id") or "").strip()),
            ("memo", lambda m: (m.get("memo") or "").strip()),
        ]:
            vals = {getter(m) for m in all_metas}
            if len(vals) > 1:
                self._multi_fields.add(key)
        bookmarks = db.get_all_bookmarks()
        rating_vals = {bookmarks.get(_safe_from_db_path(b.get("path", "")), 0) for b in self._books if b.get("path")}
        if len(rating_vals) > 1:
            self._multi_fields.add("rating")

    def _add_bulk_hint(self, layout: QVBoxLayout, field_key: str):
        """一括編集で値が異なる項目のとき、入力欄直下に赤文字の注意を追加する。"""
        if not self._bulk or field_key not in self._multi_fields:
            return
        _names = {
            "circle": "サークル名", "title": "作品名", "author": "作者", "series": "シリーズ",
            "tags": "タグ", "characters": "キャラクター", "pages": "ページ数", "release_date": "発売日",
            "price": "金額", "dlsite_id": "作品ID", "memo": "メモ", "rating": "お気に入り",
        }
        lbl = QLabel("複数の%sが選択されています" % _names.get(field_key, field_key))
        lbl.setStyleSheet(
            f"color: {PROPERTY_BULK_HINT_FG}; font-size: {config.FONT_SIZE_PROP_HINT}px; padding: 0 0 2px 0;"
        )
        row = QHBoxLayout()
        row.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        spacer = QLabel("")
        spacer.setFixedWidth(config.PROP_LABEL_WIDTH)
        row.addWidget(spacer)
        row.addWidget(lbl, 1)
        layout.addLayout(row)

    def _setup_ui(self):
        self.setWindowTitle(config.APP_TITLE)
        # 縦方向に余裕を持たせて、メモと作品IDが被らないよう高さを拡大
        self.setFixedSize(*config.PROPERTY_DIALOG_SIZE)
        self.setWindowModality(Qt.ApplicationModal)
        self.setStyleSheet(
            f"""
            QDialog {{
                background: {THEME_COLORS["bg_base"]};
                color: {THEME_COLORS["text_main"]};
            }}
            QLineEdit {{
                background: {THEME_COLORS["bg_widget"]};
                color: {THEME_COLORS["text_main"]};
                border: 1px solid {PROPERTY_BORDER};
                border-radius: {config.PROP_ACTION_BTN_RADIUS}px;
                padding: 4px 8px;
            }}
            QLabel {{
                color: {THEME_COLORS["text_main"]};
            }}
            QPushButton {{
                background: {THEME_COLORS["bg_widget"]};
                color: {THEME_COLORS["text_main"]};
                border: 1px solid {PROPERTY_BORDER};
                border-radius: {config.PROP_ACTION_BTN_RADIUS}px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background: {THEME_COLORS["hover"]};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(*config.PROPERTY_DIALOG_MARGINS)
        root.setSpacing(config.PROPERTY_DIALOG_SPACING)

        # 上段: 左カラム + 右カラム
        top = QHBoxLayout()
        top.setSpacing(config.PROPERTY_DIALOG_TOP_SPACING)
        root.addLayout(top)

        # 左カラム（幅160px固定）
        left_widget = QWidget()
        left_widget.setFixedWidth(config.PROPERTY_LEFT_COL_WIDTH)
        left = QVBoxLayout(left_widget)
        left.setSpacing(config.PROPERTY_LEFT_COL_SPACING)
        left.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        top.addWidget(left_widget)

        # サムネイル（クリックで切り抜き）
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(*config.PROPERTY_THUMB_SIZE)
        self._thumb_label.setStyleSheet(f"background:{PROPERTY_THUMB_BG}; border:1px solid {PROPERTY_BORDER};")
        self._thumb_label.setAlignment(Qt.AlignCenter)
        if not self._bulk:
            self._thumb_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self._thumb_label.setToolTip("クリックで切り抜き")
            self._thumb_label.mousePressEvent = self._on_thumb_click_crop
        left.addWidget(self._thumb_label)

        btn_change_cover = QPushButton("画像を変更")
        btn_change_cover.clicked.connect(self._on_change_cover)
        left.addWidget(btn_change_cover)

        # フォルダ名（ポップアップで編集）
        lbl_folder = QLabel("フォルダ名")
        lbl_folder.setToolTip("表示名は「[サークル名]作品名」で表示されます。作品名はこの欄と「作品名」の両方に含まれます。")
        left.addWidget(lbl_folder)
        self._folder_label = QLabel(self._name)
        self._folder_label.setFixedWidth(config.PROPERTY_LEFT_COL_WIDTH)
        self._folder_label.setWordWrap(False)
        self._folder_label.setStyleSheet(
            f"""
            QLabel {{
                background: {PROPERTY_FOLDER_BG};
                border: 1px solid {PROPERTY_BORDER};
                border-radius: {config.PROP_ACTION_BTN_RADIUS}px;
                padding: 4px 8px;
                color: {PROPERTY_FOLDER_FG};
                max-width: {config.PROPERTY_FOLDER_LABEL_MAX_WIDTH}px;
            }}
            QLabel:hover {{ border-color: {PROPERTY_FOLDER_HOVER_BORDER}; }}
            """
        )
        self._folder_label.setCursor(Qt.PointingHandCursor)
        if not self._bulk:
            self._folder_label.mousePressEvent = lambda e: self._open_rename_popup()
        else:
            self._folder_label.setToolTip("一括編集ではフォルダ名の変更はできません")
        left.addWidget(self._folder_label)

        # ブックマーク ★
        star_row = QHBoxLayout()
        star_row.setSpacing(config.PROPERTY_STAR_ROW_SPACING)
        left.addWidget(QLabel("お気に入り"))
        self._star_buttons: list[QPushButton] = []
        for i in range(5):
            idx = i + 1
            btn = QPushButton("☆")
            btn.setFixedSize(*config.PROPERTY_STAR_BTN_SIZE)
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    font-size: {config.FONT_SIZE_RATING_UI}px; padding: 0px;
                    border: none; background: transparent; color: {PROPERTY_STAR_OFF_FG};
                }}
                QPushButton:hover {{ color: {COLOR_STAR_ACTIVE}; background: transparent; }}
                """
            )
            btn.clicked.connect(lambda _=None, r=idx: self._set_rating(r))
            self._star_buttons.append(btn)
            star_row.addWidget(btn)
        star_row.addStretch()
        left.addLayout(star_row)
        if self._bulk and "rating" in self._multi_fields:
            lbl_rating_hint = QLabel("複数のお気に入りが選択されています")
            lbl_rating_hint.setStyleSheet(
                f"color: {PROPERTY_BULK_HINT_FG}; font-size: {config.FONT_SIZE_PROP_HINT}px; padding: 0 0 2px 0;"
            )
            left.addWidget(lbl_rating_hint)

        left.addStretch()

        # 右カラム
        right = QVBoxLayout()
        right.setSpacing(config.PROPERTY_RIGHT_COL_SPACING)
        top.addLayout(right, stretch=1)

        # 作品名・サークル
        row_title = QHBoxLayout()
        row_title.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_title = QLabel("作品名")
        lbl_title.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_title.addWidget(lbl_title)
        self._e_title = QLineEdit()
        self._e_title.setFocusPolicy(Qt.ClickFocus)
        row_title.addWidget(self._e_title, stretch=1)

        # 作品名フリガナ表示切替チェックボックス（かな非表示）
        self._chk_hide_kana = QCheckBox("かな非表示")
        self._chk_hide_kana.setToolTip("チェックするとフリガナ欄を非表示にします。")
        row_title.addWidget(self._chk_hide_kana)

        right.addLayout(row_title)
        self._add_bulk_hint(right, "title")

        # 作品名フリガナ
        row_title_kana = QHBoxLayout()
        row_title_kana.setSpacing(config.PROPERTY_ROW_SPACING)
        spacer_title_kana = QLabel("")
        spacer_title_kana.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_title_kana.addWidget(spacer_title_kana)
        self._e_title_kana = QLineEdit()
        self._e_title_kana.setPlaceholderText("フリガナ（作品名）")
        self._e_title_kana.setFocusPolicy(Qt.ClickFocus)
        row_title_kana.addWidget(self._e_title_kana, stretch=1)
        right.addLayout(row_title_kana)

        row_circle = QHBoxLayout()
        row_circle.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_circle = QLabel("サークル")
        lbl_circle.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_circle.addWidget(lbl_circle)
        self._e_circle = QLineEdit()
        self._e_circle.setFocusPolicy(Qt.ClickFocus)
        row_circle.addWidget(self._e_circle, stretch=1)
        right.addLayout(row_circle)
        self._add_bulk_hint(right, "circle")

        # サークル名フリガナ
        row_circle_kana = QHBoxLayout()
        row_circle_kana.setSpacing(config.PROPERTY_ROW_SPACING)
        spacer_circle_kana = QLabel("")
        spacer_circle_kana.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_circle_kana.addWidget(spacer_circle_kana)
        self._e_circle_kana = QLineEdit()
        self._e_circle_kana.setPlaceholderText("フリガナ（サークル）")
        self._e_circle_kana.setFocusPolicy(Qt.ClickFocus)
        row_circle_kana.addWidget(self._e_circle_kana, stretch=1)
        right.addLayout(row_circle_kana)

        def _on_title_changed(text: str):
            if self._e_title_kana.hasFocus():
                return
            t = text.strip()
            if not t:
                return
            self._e_title_kana.setText(_auto_kana(t))

        def _on_circle_changed(text: str):
            if self._e_circle_kana.hasFocus():
                return
            t = text.strip()
            if not t:
                return
            self._e_circle_kana.setText(_auto_kana(t))

        self._e_title.textChanged.connect(_on_title_changed)
        self._e_circle.textChanged.connect(_on_circle_changed)

        def _sync_folder_from_circle_title():
            if self._bulk or self._folder_manually_edited:
                return
            c = self._e_circle.text().strip()
            t = self._e_title.text().strip()
            synced = db.format_book_name(c, t) or self._name
            self._folder_edit_value = synced
            self._folder_label.setText(synced)

        self._e_title.textChanged.connect(lambda _: _sync_folder_from_circle_title())
        self._e_circle.textChanged.connect(lambda _: _sync_folder_from_circle_title())

        hide_kana_setting = db.get_setting("ui_hide_kana", "0")
        hide_kana = str(hide_kana_setting) == "1"
        self._chk_hide_kana.setChecked(hide_kana)
        self._e_title_kana.setVisible(not hide_kana)
        self._e_circle_kana.setVisible(not hide_kana)

        def _on_hide_kana_toggled(checked: bool):
            self._e_title_kana.setVisible(not checked)
            self._e_circle_kana.setVisible(not checked)
            db.set_setting("ui_hide_kana", "1" if checked else "0")

        self._chk_hide_kana.toggled.connect(_on_hide_kana_toggled)

        # 作者・シリーズ・キャラ・タグ
        row_author = QHBoxLayout()
        row_author.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_author = QLabel("作者")
        lbl_author.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_author.addWidget(lbl_author)
        self._e_author = QComboBox(self)
        self._e_author.setEditable(True)
        self._e_author.setInsertPolicy(QComboBox.NoInsert)
        le = self._e_author.lineEdit()
        if le:
            le.setPlaceholderText("")
        for name, _ in db.get_all_authors_with_count():
            self._e_author.addItem(name)
        row_author.addWidget(self._e_author, stretch=1)
        right.addLayout(row_author)
        self._add_bulk_hint(right, "author")

        row_series = QHBoxLayout()
        row_series.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_series = QLabel("シリーズ")
        lbl_series.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_series.addWidget(lbl_series)
        self._e_series = QComboBox(self)
        self._e_series.setEditable(True)
        self._e_series.setInsertPolicy(QComboBox.NoInsert)
        for name, _ in db.get_all_series_with_count():
            self._e_series.addItem(name)
        row_series.addWidget(self._e_series, stretch=1)
        right.addLayout(row_series)
        self._add_bulk_hint(right, "series")

        row_chars = QHBoxLayout()
        row_chars.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_chars = QLabel("キャラクター")
        lbl_chars.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_chars.addWidget(lbl_chars)
        self._e_chars = QComboBox(self)
        self._e_chars.setEditable(True)
        self._e_chars.setInsertPolicy(QComboBox.NoInsert)
        for name, _ in db.get_all_characters_with_count():
            self._e_chars.addItem(name)
        self._chars_multiselect_filter = _ComboMultiSelectFilter(self._e_chars, self)
        self._e_chars.view().viewport().installEventFilter(self._chars_multiselect_filter)
        row_chars.addWidget(self._e_chars, stretch=1)
        right.addLayout(row_chars)
        self._add_bulk_hint(right, "characters")

        row_tags = QHBoxLayout()
        row_tags.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_tags = QLabel("タグ")
        lbl_tags.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_tags.addWidget(lbl_tags)
        self._e_tags = QComboBox(self)
        self._e_tags.setEditable(True)
        self._e_tags.setInsertPolicy(QComboBox.NoInsert)
        for name, _ in db.get_all_tags_with_count():
            self._e_tags.addItem(name)
        self._tags_multiselect_filter = _ComboMultiSelectFilter(self._e_tags, self)
        self._e_tags.view().viewport().installEventFilter(self._tags_multiselect_filter)
        row_tags.addWidget(self._e_tags, stretch=1)
        right.addLayout(row_tags)
        self._add_bulk_hint(right, "tags")

        # 追加フィールド
        row_pages = QHBoxLayout()
        row_pages.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_pages = QLabel("ページ数")
        lbl_pages.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_pages.addWidget(lbl_pages)
        self._e_pages = QLineEdit()
        row_pages.addWidget(self._e_pages, stretch=1)
        right.addLayout(row_pages)
        self._add_bulk_hint(right, "pages")

        row_release = QHBoxLayout()
        row_release.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_release = QLabel("発売日")
        lbl_release.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_release.addWidget(lbl_release)
        self._e_release = QLineEdit()
        row_release.addWidget(self._e_release, stretch=1)
        right.addLayout(row_release)
        self._add_bulk_hint(right, "release_date")

        row_price = QHBoxLayout()
        row_price.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_price = QLabel("金額")
        lbl_price.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_price.addWidget(lbl_price)
        self._e_price = QLineEdit()
        row_price.addWidget(self._e_price, stretch=1)
        right.addLayout(row_price)
        self._add_bulk_hint(right, "price")

        row_memo = QHBoxLayout()
        row_memo.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_memo = QLabel("メモ")
        lbl_memo.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_memo.addWidget(lbl_memo, alignment=Qt.AlignVCenter)
        self._e_memo = QTextEdit()
        self._e_memo.setFixedHeight(3 * config.PROP_MEMO_LINE_HEIGHT)
        self._e_memo.setStyleSheet(
            f"""
            QTextEdit {{
                border: 1px solid {PROPERTY_BORDER};
                border-radius: {config.PROP_ACTION_BTN_RADIUS}px;
                padding: 4px;
            }}
            """
        )
        row_memo.addWidget(self._e_memo, stretch=1)
        right.addLayout(row_memo)
        self._add_bulk_hint(right, "memo")

        row_id = QHBoxLayout()
        row_id.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_id = QLabel("作品ID")
        lbl_id.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_id.addWidget(lbl_id)
        self._e_dlsite_id = QLineEdit()
        self._e_dlsite_id.setFocusPolicy(Qt.ClickFocus)
        row_id.addWidget(self._e_dlsite_id, stretch=1)
        self._btn_exclude = QPushButton("除外")
        self._btn_exclude.setFixedWidth(config.PROPERTY_EXCLUDE_BTN_WIDTH)
        self._btn_exclude.clicked.connect(self._on_toggle_excluded)
        row_id.addWidget(self._btn_exclude)
        right.addLayout(row_id)
        self._add_bulk_hint(right, "dlsite_id")

        row_url = QHBoxLayout()
        row_url.setSpacing(config.PROPERTY_ROW_SPACING)
        lbl_url = QLabel("商品URL")
        lbl_url.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_url.addWidget(lbl_url)
        self._e_store_url = QLineEdit()
        self._e_store_url.setFocusPolicy(Qt.ClickFocus)
        self._e_store_url.setPlaceholderText("https://...")
        row_url.addWidget(self._e_store_url, stretch=1)
        right.addLayout(row_url)

        right.addStretch()

        # 下部ボタン
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(config.PROPERTY_BOTTOM_ROW_SPACING)

        btn_save = QPushButton("保存")
        btn_cancel = QPushButton("キャンセル")

        btn_save.setStyleSheet(BTN_SAVE_STYLE)
        btn_cancel.setStyleSheet(BTN_CANCEL_STYLE)

        btn_save.setFixedSize(*config.PROPERTY_ACTION_BTN_SIZE)
        btn_cancel.setFixedSize(*config.PROPERTY_ACTION_BTN_SIZE)

        bottom_row.addSpacing(BTN_W)
        bottom_row.addStretch()
        bottom_row.addWidget(btn_save)
        bottom_row.addWidget(btn_cancel)
        try:
            from plugin_loader import get_plugin_property_widgets

            ctx = PropertyFormContext(self)
            for w in get_plugin_property_widgets(ctx):
                if isinstance(w, QPushButton):
                    w.setStyleSheet(BTN_FETCH_STYLE)
                    w.setFixedSize(BTN_W, config.PROPERTY_ACTION_BTN_SIZE[1])
                bottom_row.addWidget(w) 
        except Exception as e:
            logging.warning("[properties_dialog] プラグインプロパティUI追加失敗: %s", e)
        bottom_row.addStretch()


        btn_save.clicked.connect(self._on_save)
        btn_cancel.clicked.connect(self._on_cancel)

        root.addLayout(bottom_row)

    def mousePressEvent(self, event):
        focused = self.focusWidget()
        if focused:
            focused.clearFocus()
        super().mousePressEvent(event)

    def _load_initial_values(self):
        # サムネ
        if self._cover and os.path.exists(self._cover):
            pix = QPixmap(self._cover)
            if not pix.isNull():
                self._thumb_label.setPixmap(pix.scaled(160, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        # 文字項目（一括時は値が揃っている項目だけ表示、異なる項目はプレースホルダー）
        # 表示名: サークルあり→[サークル名]作品名、なし→作品名のみ
        canonical_folder = db.format_book_name(self._circle or "", self._title or "") or self._name
        self._folder_edit_value = canonical_folder
        self._folder_manually_edited = False
        self._folder_label.setText(canonical_folder)
        if self._bulk:
            self._e_title.setText(MULTI_PLACEHOLDER if "title" in self._multi_fields else self._title)
            self._e_circle.setText(MULTI_PLACEHOLDER if "circle" in self._multi_fields else self._circle)
        else:
            self._e_title.setText(self._title)
            self._e_circle.setText(self._circle)

        # メタデータ由来
        if self._bulk:
            self._e_title_kana.setText("" if "title" in self._multi_fields else self._meta.get("title_kana", ""))
            self._e_circle_kana.setText("" if "circle" in self._multi_fields else self._meta.get("circle_kana", ""))
            self._e_author.setEditText(MULTI_PLACEHOLDER if "author" in self._multi_fields else self._meta.get("author", ""))
            self._e_series.setEditText(MULTI_PLACEHOLDER if "series" in self._multi_fields else self._meta.get("series", ""))
            self._e_chars.setEditText(MULTI_PLACEHOLDER if "characters" in self._multi_fields else ", ".join(self._meta.get("characters", [])))
            self._e_tags.setEditText(MULTI_PLACEHOLDER if "tags" in self._multi_fields else ", ".join(self._meta.get("tags", [])))
            self._e_dlsite_id.setText(MULTI_PLACEHOLDER if "dlsite_id" in self._multi_fields else self._meta.get("dlsite_id", ""))
            self._e_store_url.setText(MULTI_PLACEHOLDER if "store_url" in self._multi_fields else self._meta.get("store_url", ""))
            self._e_pages.setText(MULTI_PLACEHOLDER if "pages" in self._multi_fields else (str(self._meta.get("pages", "")) if self._meta.get("pages") else ""))
            self._e_release.setText(MULTI_PLACEHOLDER if "release_date" in self._multi_fields else self._meta.get("release_date", ""))
            self._e_price.setText(MULTI_PLACEHOLDER if "price" in self._multi_fields else (str(self._meta.get("price", "")) if self._meta.get("price") else ""))
            self._e_memo.setPlainText(MULTI_PLACEHOLDER if "memo" in self._multi_fields else self._meta.get("memo", ""))
        else:
            self._e_title_kana.setText(self._meta.get("title_kana", ""))
            self._e_circle_kana.setText(self._meta.get("circle_kana", ""))
            self._e_author.setEditText(self._meta.get("author", ""))
            self._e_series.setEditText(self._meta.get("series", ""))
            self._e_chars.setEditText(", ".join(self._meta.get("characters", [])))
            self._e_tags.setEditText(", ".join(self._meta.get("tags", [])))
            self._e_dlsite_id.setText(self._meta.get("dlsite_id", ""))
            self._e_store_url.setText(self._meta.get("store_url", ""))
            self._e_pages.setText(str(self._meta.get("pages", "")) if self._meta.get("pages") else "")
            self._e_release.setText(self._meta.get("release_date", ""))
            self._e_price.setText(str(self._meta.get("price", "")) if self._meta.get("price") else "")
            self._e_memo.setPlainText(self._meta.get("memo", ""))

        # フリガナが空欄、または漢字が含まれている場合は自動生成して埋める
        try:
            if (not self._e_title_kana.text().strip() or _needs_kana_conversion(self._e_title_kana.text())) \
                    and self._e_title.text().strip():
                kana = _auto_kana(self._e_title.text().strip())
                self._e_title_kana.setText(kana)
            if (not self._e_circle_kana.text().strip() or _needs_kana_conversion(self._e_circle_kana.text())) \
                    and self._e_circle.text().strip():
                kana = _auto_kana(self._e_circle.text().strip())
                self._e_circle_kana.setText(kana)
        except Exception as e:
            logging.warning("[properties_dialog] かな自動補完失敗: %s", e)

        # 除外状態
        self._update_excluded_ui()

        # お気に入り表示（一括時は「複数」なら初期値を記録し、星は1件目で表示）
        if self._bulk and "rating" in self._multi_fields:
            self._rating_initial = self._rating
        # 初期は保存せず描画のみ
        self._set_rating(self._rating, save=False)

    def _on_meta_search(self):
        dlg = MetaSearchDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.result:
            return
        meta = dlg.result

        # 現在値を収集
        current = {
            "title":        self._e_title.text(),
            "circle":       self._e_circle.text(),
            "author":       self._e_author.currentText(),
            "series":       self._e_series.currentText(),
            "tags":         self._e_tags.currentText(),
            "characters":   self._e_chars.currentText(),
            "pages":        self._e_pages.text(),
            "release_date": self._e_release.text(),
            "price":        self._e_price.text(),
            "dlsite_id":    self._e_dlsite_id.text(),
            "cover":        self._cover or "",
        }
        meta["dlsite_id"] = meta.get("dojindb_url") or meta.get("id") or ""
        meta["image_url"] = meta.get("cover_url", "")
        apply_dlg = MetaApplyDialog(current, meta, self, book_path=self._path)
        ret = apply_dlg.exec()
        if ret != QDialog.Accepted:
            return

        applied = apply_dlg.selected_keys()
        if "title"        in applied: self._e_title.setText(applied["title"])
        if "circle"       in applied: self._e_circle.setText(applied["circle"])
        if "author"       in applied: self._e_author.setEditText(applied["author"])
        if "series"       in applied: self._e_series.setEditText(applied["series"])
        if "tags"         in applied: self._e_tags.setEditText(applied["tags"])
        if "characters"   in applied: self._e_chars.setEditText(applied["characters"])
        if "pages"        in applied: self._e_pages.setText(applied["pages"])
        if "release_date" in applied: self._e_release.setText(applied["release_date"])
        if "price"        in applied: self._e_price.setText(applied["price"])
        if "dlsite_id"    in applied: self._e_dlsite_id.setText(applied["dlsite_id"])
        if applied.get("cover_path"):
            db.set_cover_custom(self._path, applied["cover_path"])
            self._new_cover_path = applied["cover_path"]
            pix = QPixmap(applied["cover_path"])
            if not pix.isNull():
                self._thumb_label.setPixmap(pix.scaled(160, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            # 必ず DB 保存後に cleanup（保存前にクリアされないよう順序保証）
            db.cleanup_unused_cover_cache()

    def _apply_meta_to_form(self, meta: dict):
        if meta.get("title"):
            self._e_title.setText(meta["title"])
        if meta.get("circle"):
            self._e_circle.setText(meta["circle"])
        if meta.get("title_kana"):
            self._e_title_kana.setText(meta["title_kana"])
        if meta.get("circle_kana"):
            self._e_circle_kana.setText(meta["circle_kana"])
        if meta.get("author"):
            self._e_author.setEditText(meta["author"])
        if meta.get("parody"):
            self._e_series.setEditText(meta["parody"])
        if meta.get("characters"):
            self._e_chars.setEditText(", ".join(meta["characters"]))
        if meta.get("tags"):
            self._e_tags.setEditText(", ".join(meta["tags"]))

        # 追加フィールド
        if meta.get("pages") is not None:
            self._e_pages.setText(str(meta.get("pages") or ""))
        if meta.get("release_date"):
            import re as _re
            rd = meta["release_date"]
            _m = _re.match(r"(\\d{4})[-/\\.](\\d{1,2})[-/\\.](\\d{1,2})", rd)
            if _m:
                rd = f"{_m.group(1)}年{int(_m.group(2))}月{int(_m.group(3))}日"
            self._e_release.setText(rd)
        if meta.get("price") is not None:
            self._e_price.setText(str(meta.get("price") or ""))
        if meta.get("memo"):
            self._e_memo.setPlainText(meta["memo"])

        # 作品IDフィールド（DojinDB URLを優先、なければDLSite ID）
        if meta.get("dojindb_url"):
            self._e_dlsite_id.setText(meta["dojindb_url"])
        elif meta.get("id"):
            self._e_dlsite_id.setText(meta["id"])

    # ── お気に入り ★ ────────────────────────────────────

    def _set_rating(self, rating: int, save: bool = True):
        self._rating = rating
        if self._bulk and save:
            self._rating_edited = True
        if save and not self._bulk:
            db.set_bookmark(self._path, rating)
            if self._on_saved:
                self._on_saved()
        for i, btn in enumerate(self._star_buttons, start=1):
            filled = i <= rating
            btn.setText("★" if filled else "☆")
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    font-size: {config.FONT_SIZE_RATING_UI}px; padding: 0px;
                    border: none; background: transparent;
                    color: {"%s" % COLOR_STAR_ACTIVE if filled else "%s" % PROPERTY_STAR_OFF_FG};
                }}
                QPushButton:hover {{ color: {COLOR_STAR_ACTIVE}; background: transparent; }}
                """
            )

    # ── カバー画像変更 ────────────────────────────────────

    def _on_change_cover(self):
        if self._cover and os.path.isabs(self._cover):
            start_dir = os.path.dirname(self._cover)
        else:
            start_dir = config.COVER_CACHE_DIR
        fname, _ = QFileDialog.getOpenFileName(
            self,
            "カバー画像を選択",
            start_dir,
            "画像ファイル (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if not fname:
            return
        pix = QPixmap(fname)
        if pix.isNull():
            QMessageBox.warning(self, "エラー", "画像を読み込めませんでした。")
            return
        self._new_cover_path = fname
        self._thumb_label.setPixmap(
            pix.scaled(
                config.PROPERTY_THUMB_SIZE[0],
                config.PROPERTY_THUMB_SIZE[1],
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def _on_thumb_click_crop(self, event):
        """サムネイルクリック時: イベントを消費して切り抜きを開く（フォルダ名クリックと誤反応しないように）"""
        if event is not None:
            event.accept()
        self._on_crop_cover()

    def _on_crop_cover(self):
        """現在のサムネイルから切り抜き（cover_cacheに保存）"""
        from ui.dialogs.thumbnail_crop_dialog import ThumbnailCropDialog
        src = self._new_cover_path or self._cover
        if not src or not os.path.exists(src):
            QMessageBox.information(self, "切り抜き", "切り抜きする画像がありません。先に「画像を変更」で画像を設定してください。")
            return
        dlg = ThumbnailCropDialog(src, self._path, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.result_path:
            return
        self._new_cover_path = dlg.result_path
        pix = QPixmap(dlg.result_path)
        if not pix.isNull():
            self._thumb_label.setPixmap(
                pix.scaled(
                    config.PROPERTY_THUMB_SIZE[0],
                    config.PROPERTY_THUMB_SIZE[1],
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    # ── フォルダ名ポップアップ ─────────────────────────────

    def _open_rename_popup(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(config.APP_TITLE)
        dlg.setMinimumWidth(config.PROPERTY_RENAME_POPUP_MIN_WIDTH)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(*config.PROPERTY_RENAME_POPUP_MARGINS)
        layout.setSpacing(config.PROPERTY_RENAME_POPUP_SPACING)

        lbl = QLabel("新しいフォルダ名:")
        layout.addWidget(lbl)

        edit = QLineEdit(self._folder_edit_value)
        layout.addWidget(edit)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("キャンセル")
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        btn_cancel.clicked.connect(dlg.reject)

        def _accept():
            text = edit.text().strip()
            if not text:
                return
            self._folder_edit_value = text
            self._folder_label.setText(text)
            self._folder_label.setToolTip(text)
            self._folder_manually_edited = True  # ポップアップで明示的に変更した
            dlg.accept()

        btn_ok.clicked.connect(_accept)

        dlg.exec()

    # ── 作品IDメタデータ取得 ──────────────────────────────

    def _on_fetch_meta(self):
        text = self._e_dlsite_id.text().strip()
        if not text:
            QMessageBox.warning(self, "エラー", "作品IDまたはURLを入力してください。")
            return

        # URL判定
        if text.startswith("http"):
            import re

            if "dojindb.net" in text:
                self._fetch_by_url_dojindb(text)
                return
            m = re.search(r"product_id[/=]([A-Z0-9_]+)", text, re.IGNORECASE)
            if m:
                product_id = m.group(1).upper()
            else:
                QMessageBox.warning(self, "エラー", "URLから作品IDを取得できませんでした。")
                return
            source = "FANZA" if "dmm.co.jp" in text or "fanza" in text else "DLSite"
        else:
            product_id = text.upper()
            # D_ = FANZA、RJ/BJ/VJ = DLSite（DLSITE_API 対応）
            source = "FANZA" if product_id.startswith("D_") else "DLSite"

        self._run_fetch_worker(product_id, source)

    def _fetch_by_url_dojindb(self, url: str):
        from PySide6.QtWidgets import QProgressDialog

        progress = QProgressDialog("取得中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        class _DojinWorker(QThread):
            done = Signal(object)

            def __init__(self, url: str):
                super().__init__()
                self._url = url

            def run(self):
                meta = None
                try:
                    from plugin_loader import get_plugins
                    for plugin in get_plugins():
                        meta = plugin.get_metadata_sync(self._url)
                        if meta:
                            break
                except Exception as e:
                    logging.warning("[properties_dialog] メタ取得（URL・同人DB）失敗: %s", e)
                self.done.emit(meta)

        self._meta_worker = _DojinWorker(url)

        def _on_done(meta):
            progress.close()
            if not meta:
                QMessageBox.warning(self, "取得失敗", "メタデータを取得できませんでした。")
                return
            self._apply_meta_to_form(meta)

        self._meta_worker.done.connect(_on_done)
        self._meta_worker.finished.connect(self._meta_worker.deleteLater)
        self._meta_worker.start()

    def _run_fetch_worker(self, product_id: str, source: str):
        from PySide6.QtWidgets import QProgressDialog

        progress = QProgressDialog("メタデータ取得中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()

        class _Worker(QThread):
            done = Signal(object)

            def __init__(self, pid: str, source: str):
                super().__init__()
                self._pid = pid
                self._source = source

            def run(self):
                result = None
                try:
                    from plugin_loader import get_plugins
                    for plugin in get_plugins():
                        can = getattr(plugin, "can_handle", None)
                        if can and not can(self._pid):
                            continue
                        result = plugin.get_metadata_sync(self._pid)
                        if result:
                            break
                except Exception as e:
                    logging.warning("[properties_dialog] メタ取得（製品ID）失敗: %s", e)
                self.done.emit(result)

        self._meta_worker = _Worker(product_id, source)

        def _on_done(meta):
            progress.close()
            if not meta:
                QMessageBox.warning(self, "取得失敗", "メタデータを取得できませんでした。")
                return
            self._apply_meta_to_form(meta)

        self._meta_worker.done.connect(_on_done)
        self._meta_worker.finished.connect(self._meta_worker.deleteLater)
        self._meta_worker.start()

    # ── 除外/解除 ────────────────────────────────────────

    def _on_toggle_excluded(self):
        new_val = not self._excluded
        db.set_excluded(self._path, new_val)
        self._excluded = new_val
        self._update_excluded_ui()

    def _update_excluded_ui(self):
        if self._excluded:
            self._e_dlsite_id.setText("除外")
            self._e_dlsite_id.setEnabled(False)
            self._btn_exclude.setText("解除")
        else:
            if self._e_dlsite_id.text() == "除外":
                self._e_dlsite_id.clear()
            self._e_dlsite_id.setEnabled(True)
            self._btn_exclude.setText("除外")

    # ── 保存処理 ─────────────────────────────────────────

    def _on_save(self):
        if not self._path and not self._bulk:
            self.accept()
            return
        if self._bulk and not self._books:
            self.accept()
            return

        parent = self.parent()
        _perf_start = getattr(parent, "_property_save_perf_start", None)
        if callable(_perf_start):
            _perf_start()

        path = self._path
        original_path_for_db = path  # rename_book(old, new) で DB を更新するときの old（誤った path のままの可能性あり）
        lib_root = (db.get_setting("library_folder") or "").strip()

        # パスが実在しない（昔のフォルダ名だけなどで登録されている場合）は、ライブラリ配下から正しいパスを解決する
        if path and not (os.path.isdir(path) or os.path.isfile(path)):
            lib = (db.get_setting("library_folder") or "").strip()
            new_circle_early = self._e_circle.text().strip()
            new_title_early = self._e_title.text().strip()
            resolved = db.resolve_book_path(lib, self._name, new_circle_early or self._circle, new_title_early or self._title, path)
            if resolved:
                path = resolved
                self._path = resolved
                # DB にはまだ誤った path で登録されているので、rename_book では original_path_for_db を old に渡す
            else:
                QMessageBox.warning(
                    self,
                    "保存できません",
                    "この作品のパスが無効です。\n設定の「誤ったパスを修復」を実行するか、正しいフォルダがライブラリ内に存在するか確認してください。",
                )
                self._property_save_perf_cancel_if()
                return

        # リネーム用の表示名: フォルダ名を手動変更していなければサークル・作品名から組み立て（サークル追加で自動リネーム）
        new_circle = self._e_circle.text().strip()
        new_title = self._e_title.text().strip()
        if self._folder_manually_edited:
            folder_text = self._folder_edit_value.strip() or db.format_book_name(new_circle, new_title) or self._name
        else:
            folder_text = db.format_book_name(new_circle, new_title) or self._name
        new_circle_folder, new_title_folder = db.parse_display_name(folder_text)
        new_name = db.format_book_name(new_circle_folder, new_title_folder)

        # 右カラムの値（DB用）。作品名が空のときはフォルダ名から取りた作品名を使う
        new_title = new_title or new_title_folder

        if self._bulk:
            self._apply_bulk_save(new_circle, new_title)
            return

        # リネーム: フォルダ名欄が変わった場合のみ（リネーム対象がライブラリルートのときは禁止）
        # FS のリネームはここで行い、DB 反映は book_updater に委譲する
        new_path = path
        if new_name != self._name:
            try:
                if os.path.isdir(path):
                    # フォルダのリネーム: path がライブラリルートそのものなら禁止
                    if _is_library_root(path):
                        QMessageBox.critical(self, "リネーム不可", "ライブラリフォルダ自体の名前は変更できません。")
                        self._property_save_perf_cancel_if()
                        return
                    base_dir = os.path.dirname(path)
                    new_path = os.path.join(base_dir, new_name)
                    if new_path != path:
                        os.rename(path, new_path)
                else:
                    # ファイル（PDF/ストアファイル等）のリネーム
                    parent_dir = os.path.dirname(path)
                    if _is_library_root(parent_dir):
                        # ライブラリ直下のファイル → ファイル自体をリネーム（例: Book.dlst → NewName.dlst）
                        ext = os.path.splitext(path)[1]
                        new_path = os.path.join(parent_dir, new_name + ext)
                        if new_path != path:
                            os.rename(path, new_path)
                    else:
                        # サブフォルダ内のファイル（例: Library/[サークル]作品/作品.pdf）→ 親フォルダをリネーム
                        grand = os.path.dirname(parent_dir)
                        new_parent = os.path.join(grand, new_name)
                        if new_parent != parent_dir:
                            os.rename(parent_dir, new_parent)
                        new_path = os.path.join(new_parent, os.path.basename(path))
            except Exception as e:
                QMessageBox.critical(self, "リネームエラー", str(e))
                self._property_save_perf_cancel_if()
                return

        # カバー（set_cover_custom は rename_book の後に実行し、必ず DB 保存後に cleanup が動くようにする）
        new_cover = self._cover
        if self._new_cover_path:
            new_cover = self._new_cover_path
        # リネームした場合、カバーが旧パス配下なら新パスに差し替え（参照切れで黒サムネにならないように）
        if new_path != path and new_cover:
            old_base = path if os.path.isdir(path) else os.path.dirname(path)
            new_base = new_path if os.path.isdir(path) else os.path.dirname(new_path)
            ob = os.path.normpath(old_base)
            nb = os.path.normpath(new_base)
            nc = os.path.normpath(new_cover)
            if nc == ob or nc.startswith(ob + os.sep):
                new_cover = nb + nc[len(ob):]

        # メタ情報
        author = self._e_author.currentText().strip()
        series = self._e_series.currentText().strip()
        chars = _parse_multi(self._e_chars.currentText())
        tags = _parse_multi(self._e_tags.currentText())

        # 追加フィールド
        pages_text = self._e_pages.text().strip()
        try:
            pages = int(pages_text) if pages_text else None
        except ValueError:
            pages = None
        release_date = self._e_release.text().strip()
        # 日付正規化: 各種形式 → yyyy年m月d日
        import re as _re
        _m = _re.match(r"(\\d{4})[-/\\.](\\d{1,2})[-/\\.](\\d{1,2})", release_date)
        if _m:
            release_date = f"{_m.group(1)}年{int(_m.group(2))}月{int(_m.group(3))}日"
        price_text = self._e_price.text().strip()
        try:
            price = int(price_text) if price_text else None
        except ValueError:
            price = None
        memo = self._e_memo.toPlainText().strip()

        # フリガナ（空欄なら保存直前に自動生成）
        title_kana = self._e_title_kana.text().strip()
        circle_kana = self._e_circle_kana.text().strip()

        if not title_kana and self._e_title.text().strip():
            title_kana = _auto_kana(self._e_title.text().strip())
            self._e_title_kana.setText(title_kana)
        if not circle_kana and self._e_circle.text().strip():
            circle_kana = _auto_kana(self._e_circle.text().strip())
            self._e_circle_kana.setText(circle_kana)

        dlsite_id_text = self._e_dlsite_id.text().strip()
        dlsite_id = None
        if not self._excluded:
            dlsite_id = dlsite_id_text
        store_url_text = self._e_store_url.text().strip()
        store_url = store_url_text if store_url_text else None
        # URL・作品IDから取得元を推定して保存（サイドバー振り分け用）
        meta_src = (db._effective_meta_source("", dlsite_id_text or "") or None) if dlsite_id_text else None

        # DB 反映（誤った path から修復した場合は original_path_for_db で DB の行を特定する）
        _db_old = (
            original_path_for_db
            if os.path.normpath(original_path_for_db) != os.path.normpath(path)
            else None
        )
        try:
            bu_rename_book(
                path,
                new_path,
                new_name,
                new_circle,
                new_title,
                new_cover or None,
                db_old_path=_db_old,
                skip_fs_rename=True,
            )
        except BookUpdateError as e:
            QMessageBox.critical(self, "DB更新エラー", str(e))
            self._property_save_perf_cancel_if()
            return

        try:
            new_db_path = db.to_db_path_from_any(new_path)
        except ValueError as e:
            QMessageBox.critical(self, "DB更新エラー", str(e))
            self._property_save_perf_cancel_if()
            return

        # カバー変更時は必ず DB に保存してから cleanup（保存前にクリアされないよう順序を保証）
        if self._new_cover_path:
            db.set_cover_custom(new_db_path, self._new_cover_path)

        # メタ情報を保存
        db.set_book_meta(
            new_db_path,
            author=author,
            type_="",
            series=series,
            characters=chars,
            tags=tags,
            dlsite_id=dlsite_id,
            title_kana=title_kana,
            circle_kana=circle_kana,
            pages=pages,
            release_date=release_date,
            price=price,
            memo=memo,
            meta_source=meta_src,
            store_url=store_url,
        )

        # パス・カバーの内部状態更新
        self._path = new_path
        self._cover = new_cover
        self._new_cover_path = None

        # カバーを変更した場合は未使用のcover_cacheを削除
        if new_cover:
            db.cleanup_unused_cover_cache()

        # 保存完了後のUI更新（単一ブックのみ）
        _perf_log = getattr(parent, "_property_save_perf_log", None)
        if callable(_perf_log):
            _perf_log("dialog_saved")
        if self._on_saved:
            self._on_saved(new_path)

        self.accept()

    def _apply_bulk_save(self, new_circle: str, new_title: str):
        """一括編集: プレースホルダーでない項目だけ上書き。プレースホルダーのままなら各作品の元の値を保持。"""
        import re as _re
        bookmarks = db.get_all_bookmarks()

        def _get(form_val: str, multi_key: str, orig_val: str):
            if multi_key in self._multi_fields and (form_val.strip() == MULTI_PLACEHOLDER or form_val.strip() == ""):
                return orig_val
            return form_val.strip() if form_val.strip() != MULTI_PLACEHOLDER else orig_val

        def _get_int(form_val: str, multi_key: str, orig_val: int | None) -> int | None:
            if multi_key in self._multi_fields and (form_val.strip() == MULTI_PLACEHOLDER or form_val.strip() == ""):
                return orig_val
            if form_val.strip() == "" or form_val.strip() == MULTI_PLACEHOLDER:
                return None
            try:
                return int(form_val.strip())
            except ValueError:
                return None

        for b in self._books:
            p = _safe_from_db_path(b.get("path", ""))
            if not p:
                continue
            try:
                p_db = db.to_db_path_from_any(p)
            except ValueError:
                continue
            meta = db.get_book_meta(p) or {}
            orig_circle = (b.get("circle") or "").strip()
            orig_title = (b.get("title") or b.get("name") or "").strip()
            nc = _get(self._e_circle.text(), "circle", orig_circle)
            nt = _get(self._e_title.text(), "title", orig_title)

            author = _get(self._e_author.currentText(), "author", (meta.get("author") or "").strip())
            series = _get(self._e_series.currentText(), "series", (meta.get("series") or "").strip())
            chars_raw = self._e_chars.currentText().strip()
            if "characters" in self._multi_fields and (chars_raw == MULTI_PLACEHOLDER or chars_raw == ""):
                chars = meta.get("characters") or []
            else:
                chars = _parse_multi(chars_raw) if chars_raw != MULTI_PLACEHOLDER else (meta.get("characters") or [])
            tags_raw = self._e_tags.currentText().strip()
            if "tags" in self._multi_fields and (tags_raw == MULTI_PLACEHOLDER or tags_raw == ""):
                tags = meta.get("tags") or []
            else:
                tags = _parse_multi(tags_raw) if tags_raw != MULTI_PLACEHOLDER else (meta.get("tags") or [])
            pages = _get_int(self._e_pages.text(), "pages", meta.get("pages"))
            release_date = _get(self._e_release.text(), "release_date", (meta.get("release_date") or "").strip())
            if release_date and release_date != MULTI_PLACEHOLDER:
                _m = _re.match(r"(\\d{4})[-/\.](\\d{1,2})[-/\.](\\d{1,2})", release_date)
                if _m:
                    release_date = f"{_m.group(1)}年{int(_m.group(2))}月{int(_m.group(3))}日"
            price = _get_int(self._e_price.text(), "price", meta.get("price"))
            memo = _get(self._e_memo.toPlainText(), "memo", (meta.get("memo") or "").strip())
            dlsite_id_text = self._e_dlsite_id.text().strip()
            if "dlsite_id" in self._multi_fields and (dlsite_id_text == MULTI_PLACEHOLDER or dlsite_id_text == ""):
                dlsite_id = meta.get("dlsite_id") or ""
            else:
                dlsite_id = dlsite_id_text if dlsite_id_text != MULTI_PLACEHOLDER else (meta.get("dlsite_id") or "")
            meta_src = (db._effective_meta_source("", dlsite_id or "") or None) if dlsite_id else None

            if "title" in self._multi_fields and self._e_title.text().strip() in (MULTI_PLACEHOLDER, ""):
                title_kana = (meta.get("title_kana") or "").strip()
            else:
                title_kana = self._e_title_kana.text().strip()
                if not title_kana and nt:
                    title_kana = _auto_kana(nt)
            if "circle" in self._multi_fields and self._e_circle.text().strip() in (MULTI_PLACEHOLDER, ""):
                circle_kana = (meta.get("circle_kana") or "").strip()
            else:
                circle_kana = self._e_circle_kana.text().strip()
                if not circle_kana and nc:
                    circle_kana = _auto_kana(nc)

            if "rating" in self._multi_fields and not self._rating_edited:
                apply_rating = bookmarks.get(p, 0)
            else:
                apply_rating = self._rating

            try:
                db.update_book_display(p_db, circle=nc, title=nt)
                db.set_book_meta(
                    p_db,
                    author=author,
                    type_="",
                    series=series,
                    characters=chars,
                    tags=tags,
                    dlsite_id=dlsite_id or None,
                    title_kana=title_kana or None,
                    circle_kana=circle_kana or None,
                    pages=pages,
                    release_date=release_date or None,
                    price=price,
                    memo=memo or None,
                    meta_source=meta_src,
                )
                db.set_bookmark(p_db, apply_rating)
            except Exception as e:
                QMessageBox.critical(self, "DB更新エラー", "パス: %s\n%s" % (p, str(e)))
                self._property_save_perf_cancel_if()
                return
        _perf_log = getattr(self.parent(), "_property_save_perf_log", None)
        if callable(_perf_log):
            _perf_log("dialog_saved")
        if self._on_saved:
            self._on_saved(None)
        self.accept()

    def _on_cancel(self):
        self.reject()

