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
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
import config
from theme import (
    apply_dark_titlebar,
    APP_BAR_SEPARATOR_RGBA,
    BOOKMARKLET_THUMB_BG,
    BOOKMARKLET_THUMB_BORDER,
)
import db


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
    """ブックマークレットキューウィンドウ"""

    def __init__(self, parent=None, main_window=None) -> None:
        super().__init__(parent, Qt.Window)
        self._main_window = main_window
        apply_dark_titlebar(self)
        self.setWindowTitle(config.BOOKMARKLET_WINDOW_TITLE)
        self.resize(*config.BOOKMARKLET_WINDOW_SIZE)
        self._build_ui()
        self.refresh()

    def closeEvent(self, event: QCloseEvent) -> None:
        """×で閉じたときツールバーの紫トグルを外す（透明背景に戻す）"""
        mw = self._main_window
        if mw is not None and hasattr(mw, "_sync_bookmarklet_toolbar_toggle"):
            mw._sync_bookmarklet_toolbar_toggle(False)
        super().closeEvent(event)

    def _build_ui(self) -> None:
        from PySide6.QtWidgets import QFrame

        columns = QHBoxLayout(self)

        # ── 左ペイン ──
        left = QVBoxLayout()

        copy_row = QHBoxLayout()
        self._btn_copy = QPushButton("ブックマークレットをコピー")
        self._btn_copy.clicked.connect(self._copy_bookmarklet)
        copy_row.addWidget(self._btn_copy, stretch=1)

        self._btn_help = QPushButton("？")
        self._btn_help.setFixedWidth(32)
        self._btn_help.setToolTip("ヘルプを表示")
        self._btn_help.clicked.connect(self._open_help)
        copy_row.addWidget(self._btn_help)

        left.addLayout(copy_row)

        self._chk_auto_apply = QCheckBox("完全一致時に自動適用")
        self._chk_auto_apply.toggled.connect(self._on_auto_apply_toggled)
        val = db.get_setting("bookmarklet_auto_apply")
        self._chk_auto_apply.setChecked(val == "1" if val is not None else True)
        left.addWidget(self._chk_auto_apply)

        btn_row = QHBoxLayout()
        self._btn_del_applied = QPushButton("🟢 削除")
        self._btn_del_pending = QPushButton("🟡 削除")
        self._btn_del_added = QPushButton("🔴 削除")
        self._btn_del_all = QPushButton("全削除")
        for btn in (self._btn_del_applied, self._btn_del_pending, self._btn_del_added, self._btn_del_all):
            btn_row.addWidget(btn)
        left.addLayout(btn_row)

        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.currentItemChanged.connect(self._on_item_selected)
        left.addWidget(self._list, stretch=1)
        columns.addLayout(left, stretch=2)

        sep = QFrame()
        sep.setObjectName("BookmarkletPaneSep")
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setFixedWidth(1)
        sep.setStyleSheet(
            f"QFrame#BookmarkletPaneSep {{ background-color: {APP_BAR_SEPARATOR_RGBA}; border: none; }}"
        )
        columns.addWidget(sep)

        # 右: 詳細パネル
        right = QVBoxLayout()
        columns.addLayout(right, stretch=1)

        self._thumb = QLabel()
        self._thumb.setFixedSize(*config.BOOKMARKLET_THUMB_SIZE)
        self._thumb.setAlignment(Qt.AlignCenter)
        self._thumb.setStyleSheet(f"background: {BOOKMARKLET_THUMB_BG}; border: 1px solid {BOOKMARKLET_THUMB_BORDER};")
        right.addWidget(self._thumb)

        self._detail = QLabel()
        self._detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._detail.setWordWrap(True)
        self._detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.addWidget(self._detail)

        self._btn_apply = QPushButton("メタデータを適用")
        self._btn_apply.clicked.connect(self._apply_meta)
        self._btn_apply.setEnabled(False)
        right.addWidget(self._btn_apply)
        right.addStretch()

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

    def _on_item_selected(self, current, previous) -> None:
        """リスト選択時に右パネルを更新する"""
        if not current:
            self._thumb.clear()
            self._detail.clear()
            return
        row_id = current.data(Qt.UserRole)
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
        self._btn_apply.setEnabled(True)
        self._current_row = row  # 現在選択中のrowを保持

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
        for row in db.get_bookmarklet_queue():
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
        if not row or not found_path:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self, "未検索", "ライブラリに一致する作品が見つかりませんでした。")
            return
        import os

        from ui.dialogs.properties import MetaApplyDialog

        # 現在のメタをDBから取得
        current = db.get_book_meta(found_path) or {}

        # books テーブルから title / circle を補完（get_all_books: name, circle, title, path, cover, is_dlst）
        book_row = next((r for r in db.get_all_books() if r[3] == found_path), None)
        if book_row:
            current["title"] = book_row[2] or book_row[0] or ""
            current["circle"] = book_row[1] or ""

        # カバーパスを解決して cover キーに追加（MetaApplyDialog は current["cover"] を参照）
        book_cover_raw = book_row[4] if book_row else ""
        resolved_cover = (
            db.resolve_cover_stored_value(book_cover_raw) if book_cover_raw else ""
        )
        current["cover"] = (
            resolved_cover if (resolved_cover and os.path.isfile(resolved_cover)) else ""
        )

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
                found_path,
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

            # books テーブルのタイトル・サークルも更新
            new_title = applied.get("title", "") or ""
            new_circle = applied.get("circle", "") or ""
            if new_title or new_circle:
                db.update_book_display(found_path, circle=new_circle, title=new_title)

            # カバー画像の更新
            cover_path = applied.get("cover_path")
            if cover_path:
                db.update_book_cover_path(found_path, cover_path)

            # キューのステータス更新
            db.update_bookmarklet_queue_status(row["id"], "applied")
            self.refresh()
            self._found_path = None

