"""
properties.py - プロパティダイアログ & 名前変更ダイアログ（PySide6版）

- PropertyDialog: 作品のメタデータ編集・お気に入り・カバー変更
- RenameDialog:   サークル名 / 作品名の変更のみ行う簡易ダイアログ
"""
from __future__ import annotations

import os
import re
import unicodedata
import time
from typing import Callable, Optional

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QObject, QEvent
from PySide6.QtGui import QPixmap, QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QWidget,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QTextEdit,
    QCheckBox,
)

import db

# 一括編集で値が異なる項目のプレースホルダー（書き換えれば一括上書き、そのままだと元の値を保持）
MULTI_PLACEHOLDER = "（複数選択）"


def _is_library_root(path: str) -> bool:
    """指定パスがライブラリフォルダそのものであればTrue（リネーム禁止のガード用）"""
    if not path or not path.strip():
        return False
    lib = (db.get_setting("library_folder") or "").strip()
    if not lib:
        return False
    return os.path.normpath(os.path.abspath(path)) == os.path.normpath(os.path.abspath(lib))


def _meta_source_for_apply(meta: dict, applied: dict) -> str | None:
    """メタ適用時の取得元キー。URL・DLSite API に基づく。dlsite, fanza, とらのあな, 同人DB, other のいずれかまたは None。"""
    did = (applied.get("dlsite_id") or "").strip()
    if meta.get("dojindb_url") or "dojindb.net" in did:
        return "同人DB"
    src = meta.get("source")
    if src == "とらのあな":
        return "とらのあな"
    if src == "FANZA":
        return "fanza"
    if src == "DLSite":
        return "dlsite"
    if src == "同人DB":
        return "同人DB"
    return db._effective_meta_source("", did) or None
import config
from theme import (
    THEME_COLORS,
    apply_dark_titlebar,
    COLOR_WHITE,
    COLOR_BTN_SAVE,
    COLOR_BTN_SAVE_BORDER,
    COLOR_BTN_CANCEL,
    COLOR_BTN_CANCEL_BORDER,
    COLOR_BTN_FETCH,
    COLOR_BTN_FETCH_BORDER,
    COLOR_STAR_ACTIVE,
    COLOR_THUMB_BG,
    COLOR_FOLDER_BG,
    SITE_COLORS,
)

try:
    # pykakasi（新API）によるフリガナ自動生成
    import pykakasi

    _KKS = pykakasi.kakasi()
except Exception:  # pykakasi 未インストールなど
    _KKS = None


# ボタン用スタイル（theme の定数を使用）
BTN_SAVE_STYLE = f"""
    QPushButton {{
        background: {COLOR_BTN_SAVE}; color: {COLOR_WHITE};
        border: 1px solid {COLOR_BTN_SAVE_BORDER}; border-radius: 4px;
        padding: 6px 20px; font-size: {config.FONT_SIZE_BTN_ACTION}px;
    }}
    QPushButton:hover {{ background: {COLOR_BTN_SAVE_BORDER}; }}
"""
BTN_CANCEL_STYLE = f"""
    QPushButton {{
        background: {COLOR_BTN_CANCEL}; color: {COLOR_WHITE};
        border: 1px solid {COLOR_BTN_CANCEL_BORDER}; border-radius: 4px;
        padding: 6px 20px; font-size: {config.FONT_SIZE_BTN_ACTION}px;
    }}
    QPushButton:hover {{ background: {COLOR_BTN_CANCEL_BORDER}; }}
"""
BTN_FETCH_STYLE = f"""
    QPushButton {{
        background: {COLOR_BTN_FETCH}; color: {COLOR_WHITE};
        border: 1px solid {COLOR_BTN_FETCH_BORDER}; border-radius: 4px;
        padding: 4px 8px; font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
    }}
    QPushButton:hover {{ background: {COLOR_BTN_FETCH_BORDER}; }}
"""


def _parse_multi(text: str) -> list[str]:
    """カンマ・空白区切りの文字列をリストに変換"""
    if not text.strip():
        return []
    return [v.strip() for v in re.split(r"[,\s]+", text.strip()) if v.strip()]


def _auto_kana(text: str) -> str:
    if not text:
        return ""
    if _KKS is None:
        return text
    try:
        result = _KKS.convert(text)
        kana = "".join(item["hira"] if item["hira"] else item["orig"] for item in result)
        return kana
    except Exception:
        return text


def _needs_kana_conversion(text: str) -> bool:
    """漢字が含まれていたら再変換が必要と判定"""
    for ch in text:
        if unicodedata.category(ch) in ("Lo",) and "\u4e00" <= ch <= "\u9fff":
            return True
    return False


class PropertyFormContext:
    """プロパティフォーム用のコンテキスト。プラグインが get_property_buttons(context) で受け取り、ボタンから fetch_by_id / open_meta_search を呼ぶために使う。"""
    def __init__(self, form: QWidget):
        self._form = form

    def fetch_by_id(self) -> None:
        """作品ID欄の値でメタ取得してフォームに反映する。"""
        if hasattr(self._form, "_on_fetch_meta"):
            self._form._on_fetch_meta()

    def open_meta_search(self) -> None:
        """メタデータ検索ダイアログを開き、適用結果をフォームに反映する。"""
        if hasattr(self._form, "_on_meta_search"):
            self._form._on_meta_search()

    def get_parent(self) -> QWidget:
        """ボタンなどの親ウィジェット（ダイアログ／パネル）。"""
        return self._form


class MetaSearchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.setMinimumSize(560, 420)
        self.result: dict | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 検索行（高さを統一）
        SEARCH_ROW_HEIGHT = 28
        search_row = QHBoxLayout()
        self._e_search = QLineEdit()
        self._e_search.setFixedHeight(SEARCH_ROW_HEIGHT)
        self._e_search.setPlaceholderText("作品名 / サークル名 / 作者名 / URL")
        self._e_search.returnPressed.connect(self._on_search)
        search_row.addWidget(self._e_search, stretch=1)

        # 検索種別
        self._kind_combo = QComboBox()
        self._kind_combo.setFixedHeight(SEARCH_ROW_HEIGHT)
        self._kind_combo.setFixedWidth(110)
        self._kind_combo.addItems(["作品名", "サークル名", "作者名", "作品ID"])
        self._kind_combo.currentTextChanged.connect(self._on_kind_changed)
        search_row.addWidget(self._kind_combo)

        btn_search = QPushButton("検索")
        btn_search.setFixedHeight(SEARCH_ROW_HEIGHT)
        btn_search.setFixedWidth(60)
        btn_search.clicked.connect(self._on_search)
        search_row.addWidget(btn_search)
        layout.addLayout(search_row)

        # 結果リスト
        self._result_list = QListWidget()
        self._result_list.itemDoubleClicked.connect(self._on_apply_item)
        layout.addWidget(self._result_list)

        # ボタン行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_apply = QPushButton("このメタデータを適用")
        btn_apply.clicked.connect(self._on_apply_item)
        btn_cancel = QPushButton("閉じる")
        btn_cancel.clicked.connect(self.reject)
        btn_apply.setStyleSheet(BTN_SAVE_STYLE)
        btn_cancel.setStyleSheet(BTN_CANCEL_STYLE)
        btn_row.addWidget(btn_apply)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self._items: list[dict] = []

        # 初期状態で「作品名」を元に検索欄へ自動反映
        self._on_kind_changed(self._kind_combo.currentText())

    def _on_kind_changed(self, kind: str):
        p = self.parent()
        if kind == "作品名":
            if hasattr(p, "_e_title"):
                self._e_search.setText(p._e_title.text())
            else:
                self._e_search.setText(getattr(self, "_current_book", {}).get("title", ""))
        elif kind == "サークル名":
            if hasattr(p, "_e_circle"):
                self._e_search.setText(p._e_circle.text())
            else:
                self._e_search.setText(getattr(self, "_current_book", {}).get("circle", ""))
        elif kind == "作者名":
            if hasattr(p, "_e_author"):
                self._e_search.setText(p._e_author.currentText())
            else:
                self._e_search.setText(getattr(self, "_current_meta", {}).get("author", ""))
        elif kind == "作品ID":
            if hasattr(p, "_e_dlsite_id"):
                self._e_search.setText(p._e_dlsite_id.text())
            else:
                self._e_search.setText(getattr(self, "_current_meta", {}).get("dlsite_id", ""))

    def _on_search(self):
        query = self._e_search.text().strip()
        if not query:
            return

        # URL直接入力
        if query.startswith("http"):
            self._search_by_url(query)
            return

        kind = self._kind_combo.currentText()
        search_by = {
            "作品名": "title",
            "サークル名": "circle",
            "作者名": "author",
            "作品ID": "id",
        }.get(kind, "title")

        self._result_list.clear()
        self._items = []

        from PySide6.QtWidgets import QProgressDialog

        progress = QProgressDialog("検索中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        class _Worker(QThread):
            done = Signal(object)

            def __init__(self, query: str, search_by: str):
                super().__init__()
                self._query = query
                self._search_by = search_by

            def run(self):
                results = {}
                try:
                    from plugin_loader import get_plugins
                    for plugin in get_plugins():
                        items = plugin.search_sync(
                            self._query,
                            search_by=self._search_by,
                            max_results=10,
                        )
                        for item in items or []:
                            source = item.get("source", plugin.PLUGIN_NAME)
                            if source not in results:
                                results[source] = []
                            results[source].append(item)
                except Exception:
                    results = {}
                self.done.emit(results)

        self._worker = _Worker(query, search_by)

        def _on_done(results: dict[str, list[dict]]):
            progress.close()
            self._result_list.clear()
            self._items = []
            for site, items in results.items():
                color = SITE_COLORS.get(site, "#888")
                for item in items:
                    title = item.get("title", "")
                    circle = item.get("circle", "")
                    pid = item.get("id", "")
                    list_item = QListWidgetItem(f"[{site}]  {pid}  {title} / {circle}")
                    list_item.setForeground(QColor(color))
                    self._result_list.addItem(list_item)
                    self._items.append(item)
            if not self._items:
                self._result_list.addItem("（結果なし）")

        self._worker.done.connect(_on_done)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_apply_item(self):
        idx = self._result_list.currentRow()
        if idx < 0 or idx >= len(self._items):
            return
        item = self._items[idx]
        if "tags" in item:
            self.result = item
            self.accept()
            return

        pid = item.get("id", "")
        source = item.get("source", "DLSite")
        url = item.get("url", "")

        from PySide6.QtWidgets import QProgressDialog

        progress = QProgressDialog("取得中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        class _DetailWorker(QThread):
            done = Signal(object)

            def __init__(self, pid: str, source: str, url: str):
                super().__init__()
                self._pid = pid
                self._source = source
                self._url = url

            def run(self):
                id_or_url = self._url if self._url else self._pid
                meta = None
                try:
                    from plugin_loader import get_plugins
                    for plugin in get_plugins():
                        can = getattr(plugin, "can_handle", None)
                        if can and not can(id_or_url):
                            continue
                        meta = plugin.get_metadata_sync(id_or_url)
                        if meta:
                            break
                except Exception:
                    pass
                self.done.emit(meta)

        self._detail_worker = _DetailWorker(pid, source, url)

        def _on_done(meta):
            progress.close()
            if not meta:
                QMessageBox.warning(self, "取得失敗", "詳細取得に失敗しました。")
                return
            current_book = getattr(self, "_current_book", {})
            current_meta = getattr(self, "_current_meta", {})
            if current_book:
                current = {
                    "title": current_book.get("title", ""),
                    "circle": current_book.get("circle", ""),
                    "author": current_meta.get("author", ""),
                    "series": current_meta.get("series", ""),
                    "tags": ", ".join(current_meta.get("tags", [])),
                    "characters": ", ".join(current_meta.get("characters", [])),
                    "pages": str(current_meta.get("pages") or ""),
                    "release_date": current_meta.get("release_date", ""),
                    "price": str(current_meta.get("price") or ""),
                    "dlsite_id": current_meta.get("dlsite_id", ""),
                    "cover": current_book.get("cover", ""),
                }
                meta["dlsite_id"] = meta.get("dojindb_url") or meta.get("id") or ""
                path = current_book.get("path", "")
                apply_dlg = MetaApplyDialog(current, meta, self, book_path=path)
                if apply_dlg.exec() != QDialog.Accepted:
                    return
                applied = apply_dlg.selected_keys()
                rd = applied.get("release_date", "")
                m = re.match(r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", rd)
                if m:
                    rd = f"{m.group(1)}年{int(m.group(2))}月{int(m.group(3))}日"
                try:
                    _to_list = lambda s: [t.strip() for t in (s or "").split(",") if t.strip()]
                    _to_int = lambda s: int(str(s).strip()) if s and str(s).strip().isdigit() else None
                    meta_src = _meta_source_for_apply(meta, applied)
                    db.set_book_meta(
                        path,
                        author=applied.get("author") or None,
                        series=applied.get("series") or None,
                        characters=_to_list(applied.get("characters")) or None,
                        tags=_to_list(applied.get("tags")) or None,
                        pages=_to_int(applied.get("pages")),
                        release_date=rd or None,
                        price=_to_int(applied.get("price")),
                        dlsite_id=applied.get("dlsite_id") or None,
                        meta_source=meta_src,
                    )
                    new_title = applied.get("title", current_book.get("title", ""))
                    new_circle = applied.get("circle", current_book.get("circle", ""))
                    new_name = db.format_book_name(new_circle, new_title)
                    cover = current_book.get("cover") or ""
                    db.rename_book(path, path, new_name, new_circle, new_title, cover)
                    if applied.get("cover_path"):
                        db.set_cover_custom(path, applied["cover_path"])
                except Exception:
                    pass
                on_updated = getattr(self.parent(), "on_book_updated", None)
                if callable(on_updated):
                    on_updated(path)
                self.accept()
            else:
                self.result = meta
                self.accept()

        self._detail_worker.done.connect(_on_done)
        self._detail_worker.finished.connect(self._detail_worker.deleteLater)
        self._detail_worker.start()


class MetaApplyDialog(QDialog):
    """メタデータ取捨選択ダイアログ"""

    def __init__(self, current: dict, fetched: dict, parent=None, book_path: str = ""):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self._result: dict | None = None
        self._current_vals: dict[str, str] = {}
        self._fetched_vals: dict[str, str] = {}
        self._current_edits: dict[str, QLineEdit | QTextEdit] = {}
        self._fetched_edits: dict[str, QLineEdit | QTextEdit] = {}
        self._book_path = book_path or ""
        self._current_cover = (current.get("cover") or "").strip()
        self._fetched_image_url = (fetched.get("image_url") or "").strip()
        self._cover_choice = "current"  # "current" | "fetched" | "cropped"
        self._chosen_cover_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(8)

        # ヘッダー行
        header = QHBoxLayout()
        lbl_field = QLabel("項目")
        lbl_field.setFixedWidth(80)
        lbl_cur = QLabel("現在値")
        lbl_cur.setFixedWidth(160)
        spacer = QLabel("")
        spacer.setFixedWidth(20)
        lbl_new = QLabel("取得値")
        lbl_new.setFixedWidth(160)
        header.addWidget(lbl_field)
        header.addWidget(lbl_cur)
        header.addWidget(spacer)
        header.addWidget(lbl_new)
        layout.addLayout(header)

        # サムネイル行（取得画像がある場合のみ）
        self._cover_current_label: QLabel | None = None
        self._cover_fetched_label: QLabel | None = None
        self._cover_radio_current = None
        self._cover_radio_fetched = None
        if self._current_cover or self._fetched_image_url:
            row_cover = QHBoxLayout()
            chk_cover = QLabel("サムネイル")
            chk_cover.setFixedWidth(80)
            row_cover.addWidget(chk_cover)
            # 現在のサムネ表示
            self._cover_current_label = QLabel()
            self._cover_current_label.setFixedSize(80, 110)
            self._cover_current_label.setStyleSheet("background: #222; border: 1px solid #444; border-radius: 4px;")
            self._cover_current_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if self._current_cover and os.path.exists(self._current_cover):
                pix = QPixmap(self._current_cover).scaled(78, 108, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self._cover_current_label.setPixmap(pix)
            else:
                self._cover_current_label.setText("なし")
                self._cover_current_label.setStyleSheet("background: #222; color: #666; border: 1px solid #444; border-radius: 4px;")
            row_cover.addWidget(self._cover_current_label)
            row_cover.addWidget(QLabel("→"))
            # 取得サムネ表示（URLから非同期で読む場合は後で更新するためプレースホルダー）
            self._cover_fetched_label = QLabel()
            self._cover_fetched_label.setFixedSize(80, 110)
            self._cover_fetched_label.setStyleSheet("background: #222; border: 1px solid #444; border-radius: 4px;")
            self._cover_fetched_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if self._fetched_image_url:
                self._cover_fetched_label.setText("読込中…")
                self._cover_fetched_label.setStyleSheet("background: #222; color: #888; border: 1px solid #444; border-radius: 4px;")
                self._load_fetched_cover_async()
            else:
                self._cover_fetched_label.setText("なし")
                self._cover_fetched_label.setStyleSheet("background: #222; color: #666; border: 1px solid #444; border-radius: 4px;")
            row_cover.addWidget(self._cover_fetched_label)
            # ラジオ＋切り抜きボタン
            from PySide6.QtWidgets import QButtonGroup, QRadioButton
            cover_grp = QWidget()
            cover_grp_layout = QVBoxLayout(cover_grp)
            cover_grp_layout.setContentsMargins(0, 0, 0, 0)
            self._cover_radio_current = QRadioButton("現在のサムネ")
            self._cover_radio_fetched = QRadioButton("取得したサムネ")
            _radio_style = (
                "QRadioButton { color: #ccc; }"
                " QRadioButton::indicator:checked { background-color: #fff; border: 1px solid #888; }"
                " QRadioButton:checked { color: #fff; }"
            )
            self._cover_radio_current.setStyleSheet(_radio_style)
            self._cover_radio_fetched.setStyleSheet(_radio_style)
            cover_grp_layout.addWidget(self._cover_radio_current)
            cover_grp_layout.addWidget(self._cover_radio_fetched)
            btn_crop = QPushButton("切り抜きで選択")
            btn_crop.setStyleSheet(f"font-size: {config.FONT_SIZE_PROP_HINT}px;")
            btn_crop.clicked.connect(self._on_cover_crop)
            cover_grp_layout.addWidget(btn_crop)
            row_cover.addWidget(cover_grp)
            layout.addLayout(row_cover)
            # 初期選択: すでにサムネがある場合は現在値、ない場合は取得値
            if self._current_cover and os.path.exists(self._current_cover):
                self._cover_radio_current.setChecked(True)
            elif self._fetched_image_url:
                self._cover_radio_fetched.setChecked(True)
                self._cover_choice = "fetched"
            else:
                self._cover_radio_current.setChecked(True)
            def _set_cover_current(v):
                if v:
                    self._cover_choice = "current"
            def _set_cover_fetched(v):
                if v:
                    self._cover_choice = "fetched"
            self._cover_radio_current.toggled.connect(_set_cover_current)
            self._cover_radio_fetched.toggled.connect(_set_cover_fetched)

        # 各フィールド定義
        FIELDS = [
            ("title", "タイトル"),
            ("circle", "サークル"),
            ("author", "作者"),
            ("series", "シリーズ"),
            ("tags", "タグ"),
            ("characters", "キャラクター"),
            ("pages", "ページ数"),
            ("release_date", "発売日"),
            ("price", "金額"),
            ("dlsite_id", "作品ID"),
        ]

        def _make_toggle(chk, lbl_c, edit_n):
            def _toggle(checked):
                if checked:
                    lbl_c.setStyleSheet("border: 1px solid #444; border-radius: 3px; padding: 2px 4px; color: #aaa;")
                    edit_n.setStyleSheet("border: 1px solid #fff; border-radius: 3px; padding: 2px 4px;")
                else:
                    lbl_c.setStyleSheet("border: 1px solid #fff; border-radius: 3px; padding: 2px 4px; color: #aaa;")
                    edit_n.setStyleSheet("border: 1px solid #444; border-radius: 3px; padding: 2px 4px; color: #555;")
            chk.toggled.connect(_toggle)
            _toggle(chk.isChecked())

        self._checks: dict[str, QCheckBox] = {}

        for key, label in FIELDS:
            cur_val = current.get(key, "")
            new_val = fetched.get(key, "")

            # リストは文字列に変換
            if isinstance(cur_val, list):
                cur_val = ", ".join(cur_val)
            if isinstance(new_val, list):
                new_val = ", ".join(new_val)

            cur_str = str(cur_val) if cur_val else ""
            new_str = str(new_val) if new_val else ""
            self._current_vals[key] = cur_str
            self._fetched_vals[key] = new_str

            row = QHBoxLayout()

            chk = QCheckBox(label)
            chk.setFixedWidth(80)
            chk.setStyleSheet("""
                QCheckBox { color: #fff; }
                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                    border: 1px solid #fff;
                    border-radius: 2px;
                    background: transparent;
                }
                QCheckBox::indicator:checked {
                    background: #fff;
                }
            """)
            has_new = bool(new_str.strip())
            same = cur_str.strip() == new_str.strip()
            chk.setChecked(has_new and not same)
            self._checks[key] = chk
            row.addWidget(chk)

            if key in ("tags", "characters"):
                lbl_c = QTextEdit()
                lbl_c.setPlainText(cur_str)
                lbl_c.setFixedSize(200, 48)
            else:
                lbl_c = QLineEdit(cur_str)
                lbl_c.setFixedWidth(200)
            self._current_edits[key] = lbl_c
            row.addWidget(lbl_c)

            arrow = QLabel("→")
            arrow.setFixedWidth(20)
            arrow.setAlignment(Qt.AlignCenter)
            arrow.setStyleSheet("color: #888;")
            row.addWidget(arrow)

            if key in ("tags", "characters"):
                edit_n = QTextEdit()
                edit_n.setPlainText(new_str)
                edit_n.setFixedSize(200, 48)
            else:
                edit_n = QLineEdit(new_str)
                edit_n.setFixedWidth(200)
            self._fetched_edits[key] = edit_n
            row.addWidget(edit_n)

            _make_toggle(chk, lbl_c, edit_n)
            layout.addLayout(row)

        # ボタン
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_apply = QPushButton("適用")
        btn_apply.setStyleSheet(BTN_SAVE_STYLE)
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setStyleSheet(BTN_CANCEL_STYLE)
        btn_apply.clicked.connect(self._on_apply)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_apply)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def _load_fetched_cover_async(self):
        """取得サムネURLをバックグラウンドでダウンロードしてラベルに表示"""
        url = self._fetched_image_url
        if not url:
            return
        class _CoverWorker(QThread):
            done = Signal(object)
            def __init__(self, u):
                super().__init__()
                self._url = u
            def run(self):
                from thumbnail_crop_dialog import _download_image
                self.done.emit(_download_image(self._url))
        w = _CoverWorker(url)
        def _on_done(pix):
            if pix is not None and not pix.isNull() and getattr(self, "_cover_fetched_label", None):
                scaled = pix.scaled(78, 108, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self._cover_fetched_label.setPixmap(scaled)
                self._cover_fetched_label.setStyleSheet("background: #222; border: 1px solid #444; border-radius: 4px;")
        w.done.connect(_on_done)
        w.finished.connect(w.deleteLater)
        w.start()
        setattr(self, "_cover_worker", w)

    def _on_cover_crop(self):
        """切り抜きダイアログを開き、確定時にサムネイルパスを保存"""
        from thumbnail_crop_dialog import ThumbnailCropDialog
        if not self._fetched_image_url:
            QMessageBox.information(self, "サムネイル", "取得した画像がありません。")
            return
        dlg = ThumbnailCropDialog(self._fetched_image_url, self._book_path, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_path:
            self._chosen_cover_path = dlg.result_path
            self._cover_choice = "cropped"
            if self._cover_radio_fetched:
                self._cover_radio_fetched.setChecked(False)
            if self._cover_radio_current:
                self._cover_radio_current.setChecked(False)
            QMessageBox.information(self, "サムネイル", "切り抜きを適用しました。「適用」で確定してください。")

    def _on_apply(self):
        result = {}
        for key, chk in self._checks.items():
            cur_edit = self._current_edits[key]
            cur_val = cur_edit.toPlainText() if isinstance(cur_edit, QTextEdit) else cur_edit.text()
            edit = self._fetched_edits[key]
            new_val = edit.toPlainText() if isinstance(edit, QTextEdit) else edit.text()
            result[key] = new_val if chk.isChecked() else cur_val
        # サムネイル: 現在 / 取得 / 切り抜き
        if getattr(self, "_cover_radio_current", None) is not None:
            if self._chosen_cover_path:
                result["cover_path"] = self._chosen_cover_path
            elif self._cover_choice == "fetched" and self._fetched_image_url:
                result["cover_path"] = self._download_and_save_cover()
            else:
                result["cover_path"] = None
        self._result = result
        self.accept()

    def _download_and_save_cover(self) -> str | None:
        """取得画像URLをダウンロードしてcover_cacheに保存しパスを返す"""
        import hashlib
        from thumbnail_crop_dialog import _download_image
        pix = _download_image(self._fetched_image_url)
        if pix is None or pix.isNull():
            return None
        cover_dir = config.COVER_CACHE_DIR
        os.makedirs(cover_dir, exist_ok=True)
        key = hashlib.md5(self._book_path.encode()).hexdigest()
        out_path = os.path.join(cover_dir, f"{key}_fetched.jpg")
        if pix.save(out_path, "JPEG", quality=90):
            return out_path
        return None

    def selected_keys(self) -> dict:
        return self._result or {}

    def _search_by_url(self, query: str):
        from PySide6.QtWidgets import QProgressDialog
        import re as _re

        # 同人DB
        if "dojindb.net" in query:
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
                    except Exception:
                        pass
                    self.done.emit(meta)

            self._dojin_worker = _DojinWorker(query)

            def _on_done(meta):
                progress.close()
                self._result_list.clear()
                self._items = []
                if not meta:
                    self._result_list.addItem("（取得失敗）")
                    return
                self._items = [meta]
                title = meta.get("title", "")
                circle = meta.get("circle", "")
                pid = meta.get("id", "")
                list_item = QListWidgetItem(f"[同人DB]  {pid}  {title} / {circle}")
                list_item.setForeground(QColor("#666666"))
                self._result_list.addItem(list_item)

            self._dojin_worker.done.connect(_on_done)
            self._dojin_worker.finished.connect(self._dojin_worker.deleteLater)
            self._dojin_worker.start()
            return

        # DLSite/FANZA/とらのあな URL → product_id 抽出
        m = _re.search(r"product_id[/=]([A-Z0-9_]+)", query, _re.IGNORECASE)
        product_id = m.group(1).upper() if m else ""

        source = "DLSite"
        if "dmm.co.jp" in query or "fanza" in query:
            source = "FANZA"
        elif "toranoana" in query:
            source = "とらのあな"

        if not product_id:
            self._result_list.clear()
            self._result_list.addItem("（IDを抽出できませんでした）")
            return

        progress = QProgressDialog("取得中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        class _UrlWorker(QThread):
            done = Signal(object)

            def __init__(self, pid: str, source: str):
                super().__init__()
                self._pid = pid
                self._source = source

            def run(self):
                meta = None
                try:
                    from plugin_loader import get_plugins
                    for plugin in get_plugins():
                        can = getattr(plugin, "can_handle", None)
                        if can and not can(self._pid):
                            continue
                        meta = plugin.get_metadata_sync(self._pid)
                        if meta:
                            break
                except Exception:
                    pass
                self.done.emit(meta)

        self._url_worker = _UrlWorker(product_id, source)

        def _on_done(meta):
            progress.close()
            self._result_list.clear()
            self._items = []
            if not meta:
                self._result_list.addItem("（取得失敗）")
                return
            self._items = [meta]
            title = meta.get("title", "")
            circle = meta.get("circle", "")
            pid = meta.get("id", "")
            list_item = QListWidgetItem(f"[{source}]  {pid}  {title} / {circle}")
            color = {"DLSite": "#4a7aaa", "FANZA": "#aa4a4a", "とらのあな": "#aa9a2a"}.get(
                source, "#888"
            )
            list_item.setForeground(QColor(color))
            self._result_list.addItem(list_item)

        self._url_worker.done.connect(_on_done)
        self._url_worker.finished.connect(self._url_worker.deleteLater)
        self._url_worker.start()

    def _on_apply_item(self):
        idx = self._result_list.currentRow()
        if idx < 0 or idx >= len(self._items):
            return
        item = self._items[idx]
        if "tags" in item:
            self.result = item
            self.accept()
            return

        pid = item.get("id", "")
        source = item.get("source", "DLSite")
        url = item.get("url", "")

        from PySide6.QtWidgets import QProgressDialog

        progress = QProgressDialog("取得中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        class _DetailWorker(QThread):
            done = Signal(object)

            def __init__(self, pid: str, source: str, url: str):
                super().__init__()
                self._pid = pid
                self._source = source
                self._url = url

            def run(self):
                id_or_url = self._url if self._url else self._pid
                meta = None
                try:
                    from plugin_loader import get_plugins
                    for plugin in get_plugins():
                        can = getattr(plugin, "can_handle", None)
                        if can and not can(id_or_url):
                            continue
                        meta = plugin.get_metadata_sync(id_or_url)
                        if meta:
                            break
                except Exception:
                    pass
                self.done.emit(meta)

        self._detail_worker = _DetailWorker(pid, source, url)

        def _on_done(meta):
            progress.close()
            if not meta:
                QMessageBox.warning(self, "失敗", "詳細取得に失敗しました。")
                return
            current_book = getattr(self, "_current_book", {})
            current_meta = getattr(self, "_current_meta", {})
            if current_book:
                current = {
                    "title": current_book.get("title", ""),
                    "circle": current_book.get("circle", ""),
                    "author": current_meta.get("author", ""),
                    "series": current_meta.get("series", ""),
                    "tags": ", ".join(current_meta.get("tags", [])),
                    "characters": ", ".join(current_meta.get("characters", [])),
                    "pages": str(current_meta.get("pages") or ""),
                    "release_date": current_meta.get("release_date", ""),
                    "price": str(current_meta.get("price") or ""),
                    "dlsite_id": current_meta.get("dlsite_id", ""),
                    "cover": current_book.get("cover", ""),
                }
                meta["dlsite_id"] = meta.get("dojindb_url") or meta.get("id") or ""
                path = current_book.get("path", "")
                apply_dlg = MetaApplyDialog(current, meta, self, book_path=path)
                if apply_dlg.exec() != QDialog.Accepted:
                    return
                applied = apply_dlg.selected_keys()
                rd = applied.get("release_date", "")
                m = re.match(r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", rd)
                if m:
                    rd = f"{m.group(1)}年{int(m.group(2))}月{int(m.group(3))}日"
                try:
                    _to_list = lambda s: [t.strip() for t in (s or "").split(",") if t.strip()]
                    _to_int = lambda s: int(str(s).strip()) if s and str(s).strip().isdigit() else None
                    meta_src = _meta_source_for_apply(meta, applied)
                    db.set_book_meta(
                        path,
                        author=applied.get("author") or None,
                        series=applied.get("series") or None,
                        characters=_to_list(applied.get("characters")) or None,
                        tags=_to_list(applied.get("tags")) or None,
                        pages=_to_int(applied.get("pages")),
                        release_date=rd or None,
                        price=_to_int(applied.get("price")),
                        dlsite_id=applied.get("dlsite_id") or None,
                        meta_source=meta_src,
                    )
                    new_title = applied.get("title", current_book.get("title", ""))
                    new_circle = applied.get("circle", current_book.get("circle", ""))
                    new_name = db.format_book_name(new_circle, new_title)
                    cover = current_book.get("cover") or ""
                    db.rename_book(path, path, new_name, new_circle, new_title, cover)
                    if applied.get("cover_path"):
                        db.set_cover_custom(path, applied["cover_path"])
                except Exception:
                    pass
                on_updated = getattr(self.parent(), "on_book_updated", None)
                if callable(on_updated):
                    on_updated(path)
                self.accept()
            else:
                self.result = meta
                self.accept()

        self._detail_worker.done.connect(_on_done)
        self._detail_worker.finished.connect(self._detail_worker.deleteLater)
        self._detail_worker.start()


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


class StoreFileInputDialog(QDialog):
    """ストアファイル追加時の入力ダイアログ。作品名のみ必須。順: 作品名・サークル名・作者…。一番上にメタデータ検索。"""

    def __init__(self, path: str, name: str, mtime: float, suggested_circle: str, suggested_title: str, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self._path = path
        self._name = name
        self._mtime = mtime
        self.result = None  # accept 時: ( (name, circle, title, path, "", mtime, 0), meta_dict or None )
        self._applied_cover_path = None  # メタ適用でサムネを選んだ場合のパス

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        lbl_file = QLabel(f"ファイル: {name}")
        lbl_file.setStyleSheet(f"color: #aaa; font-size: {config.FONT_SIZE_PROP_HINT}px;")
        layout.addWidget(lbl_file)

        # 作品名 * 必須
        row_title = QHBoxLayout()
        row_title.setSpacing(4)
        lbl_title = QLabel("作品名 *")
        lbl_title.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_title.addWidget(lbl_title)
        self._e_title = QLineEdit(suggested_title)
        self._e_title.setPlaceholderText("必須")
        self._e_title.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_title.addWidget(self._e_title, stretch=1)
        layout.addLayout(row_title)

        # サークル名（任意）
        row_circle = QHBoxLayout()
        row_circle.setSpacing(4)
        lbl_circle = QLabel("サークル名")
        lbl_circle.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_circle.addWidget(lbl_circle)
        self._e_circle = QLineEdit(suggested_circle)
        self._e_circle.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_circle.addWidget(self._e_circle, stretch=1)
        layout.addLayout(row_circle)

        # 作者・シリーズ・タグ・キャラクター
        for label_text, attr in [
            ("作者", "_e_author"),
            ("シリーズ", "_e_series"),
            ("タグ", "_e_tags"),
            ("キャラクター", "_e_chars"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(config.PROP_LABEL_WIDTH)
            row.addWidget(lbl)
            edit = QLineEdit()
            edit.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
            row.addWidget(edit, stretch=1)
            setattr(self, attr, edit)
            layout.addLayout(row)

        # ページ数・発売日・金額
        row_pages = QHBoxLayout()
        row_pages.setSpacing(4)
        lbl_pages = QLabel("ページ数")
        lbl_pages.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_pages.addWidget(lbl_pages)
        self._e_pages = QLineEdit()
        self._e_pages.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_pages.addWidget(self._e_pages, stretch=1)
        layout.addLayout(row_pages)

        row_release = QHBoxLayout()
        row_release.setSpacing(4)
        lbl_release = QLabel("発売日")
        lbl_release.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_release.addWidget(lbl_release)
        self._e_release = QLineEdit()
        self._e_release.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_release.addWidget(self._e_release, stretch=1)
        layout.addLayout(row_release)

        row_price = QHBoxLayout()
        row_price.setSpacing(4)
        lbl_price = QLabel("金額")
        lbl_price.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_price.addWidget(lbl_price)
        self._e_price = QLineEdit()
        self._e_price.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_price.addWidget(self._e_price, stretch=1)
        layout.addLayout(row_price)

        # メモ
        row_memo = QHBoxLayout()
        row_memo.setSpacing(4)
        lbl_memo = QLabel("メモ")
        lbl_memo.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_memo.addWidget(lbl_memo)
        self._e_memo = QTextEdit()
        self._e_memo.setFixedHeight(config.PROP_MEMO_HEIGHT_SMALL)
        self._e_memo.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_memo.addWidget(self._e_memo, stretch=1)
        layout.addLayout(row_memo)

        # 作品ID + 取得
        row_id = QHBoxLayout()
        row_id.setSpacing(4)
        lbl_id = QLabel("作品ID")
        lbl_id.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_id.addWidget(lbl_id)
        self._e_dlsite_id = QLineEdit()
        self._e_dlsite_id.setPlaceholderText("RJ... / D_... / URL でメタ取得")
        self._e_dlsite_id.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_id.addWidget(self._e_dlsite_id, stretch=1)
        layout.addLayout(row_id)

        # OK / キャンセル ＋ プラグイン用ボタン（プラグインが自分で配置）
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("OK")
        btn_ok.setStyleSheet(BTN_SAVE_STYLE)
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setStyleSheet(BTN_CANCEL_STYLE)
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        try:
            from plugin_loader import get_plugin_property_widgets
            ctx = PropertyFormContext(self)
            for w in get_plugin_property_widgets(ctx):
                if isinstance(w, QPushButton):
                    w.setStyleSheet(BTN_FETCH_STYLE)
                    w.setFixedWidth(config.PROP_BTN_FETCH_WIDTH)
                btn_row.addWidget(w)
        except Exception:
            pass
        layout.addLayout(btn_row)

        self.setMinimumWidth(config.PROP_DIALOG_MIN_WIDTH)

    def _on_ok(self):
        title = self._e_title.text().strip()
        if not title:
            QMessageBox.warning(self, "入力エラー", "作品名を入力してください。")
            return
        circle = self._e_circle.text().strip()
        name = db.format_book_name(circle, title)
        book_tuple = (name, circle, title, self._path, "", self._mtime, 0)
        meta = self._collect_meta()
        if getattr(self, "_applied_cover_path", None):
            meta = meta or {}
            meta["cover_path"] = self._applied_cover_path
        self.result = (book_tuple, meta)
        self.accept()

    def _on_meta_search(self):
        """メタデータ検索ダイアログを開き、取得結果を適用ダイアログで選んでフォームに反映（プロパティの流用）。"""
        dlg = MetaSearchDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.result:
            return
        meta = dlg.result
        current = {
            "title": self._e_title.text(),
            "circle": self._e_circle.text(),
            "author": self._e_author.text(),
            "series": self._e_series.text(),
            "tags": self._e_tags.text(),
            "characters": self._e_chars.text(),
            "pages": self._e_pages.text(),
            "release_date": self._e_release.text(),
            "price": self._e_price.text(),
            "dlsite_id": self._e_dlsite_id.text(),
            "cover": "",
        }
        meta["dlsite_id"] = meta.get("dojindb_url") or meta.get("id") or ""
        apply_dlg = MetaApplyDialog(current, meta, self, book_path=self._path)
        if apply_dlg.exec() != QDialog.Accepted:
            return
        applied = apply_dlg.selected_keys()
        self._applied_cover_path = applied.get("cover_path")
        if "title" in applied:
            self._e_title.setText(applied["title"])
        if "circle" in applied:
            self._e_circle.setText(applied["circle"])
        if "author" in applied:
            self._e_author.setText(applied["author"])
        if "series" in applied:
            self._e_series.setText(applied["series"])
        if "tags" in applied:
            self._e_tags.setText(applied["tags"])
        if "characters" in applied:
            self._e_chars.setText(applied["characters"])
        if "pages" in applied:
            self._e_pages.setText(applied["pages"])
        if "release_date" in applied:
            self._e_release.setText(applied["release_date"])
        if "price" in applied:
            self._e_price.setText(applied["price"])
        if "dlsite_id" in applied:
            self._e_dlsite_id.setText(applied["dlsite_id"])

    def _collect_meta(self) -> dict | None:
        """フォームからメタデータ辞書を組み立て（set_book_meta 用）。空なら None。"""
        author = self._e_author.text().strip()
        series = self._e_series.text().strip()
        tags = [t.strip() for t in self._e_tags.text().split(",") if t.strip()]
        chars = [c.strip() for c in self._e_chars.text().split(",") if c.strip()]
        pages_s = self._e_pages.text().strip()
        pages = int(pages_s) if pages_s.isdigit() else None
        release = self._e_release.text().strip()
        price_s = self._e_price.text().strip()
        price = int(price_s) if price_s.isdigit() else None
        memo = self._e_memo.toPlainText().strip()
        dlsite_id = self._e_dlsite_id.text().strip()
        if not any([author, series, tags, chars, pages, release, price, memo, dlsite_id]):
            return None
        return {
            "author": author or "",
            "series": series or "",
            "tags": tags,
            "characters": chars,
            "pages": pages,
            "release_date": release or "",
            "price": price,
            "memo": memo or "",
            "dlsite_id": dlsite_id or "",
        }

    def _apply_meta_to_form(self, meta: dict):
        if meta.get("title"):
            self._e_title.setText(meta["title"])
        if meta.get("circle"):
            self._e_circle.setText(meta["circle"])
        if meta.get("author"):
            self._e_author.setText(meta["author"])
        if meta.get("parody"):
            self._e_series.setText(meta["parody"])
        if meta.get("series"):
            self._e_series.setText(meta["series"])
        if meta.get("characters"):
            self._e_chars.setText(", ".join(meta["characters"]) if isinstance(meta["characters"], list) else str(meta["characters"]))
        if meta.get("tags"):
            self._e_tags.setText(", ".join(meta["tags"]) if isinstance(meta["tags"], list) else str(meta["tags"]))
        if meta.get("pages") is not None:
            self._e_pages.setText(str(meta["pages"] or ""))
        if meta.get("release_date"):
            self._e_release.setText(meta["release_date"])
        if meta.get("price") is not None:
            self._e_price.setText(str(meta["price"] or ""))
        if meta.get("memo"):
            self._e_memo.setPlainText(meta["memo"])
        if meta.get("dojindb_url"):
            self._e_dlsite_id.setText(meta["dojindb_url"])
        elif meta.get("id"):
            self._e_dlsite_id.setText(meta["id"])

    def _on_fetch_meta(self):
        text = self._e_dlsite_id.text().strip()
        if not text:
            QMessageBox.warning(self, "エラー", "作品IDまたはURLを入力してください。")
            return
        if text.startswith("http"):
            if "dojindb.net" in text:
                self._fetch_dojindb(text)
                return
            m = re.search(r"product_id[/=]([A-Z0-9_]+)", text, re.IGNORECASE)
            if m:
                product_id = m.group(1).upper()
            else:
                QMessageBox.warning(self, "エラー", "URLから作品IDを取得できませんでした。")
                return
            source = "FANZA" if ("dmm.co.jp" in text or "fanza" in text) else "DLSite"
        else:
            product_id = text.upper()
            source = "FANZA" if product_id.startswith("D_") else "DLSite"
        self._run_fetch_worker(product_id, source)

    def _fetch_dojindb(self, url: str):
        from PySide6.QtWidgets import QProgressDialog
        progress = QProgressDialog("取得中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        class _DojinWorker(QThread):
            done = Signal(object)
            def __init__(self, u):
                super().__init__()
                self._url = u
            def run(self):
                meta = None
                try:
                    from plugin_loader import get_plugins
                    for plugin in get_plugins():
                        meta = plugin.get_metadata_sync(self._url)
                        if meta:
                            break
                except Exception:
                    pass
                self.done.emit(meta)

        w = _DojinWorker(url)
        def _on_done(meta):
            progress.close()
            if meta:
                self._apply_meta_to_form(meta)
            else:
                QMessageBox.warning(self, "取得失敗", "メタデータを取得できませんでした。")
        w.done.connect(_on_done)
        w.finished.connect(w.deleteLater)
        w.start()

    def _run_fetch_worker(self, product_id: str, source: str):
        from PySide6.QtWidgets import QProgressDialog
        progress = QProgressDialog("取得中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        class _Worker(QThread):
            done = Signal(object)
            def __init__(self, pid, src):
                super().__init__()
                self._pid, self._src = pid, src
            def run(self):
                meta = None
                try:
                    from plugin_loader import get_plugins
                    for plugin in get_plugins():
                        can = getattr(plugin, "can_handle", None)
                        if can and not can(self._pid):
                            continue
                        meta = plugin.get_metadata_sync(self._pid)
                        if meta:
                            break
                except Exception:
                    pass
                self.done.emit(meta)

        w = _Worker(product_id, source)
        def _on_done(meta):
            progress.close()
            if meta:
                self._apply_meta_to_form(meta)
            else:
                QMessageBox.warning(self, "取得失敗", "メタデータを取得できませんでした。")
        w.done.connect(_on_done)
        w.finished.connect(w.deleteLater)
        w.start()


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

        self._path: str = self._book.get("path", "")
        self._name: str = self._book.get("name", "")
        self._title: str = self._book.get("title", "") or self._name
        self._circle: str = self._book.get("circle", "")
        self._cover: str = self._book.get("cover", "")
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

    def _collect_multi_fields(self):
        """一括編集時、選択作品間で値が異なる項目を self._multi_fields に集める。"""
        for key, getter in [
            ("circle", lambda b: (b.get("circle") or "").strip()),
            ("title", lambda b: (b.get("title") or b.get("name") or "").strip()),
        ]:
            vals = {getter(b) for b in self._books}
            if len(vals) > 1:
                self._multi_fields.add(key)
        all_metas = [db.get_book_meta(b.get("path")) or {} for b in self._books]
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
        rating_vals = {bookmarks.get(b.get("path"), 0) for b in self._books if b.get("path")}
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
        lbl.setStyleSheet(f"color: #e66; font-size: {config.FONT_SIZE_PROP_HINT}px; padding: 0 0 2px 0;")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        spacer = QLabel("")
        spacer.setFixedWidth(config.PROP_LABEL_WIDTH)
        row.addWidget(spacer)
        row.addWidget(lbl, 1)
        layout.addLayout(row)

    def _setup_ui(self):
        self.setWindowTitle(config.APP_TITLE)
        # 縦方向に余裕を持たせて、メモと作品IDが被らないよう高さを拡大
        self.setFixedSize(680, 690)
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
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QLabel {{
                color: {THEME_COLORS["text_main"]};
            }}
            QPushButton {{
                background: {THEME_COLORS["bg_widget"]};
                color: {THEME_COLORS["text_main"]};
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background: {THEME_COLORS["hover"]};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # 上段: 左カラム + 右カラム
        top = QHBoxLayout()
        top.setSpacing(16)
        root.addLayout(top)

        # 左カラム（幅160px固定）
        left_widget = QWidget()
        left_widget.setFixedWidth(160)
        left = QVBoxLayout(left_widget)
        left.setSpacing(8)
        left.setContentsMargins(0, 0, 0, 0)
        top.addWidget(left_widget)

        # サムネイル（クリックで切り抜き）
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(160, 220)
        self._thumb_label.setStyleSheet("background:#111111; border:1px solid #444;")
        self._thumb_label.setAlignment(Qt.AlignCenter)
        if not self._bulk:
            self._thumb_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self._thumb_label.setToolTip("クリックで切り抜き")
            self._thumb_label.mousePressEvent = self._on_thumb_click_crop
        left.addWidget(self._thumb_label)

        btn_change_cover = QPushButton("画像を変更")
        btn_change_cover.clicked.connect(self._on_change_cover)
        left.addWidget(btn_change_cover)

        # フォルダ名（ポップアップで編集）。[サークル名]作品名のため、作品名はここと「作品名」の両方に現れます。
        lbl_folder = QLabel("フォルダ名")
        lbl_folder.setToolTip("表示名は「[サークル名]作品名」で表示されます。作品名はこの欄と「作品名」の両方に含まれます。")
        left.addWidget(lbl_folder)
        self._folder_label = QLabel(self._name)
        self._folder_label.setFixedWidth(160)
        self._folder_label.setWordWrap(False)
        self._folder_label.setStyleSheet(
            """
            QLabel {
                background: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 8px;
                color: #ccc;
                max-width: 160px;
            }
            QLabel:hover { border-color: #666; }
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
        star_row.setSpacing(2)
        left.addWidget(QLabel("お気に入り"))
        self._star_buttons: list[QPushButton] = []
        for i in range(5):
            idx = i + 1
            btn = QPushButton("☆")
            btn.setFixedSize(28, 28)
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    font-size: {config.FONT_SIZE_RATING_UI}px; padding: 0px;
                    border: none; background: transparent; color: #888;
                }}
                QPushButton:hover {{ color: #FFD700; background: transparent; }}
                """
            )
            btn.clicked.connect(lambda _=None, r=idx: self._set_rating(r))
            self._star_buttons.append(btn)
            star_row.addWidget(btn)
        star_row.addStretch()
        left.addLayout(star_row)
        if self._bulk and "rating" in self._multi_fields:
            lbl_rating_hint = QLabel("複数のお気に入りが選択されています")
            lbl_rating_hint.setStyleSheet(f"color: #e66; font-size: {config.FONT_SIZE_PROP_HINT}px; padding: 0 0 2px 0;")
            left.addWidget(lbl_rating_hint)

        left.addStretch()

        # 右カラム
        right = QVBoxLayout()
        right.setSpacing(6)
        top.addLayout(right, stretch=1)

        # 作品名・サークル
        row_title = QHBoxLayout()
        row_title.setSpacing(4)
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

        # 作品名フリガナ（ラベルなし・作品名の直下）
        row_title_kana = QHBoxLayout()
        row_title_kana.setSpacing(4)
        spacer_title_kana = QLabel("")  # ラベル幅ぶんの空き
        spacer_title_kana.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_title_kana.addWidget(spacer_title_kana)
        self._e_title_kana = QLineEdit()
        self._e_title_kana.setPlaceholderText("フリガナ（作品名）")
        self._e_title_kana.setFocusPolicy(Qt.ClickFocus)
        row_title_kana.addWidget(self._e_title_kana, stretch=1)
        right.addLayout(row_title_kana)

        row_circle = QHBoxLayout()
        row_circle.setSpacing(4)
        lbl_circle = QLabel("サークル")
        lbl_circle.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_circle.addWidget(lbl_circle)
        self._e_circle = QLineEdit()
        self._e_circle.setFocusPolicy(Qt.ClickFocus)
        row_circle.addWidget(self._e_circle, stretch=1)
        right.addLayout(row_circle)
        self._add_bulk_hint(right, "circle")

        # サークル名フリガナ（ラベルなし・サークル名の直下）
        row_circle_kana = QHBoxLayout()
        row_circle_kana.setSpacing(4)
        spacer_circle_kana = QLabel("")
        spacer_circle_kana.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_circle_kana.addWidget(spacer_circle_kana)
        self._e_circle_kana = QLineEdit()
        self._e_circle_kana.setPlaceholderText("フリガナ（サークル）")
        self._e_circle_kana.setFocusPolicy(Qt.ClickFocus)
        row_circle_kana.addWidget(self._e_circle_kana, stretch=1)
        right.addLayout(row_circle_kana)

        # 作品名 / サークル名が編集されたら、フリガナを自動再変換（ただしフリガナ欄編集中は上書きしない）
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
            """サークル・作品名の変更をフォルダ名欄に反映（手動でフォルダ名を変えていなければ）。保存時にリネームされる。"""
            if self._bulk or self._folder_manually_edited:
                return
            c = self._e_circle.text().strip()
            t = self._e_title.text().strip()
            synced = db.format_book_name(c, t) or self._name
            self._folder_edit_value = synced
            self._folder_label.setText(synced)

        self._e_title.textChanged.connect(lambda _: _sync_folder_from_circle_title())
        self._e_circle.textChanged.connect(lambda _: _sync_folder_from_circle_title())

        # フリガナ表示/非表示チェックボックスの初期状態と挙動
        hide_kana_setting = db.get_setting("ui_hide_kana", "0")
        hide_kana = str(hide_kana_setting) == "1"
        self._chk_hide_kana.setChecked(hide_kana)
        self._e_title_kana.setVisible(not hide_kana)
        self._e_circle_kana.setVisible(not hide_kana)

        def _on_hide_kana_toggled(checked: bool):
            # チェックONでフリガナ欄を隠す（作品名＋サークル両方）
            self._e_title_kana.setVisible(not checked)
            self._e_circle_kana.setVisible(not checked)
            db.set_setting("ui_hide_kana", "1" if checked else "0")

        self._chk_hide_kana.toggled.connect(_on_hide_kana_toggled)

        # 作者・シリーズ・キャラ・タグ
        row_author = QHBoxLayout()
        row_author.setSpacing(4)
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
        row_series.setSpacing(4)
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
        row_chars.setSpacing(4)
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
        row_tags.setSpacing(4)
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

        # 追加フィールド: ページ数・発売日・金額・メモ
        row_pages = QHBoxLayout()
        row_pages.setSpacing(4)
        lbl_pages = QLabel("ページ数")
        lbl_pages.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_pages.addWidget(lbl_pages)
        self._e_pages = QLineEdit()
        row_pages.addWidget(self._e_pages, stretch=1)
        right.addLayout(row_pages)
        self._add_bulk_hint(right, "pages")

        row_release = QHBoxLayout()
        row_release.setSpacing(4)
        lbl_release = QLabel("発売日")
        lbl_release.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_release.addWidget(lbl_release)
        self._e_release = QLineEdit()
        row_release.addWidget(self._e_release, stretch=1)
        right.addLayout(row_release)
        self._add_bulk_hint(right, "release_date")

        row_price = QHBoxLayout()
        row_price.setSpacing(4)
        lbl_price = QLabel("金額")
        lbl_price.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_price.addWidget(lbl_price)
        self._e_price = QLineEdit()
        row_price.addWidget(self._e_price, stretch=1)
        right.addLayout(row_price)
        self._add_bulk_hint(right, "price")

        # メモ（複数行） - ラベル左、入力欄3行分、高さ・枠線を統一
        row_memo = QHBoxLayout()
        row_memo.setSpacing(4)
        lbl_memo = QLabel("メモ")
        lbl_memo.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_memo.addWidget(lbl_memo, alignment=Qt.AlignVCenter)
        self._e_memo = QTextEdit()
        self._e_memo.setFixedHeight(3 * config.PROP_MEMO_LINE_HEIGHT)
        self._e_memo.setStyleSheet(
            """
            QTextEdit {
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px;
            }
            """
        )
        row_memo.addWidget(self._e_memo, stretch=1)
        right.addLayout(row_memo)
        self._add_bulk_hint(right, "memo")

        # 作品ID + 除外
        row_id = QHBoxLayout()
        row_id.setSpacing(4)
        lbl_id = QLabel("作品ID")
        lbl_id.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_id.addWidget(lbl_id)
        self._e_dlsite_id = QLineEdit()
        self._e_dlsite_id.setFocusPolicy(Qt.ClickFocus)
        row_id.addWidget(self._e_dlsite_id, stretch=1)
        self._btn_exclude = QPushButton("除外")
        self._btn_exclude.setFixedWidth(48)
        self._btn_exclude.clicked.connect(self._on_toggle_excluded)
        row_id.addWidget(self._btn_exclude)
        right.addLayout(row_id)
        self._add_bulk_hint(right, "dlsite_id")

        right.addStretch()

        # 下部ボタン（レイアウト・サイズ統一）
        BTN_W = 110
        BTN_H = 36

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        btn_save = QPushButton("保存")
        btn_cancel = QPushButton("キャンセル")

        btn_save.setStyleSheet(BTN_SAVE_STYLE)
        btn_cancel.setStyleSheet(BTN_CANCEL_STYLE)

        btn_save.setFixedSize(BTN_W, BTN_H)
        btn_cancel.setFixedSize(BTN_W, BTN_H)

        bottom_row.addSpacing(BTN_W)   # 左の空白
        bottom_row.addStretch()
        bottom_row.addWidget(btn_save)
        bottom_row.addWidget(btn_cancel)
        bottom_row.addStretch()
        try:
            from plugin_loader import get_plugin_property_widgets
            ctx = PropertyFormContext(self)
            for w in get_plugin_property_widgets(ctx):
                if isinstance(w, QPushButton):
                    w.setStyleSheet(BTN_FETCH_STYLE)
                    w.setFixedSize(BTN_W, BTN_H)
                bottom_row.addWidget(w)
        except Exception:
            pass

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
        except Exception:
            pass

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
        apply_dlg = MetaApplyDialog(current, meta, self, book_path=self._path)
        if apply_dlg.exec() != QDialog.Accepted:
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
                    color: {"#FFD700" if filled else "#888"};
                }}
                QPushButton:hover {{ color: #FFD700; background: transparent; }}
                """
            )

    # ── カバー画像変更 ────────────────────────────────────

    def _on_change_cover(self):
        fname, _ = QFileDialog.getOpenFileName(
            self,
            "カバー画像を選択",
            os.path.dirname(self._cover) if self._cover else "",
            "画像ファイル (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if not fname:
            return
        pix = QPixmap(fname)
        if pix.isNull():
            QMessageBox.warning(self, "エラー", "画像を読み込めませんでした。")
            return
        self._new_cover_path = fname
        self._thumb_label.setPixmap(pix.scaled(160, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _on_thumb_click_crop(self, event):
        """サムネイルクリック時: イベントを消費して切り抜きを開く（フォルダ名クリックと誤反応しないように）"""
        if event is not None:
            event.accept()
        self._on_crop_cover()

    def _on_crop_cover(self):
        """現在のサムネイルから切り抜き（cover_cacheに保存）"""
        from thumbnail_crop_dialog import ThumbnailCropDialog
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
            self._thumb_label.setPixmap(pix.scaled(160, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    # ── フォルダ名ポップアップ ─────────────────────────────

    def _open_rename_popup(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(config.APP_TITLE)
        dlg.setMinimumWidth(500)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

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
                except Exception:
                    pass
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
                except Exception:
                    pass
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

        t0 = time.time()

        path = self._path
        original_path_for_db = path  # rename_book(old, new) で DB を更新するときの old（誤った path のままの可能性あり）

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
        new_path = path
        if new_name != self._name:
            try:
                if os.path.isdir(path):
                    # フォルダのリネーム: path がライブラリルートそのものなら禁止
                    if _is_library_root(path):
                        QMessageBox.critical(self, "リネーム不可", "ライブラリフォルダ自体の名前は変更できません。")
                        return
                    base_dir = os.path.dirname(path)
                    new_path = os.path.join(base_dir, new_name)
                    if new_path != path:
                        os.rename(path, new_path)
                else:
                    # ファイル（Zip/PDF/ストアファイル等）のリネーム
                    parent_dir = os.path.dirname(path)
                    if _is_library_root(parent_dir):
                        # ライブラリ直下のファイル → ファイル自体をリネーム（例: Book.zip → NewName.zip）
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
        # 2025/09/06 or 2025-09-06 or 2025.09.06 形式
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
        # URL・作品IDから取得元を推定して保存（サイドバー振り分け用）
        meta_src = (db._effective_meta_source("", dlsite_id_text or "") or None) if dlsite_id_text else None

        # 先にリネーム（誤った path から修復した場合は original_path_for_db で DB の行を特定する）
        try:
            db.rename_book(original_path_for_db, new_path, new_name, new_circle, new_title, new_cover or "")
        except Exception as e:
            QMessageBox.critical(self, "DB更新エラー", str(e))
            return

        # カバー変更時は必ず DB に保存してから cleanup（保存前にクリアされないよう順序を保証）
        if self._new_cover_path:
            db.set_cover_custom(new_path, self._new_cover_path)

        # メタ情報を保存
        t1 = time.time()
        db.set_book_meta(
            new_path,
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
        )

        # パス・カバーの内部状態更新
        self._path = new_path
        self._cover = new_cover
        self._new_cover_path = None

        # カバーを変更した場合は未使用のcover_cacheを削除
        if new_cover:
            db.cleanup_unused_cover_cache()

        # 保存完了後のUI更新（単一ブックのみ）
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
            p = b.get("path")
            if not p:
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
                _m = _re.match(r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", release_date)
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
                db.update_book_display(p, circle=nc, title=nt)
                db.set_book_meta(
                    p,
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
                db.set_bookmark(p, apply_rating)
            except Exception as e:
                QMessageBox.critical(self, "DB更新エラー", "パス: %s\n%s" % (p, str(e)))
                return
        if self._on_saved:
            self._on_saved(None)
        self.accept()

    def _on_cancel(self):
        t0 = time.time()
        self.reject()


class RenameDialog(QDialog):
    """context_menu から呼び出す単純な名前変更ダイアログ"""

    def __init__(self, book: dict, parent=None, on_renamed: Callable[[], None] | None = None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self._book = book
        self._on_renamed = on_renamed
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle(config.APP_TITLE)
        self.setFixedSize(420, 190)
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {THEME_COLORS["bg_panel"]};
                color: {THEME_COLORS["text_main"]};
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        name = self._book.get("name", "")
        parsed_circle, parsed_title = db.parse_display_name(name)
        circle_init = parsed_circle or self._book.get("circle", "") or ""
        title_init = parsed_title or self._book.get("title", "") or name

        layout.addWidget(QLabel("サークル名"))
        self._circle_edit = QLineEdit(circle_init)
        layout.addWidget(self._circle_edit)

        layout.addWidget(QLabel("作品名"))
        self._title_edit = QLineEdit(title_init)
        layout.addWidget(self._title_edit)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("変更")
        btn_cancel = QPushButton("キャンセル")
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._apply)

    def _apply(self):
        path = self._book.get("path", "")
        cover = self._book.get("cover", "")
        circle_old = self._book.get("circle", "")
        title_old = self._book.get("title", "")

        new_circle = self._circle_edit.text().strip()
        new_title = self._title_edit.text().strip()
        if not new_title or not path:
            return
        new_name = db.format_book_name(new_circle, new_title)

        try:
            if os.path.isdir(path):
                if _is_library_root(path):
                    QMessageBox.critical(self, "リネーム不可", "ライブラリフォルダ自体の名前は変更できません。")
                    return
                base_dir = os.path.dirname(path)
                new_path = os.path.join(base_dir, new_name)
                os.rename(path, new_path)
            else:
                parent_dir = os.path.dirname(path)
                if _is_library_root(parent_dir):
                    # ライブラリ直下のファイル（Zip等）→ ファイル自体をリネーム
                    ext = os.path.splitext(path)[1]
                    new_path = os.path.join(parent_dir, new_name + ext)
                    if new_path != path:
                        os.rename(path, new_path)
                else:
                    # サブフォルダ内のファイル → 親フォルダをリネーム
                    grand = os.path.dirname(parent_dir)
                    new_parent = os.path.join(grand, new_name)
                    os.rename(parent_dir, new_parent)
                    new_path = os.path.join(new_parent, os.path.basename(path))

            new_cover = cover
            if cover:
                if os.path.isdir(path) and cover.startswith(path):
                    new_cover = cover.replace(path, new_path, 1)
                elif not os.path.isdir(path) and cover.startswith(path):
                    new_cover = new_path if path == cover else cover.replace(path, new_path, 1)
                else:
                    parent_dir_old = os.path.dirname(path)
                    if cover.startswith(parent_dir_old):
                        new_cover = cover.replace(parent_dir_old, os.path.dirname(new_path), 1)

            db.rename_book(path, new_path, new_name, new_circle, new_title, new_cover or "")

            if (circle_old != new_circle or title_old != new_title) and self._on_renamed:
                self._on_renamed()

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))

