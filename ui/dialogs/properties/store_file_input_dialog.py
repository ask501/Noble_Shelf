from __future__ import annotations

import re

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

import config
import db
from ui.dialogs.properties._utils import BTN_CANCEL_STYLE, BTN_FETCH_STYLE, BTN_SAVE_STYLE, PropertyFormContext
from ui.dialogs.properties.meta_apply_dialog import MetaApplyDialog
from ui.dialogs.properties.meta_search_dialog import MetaSearchDialog
from theme import apply_dark_titlebar, COLOR_CARD_SUB_FG


class StoreFileInputDialog(QDialog):
    """ストアファイル追加時の入力ダイアログ。作品名のみ必須。順: 作品名・サークル名・作者…。一番上にメタデータ検索。"""

    def __init__(
        self,
        path: str,
        name: str,
        mtime: float,
        suggested_circle: str,
        suggested_title: str,
        parent=None,
    ):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self._path = path
        self._name = name
        self._mtime = mtime
        self.result = None  # accept 時: ( (name, circle, title, path, "", mtime, 0), meta_dict or None )
        self._applied_cover_path = None  # メタ適用でサムネを選んだ場合のパス

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*config.STORE_FILE_INPUT_MARGINS)
        layout.setSpacing(config.STORE_FILE_INPUT_SPACING)

        lbl_file = QLabel(f"ファイル: {name}")
        lbl_file.setStyleSheet(f"color: {COLOR_CARD_SUB_FG}; font-size: {config.FONT_SIZE_PROP_HINT}px;")
        layout.addWidget(lbl_file)

        # 作品名 * 必須
        row_title = QHBoxLayout()
        row_title.setSpacing(config.STORE_FILE_INPUT_ROW_SPACING)
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
        row_circle.setSpacing(config.STORE_FILE_INPUT_ROW_SPACING)
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
            row.setSpacing(config.STORE_FILE_INPUT_ROW_SPACING)
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
        row_pages.setSpacing(config.STORE_FILE_INPUT_ROW_SPACING)
        lbl_pages = QLabel("ページ数")
        lbl_pages.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_pages.addWidget(lbl_pages)
        self._e_pages = QLineEdit()
        self._e_pages.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_pages.addWidget(self._e_pages, stretch=1)
        layout.addLayout(row_pages)

        row_release = QHBoxLayout()
        row_release.setSpacing(config.STORE_FILE_INPUT_ROW_SPACING)
        lbl_release = QLabel("発売日")
        lbl_release.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_release.addWidget(lbl_release)
        self._e_release = QLineEdit()
        self._e_release.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_release.addWidget(self._e_release, stretch=1)
        layout.addLayout(row_release)

        row_price = QHBoxLayout()
        row_price.setSpacing(config.STORE_FILE_INPUT_ROW_SPACING)
        lbl_price = QLabel("金額")
        lbl_price.setFixedWidth(config.PROP_LABEL_WIDTH)
        row_price.addWidget(lbl_price)
        self._e_price = QLineEdit()
        self._e_price.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_price.addWidget(self._e_price, stretch=1)
        layout.addLayout(row_price)

        # メモ
        row_memo = QHBoxLayout()
        row_memo.setSpacing(config.STORE_FILE_INPUT_ROW_SPACING)
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
        row_id.setSpacing(config.STORE_FILE_INPUT_ROW_SPACING)
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

