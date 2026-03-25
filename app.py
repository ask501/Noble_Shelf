"""
app.py - メインウィンドウ
"""
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QStatusBar,
    QSlider,
    QLabel,
    QProgressDialog,
    QMessageBox,
    QDialog,
    QPushButton,
    QComboBox,
    QLineEdit,
    QProgressBar,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QButtonGroup,
)
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QUrl, QMimeData
from PySide6.QtGui import QAction, QKeySequence
import logging
import os
import random
import time

import config
import db
from paths import normalize_path, to_rel
from ui.dialogs.library_folder_dialog import LibraryFolderDialog
from version import VERSION
from grid import BookGridView
from scanners import scan_library
from ui.widgets.sidebar import SidebarWidget
from ui.widgets.searchbar import SearchBar, filter_books, build_haystack_cache
from ui.widgets.toolbar import ToolBar
from drop_handler import handle_drop, _get_pdf_cover_and_pages
from ui.dialogs.filter_popover import FilterPopover
from theme import THEME_COLORS, COLOR_BORDER, apply_dark_titlebar, get_statusbar_scan_progress_qss
from ui.dialogs.properties import _auto_kana, _needs_kana_conversion, StoreFileInputDialog
from ui.widgets.menubar import setup_menubar, refresh_shortcuts
from ui.dialogs.first_run import LibrarySetupOverlay
from ui.widgets.statusbar import setup_statusbar


def _cover_has_path_segment(clean: str) -> bool:
    """相対パス文字列がライブラリ配下のサブパスとして扱えるか（区切りを含むか）。"""
    if os.sep in clean:
        return True
    if "/" in clean:
        return True
    if os.altsep and os.altsep in clean:
        return True
    return False


def _resolve_cover(path: str, cover: str, library_folder: str = "") -> str:
    """
    DBのカバーパスを表示・参照用に解決する（文字列結合のみ。実在確認はグリッド側）。
    優先: 絶対パス → 相対かつサブパスなら library_folder 結合 → resolve_cover_stored_value
    → library_folder 結合 → 作品 path 配下。
    """
    if not cover or not str(cover).strip():
        return cover or ""
    clean = str(cover).strip()
    lf = (library_folder or "").strip()
    if os.path.isabs(clean):
        return os.path.normpath(clean)
    if lf and _cover_has_path_segment(clean):
        return os.path.normpath(os.path.join(lf, clean))
    c = db.resolve_cover_stored_value(cover)
    if not c:
        return clean
    if lf and not _cover_has_path_segment(clean):
        return c
    if lf:
        return os.path.normpath(os.path.join(lf, clean))
    if path:
        return os.path.normpath(os.path.join(path, os.path.basename(c)))
    return c


class MainWindow(QMainWindow):
    bookmarkletReceived = Signal()  # ブックマークレット受信通知（既存のSignalインポートを使用）
    def __init__(self):
        """メインウィンドウを初期化しUIとDBを準備する。"""
        super().__init__()
        self._startup_t0 = time.perf_counter()
        self.setWindowTitle(f"{config.APP_TITLE} v{VERSION}")
        self.resize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)

        db.init_db()
        self._all_books: list[dict] = []
        # グリッドに表示中の一覧（フィルタ・ソート適用後）。ランダムオープン等で使用
        self._books: list[dict] = []
        # (mode, value)。value は str または history_all 用の path 集合
        self._sidebar_filter: tuple[str, str | set[str]] | None = None
        # ソート状態: デフォルトは「追加順・降順」（config.STARTUP_SORT_DEFAULT_KEY_FALLBACK 等と一致）
        self._sort_key: str = "added_date"
        self._sort_desc: bool = True
        # メタデータキャッシュ（ソート/フィルタ用）
        self._meta_cache: dict[str, dict] = {}
        # フィルターパネルで設定したアクティブ条件
        self._active_filters: list[dict] = []
        self._filter_logic: str = "and"
        self._filter_panel: FilterPopover | None = None  # _setup_central のスプリッターで生成
        # メニュー「DLSiteのファイルのみ」「FANZA/DMMのファイルのみ」（重複可＝両方ONで両方表示）
        self._filter_dlsite_only: bool = False
        self._filter_fanza_only: bool = False
        self._filter_no_cover_only: bool = False  # 表示メニュー「サムネイル未設定」選択時
        # 起動後最初のスキャン完了まで True（ストアファイル登録ダイアログを抑止する判定に使用）
        self._is_startup_scan: bool = True
        self._open_viewers: list = []  # 内置ビューワー（すべて閉じる用）
        self._bookmarklet_window = None
        self._scan_blocking = False

        self._setup_menubar()
        self._setup_central()
        self._setup_statusbar()
        self.setAcceptDrops(True)
        self._restore_ui_visibility()
        QTimer.singleShot(config.APP_STARTUP_LOAD_DELAY_MS, self._load_library)

        self.bookmarkletReceived.connect(self._on_bookmarklet_received)
        self._start_local_server()

        apply_dark_titlebar(self)
        # 最大化ボタンを有効化（フラグが外れている環境対策）
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.menuBar().installEventFilter(self)
        self.centralWidget().installEventFilter(self)
        self.installEventFilter(self)

    def _resolve_cover_fast(self, path: str, cover: str, library_folder: str) -> str:
        """I/Oゼロ版。パス組み立てのみ。存在確認は描画時に委譲。"""
        if not cover:
            return ""
        clean_cover = cover.strip()
        if os.path.isabs(clean_cover):
            return clean_cover
        # パス区切りを含む場合のみ library_folder と結合する（IDのみの場合は cover_cache 経由）
        if library_folder and _cover_has_path_segment(clean_cover):
            return os.path.normpath(os.path.join(library_folder, clean_cover))
        return db.resolve_cover_stored_value(clean_cover)

    def eventFilter(self, obj, event):
        """フォーカス解除とタイトルバー等の最大化ダブルクリックを処理する。"""
        # 右クリックは grid の customContextMenuRequested に任せる（eventFilter では扱わない）

        # 検索入力以外をクリックしたら検索フォーカスを解除
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            f = QApplication.focusWidget()
            if f is getattr(self._searchbar, "_input", None):
                if obj is not f and not (hasattr(f, "isAncestorOf") and f.isAncestorOf(obj)):
                    f.clearFocus()

        # タイトルバー・メニューバー・上端のダブルクリックで最大化/元に戻す
        if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            if obj is self:
                # ウィンドウ自体に届いたダブルクリック（タイトルバー等）
                pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                if pos.y() < config.TITLE_BAR_DBLCLICK_HEIGHT:
                    if self.isMaximized():
                        self.showNormal()
                    else:
                        self.showMaximized()
                    return True
            if obj is self.menuBar():
                if self.isMaximized():
                    self.showNormal()
                else:
                    self.showMaximized()
                return True
            if obj is self.centralWidget():
                g = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                fr = self.frameGeometry()
                if fr.contains(g) and g.y() - fr.y() < config.TITLE_BAR_DBLCLICK_HEIGHT:
                    if self.isMaximized():
                        self.showNormal()
                    else:
                        self.showMaximized()
                    return True
        return super().eventFilter(obj, event)

    # ── メニューバー ──────────────────────────────────────
    def _setup_menubar(self):
        """メニューバーとツールバー表示項目を組み立てる。"""
        setup_menubar(self)
        # 表示メニューに「ツールバー」チェック（menubar.setup_menubar 後に挿入）
        for _mb_action in self.menuBar().actions():
            _sub = _mb_action.menu()
            if _sub is not None and _mb_action.text() == "表示(&V)":
                self._act_toolbar = QAction("ツールバー", self)
                self._act_toolbar.setCheckable(True)
                self._act_toolbar.setChecked(True)
                self._act_toolbar.triggered.connect(
                    lambda checked: self._set_main_toolbar_visible(checked, save=True)
                )
                _sub.insertAction(self._act_searchbar, self._act_toolbar)
                break
        if hasattr(self, "_act_tool_library_check"):
            self._act_tool_library_check.triggered.connect(self._open_library_check_dialog)

    def _on_open_settings(self):
        """設定ダイアログを開きショートカットとカード表示を反映する。"""
        from PySide6.QtWidgets import QDialog
        from ui.dialogs.settings import SettingsDialog

        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            refresh_shortcuts(self)
        # 設定ダイアログを閉じたらカード表示設定を反映
        self._grid.apply_display_settings()

    def _open_library_check_dialog(self) -> None:
        """ライブラリ整合性チェック用ダイアログを開く。"""
        library_folder = (db.get_setting("library_folder") or "").strip()
        if not library_folder or not os.path.isdir(library_folder):
            QMessageBox.information(self, config.APP_TITLE, "ライブラリフォルダが未設定です。")
            return
        from ui.dialogs.library_check_dialog import LibraryCheckDialog

        dlg = LibraryCheckDialog(library_folder, self)
        dlg.exec()

    # ── ファイルメニュー ────────────────────────────────────
    def _get_selected_books(self) -> list[dict]:
        """グリッドで選択中のブックのリストを返す。"""
        from grid import ROLE_PATH, ROLE_TITLE, ROLE_CIRCLE, ROLE_PAGES, ROLE_COVER, ROLE_RATING
        books = []
        for idx in self._grid.selectedIndexes():
            path = idx.data(ROLE_PATH)
            if not path:
                continue
            books.append({
                "path": path,
                "title": idx.data(ROLE_TITLE) or "",
                "circle": idx.data(ROLE_CIRCLE) or "",
                "pages": idx.data(ROLE_PAGES) or 0,
                "cover": idx.data(ROLE_COVER) or "",
                "rating": idx.data(ROLE_RATING) or 0,
                "name": idx.data(ROLE_TITLE) or "",
            })
        return books

    def _on_file_menu_about_to_show(self):
        """ファイルメニュー表示直前に有効/無効を更新"""
        selected = self._get_selected_books()
        has_selection = len(selected) > 0
        library_folder = (db.get_setting("library_folder") or "").strip()
        has_library = bool(library_folder and os.path.isdir(library_folder))
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        has_clipboard = mime.hasUrls() and len(mime.urls()) > 0
        has_viewers = len(self._open_viewers) > 0

        if hasattr(self, "_act_file_open"):
            self._act_file_open.setEnabled(has_selection)
        if hasattr(self, "_act_file_close_all"):
            self._act_file_close_all.setEnabled(has_viewers)
        if hasattr(self, "_act_file_open_library"):
            self._act_file_open_library.setEnabled(has_library)
        if hasattr(self, "_act_file_copy"):
            self._act_file_copy.setEnabled(has_selection)
        if hasattr(self, "_act_file_paste"):
            self._act_file_paste.setEnabled(has_clipboard and has_library)
        if hasattr(self, "_act_file_print"):
            self._act_file_print.setEnabled(has_selection)
        if hasattr(self, "_act_file_rescan"):
            self._act_file_rescan.setEnabled(has_library)
        if hasattr(self, "_act_file_reset_cache"):
            self._act_file_reset_cache.setEnabled(True)
        if hasattr(self, "_act_file_set_library"):
            self._act_file_set_library.setEnabled(True)
        if hasattr(self, "_act_file_quit"):
            self._act_file_quit.setEnabled(True)

    def _file_open_selected(self):
        """選択中のブックを開く"""
        books = self._get_selected_books()
        if not books:
            return
        from context_menu import open_book
        modal = len(books) == 1
        for b in books:
            path = b.get("path")
            if path and os.path.exists(path):
                open_book(path, self, modal=modal)
        if hasattr(self, "_sidebar") and self._sidebar and self._sidebar._mode == "history":
            self._sidebar.refresh()

    def _file_show_recent_popup(self):
        """最近開いたブックをポップアップメニューで表示"""
        recent = db.get_recent_books(limit=config.RECENT_BOOKS_MENU_LIMIT)
        if not recent:
            return
        from PySide6.QtWidgets import QMenu
        from context_menu import open_book
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {THEME_COLORS['bg_panel']}; color: {THEME_COLORS['text_main']}; }}"
            f"QMenu::item:disabled {{ color: {THEME_COLORS['menu_disabled']}; }}"
        )

        def _open_recent_menu_item(p: str) -> None:
            """履歴から該当作品を開き履歴モードなら更新する。"""
            open_book(p, self, modal=False)
            if hasattr(self, "_sidebar") and self._sidebar and self._sidebar._mode == "history":
                self._sidebar.refresh()

        for name, path in recent:
            if not path or not os.path.exists(path):
                continue
            act = menu.addAction(name or os.path.basename(path) or path)
            act.triggered.connect(lambda checked=False, p=path: _open_recent_menu_item(p))
        if menu.actions():
            from PySide6.QtGui import QCursor
            menu.exec(QCursor.pos())

    def _file_close_all_viewers(self):
        """開いている内置ビューワーをすべて閉じる"""
        for v in list(self._open_viewers):
            if hasattr(v, "close") and v.isVisible():
                v.close()
        self._open_viewers.clear()

    def _file_open_library_folder(self):
        """設定中のライブラリフォルダをエクスプローラーで開く"""
        folder = (db.get_setting("library_folder") or "").strip()
        if not folder or not os.path.isdir(folder):
            return
        os.startfile(folder)

    def _file_copy_selected(self):
        """選択中のブックのパスをOSクリップボードにコピー（ファイル/フォルダのドラッグ用）"""
        books = self._get_selected_books()
        if not books:
            return
        urls = [
            QUrl.fromLocalFile(b["path"])
            for b in books
            if b.get("path") and os.path.exists(b["path"])
        ]
        if not urls:
            return
        clipboard = QApplication.clipboard()
        mime = QMimeData()
        mime.setUrls(urls)
        clipboard.setMimeData(mime)

    def _file_paste(self):
        """OSクリップボードから貼り付け（ドロップと同じ挙動、重複時はエラー）"""
        folder = (db.get_setting("library_folder") or "").strip()
        if not folder or not os.path.isdir(folder):
            return
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if not mime.hasUrls():
            return
        paths = [u.toLocalFile() for u in mime.urls()]
        if not paths:
            return
        handle_drop(
            paths=paths,
            library_folder=folder,
            parent=self,
            on_done=self._on_drop_done,
        )

    def _file_print_selected(self):
        """選択中のブックを印刷キューに送る"""
        books = self._get_selected_books()
        if not books:
            return
        path = books[0].get("path")
        if not path or not os.path.exists(path):
            return
        if os.path.isfile(path):
            os.startfile(path, "print")
        else:
            os.startfile(path)

    def _file_quit_with_confirm(self):
        """確認ダイアログを出して終了"""
        if QMessageBox.question(
            self,
            config.APP_TITLE,
            "アプリケーションを終了しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.close()

    def _open_bookmarklet_window(self) -> None:
        """ブックマークレットキューウィンドウを開く"""
        if not hasattr(self, "_bookmarklet_window") or self._bookmarklet_window is None:
            from ui.dialogs.bookmarklet_window import BookmarkletWindow
            from theme import apply_dark_titlebar
            self._bookmarklet_window = BookmarkletWindow(parent=self, main_window=self)
        self._bookmarklet_window.show()
        from theme import apply_dark_titlebar
        apply_dark_titlebar(self._bookmarklet_window)
        self._bookmarklet_window.raise_()
        self._bookmarklet_window.activateWindow()
        self._sync_bookmarklet_toolbar_toggle(True)

    def _sync_bookmarklet_toolbar_toggle(self, checked: bool) -> None:
        """ツールバー上のブックマークレットボタンをウィンドウ表示状態に合わせる（紫/透明）。"""
        if hasattr(self, "_main_toolbar"):
            self._main_toolbar.set_bookmarklet_toggle_checked(checked)

    def _on_bookmarklet_toolbar_toggled(self, visible: bool) -> None:
        """ブックマークレットツールバートグル：ON でキュー表示、OFF で隠す（×閉じと同じ見た目）。"""
        if visible:
            self._open_bookmarklet_window()
        else:
            if self._bookmarklet_window is not None:
                self._bookmarklet_window.hide()

    # ═══ ブックマークレット ═══
    def _start_local_server(self) -> None:
        """ローカルHTTPサーバーを起動する"""
        import local_server

        local_server.start(on_receive=self._on_receive_bookmarklet)

    def _on_receive_bookmarklet(self, url: str, html: str) -> None:
        """
        ブックマークレットからの受信処理（バックグラウンドスレッドから呼ばれる）。
        メタデータ取得→DB保存→メインスレッドへシグナルemit。
        """

        def _save_cover(cover_url: str, book_path: str) -> str | None:
            """取得画像をカバーキャッシュにJPEGで保存する。"""
            import hashlib

            from ui.dialogs.thumbnail_crop_dialog import _download_image

            pix = _download_image(cover_url)
            if pix is None or pix.isNull():
                return None
            os.makedirs(config.COVER_CACHE_DIR, exist_ok=True)
            key = hashlib.md5(book_path.encode()).hexdigest()
            out_path = os.path.join(config.COVER_CACHE_DIR, f"{key}_fetched.jpg")
            if pix.save(out_path, "JPEG", quality=90):
                return out_path
            return None

        try:
            from bookmarklet import fetch_meta
            meta = fetch_meta(url=url, html=html)
        except Exception:
            meta = {}
        try:
            matched = db.find_book_by_bookmarklet(
                dlsite_id=meta.get("dlsite_id", ""),
                title=meta.get("title", ""),
            )

            auto_apply = db.get_setting("bookmarklet_auto_apply") == "1"
            q_url = url
            q_site = meta.get("site", "")
            q_title = meta.get("title", "")
            q_circle = meta.get("circle", "")
            q_author = meta.get("author", "")
            q_dlsite_id = meta.get("dlsite_id", "")
            q_tags = ",".join(meta.get("tags", []))
            q_price = meta.get("price")
            q_release_date = meta.get("release_date", "")
            q_cover_url = meta.get("cover_url", "")
            q_store_url = meta.get("store_url", "")

            if matched is None:
                # 一致なし → no_match
                db.add_bookmarklet_queue(
                    url=q_url,
                    site=q_site,
                    title=q_title,
                    circle=q_circle,
                    author=q_author,
                    dlsite_id=q_dlsite_id,
                    tags=q_tags,
                    price=q_price,
                    release_date=q_release_date,
                    cover_url=q_cover_url,
                    store_url=q_store_url,
                    status="no_match",
                )
            elif auto_apply:
                # 一致あり＋自動適用ON → メタ適用して applied
                found_path = matched["path"]
                db.set_book_meta(
                    found_path,
                    author=meta.get("author", "") or "",
                    tags=meta.get("tags") or [],
                    dlsite_id=meta.get("dlsite_id") or None,
                    release_date=meta.get("release_date") or None,
                    price=meta.get("price"),
                    store_url=meta.get("store_url") or None,
                )
                if (meta.get("title", "") or "").strip():
                    db.update_book_display(
                        found_path,
                        title=meta.get("title") or None,
                        circle=meta.get("circle") or None,
                    )
                cover_url = (meta.get("cover_url", "") or "").strip()
                if cover_url:
                    # get_book_cover は無いため、get_all_books の cover 列（custom優先）で既存サムネを判定
                    existing_cover = ""
                    for row in db.get_all_books():
                        if row[3] == found_path:
                            existing_cover = (row[4] or "").strip()
                            break
                    resolved = (
                        db.resolve_cover_stored_value(existing_cover) if existing_cover else ""
                    )
                    if not (resolved and os.path.isfile(resolved)):
                        saved_path = _save_cover(cover_url, found_path)
                        if saved_path:
                            db.set_cover_custom(found_path, saved_path)
                db.add_bookmarklet_queue(
                    url=q_url,
                    site=q_site,
                    title=q_title,
                    circle=q_circle,
                    author=q_author,
                    dlsite_id=q_dlsite_id,
                    tags=q_tags,
                    price=q_price,
                    release_date=q_release_date,
                    cover_url=q_cover_url,
                    store_url=q_store_url,
                    status="applied",
                )
                self.on_book_updated(found_path)
            else:
                # 一致あり＋自動適用OFF → matched で止める
                db.add_bookmarklet_queue(
                    url=q_url,
                    site=q_site,
                    title=q_title,
                    circle=q_circle,
                    author=q_author,
                    dlsite_id=q_dlsite_id,
                    tags=q_tags,
                    price=q_price,
                    release_date=q_release_date,
                    cover_url=q_cover_url,
                    store_url=q_store_url,
                    status="matched",
                )
        except Exception:
            pass
        self.bookmarkletReceived.emit()

    def _on_bookmarklet_received(self) -> None:
        """メインスレッド：ウィンドウを開いてリストを更新する"""
        self._open_bookmarklet_window()
        if self._bookmarklet_window is not None:
            self._bookmarklet_window.refresh()

    def closeEvent(self, event) -> None:
        """終了時にバックアップを非同期実行してから終了する。"""
        self.hide()
        event.ignore()
        QTimer.singleShot(0, self._do_backup_and_quit)

    def _do_backup_and_quit(self) -> None:
        import time
        import local_server

        last = db.get_last_backup_time()
        if time.time() - last >= config.BACKUP_INTERVAL_SEC:
            try:
                db.backup_daily(config.DB_BACKUP_DAILY_PATH)
                db.set_last_backup_time(time.time())
            except Exception:
                pass
        try:
            os.remove(config.APP_LOCK_FILE_PATH)
        except Exception:
            pass
        local_server.stop()
        QApplication.quit()

    def _on_restore_backup(self):
        """バックアップ一覧からDBを復元し再起動を案内する。"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QDialogButtonBox, QMessageBox
        import db
        import os

        backups = db.list_backups()
        if not backups:
            QMessageBox.information(self, "バックアップ", "バックアップが見つかりませんでした。")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("バックアップから復元")
        dlg.resize(*config.RESTORE_BACKUP_DIALOG_SIZE)
        layout = QVBoxLayout(dlg)

        lst = QListWidget()
        for info in backups:
            path = info.get("path", "")
            fname = os.path.basename(path) if path else ""
            # library_YYYYMMDD_HHMMSS.db → YYYY/MM/DD HH:MM:SS
            try:
                body = fname[len("library_"):-len(".db")]
                dt = f"{body[:4]}/{body[4:6]}/{body[6:8]} {body[9:11]}:{body[11:13]}:{body[13:15]}"
            except Exception:
                dt = fname
            lst.addItem(dt)
        lst.setCurrentRow(0)
        layout.addWidget(lst)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("復元")
        btns.button(QDialogButtonBox.Cancel).setText("キャンセル")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        idx = lst.currentRow()
        if idx < 0:
            return

        confirm = QMessageBox.question(
            self, "確認",
            "選択したバックアップに復元します。\n続けますか？",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        db.restore_backup(backups[idx]["path"])
        result = QMessageBox.question(
            self, "復元完了",
            "復元しました。今すぐ再起動しますか？\n（いいえを選ぶと次回起動時に反映されます）",
            QMessageBox.Yes | QMessageBox.No
        )
        if result == QMessageBox.Yes:
            import os as _os, sys as _sys
            _os.execv(_sys.executable, [_sys.executable] + _sys.argv)

    # ── 中央レイアウト ────────────────────────────────────
    # ═══ UI初期化・レイアウト ═══
    def _setup_central(self):
        """中央部にツールバー・検索・グリッド・フィルタを配置する。"""
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        outer.setSpacing(config.LAYOUT_SPACING_ZERO)

        # メニュー直下：1行目 ToolBar、2行目 SearchBar（それぞれ独立した QWidget）
        self._toolbar_row = QWidget()
        toolbar_row_layout = QHBoxLayout(self._toolbar_row)
        toolbar_row_layout.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        toolbar_row_layout.setSpacing(config.LAYOUT_SPACING_ZERO)

        self._main_toolbar = ToolBar()
        toolbar_row_layout.addWidget(self._main_toolbar)
        self._main_toolbar.setVisible(False)

        self._searchbar_row = QWidget()
        searchbar_row_layout = QHBoxLayout(self._searchbar_row)
        searchbar_row_layout.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        searchbar_row_layout.setSpacing(config.LAYOUT_SPACING_ZERO)

        self._searchbar = SearchBar()
        self._searchbar.searchChanged.connect(self._on_search_changed)
        self._searchbar.cleared.connect(self._on_search_cleared)
        # 行いっぱいに広げ、SearchBar 内の stretch でカプセルを中央寄せ（狭い中央列だと左寄りに見える）
        searchbar_row_layout.addWidget(self._searchbar, stretch=1)

        outer.addWidget(self._toolbar_row)
        outer.addWidget(self._searchbar_row)

        sep1 = QWidget()
        sep1.setFixedHeight(config.SEPARATOR_LINE_HEIGHT)
        sep1.setStyleSheet(f"background-color: {COLOR_BORDER};")
        outer.addWidget(sep1)

        # ツールバー検索アイコン：検索バー表示＋表示メニュー・DB（ui_show_searchbar）と同期
        self._main_toolbar.searchToggled.connect(
            lambda visible: self._set_searchbar_visible(visible, save=True)
        )
        self._main_toolbar.randomRequested.connect(self._on_random_requested)
        self._main_toolbar.bookmarkletToggled.connect(self._on_bookmarklet_toolbar_toggled)

        # スプリッター（サイドバー | グリッド＋ソートバー）
        splitter = QSplitter(Qt.Horizontal)

        self._sidebar = SidebarWidget()
        self._sidebar.filterChanged.connect(self._on_filter_changed)
        self._sidebar.filterCleared.connect(self._on_filter_cleared)
        # サイドバーのモード変更 = ソート項目変更として扱う
        self._sidebar.sortModeChanged.connect(self._on_sort_mode_changed)
        # 作品名サイドバーでの選択 → グリッドへスクロール
        self._sidebar.titleSelected.connect(self._on_title_selected)
        self._sidebar.contextMenuRequested.connect(self._on_sidebar_context_menu_requested)
        splitter.addWidget(self._sidebar)

        # ツールバーサイドバーアイコン：サイドバー表示＋表示メニュー・DB（ui_show_sidebar）と同期
        self._main_toolbar.sidebarToggled.connect(
            lambda visible: self._set_sidebar_visible(visible, save=True)
        )

        # 右側コンテナ: ソートバー（ゴーストバー）＋下線、下にグリッド
        grid_container = QWidget()
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        grid_layout.setSpacing(config.LAYOUT_SPACING_ZERO)

        # ── ゴーストバー（ソートキーラベル / 昇降順） ──
        self._sort_bar = QWidget()
        self._sort_bar.setObjectName("SortBar")
        self._sort_bar.setFixedHeight(config.GHOSTBAR_HEIGHT)

        from PySide6.QtGui import QFont

        bar_layout = QHBoxLayout(self._sort_bar)
        bar_layout.setContentsMargins(config.SORT_BAR_MARGIN_LEFT, 0, config.SORT_BAR_MARGIN_RIGHT, 0)
        bar_layout.setSpacing(config.SORT_BAR_SPACING)

        font = QFont(config.FONT_FAMILY, config.FONT_SIZE_SORT_BTN)

        # クソデカラベル（現在のソートキー表示）
        self._sort_label = QLabel()
        self._sort_label.setObjectName("SortLabel")
        label_font = QFont(config.FONT_FAMILY, config.FONT_SIZE_SORT_LABEL)
        label_font.setBold(True)
        self._sort_label.setFont(label_font)
        self._sort_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        bar_layout.addWidget(self._sort_label)

        # 昇順 / 降順トグルボタン
        self._sort_order_btn = QPushButton()
        self._sort_order_btn.setObjectName("SortOrderButton")
        self._sort_order_btn.setFixedHeight(config.SORT_BAR_BUTTON_HEIGHT)
        self._sort_order_btn.setFont(font)
        self._sort_order_btn.clicked.connect(self._on_sort_order_toggled)
        bar_layout.addWidget(self._sort_order_btn)

        # 右側を埋めるストレッチ
        bar_layout.addStretch()

        # ゴーストバーのスタイル
        self._sort_bar.setStyleSheet(
            f"""
            QWidget#SortBar {{
                background-color: {THEME_COLORS["bg_panel"]};
                color: {THEME_COLORS["text_main"]};
            }}
            QLabel#SortLabel {{
                background-color: transparent;
                color: {THEME_COLORS["text_main"]};
                padding-left: {config.SORT_BAR_LABEL_PADDING_LEFT}px;
            }}
            QPushButton#SortOrderButton {{
                background-color: {THEME_COLORS["bg_widget"]};
                color: {THEME_COLORS["text_main"]};
                border: 1px solid {THEME_COLORS["border"]};
                border-radius: {config.SORT_BAR_BTN_RADIUS}px;
                padding: {config.SORT_BAR_BTN_PADDING_Y}px {config.SORT_BAR_BTN_PADDING_X}px;
            }}
            QPushButton#SortOrderButton:hover {{
                background-color: {THEME_COLORS["hover"]};
            }}
            """
        )
        grid_layout.addWidget(self._sort_bar)

        self._sort_bar_sep_bottom = QWidget()
        self._sort_bar_sep_bottom.setFixedHeight(config.SEPARATOR_LINE_HEIGHT)
        self._sort_bar_sep_bottom.setStyleSheet(f"background-color: {COLOR_BORDER};")
        grid_layout.addWidget(self._sort_bar_sep_bottom)

        self._scan_stale_flag = QLabel(config.SCAN_STALE_FLAG_TEXT)
        self._scan_stale_flag.setVisible(False)
        self._scan_stale_flag.setStyleSheet(
            f"color: {THEME_COLORS['text_sub']}; font-size: {config.FONT_SIZE_XS}px; padding: 2px 8px;"
        )
        grid_layout.addWidget(self._scan_stale_flag)

        self._main_toolbar.ghostBarToggled.connect(
            lambda visible: self._set_ghostbar_visible(visible, save=True)
        )

        self._grid = BookGridView(app_callbacks=self._make_app_callbacks())
        grid_layout.addWidget(self._grid)

        # ライブラリ未設定時に中央に表示するオーバーレイ
        self._empty_hint = LibrarySetupOverlay()
        self._empty_hint.setupClicked.connect(self._on_click_setup_library)
        grid_layout.addWidget(self._empty_hint)

        splitter.addWidget(grid_container)

        self._filter_panel = FilterPopover(
            self,
            on_apply=self._on_filter_popover_apply,
            on_clear=self._on_filter_popover_clear,
            on_clear_only=self._on_filter_popover_clear_only,
        )
        self._filter_panel.setVisible(False)
        splitter.addWidget(self._filter_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes(
            [
                config.MAIN_SPLITTER_SIDEBAR_INIT_WIDTH,
                config.WINDOW_WIDTH - config.MAIN_SPLITTER_SIDEBAR_INIT_WIDTH,
                0,  # 右パネル初期非表示（配分 0）
            ]
        )
        outer.addWidget(splitter, stretch=1)
        self._splitter = splitter

        self._main_toolbar.filterToggled.connect(self._on_filter_toggled)
        self._main_toolbar._btn_settings.clicked.connect(self._on_open_settings)

        # 初期ソートバー表示
        self._update_sort_bar()

    def _make_app_callbacks(self) -> dict:
        """グリッド向けコールバック辞書を返す。"""
        return {
            "rescan": self._rescan_library,
            "get_library_folder": lambda: (db.get_setting("library_folder") or "").strip(),
            "filter_by_circle": self._goto_circle,
        }

    def _goto_circle(self, circle: str):
        """サークルに移動：サイドバーをサークルモードにして該当サークルを選択状態にする"""
        self._sidebar.set_mode_and_select("circle", circle)

    # ── ステータスバー ────────────────────────────────────
    def _setup_statusbar(self):
        """ステータスバーとカード幅スライダーを設定する。"""
        sb = QStatusBar()
        sb.setSizeGripEnabled(True)
        sb.setStyleSheet(
            f"""
            QStatusBar {{
                background: {THEME_COLORS["bg_base"]};
                color: {THEME_COLORS["text_main"]};
                border-top: 1px solid {COLOR_BORDER};
                font-size: {config.FONT_SIZE_STATUS_BAR}px;
            }}
            QStatusBar QLabel,
            QStatusBar QSlider,
            QStatusBar QWidget {{
                background: transparent;
            }}
            QStatusBar::item {{
                border: none;
            }}
            """
        )
        self.setStatusBar(sb)
        self._statusbar = sb

        self._status_label = QLabel("0 冊")
        sb.addWidget(self._status_label)

        # スキャン進捗（初期は非表示）
        self._scan_progress_container = QWidget()
        _scan_progress_row = QHBoxLayout(self._scan_progress_container)
        _scan_progress_row.setContentsMargins(0, 0, 0, 0)
        _scan_progress_row.setSpacing(config.STATUSBAR_SCAN_PROGRESS_SPACING)
        self._scan_progress_label = QLabel("")
        self._scan_progress_label.setStyleSheet(
            f"font-size: {config.FONT_SIZE_STATUS_BAR}px;"
        )
        self._scan_progress_bar = QProgressBar()
        self._scan_progress_bar.setObjectName("StatusBarScanProgress")
        self._scan_progress_bar.setTextVisible(False)
        self._scan_progress_bar.setFixedSize(
            config.STATUSBAR_SCAN_PROGRESS_WIDTH,
            config.STATUSBAR_SCAN_PROGRESS_HEIGHT,
        )
        self._scan_progress_bar.setStyleSheet(
            get_statusbar_scan_progress_qss(config.STATUSBAR_SCAN_PROGRESS_BORDER_RADIUS)
        )
        _scan_progress_row.addWidget(self._scan_progress_label)
        _scan_progress_row.addWidget(self._scan_progress_bar)
        self._scan_progress_container.setVisible(False)
        sb.addWidget(self._scan_progress_container)

        self._size_slider = setup_statusbar(self, sb)
        self._size_slider.valueChanged.connect(self._on_card_size_changed)

        self._grid.ctrlWheelZoom.connect(self._on_ctrl_wheel_zoom)

    def _on_card_size_changed(self, value: int):
        """スライダー値に合わせてカード幅を更新する。"""
        self._grid.set_card_width(value)

    def _on_ctrl_wheel_zoom(self, delta: int):
        """Ctrl+ホイール: delta > 0 で拡大、< 0 で縮小"""
        step = config.CARD_SIZE_WHEEL_STEP
        new_val = self._size_slider.value() + (step if delta > 0 else -step)
        new_val = max(config.SLIDER_MIN_WIDTH, min(config.SLIDER_MAX_WIDTH, new_val))
        self._size_slider.setValue(new_val)  # valueChanged経由でgridも更新される


    def _toggle_searchbar(self):
        """検索バーの表示を切り替え設定に保存する。"""
        visible = not self._searchbar.isVisible()
        self._set_searchbar_visible(visible, save=True)

    def _safe_from_db_path(self, path: str) -> str:
        """DB保存パスを安全に絶対パスへ解決する。"""
        if not path:
            return ""
        try:
            return db._from_db_path(path)
        except Exception:
            return path

    def _set_scan_blocked(self, blocked: bool) -> None:
        """スキャン中のグリッド操作ブロックを切り替える。"""
        self._scan_blocking = blocked
        if hasattr(self, "_grid"):
            self._grid.setEnabled(not blocked)

    def _show_scan_progress_started(self) -> None:
        """スキャン開始時: 進捗バーを 0 にリセットして表示する。"""
        if not hasattr(self, "_scan_progress_container"):
            return
        self._scan_progress_label.setText(
            config.SCAN_PROGRESS_LABEL_TEMPLATE.format(scanned=0, total=0)
        )
        self._scan_progress_bar.setRange(0, 1)
        self._scan_progress_bar.setValue(0)
        self._scan_progress_container.setVisible(True)

    def _hide_scan_progress_ui(self) -> None:
        """スキャン終了・エラー時: 進捗バーとラベルを非表示にする。"""
        if not hasattr(self, "_scan_progress_container"):
            return
        self._scan_progress_container.setVisible(False)

    # ── ライブラリ読み込み ────────────────────────────────
    # ═══ ライブラリ管理 ═══
    def _load_library(self):
        """DBから一覧を表示しバックグラウンドでスキャンする。"""
        library_folder = (db.get_setting("library_folder") or "").strip()
        if not library_folder or not os.path.isdir(library_folder):
            # ライブラリ未設定: グリッドを隠し、中央ボタンのみ表示
            if hasattr(self, "_grid"):
                self._grid.hide()
            if hasattr(self, "_empty_hint"):
                self._empty_hint.show()
            return
        # ライブラリが設定済み: オーバーレイを隠し、グリッドを表示
        if hasattr(self, "_empty_hint"):
            self._empty_hint.hide()
        if hasattr(self, "_grid"):
            self._grid.show()
        # 起動時はDBキャッシュから即表示（ソート・フィルタなし）
        try:
            rows = db.get_all_books()
        except Exception:
            rows = []
        if rows:
            t_rows = time.perf_counter()
            _resolve_fast = self._resolve_cover_fast
            books = [
                {
                    "path": os.path.normpath(os.path.join(library_folder, row[3])) if library_folder else row[3],
                    "name":   row[0],
                    "title":  row[2] or row[0],
                    "circle": row[1] or "",
                    "cover":  _resolve_fast(row[3], row[4], library_folder) if row[4] else "",
                    "pages":  0,
                    "rating": 0,
                }
                for row in rows
                if row[3]
            ]
            self._all_books = books
            if hasattr(self, "_sidebar"):
                t_sort = time.perf_counter()
                self._apply_startup_sort_from_settings()
            else:
                self._sort_key = "title"
                self._sort_desc = False
            self._apply_filters()

        # 裏でスキャン
        self._start_scan(library_folder)

        # 起動時にもカード表示設定を反映
        self._grid.apply_display_settings()

    def _select_library_folder(self):
        """フォルダ選択後に設定保存とスキャンを行う。"""
        current = (db.get_setting("library_folder") or "").strip()
        dlg = LibraryFolderDialog(self, current_path=current)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        folder = dlg.selected_path
        if not folder:
            return
        db.set_setting("library_folder", folder)
        # 設定されたらオーバーレイを隠し、グリッドを表示してスキャン
        if hasattr(self, "_empty_hint"):
            self._empty_hint.hide()
        if hasattr(self, "_grid"):
            self._grid.show()
        is_changed = os.path.normcase(os.path.normpath(current)) != os.path.normcase(os.path.normpath(folder))
        self._start_scan(folder, block_ui=is_changed)

    def _on_click_setup_library(self):
        """中央ボタンからライブラリフォルダ設定を開く"""
        self._select_library_folder()

    def _rescan_library(self):
        """現在のライブラリフォルダを再スキャンする。"""
        folder = (db.get_setting("library_folder") or "").strip()
        if folder and os.path.isdir(folder):
            self._start_scan(folder)

    # ═══ スキャン ═══
    def _start_scan(self, folder: str, block_ui: bool = False):
        """指定フォルダでライブラリスキャンを非同期実行する。"""
        if block_ui:
            self._set_scan_blocked(True)
        if hasattr(self, "_scan_stale_flag"):
            self._scan_stale_flag.setVisible(False)
        self.setWindowTitle(f"{config.APP_TITLE} v{VERSION}")
        self._show_scan_progress_started()
        scan_library(
            folder,
            on_finished=self._on_scan_finished,
            on_progress=self._on_scan_progress,
            on_error=self._on_scan_error,
            on_store_files_pending=self._on_store_files_pending,
            on_uuid_duplicate_toast=self._on_uuid_duplicate_toast,
        )

    def _on_scan_finished(self, books: list):
        """スキャン完了時に一覧・件数・サイドバーを更新する。"""
        try:
            # スキャン結果の cover は DB の生値（ID/相対パス）なので表示用に解決する（サムネ設定が剥がれて見えない問題を防ぐ）
            for b in books:
                raw_path = b.get("path") or ""
                b["path"] = self._safe_from_db_path(raw_path)
            # cover は生のDB値のまま渡す（model.py 側で解決する）

            # 直前の一覧とスキャン結果を比較し、差分がなければグリッドの再読み込みを行わない
            old_books = self._all_books or []

            def _books_changed(a: list[dict], b: list[dict]) -> bool:
                """新旧ブック一覧に差分があるか判定する。"""
                if len(a) != len(b):
                    return True
                for x, y in zip(a, b):
                    if (
                        x.get("path") != y.get("path")
                        or x.get("name") != y.get("name")
                        or x.get("title") != y.get("title")
                        or x.get("circle") != y.get("circle")
                        or x.get("cover") != y.get("cover")
                    ):
                        return True
                return False

            changed = _books_changed(old_books, books)

            self._all_books = books

            # 検索用ハヤスタックキャッシュを更新
            t0 = time.perf_counter()
            build_haystack_cache(books)
            logging.info("[FINISHED] haystack=%.3fs", time.perf_counter() - t0)

            # 差分なしならグリッドはそのまま維持して一瞬消える問題を回避
            if changed:
                t1 = time.perf_counter()
                self._apply_filters()
                logging.info("[FINISHED] apply_filters=%.3fs", time.perf_counter() - t1)
            else:
                logging.info("[FINISHED] apply_filters=skipped changed=%s", changed)

            self._sidebar.refresh()
            folder = (db.get_setting("library_folder") or "").strip()
            self.setWindowTitle(f"{config.APP_TITLE} v{VERSION}")
            self._status_label.setText(f"{len(books)} 冊")
            self._set_scan_blocked(False)
            if hasattr(self, "_scan_stale_flag"):
                self._scan_stale_flag.setVisible(False)
        finally:
            # 起動時スキャンは1回完了したら終了（以降のスキャンではストアダイアログを通常表示）
            self._is_startup_scan = False
            self._hide_scan_progress_ui()

    def _on_store_files_pending(self, pending_list: list):
        """ストアファイル追加時に入力ダイアログで登録。起動後最初のスキャン中はダイアログを出さずファイル名から登録する。"""
        if self._is_startup_scan:
            for item in pending_list:
                path = item["path"]
                name = item["name"]
                mtime = item["mtime"]
                sc = (item.get("suggested_circle") or "").strip()
                st = (item.get("suggested_title") or name).strip()
                display_name = db.format_book_name(sc, st) or name
                ext = os.path.splitext(name)[1].lower()
                is_dlst = 1 if ext == config.STORE_FILE_EXT_DLSITE else 0
                db.upsert_store_file_book(
                    path, display_name, sc, st, "", mtime, is_dlst, None
                )
            return
        for item in pending_list:
            path = item["path"]
            name = item["name"]
            mtime = item["mtime"]
            suggested_circle = item.get("suggested_circle", "")
            suggested_title = item.get("suggested_title", name)
            dlg = StoreFileInputDialog(
                path, name, mtime, suggested_circle, suggested_title, self
            )
            if dlg.exec() != QDialog.Accepted or not dlg.result:
                continue
            book_tuple, meta = dlg.result
            disp_name, circle, title, abs_path, _cover_empty, mtime, _tuple_is_dlst = book_tuple
            ext = os.path.splitext(name)[1].lower()
            is_dlst = 1 if ext == config.STORE_FILE_EXT_DLSITE else 0
            cover_arg = ""
            if meta and meta.get("cover_path"):
                cover_arg = meta["cover_path"]
            db.upsert_store_file_book(
                abs_path,
                disp_name,
                circle,
                title,
                cover_arg,
                mtime,
                is_dlst,
                None,
            )
            if meta:
                meta_src = db._effective_meta_source("", (meta.get("dlsite_id") or "").strip())
                db.set_book_meta(
                    path,
                    author=meta.get("author", ""),
                    series=meta.get("series", ""),
                    characters=meta.get("characters"),
                    tags=meta.get("tags"),
                    pages=meta.get("pages"),
                    release_date=meta.get("release_date") or None,
                    price=meta.get("price"),
                    memo=meta.get("memo") or None,
                    dlsite_id=meta.get("dlsite_id") or None,
                    meta_source=meta_src,
                )

    def _refresh_books_from_db(self):
        """DBから一覧を再取得してグリッド・サイドバー・タイトルを更新する。"""
        try:
            self._meta_cache = db.get_all_book_metas()
            self._norm_meta_cache = {}
        except Exception:
            self._meta_cache = {}
            self._norm_meta_cache = {}
        try:
            rows = db.get_all_books()
        except Exception:
            rows = []
        lib_root = (db.get_setting("library_folder") or "").strip()
        books = []
        for row in rows:
            if not row[3]:
                continue
            resolved = _resolve_cover(row[3], row[4], lib_root) if row[4] else ""
            books.append(
                {
                    "path": self._safe_from_db_path(row[3] or ""),
                    "name": row[0],
                    "title": row[2] or row[0],
                    "circle": row[1] or "",
                    "cover": resolved,
                    "pages": 0,
                    "rating": 0,
                    "is_dlst": int(row[5]) if len(row) > 5 else 0,
                }
            )
        self._all_books = books
        build_haystack_cache(books)
        self._apply_filters()
        self._sidebar.refresh()
        folder = (db.get_setting("library_folder") or "").strip()
        self.setWindowTitle(f"{config.APP_TITLE} v{VERSION}")
        self._status_label.setText(f"{len(books)} 冊")

    # ── 単一ブック更新（プロパティ保存などから呼ばれる） ────────────

    def _property_save_perf_start(self) -> None:
        """PropertyDialog の保存処理開始時のみ呼ぶ（計測起点）。"""
        self._property_save_perf_t0 = time.perf_counter()

    def _property_save_perf_cancel(self) -> None:
        """保存中断・失敗時に計測だけ打ち切る（ログなし）。"""
        self._property_save_perf_t0 = None

    def _property_save_perf_log(self, phase: str) -> None:
        """中間フェーズの経過時間をログ（未計測時は何もしない）。"""
        t0 = getattr(self, "_property_save_perf_t0", None)
        if t0 is None:
            return
        dt = time.perf_counter() - t0
        print(f"{config.PROPERTY_SAVE_PERF_LOG_PREFIX} {phase} +{dt:.3f}s")

    def _property_save_perf_finish(self, phase: str = "stable") -> None:
        """計測終了（ログ＋起点クリア）。"""
        self._property_save_perf_log(phase)
        self._property_save_perf_t0 = None

    def on_book_updated(self, path: str | None = None):
        """
        プロパティ保存やお気に入り変更後に呼ばれるフック。
        既存の _all_books / グリッドモデルから対象 book を取り出し、
        DB状態で上書きして最小限の再描画のみ行う。

        ※ 現状はシンプルに全フィルタ適用＋グリッド再描画だが、
          将来的に最小限の dataChanged だけに最適化するためのフックポイント。
        """
        # coverが変わっていたらサムネキャッシュを破棄
        if path:
            old_cover = next(
                (b.get("cover", "") for b in self._all_books if b.get("path") == path),
                "",
            )
            if old_cover:
                model = self._grid.model() if hasattr(self, "_grid") else None
                if model and hasattr(model, "invalidate_thumb"):
                    model.invalidate_thumb(old_cover)
        # コンテキストメニュー展開時に保存したスクロール位置を復元用に取得（未設定時は復元しない）
        # クリアは復元実行後に行うので、on_book_updated が複数回呼ばれても最後の更新後に復元できる
        saved = getattr(self, "_context_menu_scroll", None)
        if saved is not None:
            v_scroll, h_scroll = saved
        else:
            v_scroll = h_scroll = None  # 復元しない

        # メタデータキャッシュ: 更新後は全件を一括再取得して最新状態にする
        try:
            self._meta_cache = db.get_all_book_metas()
            self._norm_meta_cache = {}
        except Exception:
            self._meta_cache = {}
            self._norm_meta_cache = {}

        # DBから最新のbooks一覧を取得して _all_books を更新
        try:
            rows = db.get_all_books()
        except Exception:
            rows = []
        lib_root = (db.get_setting("library_folder") or "").strip()
        books = [
            {
                "path": (
                    _p := os.path.normpath(os.path.join(lib_root, (row[3] or "").strip()))
                    if lib_root else (row[3] or "").strip()
                ),
                "name":   row[0],
                "title":  row[2] or row[0],
                "circle": row[1] or "",
                "cover":  _resolve_cover(_p, row[4] or "", lib_root),
                "pages":  0,
                "rating": 0,
                "is_dlst": int(row[5]) if len(row) > 5 else 0,
            }
            for row in rows
            if row[3]
        ]
        self._all_books = books

        # 検索用ハヤスタックキャッシュも再構築
        build_haystack_cache(books)

        # スクロール復元する場合は「一瞬トップに戻る」フレームを見せないよう描画を止める
        g = getattr(self, "_grid", None) if (v_scroll is not None and h_scroll is not None) else None
        if g is not None:
            g.setUpdatesEnabled(False)

        # とりあえず現状ロジックでは全体フィルタ＋ソートを再実行
        # （全件スキャンは行わない）
        self._apply_filters()

        if (
            hasattr(self, "_filter_panel")
            and self._filter_panel is not None
            and self._filter_panel.isVisible()
        ):
            self._filter_panel.repopulate_all_combos()

        if getattr(self, "_property_save_perf_t0", None) is not None:
            self._property_save_perf_log("after_filters")
            if v_scroll is None or h_scroll is None:
                QTimer.singleShot(0, lambda: self._property_save_perf_finish("stable"))

        # コンテキストメニュー展開時に保存したスクロール位置があれば、レイアウト確定後に復元
        # rangeChanged で「max が十分になった瞬間」に復元（最速）。フォールバックで遅延復元も行う
        if v_scroll is not None and h_scroll is not None:
            if g is None:
                g = getattr(self, "_grid", None)
            vb = g.verticalScrollBar() if g else None
            if not g or not vb:
                if g:
                    g.setUpdatesEnabled(True)
                self._context_menu_scroll = None
                self._property_save_perf_finish("stable")
            else:
                hb = g.horizontalScrollBar()
                done = [False]

                def do_apply():
                    """保存位置へスクロールを戻し描画更新を再開する。"""
                    if done[0]:
                        g.setUpdatesEnabled(True)
                        return
                    done[0] = True
                    v_max = vb.maximum()
                    v_apply = min(v_scroll, v_max)
                    vb.setValue(v_apply)
                    if hb:
                        h_max = hb.maximum()
                        h_apply = min(h_scroll, h_max)
                        hb.setValue(h_apply)
                    g.setUpdatesEnabled(True)
                    self._property_save_perf_finish("stable")
                    # 2回目以降の on_book_updated で _apply_filters が再度走るとグリッドがリセットされるため、
                    # 即クリアせず遅延クリアする（複数回の更新後も最後の復元が効くようにする）
                    QTimer.singleShot(
                        config.CONTEXT_MENU_SCROLL_RESET_DELAY_MS,
                        lambda: setattr(self, "_context_menu_scroll", None),
                    )

                def on_range_changed(_min, max_val):
                    """範囲が十分なら復元してシグナルを外す。"""
                    if max_val >= v_scroll:
                        try:
                            vb.rangeChanged.disconnect(on_range_changed)
                        except Exception:
                            pass
                        do_apply()

                vb.rangeChanged.connect(on_range_changed)
                # 既に max が十分なら即復元（rangeChanged がもう発火しない場合用）
                if vb.maximum() >= v_scroll:
                    try:
                        vb.rangeChanged.disconnect(on_range_changed)
                    except Exception:
                        pass
                    do_apply()
                else:
                    # フォールバック: 一定時間で rangeChanged が来ない場合に復元
                    def fallback():
                        """range未発火時に遅延でスクロール復元を試みる。"""
                        if done[0]:
                            return
                        try:
                            vb.rangeChanged.disconnect(on_range_changed)
                        except Exception:
                            pass
                        do_apply()
                    QTimer.singleShot(config.CONTEXT_MENU_SCROLL_FALLBACK_DELAY_MS, fallback)

    def _on_scan_progress(self, scanned: int, total: int):
        """進捗中はウィンドウタイトルを既定の短い表記に戻す。"""
        self.setWindowTitle(config.APP_TITLE)
        if not hasattr(self, "_scan_progress_container"):
            return
        self._scan_progress_container.setVisible(True)
        t = max(0, int(total))
        s = max(0, int(scanned))
        if t <= 0:
            self._scan_progress_bar.setRange(0, 1)
            self._scan_progress_bar.setValue(0)
        else:
            self._scan_progress_bar.setRange(0, t)
            self._scan_progress_bar.setValue(min(s, t))
        self._scan_progress_label.setText(
            config.SCAN_PROGRESS_LABEL_TEMPLATE.format(scanned=s, total=t)
        )

    def _on_uuid_duplicate_toast(self, message: str) -> None:
        """UUID重複解消メッセージをステータスバーに表示する。"""
        if hasattr(self, "_statusbar"):
            self._statusbar.showMessage(message, config.SCAN_TOAST_DURATION_MS)

    def _on_scan_error(self, msg: str):
        """エラー時もウィンドウタイトルを既定の短い表記に戻す。"""
        print(f"[SCAN_ERROR] msg={msg!r}")
        self._is_startup_scan = False
        self._hide_scan_progress_ui()
        self.setWindowTitle(config.APP_TITLE)
        self._set_scan_blocked(False)
        if hasattr(self, "_scan_stale_flag"):
            self._scan_stale_flag.setVisible(True)
        if hasattr(self, "_statusbar"):
            self._statusbar.showMessage(msg or config.SCAN_STALE_FLAG_TEXT, config.SCAN_TOAST_DURATION_MS)

    # ── フィルタリング（サイドバー + 検索の合成） ─────────
    # ═══ フィルター・ソート ═══
    def _apply_filters(self):
        """各種フィルタとソートを合成しグリッドへ反映する。"""
        t0 = time.perf_counter()
        lib_root = (db.get_setting("library_folder") or "").strip()
        # 元の全件リスト
        all_books = self._all_books
        # サイドバー（作品名一覧）用に、フィルタ前の並び順を準備
        sidebar_books = self._sort_books(all_books) if all_books else []

        books = all_books

        # サイドバーフィルタ
        if self._sidebar_filter:
            mode, value = self._sidebar_filter
            if mode in ("author", "series", "character", "tag"):
                if (
                    not hasattr(self, "_norm_meta_cache")
                    or len(self._norm_meta_cache) != len(self._meta_cache)
                ):
                    self._norm_meta_cache = {
                        normalize_path(
                            k if os.path.isabs(k or "") else os.path.join(lib_root, k or "")
                        ): v
                        for k, v in self._meta_cache.items()
                    }
            books = self._apply_sidebar_filter(books, mode, value)

        # ストアファイルフィルタ（DLSiteのみ / FANZAのみ、重複可）
        books = self._apply_store_filter(books)

        # サムネイル未設定フィルタ（表示メニュー）
        books = self._apply_no_cover_filter(books)

        # 検索フィルタ
        query = self._searchbar._input.text()
        if query.strip():
            books = filter_books(books, query)

        # フィルターパネルで設定した条件
        if self._active_filters:
            books = self._apply_active_filters(books)

        # ソートを適用
        books = self._sort_books(books)

        # フィルター適用時は件数を保持（ソートバーラベルで「全 N 件」表示用）
        if self._active_filters:
            self._filtered_count = len(books)
        elif hasattr(self, "_filtered_count"):
            delattr(self, "_filtered_count")

        # グリッドへの反映（表示中リストを保持）
        self._books = books
        self._grid.load_books(books)
        # サイドバー: フィルター指定時はプルダウンを隠し「フィルター」＋結果一覧に切替
        if hasattr(self, "_sidebar"):
            if self._active_filters:
                self._sidebar.set_filter_result_mode(True, books)
            else:
                self._sidebar.set_filter_result_mode(False, None)
                self._sidebar.set_title_items(sidebar_books)

    def _on_random_requested(self) -> None:
        """ツールバーランダム：表示中グリッドから1冊をビューアで開く。"""
        candidates = [b for b in (self._books or []) if b.get("path")]
        if not candidates:
            return
        from context_menu import open_book

        open_book(random.choice(candidates)["path"], self, modal=False)
        if hasattr(self, "_sidebar") and self._sidebar and self._sidebar._mode == "history":
            self._sidebar.refresh()

    # ── ソート関連 ───────────────────────────────────────

    def _persist_sort_state_for_next_launch(self) -> None:
        """次回起動「前回のソート状態を復元」用に DB に保持（キー名は config のみ参照）。"""
        try:
            db.set_setting(
                config.SORT_LAST_KEY_SETTING_KEY,
                self._sort_key or config.STARTUP_SORT_DEFAULT_KEY_FALLBACK,
            )
            db.set_setting(
                config.SORT_LAST_DESC_SETTING_KEY,
                "1" if self._sort_desc else "0",
            )
        except Exception:
            pass

    def _apply_startup_sort_from_settings(self) -> None:
        """起動時ソート（設定ダイアログで保存した DB 値）。サイドバーモード表示を同期する。"""
        restore = (
            db.get_setting(config.STARTUP_SORT_RESTORE_LAST_SETTING_KEY, "1") == "1"
        )
        fb = config.STARTUP_SORT_DEFAULT_KEY_FALLBACK
        if restore:
            raw_key = (db.get_setting(config.SORT_LAST_KEY_SETTING_KEY) or "").strip()
            key = raw_key if raw_key else fb
            desc = db.get_setting(config.SORT_LAST_DESC_SETTING_KEY) == "1"
        else:
            raw_key = (
                db.get_setting(config.STARTUP_SORT_DEFAULT_KEY_SETTING_KEY) or ""
            ).strip()
            key = raw_key if raw_key else fb
            desc = key in config.SORT_KEYS_DEFAULT_DESC

        sb = self._sidebar
        valid = {sb._combo.itemData(i) for i in range(sb._combo.count())}
        if key not in valid:
            key = fb
            if key not in valid:
                key = sb._combo.itemData(0)
        self._sort_key = key
        self._sort_desc = desc
        sb._combo.blockSignals(True)
        for i in range(sb._combo.count()):
            if sb._combo.itemData(i) == key:
                sb._combo.setCurrentIndex(i)
                sb._mode = key
                break
        sb._combo.blockSignals(False)
        sb.refresh()
        self._update_sort_bar()

    def _update_sort_bar(self):
        """ソートバーのラベルと昇降順ボタンの表示を更新"""
        # フィルター適用中はラベルを「全 N 件」に（サイドバー選択状態にしない）
        if getattr(self, "_active_filters", None):
            count = getattr(self, "_filtered_count", 0)
            label = f"全 {count} 件"
        else:
            label_map = {
                "title": "作品名",
                "circle": "サークル",
                "author": "作者",
                "series": "シリーズ",
                "character": "キャラクター",
                "tag": "タグ",
                "metadata": "メタデータ",
                "favorite": "お気に入り",
                "added_date": "最終更新順",
                "history": "履歴",
            }
            key = self._sort_key or "title"
            label = label_map.get(key, "作品名")
        if hasattr(self, "_sort_label"):
            self._sort_label.setText(label)

        # 昇降順トグルボタンのラベル更新
        if hasattr(self, "_sort_order_btn"):
            arrow = "▼" if self._sort_desc else "▲"
            text = "降順 " if self._sort_desc else "昇順 "
            self._sort_order_btn.setText(f"{text}{arrow}")

    def _on_sort_order_toggled(self):
        """昇順↔降順トグルボタン"""
        self._sort_desc = not self._sort_desc
        self._update_sort_bar()
        self._apply_filters()
        # 昇降順トグル時もサイドバーの表示順を最新状態に反映
        self._sidebar.refresh()
        self._persist_sort_state_for_next_launch()

    def _on_filter_toggled(self, visible: bool) -> None:
        """ツールバーフィルター：パネル表示とスプリッター幅を同期する。"""
        if self._filter_panel is None or not hasattr(self, "_splitter"):
            return
        # showEvent 内の _emit_apply より先に論理・条件を同期する（順序逆だと AND に戻る等の不整合）
        if visible:
            self._filter_panel.sync_from_parent(
                self._active_filters, self._filter_logic
            )
        self._filter_panel.setVisible(visible)
        sizes = list(self._splitter.sizes())
        if len(sizes) < 3:
            return
        if visible:
            sizes[1] = max(0, sizes[1] - config.FILTER_POPOVER_WIDTH)
            sizes[2] = config.FILTER_POPOVER_WIDTH
        else:
            sizes[1] = sizes[1] + sizes[2]
            sizes[2] = 0
        self._splitter.setSizes(sizes)

    def _on_filter_popover_apply(self, conditions: list[dict], logic: str):
        """フィルターパネルから条件が変わったたびに即時反映（結合は logic に従う）。"""
        cleaned = []
        for c in conditions:
            field = (c.get("field") or "").strip()
            value = (c.get("value") or "").strip()
            if not field or not value:
                continue
            cleaned.append({"field": field, "value": value})
        self._active_filters = cleaned
        logic_norm = (logic or "and").strip().lower()
        self._filter_logic = logic_norm if logic_norm in ("and", "or") else "and"
        self._apply_filters()
        self._update_sort_bar()

    def _on_filter_popover_clear_only(self):
        """フィルター条件と論理のみクリア（パネルは開いたまま）。"""
        self._active_filters = []
        self._filter_logic = "and"
        self._update_sort_bar()
        self._apply_filters()

    def _on_filter_popover_clear(self):
        """パネル [×]：条件クリア＆パネルを閉じる"""
        self._active_filters = []
        self._filter_logic = "and"
        self._update_sort_bar()
        self._apply_filters()
        self._on_filter_toggled(False)
        _bf = getattr(self._main_toolbar, "_btn_filter", None)
        if _bf is not None:
            _bf.blockSignals(True)
            _bf.setChecked(False)
            _bf.blockSignals(False)

    def _apply_active_filters(self, books: list[dict]) -> list[dict]:
        """フィルターパネルで設定した条件を適用。
        - AND: 全条件（field+value）をフラットに列挙し、すべて一致が必要。
        - OR: 各条件（field, value）のいずれかが一致すれば採用。
        """
        if not self._active_filters:
            return books

        # メタキャッシュを準備
        if not self._meta_cache:
            try:
                self._meta_cache = db.get_all_book_metas()
                self._norm_meta_cache = {}
            except Exception:
                self._meta_cache = {}
                self._norm_meta_cache = {}
        if (
            not hasattr(self, "_norm_meta_cache")
            or len(self._norm_meta_cache) != len(self._meta_cache)
        ):
            lib_root = (db.get_setting("library_folder") or "").strip()
            self._norm_meta_cache = {
                normalize_path(
                    k if os.path.isabs(k or "") else os.path.join(lib_root, k or "")
                ): v
                for k, v in self._meta_cache.items()
            }

        def match_condition(book: dict, field: str, value: str) -> bool:
            """1条件がブックのメタと一致するか判定する。"""
            path = book.get("path", "") or ""
            meta = self._norm_meta_cache.get(normalize_path(path)) if path else {}
            if meta is None:
                return False

            if field == "author":
                author_val = meta.get("author")
                if isinstance(author_val, str):
                    return value in author_val
                if isinstance(author_val, (list, tuple)):
                    return value in author_val
                return False
            if field == "circle":
                circle_val = book.get("circle") or meta.get("circle") or ""
                return value in circle_val
            if field == "series":
                series_val = meta.get("series") or ""
                return value in series_val
            if field == "character":
                chars = meta.get("characters") or []
                if isinstance(chars, str):
                    chars = [chars]
                return value in chars
            if field == "tag":
                tags = meta.get("tags") or []
                if isinstance(tags, str):
                    tags = [tags]
                return value in tags
            return True

        logic_raw = getattr(self, "_filter_logic", "and") or "and"
        logic = logic_raw.strip().lower()
        if logic not in ("and", "or"):
            logic = "and"
        if logic == "or":
            filtered_or: list[dict] = []
            for b in books:
                matched = False
                for c in self._active_filters:
                    field = (c.get("field") or "").strip()
                    value = (c.get("value") or "").strip()
                    if field and value and match_condition(b, field, value):
                        matched = True
                        break
                if matched:
                    filtered_or.append(b)
            return filtered_or

        # AND: 全条件（field+value）がすべて一致
        filtered: list[dict] = []
        for b in books:
            if all(
                match_condition(
                    b,
                    (c.get("field") or "").strip(),
                    (c.get("value") or "").strip(),
                )
                for c in self._active_filters
                if (c.get("field") or "").strip() and (c.get("value") or "").strip()
            ):
                filtered.append(b)
        return filtered

    def _on_sort_mode_changed(self, mode: str):
        """サイドバーでモードが選ばれたとき"""
        self._sort_key = mode or "title"
        self._sort_desc = self._sort_key in config.SORT_KEYS_DEFAULT_DESC
        if mode == "history":
            # 履歴に存在する path セットでグリッドを絞り込む
            rows = db.get_recent_books(limit=config.SIDEBAR_HISTORY_RECENT_LIMIT)
            history_paths = {r[1] for r in rows}
            self._sidebar_filter = ("history_all", history_paths)
        else:
            self._sidebar_filter = None  # モード切替時はフィルターをクリアし作品名昇順で表示
        self._update_sort_bar()
        self._apply_filters()
        self._sidebar.refresh()
        self._persist_sort_state_for_next_launch()

    def _sort_books(self, books: list[dict]) -> list[dict]:
        """現在のソートキー/順序に基づいて books を並べ替える"""
        t0 = time.perf_counter()
        if not books:
            return []

        # メタキャッシュが空なら先に一括ロード（1件ずつDBアクセスを防ぐ）
        if not self._meta_cache:
            try:
                t_meta = time.perf_counter()
                self._meta_cache = db.get_all_book_metas()
                self._norm_meta_cache = {}
            except Exception:
                pass

        key = self._sort_key
        desc = self._sort_desc

        # メタデータはアプリ全体でキャッシュして、繰り返しDBアクセスを抑える
        def get_meta(path: str) -> dict:
            """キャッシュからパス別メタ辞書を返す。"""
            return self._meta_cache.get(path, {})

        # 追加順: mtime を取得
        mtime_map: dict[str, float] = {}
        if key == "added_date":
            try:
                t_added = time.perf_counter()
                raw_map = db.get_books_updated_at_map()
                lib_root = (db.get_setting("library_folder") or "").strip()
                mtime_map = {
                    normalize_path(
                        k if os.path.isabs(k or "") else os.path.join(lib_root, k or "")
                    ): v
                    for k, v in raw_map.items()
                }
            except Exception:
                mtime_map = {}

        # 履歴: recent_books の順序をマップに
        history_order: dict[str, int] = {}
        if key == "history":
            try:
                recent = db.get_recent_books(limit=config.RECENT_BOOKS_LIST_LIMIT)
                # get_recent_books は [(name, path), ...] の想定
                for idx, (name, path) in enumerate(recent):
                    history_order[path] = idx
            except Exception:
                history_order = {}

        def sort_key(b: dict):
            """現在のソートキーに応じた比較用キーを返す。"""
            path = b.get("path", "")
            meta = get_meta(path) if path else {}

            if key == "title":
                # 作品名ソートキー（フリガナ優先）を book dict 内にキャッシュ
                cache_key = "_sort_title_key"
                if cache_key in b:
                    primary = b[cache_key]
                else:
                    title_kana = meta.get("title_kana") or ""
                    if title_kana:
                        primary = title_kana
                    else:
                        primary = (b.get("title") or b.get("name") or "") + " " + (b.get("circle") or "")
                    b[cache_key] = primary
                return primary.lower()

            if key == "circle":
                # サークル名ソートキー（フリガナ優先）を book dict 内にキャッシュ
                cache_key = "_sort_circle_key"
                if cache_key in b:
                    primary = b[cache_key]
                else:
                    circle_kana = meta.get("circle_kana") or ""
                    if circle_kana:
                        primary = circle_kana
                    else:
                        primary = (b.get("circle") or "") or (b.get("title") or b.get("name") or "")
                    b[cache_key] = primary
                return primary.lower()

            if key == "author":
                return (meta.get("author") or "").lower()

            if key == "series":
                return (meta.get("series") or "").lower()

            if key == "character":
                chars = meta.get("characters") or []
                return " ".join(chars).lower()

            if key == "tag":
                tags = meta.get("tags") or []
                return " ".join(tags).lower()

            if key == "added_date":
                # mtime が大きいほど新しい
                return mtime_map.get(normalize_path(path or ""), 0.0)

            if key == "history":
                # recent_books にないものは末尾
                return history_order.get(path, len(history_order))

            if key in ("metadata", "favorite"):
                return (b.get("title") or b.get("name") or "").lower()

            # 不明なキー → 作品名でフォールバック
            return (b.get("title") or b.get("name") or "").lower()

        try:
            result = sorted(books, key=sort_key, reverse=desc)
        except Exception:
            result = books

        return result

    # ── キャッシュの削除 ────────────────────────────────────

    def _clear_caches(self):
        """サムネイル・カバーキャッシュを全削除し、表示を更新する"""
        if QMessageBox.question(
            self,
            "キャッシュの削除",
            "グリッド用サムネキャッシュ（表示用PNG）を削除します。\n"
            "PDF・dmme・dlst 等のサムネ元画像は残します。\nよろしいですか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        removed, err = db.clear_all_caches()
        if err:
            QMessageBox.critical(self, "キャッシュの削除", f"削除中にエラーが発生しました:\n{err}")
            return
        model = self._grid.model() if hasattr(self, "_grid") else None
        if model and hasattr(model, "invalidate_thumbs"):
            model.invalidate_thumbs()
        repaired = db.repair_folder_covers()
        repaired_pdf = 0
        try:
            rows = db.get_all_books()
            library_folder = os.path.normcase(
                os.path.normpath((db.get_setting("library_folder") or "").strip())
            )
            for row in rows:
                path = row[3] or ""
                cover = row[4] or ""
                ext = os.path.splitext(path)[1].lower() if path else ""
                if ext == ".pdf":
                    if library_folder and os.path.normcase(
                        os.path.normpath(os.path.dirname(path))
                    ) != library_folder:
                        continue
                    if not cover or not os.path.isfile(cover):
                        new_cover, pages = _get_pdf_cover_and_pages(path)
                        if new_cover and db.update_book_cover_path(path, new_cover):
                            repaired_pdf += 1
                    continue
        except Exception:
            pass
        msg = (
            f"グリッド用サムネキャッシュを {removed} 件削除しました。\n"
            f"（PDF・dmme・dlst・アーカイブ等のサムネ元画像は保持しています）\n"
            f"フォルダ型: {repaired} 件、PDF: {repaired_pdf} 件を再設定しました。"
        )
        QMessageBox.information(self, "キャッシュの削除", msg)
        self._apply_filters()

    # ═══ DB・メンテナンス ═══
    def _repair_pdf_covers(self):
        """PDFの1枚目をカバーとして未設定・壊れているものを cover_cache に生成して DB を更新する"""
        try:
            rows = db.get_all_books()
        except Exception as e:
            QMessageBox.critical(self, "PDFサムネ修復", f"一覧の取得に失敗しました:\n{e}")
            return
        library_folder = os.path.normcase(
            os.path.normpath((db.get_setting("library_folder") or "").strip())
        )
        pdf_rows = [
            (r[3], r[4]) for r in rows
            if r[3]
            and os.path.splitext(r[3])[1].lower() == ".pdf"
            and (
                not library_folder
                or os.path.normcase(os.path.normpath(os.path.dirname(r[3]))) == library_folder
            )
        ]
        need_repair = [(path, cover) for path, cover in pdf_rows if not cover or not os.path.isfile(cover)]
        if not need_repair:
            QMessageBox.information(self, "PDFサムネ修復", "修復が必要なPDFはありません。")
            return
        progress = QProgressDialog("PDFの1枚目をサムネに設定しています...", None, 0, len(need_repair), self)
        progress.setWindowTitle(config.APP_TITLE)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(config.PROGRESS_DIALOG_MIN_DURATION_MS)
        progress.setValue(0)
        repaired = 0
        for i, (path, _) in enumerate(need_repair):
            if progress.wasCanceled():
                break
            progress.setValue(i + 1)
            progress.setLabelText(os.path.basename(path) or path)
            QApplication.processEvents()
            if not os.path.isfile(path):
                continue
            new_cover, _ = _get_pdf_cover_and_pages(path)
            if new_cover and db.update_book_cover_path(path, new_cover):
                repaired += 1
        progress.close()
        QMessageBox.information(
            self,
            "PDFサムネ修復",
            f"{repaired} 件のPDFで1枚目をサムネに設定しました。",
        )
        self._apply_filters()

    # ── ふりがな一括取得 ──────────────────────────────────

    def _bulk_update_kana(self):
        """全書籍の title_kana / circle_kana を一括で自動生成・更新"""
        try:
            rows = db.get_all_books()  # [(name, circle, title, path, cover, is_dlst), ...]
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"書籍一覧の取得に失敗しました: {e}")
            return

        total = len(rows)
        if total == 0:
            QMessageBox.information(self, "情報", "対象となる書籍がありません。")
            return

        # get_all_books にはふりがなが含まれないため、全件パスでメタを見て既存ふりがなの有無だけ判定する
        has_existing_kana = False
        for row in rows:
            _path = row[3]
            try:
                _meta = db.get_book_meta(_path) or {}
            except Exception:
                continue
            _tk = (_meta.get("title_kana") or "").strip()
            _ck = (_meta.get("circle_kana") or "").strip()
            if _tk or _ck:
                has_existing_kana = True
                break

        if has_existing_kana:
            reply = QMessageBox.question(
                self,
                "ふりがなの上書き確認",
                "既存のふりがなをすべて上書きします。手動で入力したふりがなも消えます。続けますか？",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return

        progress = QProgressDialog("ふりがな一括取得中...", None, 0, total, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(config.PROGRESS_DIALOG_MIN_DURATION_MS)
        progress.setValue(0)

        updated = 0

        for i, row in enumerate(rows, start=1):
            if progress.wasCanceled():
                break
            progress.setValue(i)

            name, circle, title, path, cover, is_dlst = row
            title_src = title or name or ""
            circle_src = circle or ""

            try:
                meta = db.get_book_meta(path) or {}
            except Exception:
                meta = {}

            cur_tk = meta.get("title_kana", "") or ""
            cur_ck = meta.get("circle_kana", "") or ""

            need_title = bool(title_src)
            need_circle = bool(circle_src)

            if not (need_title or need_circle):
                continue

            new_tk = _auto_kana(title_src) if need_title else cur_tk
            new_ck = _auto_kana(circle_src) if need_circle else cur_ck

            try:
                db.set_book_meta(
                    path,
                    author=meta.get("author", ""),
                    type_=meta.get("type", ""),
                    series=meta.get("series", ""),
                    characters=meta.get("characters") or [],
                    tags=meta.get("tags") or [],
                    dlsite_id=meta.get("dlsite_id"),
                    title_kana=new_tk,
                    circle_kana=new_ck,
                    pages=meta.get("pages"),
                    release_date=meta.get("release_date"),
                    price=meta.get("price"),
                    memo=meta.get("memo"),
                )
                updated += 1
            except Exception:
                continue

        progress.close()
        QMessageBox.information(self, "完了", f"{updated}件のふりがなを更新しました。")

    def _apply_store_filter(self, books: list[dict]) -> list[dict]:
        """DLSiteのファイルのみ / FANZA(DMM)のファイルのみ。両方ONのときは両方表示（重複可）。"""
        if not self._filter_dlsite_only and not self._filter_fanza_only:
            return books
        result = []
        for b in books:
            path = (b.get("path") or "").strip()
            ext = os.path.splitext(path)[1].lower()
            is_dlst = ext == config.STORE_FILE_EXT_DLSITE or (b.get("is_dlst") or 0)
            is_dmm = ext in config.STORE_FILE_EXTS_DMM
            if self._filter_dlsite_only and self._filter_fanza_only:
                if is_dlst or is_dmm:
                    result.append(b)
            elif self._filter_dlsite_only and is_dlst:
                result.append(b)
            elif self._filter_fanza_only and is_dmm:
                result.append(b)
        return result

    def _set_filter_dlsite_only(self, checked: bool):
        """DLSiteのみ表示フラグを更新し一覧を再適用する。"""
        self._filter_dlsite_only = checked
        if hasattr(self, "_act_filter_dlsite"):
            self._act_filter_dlsite.setChecked(checked)
        self._apply_filters()

    def _set_filter_fanza_only(self, checked: bool):
        """FANZAのみ表示フラグを更新し一覧を再適用する。"""
        self._filter_fanza_only = checked
        if hasattr(self, "_act_filter_fanza"):
            self._act_filter_fanza.setChecked(checked)
        self._apply_filters()

    def _apply_no_cover_filter(self, books: list[dict]) -> list[dict]:
        """サムネイル未設定のカードのみに絞る（表示メニュー「サムネイル未設定」ON時）"""
        if not getattr(self, "_filter_no_cover_only", False):
            return books
        result = []
        for b in books:
            cover = (b.get("cover") or "").strip()
            if not cover or not os.path.exists(cover):
                result.append(b)
        return result

    def _set_filter_no_cover_only(self, checked: bool):
        """サムネ未設定のみ表示フラグを更新し再適用する。"""
        self._filter_no_cover_only = checked
        if hasattr(self, "_act_filter_no_cover"):
            self._act_filter_no_cover.setChecked(checked)
        self._apply_filters()

    def _apply_sidebar_filter(
        self, books: list, mode: str, value: str | set[str]
    ) -> list:
        """サイドバー選択に応じてブック一覧を絞り込む。"""
        lib_root = os.path.normpath((db.get_setting("library_folder") or "").strip())
        if mode == "circle":
            if value == "__unknown__":
                return [b for b in books if not (b.get("circle") or "").strip()]
            return [b for b in books if b["circle"] == value]
        elif mode == "title":
            return books
        elif mode in ("author", "series", "character", "tag"):
            norm_cache = getattr(self, "_norm_meta_cache", {}) or {}
            result = []
            for b in books:
                norm_key = normalize_path(b.get("path", ""))
                meta = norm_cache.get(norm_key) or {}
                if value == "__unknown__":
                    if mode == "author" and not (meta.get("author") or ""):
                        result.append(b)
                    elif mode == "series" and not (meta.get("series") or ""):
                        result.append(b)
                    elif mode == "character" and not (meta.get("characters") or []):
                        result.append(b)
                    elif mode == "tag" and not (meta.get("tags") or []):
                        result.append(b)
                    continue
                if not meta:
                    continue
                if mode == "author":
                    author_val = meta.get("author")
                    if isinstance(author_val, str) and author_val == value:
                        result.append(b)
                    elif isinstance(author_val, (list, tuple)) and value in author_val:
                        result.append(b)
                elif mode == "series" and meta.get("series") == value:
                    result.append(b)
                elif mode == "character" and value in (meta.get("characters") or []):
                    result.append(b)
                elif mode == "tag" and value in (meta.get("tags") or []):
                    result.append(b)
            return result
        elif mode == "history_all":
            # value は path の set
            norm_value = {normalize_path(p) for p in value}
            return [b for b in books if normalize_path(b["path"]) in norm_value]
        elif mode == "history":
            return books
        elif mode == "added_date":
            return books
        elif mode == "metadata":
            if value == "__unknown__":
                return books
            try:
                rows = db.get_books_by_meta_source(value)
                paths = {normalize_path(r[3]) for r in rows}
                return [b for b in books if normalize_path(b.get("path", "")) in paths]
            except Exception:
                return books
        elif mode == "favorite":
            if value == "__unknown__":
                return books
            try:
                bookmarks = db.get_all_bookmarks()
                norm_bookmarks = {normalize_path(k): v for k, v in bookmarks.items()}
                rating = int(value) if value.isdigit() else 0
                if rating == 0:
                    return [b for b in books if norm_bookmarks.get(normalize_path(b.get("path", "")), 0) == 0]
                return [b for b in books if norm_bookmarks.get(normalize_path(b.get("path", "")), 0) == rating]
            except Exception:
                return books
        return books

    def _on_filter_changed(self, mode: str, value: str):
        """サイドバー選択に合わせフィルタ状態を更新する。"""
        scroll_modes = {"title", "added_date", "history"}
        self._sidebar_filter = (mode, value)
        if mode in scroll_modes:
            lib_root = (db.get_setting("library_folder") or "").strip()
            abs_value = value if os.path.isabs(value) else os.path.join(lib_root, value)
            norm = normalize_path(abs_value)
            QTimer.singleShot(
                config.CONTEXT_MENU_SCROLL_FALLBACK_DELAY_MS,
                lambda: self._grid.scroll_to_path(norm),
            )
            return
        self._apply_filters()

    def _on_filter_cleared(self):
        """サイドバー絞り込みを解除して一覧を再適用する。"""
        self._sidebar_filter = None
        self._apply_filters()

    def _on_search_changed(self, query: str):
        """検索語変更に応じてフィルタを再適用する。"""
        self._apply_filters()

    def _on_search_cleared(self):
        """検索クリア時にフィルタを再適用する。"""
        self._apply_filters()

    def _on_title_selected(self, path: str):
        """作品名サイドバーでアイテム選択→グリッドの該当カードにスクロール"""
        if not path:
            return
        self._grid.scroll_to_path(path)

    def _on_sidebar_context_menu_requested(self, path: str, global_pos):
        """サイドバー右クリックで選択項目のコンテキストメニューを表示（開く・プロパティ・削除など）"""
        if not path:
            return
        book = None
        for b in (self._all_books or []):
            if (b.get("path") or "") == path:
                book = b
                break
        if not book:
            book = {
                "path": path,
                "name": "",
                "title": "",
                "circle": "",
                "cover": "",
                "pages": 0,
                "rating": 0,
            }
        from context_menu import BookContextMenu
        menu = BookContextMenu(book, self, self._make_app_callbacks(), selected_books=[book])
        menu.exec(global_pos)

    # ── ドラッグ&ドロップ ─────────────────────────────────
    # ═══ ドロップ処理 ═══
    def dragEnterEvent(self, event):
        """URLドロップを受け付けるか判定する。"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """移動中もURLドロップ可否を維持する。"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """ドロップされたパスを取り込み処理に渡す。"""
        urls = event.mimeData().urls()
        if not urls:
            return
        paths = [u.toLocalFile() for u in urls]
        folder = (db.get_setting("library_folder") or "").strip()
        if not folder:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "未設定", "先にライブラリフォルダを設定してください。")
            return
        handle_drop(
            paths=paths,
            library_folder=folder,
            parent=self,
            on_done=self._on_drop_done,
        )
        event.acceptProposedAction()

    def _on_drop_done(self):
        """D&D完了後にライブラリを再スキャン"""
        folder = (db.get_setting("library_folder") or "").strip()
        if folder:
            self._start_scan(folder)

    # ── UI表示状態の復元・制御 ────────────────────────────

    def _restore_ui_visibility(self):
        """DB設定に従い各バー類の表示を復元する。"""
        # ツールバーと検索バーは別設定・未設定時は表示
        show_tool = db.get_setting("ui_show_toolbar", "1")
        self._set_main_toolbar_visible(show_tool == "1", save=False)
        show_search = db.get_setting("ui_show_searchbar", "1")
        self._set_searchbar_visible(show_search == "1", save=False)

        # サイドバー
        show_sidebar = db.get_setting("ui_show_sidebar", "1")
        self._set_sidebar_visible(show_sidebar != "0", save=False)

        # ゴーストバー（ソートバー）
        show_ghostbar = db.get_setting("ui_show_ghostbar", "1")
        self._set_ghostbar_visible(show_ghostbar != "0", save=False)

        # 情報バー（ステータスバー）
        show_infobar = db.get_setting("ui_show_infobar", "1")
        self._set_infobar_visible(show_infobar != "0", save=False)

    # ═══ UI表示切り替え ═══
    def _set_main_toolbar_visible(self, visible: bool, save: bool):
        """表示メニュー「ツールバー」：アイコン行の表示。"""
        self._main_toolbar.apply_visibility(visible)
        if hasattr(self, "_act_toolbar"):
            self._act_toolbar.setChecked(visible)
        if save:
            db.set_setting("ui_show_toolbar", "1" if visible else "0")

    def _set_searchbar_visible(self, visible: bool, save: bool):
        """表示メニュー「検索バー」／Ctrl+F：検索入力のみ。"""
        self._searchbar_row.setVisible(visible)
        if visible:
            self._searchbar.focus_input()
        else:
            self._searchbar.clear_search()
        if hasattr(self, "_act_searchbar"):
            self._act_searchbar.setChecked(visible)
        if hasattr(self, "_main_toolbar"):
            _sb = getattr(self._main_toolbar, "_btn_search", None)
            if _sb is not None:
                _sb.blockSignals(True)
                _sb.setChecked(visible)
                _sb.blockSignals(False)
        if save:
            db.set_setting("ui_show_searchbar", "1" if visible else "0")

    def _set_sidebar_visible(self, visible: bool, save: bool):
        """サイドバー表示とメニュー・ツールバーを同期する。"""
        self._sidebar.setVisible(visible)
        if hasattr(self, "_act_sidebar"):
            self._act_sidebar.setChecked(visible)
        if hasattr(self, "_main_toolbar"):
            _bs = getattr(self._main_toolbar, "_btn_sidebar", None)
            if _bs is not None:
                _bs.blockSignals(True)
                _bs.setChecked(visible)
                _bs.blockSignals(False)
        if save:
            db.set_setting("ui_show_sidebar", "1" if visible else "0")

    def _set_ghostbar_visible(self, visible: bool, save: bool) -> None:
        """ゴーストバー（ソートバー）とツールバー title アイコンの同期。"""
        self._sort_bar.setVisible(visible)
        if hasattr(self, "_sort_bar_sep_bottom"):
            self._sort_bar_sep_bottom.setVisible(visible)
        if hasattr(self, "_act_ghostbar"):
            self._act_ghostbar.setChecked(visible)
        if hasattr(self, "_main_toolbar"):
            self._main_toolbar.set_ghostbar_toggle_checked(visible)
        if save:
            db.set_setting("ui_show_ghostbar", "1" if visible else "0")

    def _set_infobar_visible(self, visible: bool, save: bool):
        """ステータスバー表示とメニューチェックを同期する。"""
        if hasattr(self, "_statusbar"):
            self._statusbar.setVisible(visible)
        if hasattr(self, "_act_infobar"):
            self._act_infobar.setChecked(visible)
        if save:
            db.set_setting("ui_show_infobar", "1" if visible else "0")

