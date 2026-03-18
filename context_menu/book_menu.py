from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Any, Callable

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QWidget,
    QWidgetAction,
)
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtCore import QUrl

import config
import db
from context_menu._utils import (
    ALLOWED_DLSITE_VIEWER_NAMES,
    ALLOWED_DMM_VIEWER_NAMES,
    STORE_FILE_EXTS_DMM,
    _get_shortcut_for_display,
    _get_store_viewer_path,
    _is_allowed_store_viewer,
    _is_store_file,
    _show_viewer_not_set_dialog,
    _show_wrong_viewer_dialog,
    open_book,
    resolve_shortcut,
)
from properties import PropertyDialog, RenameDialog
from theme import THEME_COLORS, CONTEXT_MENU_SEP_COLOR


class BookContextMenu(QMenu):
    def __init__(self, book: dict, parent_window, app_callbacks: dict[str, Callable[..., Any]], selected_books: list[dict] | None = None):
        """
        book: 右クリックした1冊のdict
        selected_books: 複数選択時はそのリスト（2件以上）。単一または未選択時は None。
        """
        super().__init__(parent_window)
        self._book = book
        self._parent_window = parent_window
        self._callbacks = app_callbacks or {}
        self._selected_books = selected_books if selected_books and len(selected_books) > 1 else None
        if self._selected_books is None and book and book.get("path"):
            self._selected_books = [book]

        self._path = book.get("path", "")
        self._name = book.get("name", "")
        self._title = book.get("title", "") or self._name
        self._circle = book.get("circle", "")
        self._cover = book.get("cover", "")
        self._has_path = bool(self._path and os.path.exists(self._path))
        if self._selected_books:
            self._has_path = any(b.get("path") and os.path.exists(b.get("path", "")) for b in self._selected_books)

        # dlsite_idの有無（ストアページ開くの有効/無効判定用）
        try:
            meta = db.get_book_meta(self._path) if self._path else None
            self._has_store = bool(meta and meta.get("dlsite_id"))
        except Exception:
            self._has_store = False

        self._setup_style()
        self._build_menu()
        self.setMinimumWidth(config.BOOK_CONTEXT_MENU_MIN_WIDTH)

    def _setup_style(self):
        self.setStyleSheet(
            f"""
            QMenu {{
                background-color: {THEME_COLORS["bg_panel"]};
                color: {THEME_COLORS["text_main"]};
                border: 1px solid {CONTEXT_MENU_SEP_COLOR};
                border-radius: {config.BOOK_CONTEXT_MENU_BORDER_RADIUS}px;
                padding: {config.BOOK_CONTEXT_MENU_PADDING_Y}px 0;
                font-family: "{config.DROPDOWN_FONT_FAMILY}";
                font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
            }}
            QMenu::item {{
                padding: {config.BOOK_CONTEXT_MENU_ITEM_PADDING[0]}px {config.BOOK_CONTEXT_MENU_ITEM_PADDING[1]}px {config.BOOK_CONTEXT_MENU_ITEM_PADDING[2]}px {config.BOOK_CONTEXT_MENU_ITEM_PADDING[3]}px;
                border-radius: {config.BOOK_CONTEXT_MENU_ITEM_RADIUS}px;
            }}
            QMenu::item:selected {{
                background-color: {THEME_COLORS["hover"]};
            }}
            QMenu::item:disabled {{
                color: {THEME_COLORS["menu_disabled"]};
            }}
            QMenu::separator {{
                height: {config.BOOK_CONTEXT_MENU_SEP_HEIGHT}px;
                background: {CONTEXT_MENU_SEP_COLOR};
                margin: {config.BOOK_CONTEXT_MENU_SEP_MARGIN[0]}px {config.BOOK_CONTEXT_MENU_SEP_MARGIN[1]}px;
            }}
            QMenu::item#menu_danger {{
                color: {THEME_COLORS["delete"]};
            }}
            QMenu::item#menu_danger:selected {{
                color: {THEME_COLORS["text_main"]};
                background-color: {THEME_COLORS["hover"]};
            }}
            """
        )

    def _add_action(self, text: str, enabled: bool, handler: Callable[[], None] | None) -> QAction:
        act = QAction(text, self)
        act.setEnabled(enabled)
        if handler:
            act.triggered.connect(handler)
        self.addAction(act)
        return act

    def _add_action_with_shortcut(
        self,
        text: str,
        shortcut_key: str,
        enabled: bool,
        handler: Callable[[], None] | None,
    ) -> QAction | None:
        shortcut_str = (_get_shortcut_for_display(shortcut_key) or "").strip()
        if not shortcut_str:
            self._add_action(text, enabled, handler)
            return None

        wa = QWidgetAction(self)
        wa.setEnabled(enabled)
        if handler:
            wa.triggered.connect(handler)

        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(*config.BOOK_CONTEXT_MENU_ROW_MARGINS)
        lay.setSpacing(config.BOOK_CONTEXT_MENU_ROW_SPACING)

        lbl_text = QLabel(text)
        lbl_shortcut = QLabel(shortcut_str)

        if enabled:
            row.setStyleSheet(
                f"""
                QWidget {{
                    background: transparent;
                    padding: 0;
                }}
                QWidget:hover {{
                    background-color: {THEME_COLORS['hover']};
                    border-radius: {config.BOOK_CONTEXT_MENU_ITEM_RADIUS}px;
                }}
            """
            )
            lbl_text.setStyleSheet(
                f"""
                color: {THEME_COLORS['text_main']};
                background: transparent;
                padding: {config.BOOK_CONTEXT_MENU_ROW_LABEL_PADDING_Y}px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
            """
            )
            lbl_shortcut.setStyleSheet(
                f"""
                color: {THEME_COLORS['context_menu_shortcut']};
                background: transparent;
                padding: {config.BOOK_CONTEXT_MENU_ROW_LABEL_PADDING_Y}px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU_SHORTCUT}px;
            """
            )
        else:
            row.setStyleSheet("background: transparent;")
            lbl_text.setStyleSheet(
                f"""
                color: {THEME_COLORS['menu_disabled']};
                background: transparent;
                padding: {config.BOOK_CONTEXT_MENU_ROW_LABEL_PADDING_Y}px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
            """
            )
            lbl_shortcut.setStyleSheet(
                f"""
                color: {THEME_COLORS['menu_disabled']};
                background: transparent;
                padding: {config.BOOK_CONTEXT_MENU_ROW_LABEL_PADDING_Y}px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU_SHORTCUT}px;
            """
            )

        lay.addWidget(lbl_text)
        lay.addStretch()
        lay.addWidget(lbl_shortcut)

        wa.setDefaultWidget(row)
        self.addAction(wa)
        return wa

    def _build_menu(self):
        selected_count = len(self._selected_books) if self._selected_books else 1
        label_open = f"{selected_count}件を開く" if selected_count > 1 else "開く"
        self._add_action_with_shortcut(label_open, "file_open", self._has_path, self._on_open)

        # 外部ビュワーで開く
        viewer_path = db.get_setting("external_viewer") or ""
        viewer_name = os.path.splitext(os.path.basename(viewer_path))[0] if viewer_path else ""
        label = f"{viewer_name}で開く" if viewer_name else "既定のビュアーで開く"
        self._add_action(label, self._has_path, self._on_open_viewer)

        # ストアページを開く
        self._add_action("ストアページを開く", self._has_store, self._on_open_store)

        # エクスプローラーで表示
        self._add_action("エクスプローラーで表示", self._has_path, self._on_open_explorer)

        self.addSeparator()

        # サークル名をコピー
        text_circle = f"サークル名をコピー  ({self._circle})" if self._circle else "サークル名をコピー"
        self._add_action(text_circle, bool(self._circle), self._on_copy_circle)

        # サークルに移動
        self._add_action("サークルに移動", bool(self._circle), self._on_goto_circle)

        # 作品名をコピー
        text_title = f"作品名をコピー  ({self._title})" if self._title else "作品名をコピー"
        self._add_action(text_title, bool(self._title), self._on_copy_title)

        self.addSeparator()

        # 新しい作品を追加
        self._add_action("新しい作品を追加", True, self._on_add_new_book)

        # 最新の情報に更新 — ショートカット設定時は右に表示
        self._add_action_with_shortcut("最新の情報に更新", "file_rescan", True, self._on_rescan)

        # ライブラリの場所を表示 — ショートカット設定時は右に表示
        self._add_action_with_shortcut("ライブラリの場所を表示", "file_open_library", True, self._on_open_library_folder)

        # 設定
        self._add_action("設定", True, self._on_open_settings)

        self.addSeparator()

        # お気に入りに追加/編集
        self._add_action("お気に入りに追加/編集", self._has_path, self._on_bookmark)

        # 名前を変更
        self._add_action("名前を変更", self._has_path, self._on_rename)

        # メタデータの取得（プラグインが1つ以上あるときのみ表示）
        try:
            from plugin_loader import has_enabled_plugins
            if has_enabled_plugins():
                self._add_action("メタデータの取得", self._has_path, self._on_fetch_metadata)
        except Exception:
            pass

        # プロパティ
        self._add_action("プロパティ", self._has_path, self._on_properties)

        self.addSeparator()

        # ファイルを削除
        act_del = QWidgetAction(self)
        act_del.setEnabled(self._has_path)
        act_del.triggered.connect(self._on_delete)
        row_del = QWidget()
        lay_del = QHBoxLayout(row_del)
        lay_del.setContentsMargins(*config.BOOK_CONTEXT_MENU_ROW_MARGINS)
        lay_del.setSpacing(config.LAYOUT_SPACING_ZERO)
        lbl_del = QLabel("ファイルを削除")
        if self._has_path:
            row_del.setStyleSheet(
                f"""
                QWidget {{
                    background: transparent;
                }}
                QWidget:hover {{
                    background-color: {THEME_COLORS['hover']};
                    border-radius: {config.BOOK_CONTEXT_MENU_ITEM_RADIUS}px;
                }}
            """
            )
            lbl_del.setStyleSheet(
                f"""
                color: {THEME_COLORS['delete']};
                background: transparent;
                padding: {config.BOOK_CONTEXT_MENU_ROW_LABEL_PADDING_Y}px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
            """
            )
        else:
            row_del.setStyleSheet("background: transparent;")
            lbl_del.setStyleSheet(
                f"""
                color: {THEME_COLORS['menu_disabled']};
                background: transparent;
                padding: {config.BOOK_CONTEXT_MENU_ROW_LABEL_PADDING_Y}px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
            """
            )
        lay_del.addWidget(lbl_del)
        row_del.setFixedHeight(config.BOOK_CONTEXT_MENU_DELETE_ROW_HEIGHT)
        act_del.setDefaultWidget(row_del)
        self.addAction(act_del)

    # ── メニューアクション実装 ──────────────────────────

    def _on_open(self):
        if not self._has_path or not self._selected_books:
            return
        modal = len(self._selected_books) == 1
        for b in self._selected_books:
            path = b.get("path")
            if not path or not os.path.exists(path):
                continue
            if not open_book(path, self._parent_window, modal=modal):
                break

    def _on_open_viewer(self):
        """外部ビュアーで開く。ストアファイルの場合は DMM/DLSite 専用ビュアーのみ使用し、未設定なら設定ダイアログを促す。"""
        if not self._has_path:
            return
        if _is_store_file(self._path):
            viewer_path, label = _get_store_viewer_path(self._path)
            if not viewer_path:
                _show_viewer_not_set_dialog(self._parent_window, label)
                return
            resolved = resolve_shortcut(viewer_path)
            if not os.path.isfile(resolved):
                _show_viewer_not_set_dialog(self._parent_window, label)
                return
            is_dmm = os.path.splitext(self._path)[1].lower() in STORE_FILE_EXTS_DMM
            if not _is_allowed_store_viewer(resolved, is_dmm):
                allowed = ALLOWED_DMM_VIEWER_NAMES if is_dmm else ALLOWED_DLSITE_VIEWER_NAMES
                _show_wrong_viewer_dialog(self._parent_window, label, allowed)
                return
            try:
                subprocess.Popen([resolved, self._path])
            except Exception as e:
                QMessageBox.warning(self._parent_window, "エラー", f"ビュアーを開けませんでした:\n{e}")
            return
        folder = self._path if os.path.isdir(self._path) else os.path.dirname(self._path)
        viewer_path = db.get_setting("external_viewer") or ""
        try:
            resolved_viewer = resolve_shortcut(viewer_path) if viewer_path else ""
            if resolved_viewer and os.path.isfile(resolved_viewer):
                subprocess.Popen([resolved_viewer, folder])
            else:
                exts = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
                images = sorted([f for f in os.listdir(folder) if f.lower().endswith(exts)])
                if images:
                    os.startfile(os.path.join(folder, images[0]))
                else:
                    os.startfile(folder)
        except Exception as e:
            QMessageBox.warning(self._parent_window, "エラー", f"ビュアーを開けませんでした:\n{e}")

    def _on_open_explorer(self):
        folder = self._path if os.path.isdir(self._path) else os.path.dirname(self._path)
        try:
            if os.name == "nt":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            QMessageBox.warning(self._parent_window, "エラー", f"フォルダを開けませんでした:\n{e}")

    def _on_open_store(self):
        """作品のストアページをブラウザで開く（DLsite / FANZA / とら / URL直指定対応）"""
        dlsite_id = (self._book.get("dlsite_id") or "").strip()
        store_url = ""
        if not dlsite_id and self._path:
            try:
                meta = db.get_book_meta(self._path) or {}
                dlsite_id = (meta.get("dlsite_id") or "").strip()
            except Exception:
                dlsite_id = ""

        if self._path:
            try:
                meta = db.get_book_meta(self._path) or {}
                store_url = (meta.get("store_url") or "").strip()
            except Exception:
                store_url = ""

        if store_url:
            QDesktopServices.openUrl(QUrl(store_url))
            return

        if not dlsite_id:
            QMessageBox.warning(self._parent_window, "作品IDなし", "作品IDが設定されていません。")
            return

        # IDの種類に応じてURLを構築
        if dlsite_id.startswith("http"):
            # URL直接登録（DojinDB等）
            url = dlsite_id
        elif dlsite_id.upper().startswith(("RJ", "BJ", "VJ")):
            # DLsite
            url = f"https://www.dlsite.com/maniax/work/=/product_id/{dlsite_id}.html"
        elif dlsite_id.upper().startswith("D_") or re.match(r"^b[0-9a-z]+$", dlsite_id, re.IGNORECASE):
            # FANZA（D_xxxxx 形式 または bxxxxxxxx 形式）
            url = f"https://book.dmm.co.jp/search/?searchstr={dlsite_id}"
        elif dlsite_id.startswith("042"):
            # とらのあな
            url = f"https://ec.toranoana.jp/tora_rd/digi/item/{dlsite_id}/"
        else:
            # 不明なIDはDLsiteにフォールバック
            url = f"https://www.dlsite.com/maniax/work/=/product_id/{dlsite_id}.html"

        QDesktopServices.openUrl(QUrl(url))

    def _on_open_settings(self):
        """設定ダイアログを開く"""
        from settings_dialog import SettingsDialog
        dlg = SettingsDialog(self._parent_window)
        dlg.exec()

    def _on_copy_circle(self):
        self._copy_text(self._circle)

    def _on_copy_title(self):
        self._copy_text(self._title)

    def _on_goto_circle(self):
        cb = self._callbacks.get("filter_by_circle")
        if cb and self._circle:
            cb(self._circle)

    def _on_add_new_book(self):
        cb_get_folder = self._callbacks.get("get_library_folder")
        library_folder = cb_get_folder() if cb_get_folder else None
        if not library_folder or not os.path.isdir(library_folder):
            QMessageBox.warning(self._parent_window, "未設定", "先にライブラリフォルダを設定してください。")
            return

        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        paths, _ = QFileDialog.getOpenFileNames(
            self._parent_window,
            "追加するファイルを選択",
            downloads,
            "対応ファイル (*.zip *.cbz *.7z *.cb7 *.rar *.cbr *.pdf *.dlst *.dmme)",
        )
        if not paths:
            return

        from drop_handler import handle_drop

        cb_rescan = self._callbacks.get("rescan")
        handle_drop(paths, library_folder, self._parent_window, on_done=(cb_rescan or (lambda: None)))

    def _on_rescan(self):
        cb = self._callbacks.get("rescan")
        if cb:
            cb()

    def _on_open_library_folder(self):
        cb_get_folder = self._callbacks.get("get_library_folder")
        folder = cb_get_folder() if cb_get_folder else None
        if folder and os.path.isdir(folder):
            os.startfile(folder)

    def _on_bookmark(self):
        from context_menu.actions_bookmark import edit_bookmark
        edit_bookmark(self._book, self._parent_window)

    def _on_rename(self):
        if not self._has_path:
            return
        dlg = RenameDialog(self._book, self._parent_window, self._callbacks.get("rescan"))
        dlg.exec()

    def _on_properties(self):
        if not self._has_path:
            return

        def _on_saved_wrapper(path: str | None = None):
            on_updated = getattr(self._parent_window, "on_book_updated", None)
            if callable(on_updated):
                on_updated(path)

        books_arg = self._selected_books if (self._selected_books and len(self._selected_books) > 1) else self._book
        dlg = PropertyDialog(books_arg, self._parent_window, on_saved=_on_saved_wrapper)
        dlg.exec()

    def _on_fetch_metadata(self):
        from context_menu.actions_meta import fetch_metadata
        fetch_metadata(self._book, self._parent_window)

    def _on_delete(self):
        from context_menu.actions_file import delete_book
        delete_book(self._book, self._parent_window, self._callbacks.get("rescan"))

    @staticmethod
    def _copy_text(text: str):
        if not text:
            return
        import unicodedata

        QApplication.clipboard().setText(unicodedata.normalize("NFKC", text))

