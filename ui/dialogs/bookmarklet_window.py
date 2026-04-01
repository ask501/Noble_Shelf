from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QMenu,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QPixmapCache
import logging
import config
from theme import (
    APP_BAR_SEPARATOR_RGBA,
    BOOKMARKLET_THUMB_BG,
    BOOKMARKLET_THUMB_BORDER,
    THEME_COLORS,
    COLOR_WHITE,
)
import db
from book_updater import update_book_meta

# ローカルモジュール
from cover_paths import resolve_cover_path

_logger = logging.getLogger(__name__)


# ステータス定数
STATUS_PENDING = "pending"   # 既存（使わなくなるが残す）
STATUS_APPLIED = "applied"   # 🟢 自動適用済み
STATUS_ADDED = "added"       # 既存（使わなくなるが残す）
STATUS_NO_MATCH = "no_match"  # 🔴 一致なし
STATUS_MATCHED = "matched"  # 🟡 一致あり・手動待ち

STATUS_LABEL = {
    "pending": "🟡",
    "applied": "🟢",
    "added": "🔴",
    "no_match": "🔴",
    "matched": "🟡",
}


class BookmarkletWindow(QWidget):
    bookSelected = Signal(dict)  # matched row を emit
    """ブックマークレットキューパネル"""

    def __init__(self, parent=None, main_window=None) -> None:
        super().__init__(parent)
        self._main_window = main_window
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        from PySide6.QtWidgets import QFrame, QScrollArea

        outer = QVBoxLayout(self)

        copy_row = QHBoxLayout()
        self._btn_copy = QPushButton("ブックマークレットをコピー")
        self._btn_copy.clicked.connect(self._copy_bookmarklet)
        copy_row.addWidget(self._btn_copy, stretch=1)

        self._btn_help = QPushButton("？")
        self._btn_help.setFixedWidth(32)
        self._btn_help.setToolTip("手順のヘルプを開く（初めての方はこちら）")
        self._btn_help.clicked.connect(self._open_help)
        copy_row.addWidget(self._btn_help)

        outer.addLayout(copy_row)

        self._chk_auto_apply = QCheckBox("完全一致時に自動適用")
        self._chk_auto_apply.toggled.connect(self._on_auto_apply_toggled)
        val = db.get_setting("bookmarklet_auto_apply")
        self._chk_auto_apply.setChecked(val == "1" if val is not None else True)
        outer.addWidget(self._chk_auto_apply)
        self._chk_overwrite_thumb = QCheckBox("サムネイルを上書きする")
        self._chk_overwrite_thumb.toggled.connect(self._on_overwrite_thumb_toggled)
        val = db.get_setting("bookmarklet_overwrite_thumb")
        self._chk_overwrite_thumb.setChecked(val == "1" if val is not None else False)
        outer.addWidget(self._chk_overwrite_thumb)

        btn_row = QHBoxLayout()
        self._btn_del_applied = QPushButton("🟢 削除")
        self._btn_del_pending = QPushButton("🟡 削除")
        self._btn_del_added = QPushButton("🔴 削除")
        self._btn_del_all = QPushButton("全削除")
        for btn in (self._btn_del_applied, self._btn_del_pending, self._btn_del_added, self._btn_del_all):
            btn_row.addWidget(btn)
        outer.addLayout(btn_row)

        sep_top = QFrame()
        sep_top.setObjectName("BookmarkletPaneSep")
        sep_top.setFrameShape(QFrame.Shape.NoFrame)
        sep_top.setFixedHeight(1)
        sep_top.setStyleSheet(
            f"QFrame#BookmarkletPaneSep {{ background-color: {APP_BAR_SEPARATOR_RGBA}; border: none; }}"
        )
        outer.addWidget(sep_top)

        self._list = QListWidget()
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                color: {THEME_COLORS['text_main']};
                border-radius: {config.SIDEBAR_ITEM_RADIUS}px;
                padding: {config.SIDEBAR_ITEM_PADDING_Y}px {config.SIDEBAR_ITEM_PADDING_X}px;
            }}
            QListWidget::item:selected {{
                background: {THEME_COLORS['accent']};
                color: {COLOR_WHITE};
            }}
            QListWidget::item:hover:!selected {{
                background: {THEME_COLORS['hover']};
            }}
        """)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.currentItemChanged.connect(self._on_item_selected)
        outer.addWidget(self._list, stretch=1)

        sep_bottom = QFrame()
        sep_bottom.setObjectName("BookmarkletPaneSep")
        sep_bottom.setFrameShape(QFrame.Shape.NoFrame)
        sep_bottom.setFixedHeight(1)
        sep_bottom.setStyleSheet(
            f"QFrame#BookmarkletPaneSep {{ background-color: {APP_BAR_SEPARATOR_RGBA}; border: none; }}"
        )
        outer.addWidget(sep_bottom)

        detail_widget = QWidget()
        detail_widget.setFixedHeight(config.BOOKMARKLET_DETAIL_HEIGHT)
        detail_layout = QHBoxLayout(detail_widget)
        outer.addWidget(detail_widget)

        self._thumb = QLabel()
        self._thumb.setFixedSize(*config.BOOKMARKLET_THUMB_SIZE)
        self._thumb.setAlignment(Qt.AlignCenter)
        self._thumb.setStyleSheet(f"background: {BOOKMARKLET_THUMB_BG}; border: 1px solid {BOOKMARKLET_THUMB_BORDER};")
        detail_layout.addWidget(self._thumb)

        info_col = QVBoxLayout()
        detail_layout.addLayout(info_col, stretch=1)

        self._detail = QLabel()
        self._detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._detail.setWordWrap(True)
        self._detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._detail)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        info_col.addWidget(scroll, stretch=1)

        self._btn_apply = QPushButton("メタデータを適用")
        self._btn_apply.clicked.connect(self._apply_meta)
        self._btn_apply.setEnabled(False)
        info_col.addWidget(self._btn_apply)

        # シグナル接続
        self._btn_del_applied.clicked.connect(lambda: self._delete_by_status(STATUS_APPLIED))
        self._btn_del_pending.clicked.connect(lambda: self._delete_by_status(STATUS_PENDING))
        self._btn_del_added.clicked.connect(lambda: self._delete_by_status(STATUS_ADDED))
        self._btn_del_all.clicked.connect(self._delete_all)

    def _open_help(self) -> None:
        from ui.dialogs.bookmarklet_help_dialog import BookmarkletHelpDialog

        dlg = getattr(self, "_bookmarklet_help_dialog", None)
        if dlg is None:
            self._bookmarklet_help_dialog = BookmarkletHelpDialog(self)
            dlg = self._bookmarklet_help_dialog
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_overwrite_thumb_toggled(self, checked: bool) -> None:
        db.set_setting("bookmarklet_overwrite_thumb", "1" if checked else "0")

    def is_overwrite_thumb(self) -> bool:
        return self._chk_overwrite_thumb.isChecked()

    def _on_item_selected(self, current, previous) -> None:
        """リスト選択時に右パネルを更新する"""
        if not current:
            self._thumb.clear()
            self._detail.clear()
            return
        row_id = current.data(Qt.UserRole)
        if row_id == config.BOOKMARKLET_QUEUE_PLACEHOLDER_ROW_ID:
            self._thumb.clear()
            self._detail.clear()
            self._btn_apply.setEnabled(False)
            self._current_row = None
            self._found_path = None
            return
        row = db.get_bookmarklet_queue_by_id(row_id)
        if not row:
            return

        # サムネイル
        cover_url = row.get("cover_url", "")
        if cover_url:
            try:
                import urllib.request
                from PySide6.QtGui import QPixmap

                req = urllib.request.Request(
                    cover_url,
                    headers={
                        "User-Agent": config.BOOKMARKLET_UA,
                        "Referer": config.BOOKMARKLET_REFERER_DLSITE,
                    },
                )
                data = urllib.request.urlopen(req, timeout=config.BOOKMARKLET_HTTP_TIMEOUT_SEC).read()
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                self._thumb.setPixmap(
                    pixmap.scaled(
                        config.BOOKMARKLET_THUMB_SIZE[0],
                        config.BOOKMARKLET_THUMB_SIZE[1],
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
            except Exception:
                self._thumb.setText("画像なし")
        else:
            self._thumb.setText("画像なし")

        # 詳細テキスト
        tags = row.get("tags", "")
        lines = [
            f"タイトル: {row.get('title') or '—'}",
            f"サークル: {row.get('circle') or '—'}",
            f"作者: {row.get('author') or '—'}",
            f"ID: {row.get('dlsite_id') or '—'}",
            f"発売日: {row.get('release_date') or '—'}",
            f"価格: {row.get('price') or '—'}",
            f"サイト: {row.get('site') or '—'}",
            f"ステータス: {row.get('status') or '—'}",
            f"取得日時: {row.get('fetched_at') or '—'}",
            f"商品URL: {row.get('store_url') or '—'}",
            f"タグ: {tags or '—'}",
        ]
        self._detail.setText("\n".join(lines))
        # DBからマッチしたパスを自動取得
        result = db.find_book_by_bookmarklet(
            dlsite_id=row.get("dlsite_id", ""),
            title=row.get("title", ""),
            url=row.get("url", ""),
        )
        self._found_path = result["path"] if result else None
        self._current_row = row
        self._update_apply_button()
        if result:
            self.bookSelected.emit(result)

    def _update_apply_button(self) -> None:
        """適用ボタンの有効/無効を更新する"""
        row = getattr(self, "_current_row", None)
        if not row:
            self._btn_apply.setEnabled(False)
            return
        if self._found_path:
            # 黄・緑など：従来どおり
            self._btn_apply.setEnabled(True)
        else:
            # 赤：グリッドで書籍が選択されているときだけ有効
            path = getattr(self._main_window, "get_selected_book_path", lambda: None)()
            self._btn_apply.setEnabled(path is not None)

    def _on_auto_apply_toggled(self, checked: bool) -> None:
        db.set_setting("bookmarklet_auto_apply", "1" if checked else "0")

    def _copy_bookmarklet(self) -> None:
        """圧縮版ブックマークレットJSをクリップボードにコピーする"""
        port = config.BOOKMARKLET_PORT
        js = (
            f'javascript:(function(){{const PORT={port};const url=location.href;'
            f'const html=document.documentElement.outerHTML;'
            f'fetch(`http://127.0.0.1:${{PORT}}/bookmarklet`,{{method:"POST",'
            f'headers:{{"Content-Type":"application/json"}},'
            f'body:JSON.stringify({{url,html}})}})'
            f'.then(r=>r.json()).then(d=>{{if(d.status==="ok")'
            f'{{alert("Noble Shelfに送信しました！")}}'
            f'else{{alert("エラー: "+JSON.stringify(d))}}}})'
            f'.catch(()=>{{alert("Noble Shelfが起動していません。起動してからやり直してください。")}})}})()'
        )
        from PySide6.QtWidgets import QApplication, QToolTip
        from PySide6.QtGui import QCursor

        QApplication.clipboard().setText(js)
        QToolTip.showText(QCursor.pos(), "コピーしました！", self)

    def refresh(self) -> None:
        """DBからキューを再読み込みしてリストを更新する"""
        self._list.clear()
        rows = db.get_bookmarklet_queue()
        if not rows:
            ph = QListWidgetItem(config.BOOKMARKLET_QUEUE_EMPTY_PLACEHOLDER)
            ph.setData(Qt.UserRole, config.BOOKMARKLET_QUEUE_PLACEHOLDER_ROW_ID)
            ph.setFlags(Qt.ItemFlag.ItemIsEnabled)
            ph.setForeground(QBrush(QColor(THEME_COLORS["text_sub"])))
            ph_font = QFont(config.FONT_FAMILY, config.FONT_SIZE_PROP_HINT)
            ph.setFont(ph_font)
            self._list.addItem(ph)
            self._thumb.clear()
            self._detail.clear()
            self._btn_apply.setEnabled(False)
            self._current_row = None
            self._found_path = None
            self._list.setCurrentRow(-1)
            return
        for row in rows:
            lamp = STATUS_LABEL.get(row["status"], "⚪")
            text = f"{lamp}  {row['title'] or row['url']}  [{row['site']}]  {row['fetched_at']}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, row["id"])
            self._list.addItem(item)

    def _delete_by_status(self, status: str) -> None:
        db.delete_bookmarklet_queue_by_status(status)
        self.refresh()

    def _delete_all(self) -> None:
        db.delete_bookmarklet_queue_all()
        self.refresh()

    def _on_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        row_id = item.data(Qt.UserRole)
        if row_id == config.BOOKMARKLET_QUEUE_PLACEHOLDER_ROW_ID:
            return
        menu = QMenu(self)
        act_del = QAction("削除", self)
        act_del.triggered.connect(lambda: self._delete_item(row_id))
        menu.addAction(act_del)
        menu.exec(self._list.mapToGlobal(pos))

    def _delete_item(self, row_id: int) -> None:
        db.delete_bookmarklet_queue_by_id(row_id)
        self.refresh()

    def _apply_meta(self) -> None:
        row = getattr(self, "_current_row", None)
        found_path = getattr(self, "_found_path", None)
        if not found_path:
            # 赤アイテム：グリッド選択から取得
            found_path = getattr(self._main_window, "get_selected_book_path", lambda: None)()
        if not row or not found_path:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self, "未選択", "グリッドで適用先の作品を選択してください。")
            return

        from ui.dialogs.properties import MetaApplyDialog

        try:
            found_path_db = db.to_db_path_from_any(found_path)
        except ValueError as exc:
            _logger.warning("bookmarklet: DB 用パスに変換できず中止: %s", exc)
            return

        # 現在のメタをDBから取得
        current = db.get_book_meta(found_path) or {}

        # books テーブルから title / circle を補完（get_all_books: name, circle, title, path, cover, is_dlst）
        book_row = next((r for r in db.get_all_books() if r["path"] == found_path_db), None)
        if book_row:
            current["title"] = book_row["title"] or book_row["name"] or ""
            current["circle"] = book_row["circle"] or ""

        # カバーパスを解決して cover キーに追加（MetaApplyDialog は current["cover"] を参照）
        book_cover_raw = book_row["cover_path"] if book_row else ""
        current["cover"] = resolve_cover_path(book_cover_raw)

        # fetchedはキューのメタをMetaApplyDialog形式に変換
        fetched = {
            "title": row.get("title", ""),
            "circle": row.get("circle", ""),
            "author": row.get("author", ""),
            "dlsite_id": row.get("dlsite_id", ""),
            "tags": row.get("tags", "").split(",") if row.get("tags") else [],
            "price": row.get("price"),
            "release_date": row.get("release_date", ""),
            "image_url": row.get("cover_url", ""),
            "site": row.get("site", ""),
            "store_url": row.get("store_url", ""),
        }

        dlg = MetaApplyDialog(current=current, fetched=fetched, parent=self, book_path=found_path)
        result = dlg.exec()
        if result:
            applied = dlg.selected_keys()

            # release_dateの正規化
            import re as _re

            rd = applied.get("release_date", "")
            m = _re.match(r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", rd)
            if m:
                rd = f"{m.group(1)}年{int(m.group(2))}月{int(m.group(3))}日"

            _to_list = lambda s: [t.strip() for t in (s or "").split(",") if t.strip()]
            _to_int = lambda s: int(str(s).strip()) if s and str(s).strip().isdigit() else None

            db.set_book_meta(
                found_path_db,
                author=applied.get("author") or None,
                series=applied.get("series") or None,
                characters=_to_list(applied.get("characters")) or None,
                tags=_to_list(applied.get("tags")) or None,
                pages=_to_int(applied.get("pages")),
                release_date=rd or None,
                price=_to_int(applied.get("price")),
                dlsite_id=applied.get("dlsite_id") or None,
                store_url=applied.get("store_url") or None,
            )

            # books テーブルのタイトル・サークル・カバー（カスタム）を更新
            new_title = applied.get("title", "") or ""
            new_circle = applied.get("circle", "") or ""
            cover_path = applied.get("cover_path")
            if new_title or new_circle or cover_path:
                if new_title or new_circle:
                    new_name_bm = db.format_book_name(new_circle, new_title)
                    update_book_meta(
                        found_path,
                        new_name_bm,
                        new_circle,
                        new_title,
                        cover_path=cover_path if cover_path else None,
                    )
                elif cover_path:
                    for row in db.get_all_books():
                        if row["path"] == found_path_db:
                            update_book_meta(
                                found_path,
                                row["name"],
                                row["circle"],
                                row["title"] or row["name"],
                                cover_path=cover_path,
                            )
                            break

            # キューのステータス更新
            db.update_bookmarklet_queue_status(row["id"], "applied")
            QPixmapCache.clear()
            on_updated = getattr(self._main_window, "on_book_updated", None)
            if not callable(on_updated):
                on_updated = getattr(self.parent(), "on_book_updated", None)
            if callable(on_updated):
                on_updated(found_path)
            self.refresh()
            self._found_path = None

