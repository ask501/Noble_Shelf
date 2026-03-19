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
    QFileDialog,
    QStatusBar,
    QSlider,
    QLabel,
    QProgressDialog,
    QMessageBox,
    QDialog,
    QPushButton,
    QComboBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QButtonGroup,
)
from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QEvent, QUrl, QMimeData
from PySide6.QtGui import QAction, QKeySequence
import os
import time

import config
import db
from version import VERSION
from grid import BookGridView
from scanner import scan_library
from sidebar import SidebarWidget
from searchbar import SearchBar, filter_books, build_haystack_cache
from drop_handler import handle_drop, _get_pdf_cover_and_pages
from filter_popover import FilterPopover
from theme import THEME_COLORS, apply_dark_titlebar, APP_BAR_SEPARATOR_RGBA, COLOR_WHITE
from properties import _auto_kana, _needs_kana_conversion, StoreFileInputDialog
from menubar import setup_menubar, refresh_shortcuts
from first_run import LibrarySetupOverlay
from statusbar import setup_statusbar


def _resolve_cover(path: str, cover: str) -> str:
    """
    DBのカバーパスを表示・参照用に解決する。
    - DB に ID のみ保存されている場合は cover_cache と結合してフルパスに変換。
    - 絶対パスで存在すればそのまま返す。
    - 相対パスなら APP_BASE 基準で解決して存在すれば返す（cover_cache 等）。
    - リネームでフォルダだけ変わった場合は path 配下の同名ファイルを試す。
    """
    if not cover or not str(cover).strip():
        return cover or ""
    c = db.resolve_cover_stored_value(cover)
    if not c:
        return cover.strip()
    if os.path.exists(c):
        return c
    if not os.path.isabs(c):
        resolved = os.path.normpath(os.path.join(config.APP_BASE, c))
        if os.path.exists(resolved):
            return resolved
    if path and os.path.isdir(path):
        alt = os.path.join(path, os.path.basename(c))
        if os.path.exists(alt):
            return alt
    return c


class MainWindow(QMainWindow):
    bookmarkletReceived = Signal()  # ブックマークレット受信通知（既存のSignalインポートを使用）
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_TITLE} v{VERSION}")
        self.resize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)

        db.init_db()
        self._all_books: list[dict] = []
        self._sidebar_filter: tuple[str, str] | None = None  # (mode, value)
        # ソート状態: デフォルトは「作品名・昇順」
        self._sort_key: str = "title"
        self._sort_desc: bool = False
        # メタデータキャッシュ（ソート/フィルタ用）
        self._meta_cache: dict[str, dict] = {}
        # ゴーストバーのアクティブフィルター
        self._active_filters: list[dict] = []
        self._filter_logic: str = "and"
        self._filter_popover: FilterPopover | None = None
        # メニュー「DLSiteのファイルのみ」「FANZA/DMMのファイルのみ」（重複可＝両方ONで両方表示）
        self._filter_dlsite_only: bool = False
        self._filter_fanza_only: bool = False
        self._filter_no_cover_only: bool = False  # 表示メニュー「サムネイル未設定」選択時
        self._startup_time = time.time()
        self._open_viewers: list = []  # 内置ビューワー（すべて閉じる用）
        self._bookmarklet_window = None

        self._setup_menubar()
        self._setup_central()
        self._setup_statusbar()
        self.setAcceptDrops(True)
        self._setup_titlebar_context_menu()
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

    def eventFilter(self, obj, event):
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
        setup_menubar(self)

    def _on_open_settings(self):
        from PySide6.QtWidgets import QDialog
        from settings_dialog import SettingsDialog

        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            refresh_shortcuts(self)
        # 設定ダイアログを閉じたらカード表示設定を反映
        self._grid.apply_display_settings()

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
        for name, path in recent:
            if not path or not os.path.exists(path):
                continue
            act = menu.addAction(name or os.path.basename(path) or path)
            act.triggered.connect(lambda checked=False, p=path: open_book(p, self, modal=False))
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
            from bookmarklet_window import BookmarkletWindow
            from theme import apply_dark_titlebar
            self._bookmarklet_window = BookmarkletWindow(parent=self, main_window=self)
        self._bookmarklet_window.show()
        from theme import apply_dark_titlebar
        apply_dark_titlebar(self._bookmarklet_window)
        self._bookmarklet_window.raise_()
        self._bookmarklet_window.activateWindow()

    def _start_local_server(self) -> None:
        """ローカルHTTPサーバーを起動する"""
        import local_server

        local_server.start(on_receive=self._on_receive_bookmarklet)

    def _on_receive_bookmarklet(self, url: str, html: str) -> None:
        """
        ブックマークレットからの受信処理（バックグラウンドスレッドから呼ばれる）。
        メタデータ取得→DB保存→メインスレッドへシグナルemit。
        """
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

            if matched is None:
                # 一致なし → 従来通りキューに追加（🟡）
                db.add_bookmarklet_queue(
                    url=url,
                    site=meta.get("site", ""),
                    title=meta.get("title", ""),
                    circle=meta.get("circle", ""),
                    author=meta.get("author", ""),
                    dlsite_id=meta.get("dlsite_id", ""),
                    tags=",".join(meta.get("tags", [])),
                    price=meta.get("price"),
                    release_date=meta.get("release_date", ""),
                    cover_url=meta.get("cover_url", ""),
                    store_url=meta.get("store_url", ""),
                    status="pending",
                )
            else:
                # 一致あり → 空でないフィールド数で分岐
                non_empty = 0
                for k in ("title", "circle", "author", "dlsite_id", "release_date", "cover_url"):
                    if (meta.get(k, "") or "").strip():
                        non_empty += 1
                if meta.get("tags") or []:
                    non_empty += 1
                if meta.get("price") is not None:
                    non_empty += 1

                if non_empty <= 1:
                    # 即時適用（🟢）
                    found_path = matched["path"]

                    db.set_book_meta(
                        found_path,
                        author=meta.get("author", "") or "",
                        tags=meta.get("tags") or [],
                        dlsite_id=meta.get("dlsite_id") or None,
                        release_date=meta.get("release_date") or None,
                        price=meta.get("price"),
                        meta_source=meta.get("site") or None,
                    )

                    if (meta.get("title", "") or "").strip() and (meta.get("circle", "") or "").strip():
                        db.update_book_display(
                            found_path,
                            title=meta.get("title") or None,
                            circle=meta.get("circle") or None,
                        )

                    if (meta.get("cover_url", "") or "").strip():
                        db.update_book_cover_path(found_path, meta.get("cover_url"))

                    db.add_bookmarklet_queue(
                        url=url,
                        site=meta.get("site", ""),
                        title=meta.get("title", ""),
                        circle=meta.get("circle", ""),
                        author=meta.get("author", ""),
                        dlsite_id=meta.get("dlsite_id", ""),
                        tags=",".join(meta.get("tags", [])),
                        price=meta.get("price"),
                        release_date=meta.get("release_date", ""),
                        cover_url=meta.get("cover_url", ""),
                        store_url=meta.get("store_url", ""),
                        status="done",
                    )
                else:
                    # ユーザー確認（🟡）
                    db.add_bookmarklet_queue(
                        url=url,
                        site=meta.get("site", ""),
                        title=meta.get("title", ""),
                        circle=meta.get("circle", ""),
                        author=meta.get("author", ""),
                        dlsite_id=meta.get("dlsite_id", ""),
                        tags=",".join(meta.get("tags", [])),
                        price=meta.get("price"),
                        release_date=meta.get("release_date", ""),
                        cover_url=meta.get("cover_url", ""),
                        store_url=meta.get("store_url", ""),
                        status="pending",
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
        import local_server

        local_server.stop()
        super().closeEvent(event)

    def _on_restore_backup(self):
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
    def _setup_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        outer.setSpacing(config.LAYOUT_SPACING_ZERO)

        # 検索バー（初期非表示）
        self._searchbar = SearchBar()
        self._searchbar.searchChanged.connect(self._on_search_changed)
        self._searchbar.cleared.connect(self._on_search_cleared)
        self._searchbar.setVisible(False)
        outer.addWidget(self._searchbar)

        # スプリッター（サイドバー | グリッド＋ソートバー）
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(config.MAIN_SPLITTER_HANDLE_WIDTH)

        self._sidebar = SidebarWidget()
        self._sidebar.filterChanged.connect(self._on_filter_changed)
        self._sidebar.filterCleared.connect(self._on_filter_cleared)
        # サイドバーのモード変更 = ソート項目変更として扱う
        self._sidebar.sortModeChanged.connect(self._on_sort_mode_changed)
        # 作品名サイドバーでの選択 → グリッドへスクロール
        self._sidebar.titleSelected.connect(self._on_title_selected)
        self._sidebar.contextMenuRequested.connect(self._on_sidebar_context_menu_requested)
        splitter.addWidget(self._sidebar)

        # 右側コンテナ: 上にソートバー（ゴーストバー）、下にグリッド
        grid_container = QWidget()
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        grid_layout.setSpacing(config.LAYOUT_SPACING_ZERO)

        # ── ゴーストバー（ソートキーラベル / 昇降順 / フィルター / クリア） ──
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

        # フィルターボタン（現状はダミー）
        self._filter_btn = QPushButton("フィルター 🔧")
        self._filter_btn.setObjectName("FilterButton")
        self._filter_btn.setFixedHeight(config.SORT_BAR_BUTTON_HEIGHT)
        self._filter_btn.setFont(font)
        self._filter_btn.clicked.connect(self._on_filter_button_clicked)
        bar_layout.addWidget(self._filter_btn)

        # クリアボタン（ソート・フィルター条件をリセット）
        self._clear_btn = QPushButton("クリア")
        self._clear_btn.setObjectName("ClearButton")
        self._clear_btn.setFixedHeight(config.SORT_BAR_BUTTON_HEIGHT)
        self._clear_btn.setFont(font)
        self._clear_btn.clicked.connect(self._on_clear_sort_and_filters)
        bar_layout.addWidget(self._clear_btn)

        # フィルターバッジエリア（条件タグを横並びで表示）
        self._filter_badge_layout = QHBoxLayout()
        self._filter_badge_layout.setSpacing(config.SORT_BAR_BADGE_SPACING)
        self._filter_badge_layout.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        bar_layout.addLayout(self._filter_badge_layout)

        # 右側を埋めるストレッチ
        bar_layout.addStretch()

        # ゴーストバーのスタイル
        self._sort_bar.setStyleSheet(
            f"""
            QWidget#SortBar {{
                background-color: {THEME_COLORS["card_bg"]};
                color: {THEME_COLORS["text_main"]};
                border-bottom: 1px solid {APP_BAR_SEPARATOR_RGBA};
            }}
            QLabel#SortLabel {{
                background-color: transparent;
                color: {THEME_COLORS["text_main"]};
                padding-left: {config.SORT_BAR_LABEL_PADDING_LEFT}px;
            }}
            QPushButton#SortOrderButton, QPushButton#FilterButton, QPushButton#ClearButton {{
                background-color: {THEME_COLORS["bg_widget"]};
                color: {THEME_COLORS["text_main"]};
                border: 1px solid {THEME_COLORS["border"]};
                border-radius: {config.SORT_BAR_BTN_RADIUS}px;
                padding: {config.SORT_BAR_BTN_PADDING_Y}px {config.SORT_BAR_BTN_PADDING_X}px;
            }}
            QPushButton#SortOrderButton:hover, QPushButton#FilterButton:hover, QPushButton#ClearButton:hover {{
                background-color: {THEME_COLORS["hover"]};
            }}
            """
        )
        grid_layout.addWidget(self._sort_bar)

        self._grid = BookGridView(app_callbacks=self._make_app_callbacks())
        grid_layout.addWidget(self._grid)

        # ライブラリ未設定時に中央に表示するオーバーレイ
        self._empty_hint = LibrarySetupOverlay()
        self._empty_hint.setupClicked.connect(self._on_click_setup_library)
        grid_layout.addWidget(self._empty_hint)

        splitter.addWidget(grid_container)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes(
            [
                config.MAIN_SPLITTER_SIDEBAR_INIT_WIDTH,
                config.WINDOW_WIDTH - config.MAIN_SPLITTER_SIDEBAR_INIT_WIDTH,
            ]
        )
        outer.addWidget(splitter)
        self._splitter = splitter

        # 初期ソートバー表示
        self._update_sort_bar()

    def _make_app_callbacks(self) -> dict:
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
        sb = QStatusBar()
        sb.setSizeGripEnabled(True)
        sb.setStyleSheet(
            f"""
            QStatusBar {{
                background-color: {THEME_COLORS["card_bg"]};
                color: {THEME_COLORS["text_main"]};
                border-top: 1px solid {APP_BAR_SEPARATOR_RGBA};
                font-size: {config.FONT_SIZE_STATUS_BAR}px;
            }}
            """
        )
        self.setStatusBar(sb)
        self._statusbar = sb

        self._status_label = QLabel("0 冊")
        sb.addWidget(self._status_label)

        self._size_slider = setup_statusbar(self, sb)
        self._size_slider.valueChanged.connect(self._on_card_size_changed)

        self._grid.ctrlWheelZoom.connect(self._on_ctrl_wheel_zoom)

    def _on_card_size_changed(self, value: int):
        self._grid.set_card_width(value)

    def _on_ctrl_wheel_zoom(self, delta: int):
        """Ctrl+ホイール: delta > 0 で拡大、< 0 で縮小"""
        step = config.CARD_SIZE_WHEEL_STEP
        new_val = self._size_slider.value() + (step if delta > 0 else -step)
        new_val = max(config.SLIDER_MIN_WIDTH, min(config.SLIDER_MAX_WIDTH, new_val))
        self._size_slider.setValue(new_val)  # valueChanged経由でgridも更新される


    def _toggle_searchbar(self):
        visible = not self._searchbar.isVisible()
        self._set_searchbar_visible(visible, save=True)

    # ── ライブラリ読み込み ────────────────────────────────
    def _load_library(self):
        folder = (db.get_setting("library_folder") or "").strip()
        if not folder or not os.path.isdir(folder):
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
            books = [
                {
                    "path":   row[3],
                    "name":   row[0],
                    "title":  row[2] or row[0],
                    "circle": row[1] or "",
                    "cover":  _resolve_cover(row[3] or "", row[4] or ""),
                    "pages":  0,
                    "rating": 0,
                }
                for row in rows
                if row[3]
            ]
            self._all_books = books
            # 起動時は作品名昇順で表示＋サイドバーを作品名に
            self._sort_key = "title"
            self._sort_desc = False
            if hasattr(self, "_sidebar"):
                self._sidebar._combo.setCurrentIndex(0)
            self._apply_filters()

        # 裏でスキャン
        self._start_scan(folder)

        # 起動時にもカード表示設定を反映
        self._grid.apply_display_settings()

    def _select_library_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "ライブラリフォルダを選択", ""
        )
        if folder:
            db.set_setting("library_folder", folder)
            # 設定されたらオーバーレイを隠し、グリッドを表示してスキャン
            if hasattr(self, "_empty_hint"):
                self._empty_hint.hide()
            if hasattr(self, "_grid"):
                self._grid.show()
            self._start_scan(folder)

    def _on_click_setup_library(self):
        """中央ボタンからライブラリフォルダ設定を開く"""
        self._select_library_folder()

    def _rescan_library(self):
        folder = (db.get_setting("library_folder") or "").strip()
        if folder and os.path.isdir(folder):
            self._start_scan(folder)

    def _start_scan(self, folder: str):
        self.setWindowTitle(f"{config.APP_TITLE} v{VERSION}")
        scan_library(
            folder,
            on_finished=self._on_scan_finished,
            on_progress=self._on_scan_progress,
            on_error=self._on_scan_error,
            on_store_files_pending=self._on_store_files_pending,
        )

    def _on_scan_finished(self, books: list):
        # スキャン結果の cover は DB の生値（ID/相対パス）なので表示用に解決する（サムネ設定が剥がれて見えない問題を防ぐ）
        for b in books:
            b["cover"] = _resolve_cover(b.get("path") or "", b.get("cover") or "")

        # 直前の一覧とスキャン結果を比較し、差分がなければグリッドの再読み込みを行わない
        old_books = self._all_books or []

        def _books_changed(a: list[dict], b: list[dict]) -> bool:
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
        build_haystack_cache(books)

        # 差分なしならグリッドはそのまま維持して一瞬消える問題を回避
        if changed:
            self._apply_filters()

        self._sidebar.refresh()
        folder = (db.get_setting("library_folder") or "").strip()
        self.setWindowTitle(f"{config.APP_TITLE} v{VERSION}")
        self._status_label.setText(f"{len(books)} 冊")

    def _on_store_files_pending(self, pending_list: list):
        """ストアファイル追加時に入力ダイアログで登録。起動直後（約3秒以内）のスキャンではダイアログを出さずファイル名から登録（強制終了後に起動するとダイアログが出るバグを防ぐ）。"""
        is_initial_scan = (time.time() - self._startup_time) < config.INITIAL_SCAN_SUPPRESS_DIALOG_SEC
        if is_initial_scan:
            for item in pending_list:
                path = item["path"]
                name = item["name"]
                mtime = item["mtime"]
                sc = (item.get("suggested_circle") or "").strip()
                st = (item.get("suggested_title") or name).strip()
                display_name = db.format_book_name(sc, st) or name
                db.bulk_upsert_books([(display_name, sc, st, path, "", mtime, 0)])
            self._refresh_books_from_db()
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
            db.bulk_upsert_books([book_tuple])
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
        self._refresh_books_from_db()

    def _refresh_books_from_db(self):
        """DBから一覧を再取得してグリッド・サイドバー・タイトルを更新する。"""
        try:
            self._meta_cache = db.get_all_book_metas()
        except Exception:
            self._meta_cache = {}
        try:
            rows = db.get_all_books()
        except Exception:
            rows = []
        books = [
            {
                "path": row[3],
                "name": row[0],
                "title": row[2] or row[0],
                "circle": row[1] or "",
                "cover": _resolve_cover(row[3] or "", row[4] or ""),
                "pages": 0,
                "rating": 0,
                "is_dlst": int(row[5]) if len(row) > 5 else 0,
            }
            for row in rows
            if row[3]
        ]
        self._all_books = books
        build_haystack_cache(books)
        self._apply_filters()
        self._sidebar.refresh()
        folder = (db.get_setting("library_folder") or "").strip()
        self.setWindowTitle(f"{config.APP_TITLE} v{VERSION}")
        self._status_label.setText(f"{len(books)} 冊")

    # ── 単一ブック更新（プロパティ保存などから呼ばれる） ────────────

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
        except Exception:
            self._meta_cache = {}

        # DBから最新のbooks一覧を取得して _all_books を更新
        try:
            rows = db.get_all_books()
        except Exception:
            rows = []
        books = [
            {
                "path":   row[3],
                "name":   row[0],
                "title":  row[2] or row[0],
                "circle": row[1] or "",
                "cover":  _resolve_cover(row[3] or "", row[4] or ""),
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
            else:
                hb = g.horizontalScrollBar()
                done = [False]

                def do_apply():
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
                    # 2回目以降の on_book_updated で _apply_filters が再度走るとグリッドがリセットされるため、
                    # 即クリアせず遅延クリアする（複数回の更新後も最後の復元が効くようにする）
                    QTimer.singleShot(
                        config.CONTEXT_MENU_SCROLL_RESET_DELAY_MS,
                        lambda: setattr(self, "_context_menu_scroll", None),
                    )

                def on_range_changed(_min, max_val):
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
                        if done[0]:
                            return
                        try:
                            vb.rangeChanged.disconnect(on_range_changed)
                        except Exception:
                            pass
                        do_apply()
                    QTimer.singleShot(config.CONTEXT_MENU_SCROLL_FALLBACK_DELAY_MS, fallback)

    def _on_scan_progress(self, scanned: int, total: int):
        self.setWindowTitle(config.APP_TITLE)

    def _on_scan_error(self, msg: str):
        self.setWindowTitle(config.APP_TITLE)

    # ── フィルタリング（サイドバー + 検索の合成） ─────────
    def _apply_filters(self):
        # 元の全件リスト
        all_books = self._all_books
        # サイドバー（作品名一覧）用に、フィルタ前の並び順を準備
        sidebar_books = self._sort_books(all_books) if all_books else []

        books = all_books

        # サイドバーフィルタ
        if self._sidebar_filter:
            mode, value = self._sidebar_filter
            books = self._apply_sidebar_filter(books, mode, value)

        # ストアファイルフィルタ（DLSiteのみ / FANZAのみ、重複可）
        books = self._apply_store_filter(books)

        # サムネイル未設定フィルタ（表示メニュー）
        books = self._apply_no_cover_filter(books)

        # 検索フィルタ
        query = self._searchbar._input.text()
        if query.strip():
            books = filter_books(books, query)

        # ゴーストバーのフィルタ条件
        if self._active_filters:
            books = self._apply_active_filters(books)

        # ソートを適用
        books = self._sort_books(books)

        # フィルター適用時は件数を保持（ゴーストバーで「全 N 件」表示用）
        if self._active_filters:
            self._filtered_count = len(books)
        elif hasattr(self, "_filtered_count"):
            delattr(self, "_filtered_count")

        # グリッドへの反映
        self._grid.load_books(books)
        # サイドバー: フィルター指定時はプルダウンを隠し「フィルター」＋結果一覧に切替
        if hasattr(self, "_sidebar"):
            if self._active_filters:
                self._sidebar.set_filter_result_mode(True, books)
            else:
                self._sidebar.set_filter_result_mode(False, None)
                self._sidebar.set_title_items(sidebar_books)

    # ── ソート関連 ───────────────────────────────────────

    def _update_sort_bar(self):
        """ソートバーのラベルと昇降順ボタンの表示を更新"""
        # フィルター適用中はゴーストバーラベルを「全 N 件」に（サイドバー選択状態にしない）
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
                "added_date": "追加順",
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

    def _update_filter_badges(self):
        """アクティブフィルターをゴーストバーにバッジ表示"""
        if not hasattr(self, "_filter_badge_layout"):
            return
        # 既存バッジを全削除
        while self._filter_badge_layout.count():
            item = self._filter_badge_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._active_filters:
            return

        label_map = {
            "author": "作者",
            "circle": "サークル",
            "series": "シリーズ",
            "character": "キャラクター",
            "tag": "タグ",
        }

        from functools import partial

        for i, cond in enumerate(self._active_filters):
            field = cond.get("field", "")
            value = cond.get("value", "")
            if not field or not value:
                continue
            name = label_map.get(field, field)
            badge = QPushButton(f"{name}: {value}  ×")
            badge.setFixedHeight(config.FILTER_BADGE_HEIGHT)
            badge.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {THEME_COLORS["bg_widget"]};
                    color: {THEME_COLORS["text_main"]};
                    border: 1px solid {THEME_COLORS["accent"]};
                    border-radius: {config.FILTER_BADGE_RADIUS}px;
                    padding: {config.FILTER_BADGE_PADDING_Y}px {config.FILTER_BADGE_PADDING_X}px;
                    font-size: {config.FONT_SIZE_PROP_HINT}px;
                }}
                QPushButton:hover {{
                    background-color: {THEME_COLORS["delete"]};
                    color: {COLOR_WHITE};
                    border-color: {THEME_COLORS["delete"]};
                }}
                """
            )
            badge.clicked.connect(partial(self._remove_filter_badge, i))
            self._filter_badge_layout.addWidget(badge)

    def _remove_filter_badge(self, index: int):
        """バッジの×クリックで該当フィルター削除"""
        if 0 <= index < len(self._active_filters):
            self._active_filters.pop(index)
            self._update_filter_badges()
            self._apply_filters()

    def _on_sort_order_toggled(self):
        """昇順↔降順トグルボタン"""
        self._sort_desc = not self._sort_desc
        self._update_sort_bar()
        self._apply_filters()
        # 昇降順トグル時もサイドバーの表示順を最新状態に反映
        self._sidebar.refresh()

    def _on_clear_sort_and_filters(self):
        """ソート・フィルター条件をリセット（フィルター系は後で実装）"""
        # ソート状態リセット
        self._sort_key = "title"
        self._sort_desc = False  # 昇順
        # フィルター条件リセット
        self._active_filters = []
        self._filter_logic = "and"
        self._filter_dlsite_only = False
        self._filter_fanza_only = False
        self._filter_no_cover_only = False
        if hasattr(self, "_act_filter_dlsite"):
            self._act_filter_dlsite.setChecked(False)
        if hasattr(self, "_act_filter_fanza"):
            self._act_filter_fanza.setChecked(False)
        if hasattr(self, "_act_filter_no_cover"):
            self._act_filter_no_cover.setChecked(False)
        # フィルターポップオーバーのUIリセット
        if hasattr(self, "_filter_popover") and self._filter_popover:
            # reset() が存在する場合のみ呼び出し（古いバージョン互換）
            reset_fn = getattr(self._filter_popover, "reset", None)
            if callable(reset_fn):
                reset_fn()
        # サイドバーコンボを先頭（作品名）に戻す
        if hasattr(self, "_sidebar"):
            self._sidebar._combo.setCurrentIndex(0)
        # バー表示とグリッド反映の更新
        self._update_sort_bar()
        self._update_filter_badges()
        self._apply_filters()

    def _on_filter_button_clicked(self):
        """フィルター🔧ボタン押下時にポップオーバーを表示"""
        if self._filter_popover is None:
            self._filter_popover = FilterPopover(
                parent=self,
                on_apply=self._on_filter_popover_apply,
                on_clear=self._on_filter_popover_clear,
                on_remove=self._on_filter_popover_remove,
            )
        if self._filter_popover.isVisible():
            self._filter_popover.hide()
            return
        # ボタン直下に表示
        btn_pos = self._filter_btn.mapToGlobal(QPoint(0, self._filter_btn.height()))
        self._filter_popover.move(btn_pos)
        self._filter_popover.show()

    def _on_filter_popover_apply(self, conditions: list[dict], logic: str):
        """ポップオーバーからフィルター条件が適用されたとき"""
        cleaned = []
        for c in conditions:
            field = (c.get("field") or "").strip()
            value = (c.get("value") or "").strip()
            if not field or not value:
                continue
            cleaned.append({"field": field, "value": value})
        self._active_filters = cleaned
        self._filter_logic = logic if logic in ("and", "or") else "and"
        self._update_filter_badges()
        self._apply_filters()
        self._update_sort_bar()

    def _on_filter_popover_clear(self):
        """ポップオーバーからフィルター条件がクリアされたとき"""
        self._active_filters = []
        self._filter_logic = "and"
        self._update_sort_bar()
        self._update_filter_badges()
        self._apply_filters()

    def _on_filter_popover_remove(self, index: int):
        """フィルターポップオーバーのバッジ×で1件削除"""
        if 0 <= index < len(self._active_filters):
            self._active_filters.pop(index)
            self._update_filter_badges()
            self._apply_filters()
            self._update_sort_bar()

    def _apply_active_filters(self, books: list[dict]) -> list[dict]:
        """ゴーストバーのフィルター条件を適用"""
        if not self._active_filters:
            return books

        # メタキャッシュを準備
        if not self._meta_cache:
            try:
                self._meta_cache = db.get_all_book_metas()
            except Exception:
                self._meta_cache = {}

        logic = self._filter_logic if self._filter_logic in ("and", "or") else "and"

        def match_condition(book: dict, cond: dict) -> bool:
            field = cond.get("field")
            value = (cond.get("value") or "").strip()
            if not value:
                return True

            path = book.get("path", "") or ""
            meta = self._meta_cache.get(path) if path else {}

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

        filtered: list[dict] = []
        for b in books:
            results = [match_condition(b, c) for c in self._active_filters]
            if not results:
                filtered.append(b)
                continue
            if logic == "and":
                if all(results):
                    filtered.append(b)
            else:
                if any(results):
                    filtered.append(b)
        return filtered

    def _on_sort_mode_changed(self, mode: str):
        """サイドバーでモードが選ばれたとき"""
        self._sort_key = mode or "title"
        self._sidebar_filter = None  # モード切替時はフィルターをクリアし作品名昇順で表示
        self._update_sort_bar()
        self._apply_filters()
        self._sidebar.refresh()

    def _sort_books(self, books: list[dict]) -> list[dict]:
        """現在のソートキー/順序に基づいて books を並べ替える"""
        if not books:
            return []

        # メタキャッシュが空なら先に一括ロード（1件ずつDBアクセスを防ぐ）
        if not self._meta_cache:
            try:
                self._meta_cache = db.get_all_book_metas()
            except Exception:
                pass

        key = self._sort_key
        desc = self._sort_desc

        # メタデータはアプリ全体でキャッシュして、繰り返しDBアクセスを抑える
        def get_meta(path: str) -> dict:
            return self._meta_cache.get(path, {})

        # 追加順: mtime を取得
        mtime_map: dict[str, float] = {}
        if key == "added_date":
            try:
                mtime_map = db.get_known_paths()
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
                return mtime_map.get(path, 0.0)

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
            for row in rows:
                path = row[3] or ""
                cover = row[4] or ""
                ext = os.path.splitext(path)[1].lower() if path else ""
                if ext == ".pdf":
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

    def _repair_pdf_covers(self):
        """PDFの1枚目をカバーとして未設定・壊れているものを cover_cache に生成して DB を更新する"""
        try:
            rows = db.get_all_books()
        except Exception as e:
            QMessageBox.critical(self, "PDFサムネ修復", f"一覧の取得に失敗しました:\n{e}")
            return
        pdf_rows = [(r[3], r[4]) for r in rows if r[3] and os.path.splitext(r[3])[1].lower() == ".pdf"]
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

            need_title = (not cur_tk or _needs_kana_conversion(cur_tk)) and title_src
            need_circle = (not cur_ck or _needs_kana_conversion(cur_ck)) and circle_src

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
        self._filter_dlsite_only = checked
        if hasattr(self, "_act_filter_dlsite"):
            self._act_filter_dlsite.setChecked(checked)
        self._apply_filters()

    def _set_filter_fanza_only(self, checked: bool):
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
        self._filter_no_cover_only = checked
        if hasattr(self, "_act_filter_no_cover"):
            self._act_filter_no_cover.setChecked(checked)
        self._apply_filters()

    def _apply_sidebar_filter(self, books: list, mode: str, value: str) -> list:
        if mode == "circle":
            if value == "__unknown__":
                return [b for b in books if not (b.get("circle") or "").strip()]
            return [b for b in books if b["circle"] == value]
        elif mode == "title":
            return [b for b in books if b["path"] == value]
        elif mode in ("author", "series", "character", "tag"):
            result = []
            for b in books:
                meta = (self._meta_cache.get(b["path"]) or {}) if self._meta_cache else {}
                if value == "__unknown__":
                    # フィールドが未設定の本を抽出
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
                    # author が文字列でもリストでもマッチするようにする
                    if isinstance(author_val, str) and author_val == value:
                        result.append(b)
                    elif isinstance(author_val, (list, tuple)) and value in author_val:
                        result.append(b)
                elif mode == "series"  and meta.get("series") == value:
                    result.append(b)
                elif mode == "character" and value in (meta.get("characters") or []):
                    result.append(b)
                elif mode == "tag"     and value in (meta.get("tags") or []):
                    result.append(b)
            return result
        elif mode == "history":
            return [b for b in books if b["path"] == value]
        elif mode == "added_date":
            if not value:
                return books
            return [b for b in books if b["path"] == value]
        elif mode == "metadata":
            if value == "__unknown__":
                return books
            try:
                rows = db.get_books_by_meta_source(value)
                paths = {r[3] for r in rows}
                return [b for b in books if b.get("path") in paths]
            except Exception:
                return books
        elif mode == "favorite":
            if value == "__unknown__":
                return books
            try:
                bookmarks = db.get_all_bookmarks()
                rating = int(value) if value.isdigit() else 0
                if rating == 0:
                    return [b for b in books if bookmarks.get(b.get("path"), 0) == 0]
                return [b for b in books if bookmarks.get(b.get("path"), 0) == rating]
            except Exception:
                return books
        return books

    def _on_filter_changed(self, mode: str, value: str):
        self._sidebar_filter = (mode, value)
        self._apply_filters()

    def _on_filter_cleared(self):
        self._sidebar_filter = None
        self._apply_filters()

    def _on_search_changed(self, query: str):
        self._apply_filters()

    def _on_search_cleared(self):
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
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
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
        # メニューバー
        show_menubar = db.get_setting("ui_show_menubar", "1")
        self._set_menubar_visible(show_menubar != "0", save=False)

        # 検索バー（デフォルトは非表示）
        show_search = db.get_setting("ui_show_searchbar", "0")
        self._set_searchbar_visible(show_search == "1", save=False)

        # サイドバー
        show_sidebar = db.get_setting("ui_show_sidebar", "1")
        self._set_sidebar_visible(show_sidebar != "0", save=False)

        # 情報バー（ステータスバー）
        show_infobar = db.get_setting("ui_show_infobar", "1")
        self._set_infobar_visible(show_infobar != "0", save=False)

    def _set_menubar_visible(self, visible: bool, save: bool):
        mb = self.menuBar()
        mb.setVisible(visible)
        if hasattr(self, "_act_menubar"):
            self._act_menubar.setChecked(visible)
        if save:
            db.set_setting("ui_show_menubar", "1" if visible else "0")

    def _set_searchbar_visible(self, visible: bool, save: bool):
        self._searchbar.setVisible(visible)
        if visible:
            self._searchbar.focus_input()
        else:
            self._searchbar.clear_search()
        if hasattr(self, "_act_searchbar"):
            self._act_searchbar.setChecked(visible)
        if save:
            db.set_setting("ui_show_searchbar", "1" if visible else "0")

    def _set_sidebar_visible(self, visible: bool, save: bool):
        if visible:
            self._sidebar.show()
        else:
            self._sidebar.hide()
        if hasattr(self, "_act_sidebar"):
            self._act_sidebar.setChecked(visible)
        if save:
            db.set_setting("ui_show_sidebar", "1" if visible else "0")

    def _set_infobar_visible(self, visible: bool, save: bool):
        if hasattr(self, "_statusbar"):
            self._statusbar.setVisible(visible)
        if hasattr(self, "_act_infobar"):
            self._act_infobar.setChecked(visible)
        if save:
            db.set_setting("ui_show_infobar", "1" if visible else "0")

    def _setup_titlebar_context_menu(self):
        # メニューバー非表示時にも復元できるように、ウィンドウのコンテキストメニューに追加
        self._restore_menubar_action = QAction("メニューバーを表示", self)
        self._restore_menubar_action.triggered.connect(
            lambda: self._set_menubar_visible(True, save=True)
        )
        self.addAction(self._restore_menubar_action)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

