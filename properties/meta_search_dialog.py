# プラグインが有効な場合のみ使用されるメタデータ検索UI
# plugin_loader.get_plugins() に処理を委譲する（サイト固有実装はプラグイン側）

from __future__ import annotations

import re

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

import config
import db
from properties._utils import BTN_CANCEL_STYLE, BTN_SAVE_STYLE, _meta_source_for_apply
from properties.meta_apply_dialog import MetaApplyDialog
from theme import SITE_COLORS, apply_dark_titlebar, META_SEARCH_SITE_DEFAULT, META_SEARCH_ITEM_DIM_FG


class MetaSearchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.setMinimumSize(*config.META_SEARCH_DIALOG_MIN_SIZE)
        self.result: dict | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(config.META_SEARCH_LAYOUT_SPACING)

        # 検索行（高さを統一）
        SEARCH_ROW_HEIGHT = config.META_SEARCH_ROW_HEIGHT
        search_row = QHBoxLayout()
        self._e_search = QLineEdit()
        self._e_search.setFixedHeight(SEARCH_ROW_HEIGHT)
        self._e_search.setPlaceholderText("作品名 / サークル名 / 作者名 / URL")
        self._e_search.returnPressed.connect(self._on_search)
        search_row.addWidget(self._e_search, stretch=1)

        # 検索種別
        self._kind_combo = QComboBox()
        self._kind_combo.setFixedHeight(SEARCH_ROW_HEIGHT)
        self._kind_combo.setFixedWidth(config.META_SEARCH_KIND_COMBO_WIDTH)
        self._kind_combo.addItems(["作品名", "サークル名", "作者名", "作品ID"])
        self._kind_combo.currentTextChanged.connect(self._on_kind_changed)
        search_row.addWidget(self._kind_combo)

        btn_search = QPushButton("検索")
        btn_search.setFixedHeight(SEARCH_ROW_HEIGHT)
        btn_search.setFixedWidth(config.META_SEARCH_BTN_SEARCH_WIDTH)
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
        progress.setMinimumDuration(config.META_SEARCH_PROGRESS_MIN_DURATION_MS)
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
                            max_results=config.META_SEARCH_MAX_RESULTS,
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
                color = SITE_COLORS.get(site, META_SEARCH_SITE_DEFAULT)
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

    def _search_by_url(self, query: str):
        from PySide6.QtWidgets import QProgressDialog
        import re as _re

        # 同人DB
        if "dojindb.net" in query:
            progress = QProgressDialog("取得中...", None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(config.META_SEARCH_PROGRESS_MIN_DURATION_MS)
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
                list_item.setForeground(QColor(META_SEARCH_ITEM_DIM_FG))
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
        progress.setMinimumDuration(config.META_SEARCH_PROGRESS_MIN_DURATION_MS)
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
            color = SITE_COLORS.get(source, META_SEARCH_SITE_DEFAULT)
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
        progress.setMinimumDuration(config.META_SEARCH_PROGRESS_MIN_DURATION_MS)
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

