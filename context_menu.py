"""
context_menu.py - グリッド用右クリックコンテキストメニュー（PySide6版）

BookContextMenu(QMenu) を中心に、名前変更・削除ダイアログを提供する。
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable, Any

from PySide6.QtWidgets import (
    QMenu,
    QApplication,
    QMessageBox,
    QFileDialog,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QWidget,
    QPushButton,
    QWidgetAction,
)
from PySide6.QtGui import QAction, QDesktopServices, QFont
from PySide6.QtCore import QUrl

import db
import config
from theme import THEME_COLORS, apply_dark_titlebar
from properties import PropertyDialog, RenameDialog, MetaSearchDialog


def _get_shortcut_for_display(key: str) -> str:
    """設定のショートカット文字列を返す（コンテキストメニュー表示用）。menubar と同様の取得だが import 循環を避けるためここで定義。"""
    val = db.get_setting(f"shortcut_{key}")
    if val is not None:
        return (val or "").strip()
    return (config.DEFAULT_SHORTCUTS.get(key) or "").strip()

# DMM/DLSite ストアファイルは独自ビュアーのみで開く（内置ビュアー・外部ビュアーは使わない）
STORE_FILE_EXTS_DMM = (".dmmb", ".dmme", ".dmmr")
STORE_FILE_EXT_DLSITE = ".dlst"

# ストアファイル起動に許可する実行ファイル名（大文字小文字無視）
ALLOWED_DMM_VIEWER_NAMES = ("DMMBooks.exe", "DMMbookviewer.exe")
ALLOWED_DLSITE_VIEWER_NAMES = ("DLSitePlay.exe", "DLsiteViewer.exe")


def resolve_shortcut(path: str) -> str:
    """
    パスが Windows のショートカット(.lnk) の場合、リンク先の実体パスを返す。
    それ以外はそのまま返す。解決に失敗した場合は元の path を返す。
    """
    if not path or not os.path.isfile(path):
        return path or ""
    if sys.platform != "win32" or os.path.splitext(path)[1].lower() != ".lnk":
        return path
    try:
        # PowerShell で .lnk の TargetPath を取得（追加ライブラリ不要）
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "$p = $env:SHORTCUT_PATH; (New-Object -ComObject WScript.Shell).CreateShortcut($p).TargetPath",
        ]
        env = os.environ.copy()
        env["SHORTCUT_PATH"] = os.path.abspath(path)
        r = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if r.returncode == 0 and r.stdout:
            resolved = r.stdout.strip().strip('"')
            if resolved and os.path.exists(resolved):
                return resolved
    except Exception:
        pass
    return path


def _is_store_file(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    ext = os.path.splitext(path)[1].lower()
    return ext in STORE_FILE_EXTS_DMM or ext == STORE_FILE_EXT_DLSITE


def _get_store_viewer_path(path: str) -> tuple[str, str]:
    """ストアファイル用ビュアーパスと未設定時のラベルを返す。(path, label) 未設定時は ("", "DMMビュアー") など。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in STORE_FILE_EXTS_DMM:
        return (db.get_setting("dmm_viewer") or "").strip(), "DMMビュアー"
    if ext == STORE_FILE_EXT_DLSITE:
        return (db.get_setting("dlsite_viewer") or "").strip(), "DLSiteビュアー"
    return "", ""


def _is_allowed_store_viewer(resolved_exe_path: str, for_dmm: bool) -> bool:
    """ストア用に許可されたビュアー（DMMbookviewer.exe / DLsiteViewer.exe 等）かどうか。"""
    if not resolved_exe_path or not os.path.isfile(resolved_exe_path):
        return False
    name = os.path.basename(resolved_exe_path)
    allowed = (
        ALLOWED_DMM_VIEWER_NAMES if for_dmm else ALLOWED_DLSITE_VIEWER_NAMES
    )
    return name.lower() in (a.lower() for a in allowed)


def is_valid_store_viewer_path(path: str, for_dmm: bool) -> bool:
    """
    設定用: パスが空、または実在し且つストア用に許可された exe（.lnk の場合はリンク先）なら True。
    設定ダイアログの保存時チェックに使用。
    """
    p = (path or "").strip()
    if not p:
        return True
    if not os.path.isfile(p):
        return False
    resolved = resolve_shortcut(p)
    if not resolved or not os.path.isfile(resolved):
        return False
    if os.path.splitext(p)[1].lower() == ".lnk" and resolved == p:
        return False
    return _is_allowed_store_viewer(resolved, for_dmm)


def _show_viewer_not_set_dialog(parent, label: str):
    """ビュアー未設定時に「設定でパスを指定してください」と設定を開くオプションを表示する。"""
    msg = QMessageBox(parent)
    msg.setWindowTitle(config.APP_TITLE)
    msg.setIcon(QMessageBox.Warning)
    msg.setText(f"{label}が未設定です。")
    msg.setInformativeText("設定でパスを指定してください。")
    btn_settings = msg.addButton("設定を開く", QMessageBox.AcceptRole)
    msg.addButton(QMessageBox.Close)
    msg.exec()
    if msg.clickedButton() == btn_settings:
        from settings_dialog import SettingsDialog
        dlg = SettingsDialog(parent)
        dlg.exec()


def _show_wrong_viewer_dialog(parent, label: str, allowed_names: tuple[str, ...]):
    """ストア用以外のビュアーが指定されているときに、許可 exe 名を案内して設定を開けるようにする。"""
    msg = QMessageBox(parent)
    msg.setWindowTitle(config.APP_TITLE)
    msg.setIcon(QMessageBox.Warning)
    msg.setText(f"{label}には、以下のいずれかを指定してください。")
    msg.setInformativeText("許可: " + " / ".join(allowed_names))
    btn_settings = msg.addButton("設定を開く", QMessageBox.AcceptRole)
    msg.addButton(QMessageBox.Close)
    msg.exec()
    if msg.clickedButton() == btn_settings:
        from settings_dialog import SettingsDialog
        dlg = SettingsDialog(parent)
        dlg.exec()


def open_book(path: str, parent_window, modal: bool = True) -> bool:
    """
    作品を開く。ストアファイル(.dmmb/.dmme/.dmmr/.dlst)は専用ビュアーのみで開き、
    未設定の場合は「設定してください」ダイアログを表示する。それ以外は内置ビュアーで開く。
    modal: True のとき Viewer は exec()、False のとき show()。
    戻り値: 開いた or 通常の開くを実行したなら True、ビュアー未設定でダイアログ表示したなら False。
    """
    if not path or not os.path.exists(path):
        return True
    if _is_store_file(path):
        viewer_path, label = _get_store_viewer_path(path)
        if not viewer_path:
            _show_viewer_not_set_dialog(parent_window, label)
            return False
        resolved = resolve_shortcut(viewer_path)
        if not os.path.isfile(resolved):
            _show_viewer_not_set_dialog(parent_window, label)
            return False
        is_dmm = os.path.splitext(path)[1].lower() in STORE_FILE_EXTS_DMM
        if not _is_allowed_store_viewer(resolved, is_dmm):
            allowed = ALLOWED_DMM_VIEWER_NAMES if is_dmm else ALLOWED_DLSITE_VIEWER_NAMES
            _show_wrong_viewer_dialog(parent_window, label, allowed)
            return False
        try:
            subprocess.Popen([resolved, path])
        except Exception as e:
            QMessageBox.warning(parent_window, "エラー", f"ビュアーを開けませんでした:\n{e}")
            return False
        name = db.get_book_name_by_path(path) or os.path.basename(path) or path
        db.add_recent_book(name, path)
        return True
    from viewer import Viewer
    v = Viewer(parent_window, path)
    if modal:
        v.exec()
    else:
        v.show()
    name = db.get_book_name_by_path(path) or os.path.basename(path) or path
    db.add_recent_book(name, path)
    return True


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
            self._has_path = any(
                b.get("path") and os.path.exists(b.get("path", ""))
                for b in self._selected_books
            )

        # dlsite_idの有無（ストアページ開くの有効/無効判定用）
        try:
            meta = db.get_book_meta(self._path) if self._path else None
            self._has_store = bool(meta and meta.get("dlsite_id"))
        except Exception:
            self._has_store = False

        self._setup_style()
        self._build_menu()
        self.setMinimumWidth(260)

    def _setup_style(self):
        self.setStyleSheet(
            f"""
            QMenu {{
                background-color: {THEME_COLORS["bg_panel"]};
                color: {THEME_COLORS["text_main"]};
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 0;
                font-family: "{config.DROPDOWN_FONT_FAMILY}";
                font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 16px;
                border-radius: 3px;
            }}
            QMenu::item:selected {{
                background-color: {THEME_COLORS["hover"]};
            }}
            QMenu::item:disabled {{
                color: {THEME_COLORS["menu_disabled"]};
            }}
            QMenu::separator {{
                height: 1px;
                background: #444;
                margin: 3px 8px;
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
        lay.setContentsMargins(12, 0, 16, 0)
        lay.setSpacing(24)

        lbl_text = QLabel(text)
        lbl_shortcut = QLabel(shortcut_str)

        if enabled:
            row.setStyleSheet(f"""
                QWidget {{
                    background: transparent;
                    padding: 0;
                }}
                QWidget:hover {{
                    background-color: {THEME_COLORS['hover']};
                    border-radius: 3px;
                }}
            """)
            lbl_text.setStyleSheet(f"""
                color: {THEME_COLORS['text_main']};
                background: transparent;
                padding: 6px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
            """)
            lbl_shortcut.setStyleSheet(f"""
                color: {THEME_COLORS['context_menu_shortcut']};
                background: transparent;
                padding: 6px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU_SHORTCUT}px;
            """)
        else:
            row.setStyleSheet("background: transparent;")
            lbl_text.setStyleSheet(f"""
                color: {THEME_COLORS['menu_disabled']};
                background: transparent;
                padding: 6px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
            """)
            lbl_shortcut.setStyleSheet(f"""
                color: {THEME_COLORS['menu_disabled']};
                background: transparent;
                padding: 6px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU_SHORTCUT}px;
            """)

        lay.addWidget(lbl_text)
        lay.addStretch()
        lay.addWidget(lbl_shortcut)

        wa.setDefaultWidget(row)
        self.addAction(wa)
        return wa

    def _add_stub_action(self, text: str) -> QAction:
        # 仕様上は緑色表現だが、シンプルに "(準備中)" を付けたスタブにする
        act = QAction(f"{text}  (準備中)", self)
        act.setEnabled(True)
        act.triggered.connect(lambda: None)
        self.addAction(act)
        return act

    def _build_menu(self):
        # 開く（複数選択時は件数表示）— ショートカット設定時は右に表示
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
        self._add_action("お気に入りに追加/編集", self._has_path, self._on_edit_bookmark)

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
        lay_del.setContentsMargins(12, 0, 16, 0)
        lay_del.setSpacing(0)
        lbl_del = QLabel("ファイルを削除")
        if self._has_path:
            row_del.setStyleSheet(f"""
                QWidget {{
                    background: transparent;
                }}
                QWidget:hover {{
                    background-color: {THEME_COLORS['hover']};
                    border-radius: 3px;
                }}
            """)
            lbl_del.setStyleSheet(f"""
                color: {THEME_COLORS['delete']};
                background: transparent;
                padding: 6px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
            """)
        else:
            row_del.setStyleSheet("background: transparent;")
            lbl_del.setStyleSheet(f"""
                color: {THEME_COLORS['menu_disabled']};
                background: transparent;
                padding: 6px 0;
                font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
            """)
        lay_del.addWidget(lbl_del)
        row_del.setFixedHeight(32)
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
                images = sorted(
                    [f for f in os.listdir(folder) if f.lower().endswith(exts)]
                )
                if images:
                    os.startfile(os.path.join(folder, images[0]))
                else:
                    os.startfile(folder)
        except Exception as e:
            QMessageBox.warning(
                self._parent_window,
                "エラー",
                f"ビュアーを開けませんでした:\n{e}",
            )

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
            QMessageBox.warning(
                self._parent_window,
                "エラー",
                f"フォルダを開けませんでした:\n{e}",
            )

    def _on_open_store(self):
        """作品のストアページをブラウザで開く（DLsite / FANZA / とら / URL直指定対応）"""
        dlsite_id = (self._book.get("dlsite_id") or "").strip()
        if not dlsite_id and self._path:
            try:
                meta = db.get_book_meta(self._path) or {}
                dlsite_id = (meta.get("dlsite_id") or "").strip()
            except Exception:
                dlsite_id = ""

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
        elif dlsite_id.upper().startswith("D_"):
            # FANZA
            url = f"https://www.dmm.co.jp/dc/doujin/-/detail/=/cid={dlsite_id}/"
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

    def _on_edit_bookmark(self):
        """お気に入り編集ダイアログ"""
        if not self._path:
            return

        from theme import apply_dark_titlebar
        from functools import partial

        dlg = QDialog(self._parent_window)
        dlg.setWindowTitle(config.APP_TITLE)
        dlg.setModal(True)
        dlg.setFixedSize(260, 140)
        apply_dark_titlebar(dlg)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # タイトル
        lbl = QLabel(self._title or self._name)
        from PySide6.QtGui import QFont
        font = lbl.font()
        font.setBold(True)
        lbl.setFont(font)
        layout.addWidget(lbl)

        # 星ボタン行
        try:
            bookmarks = db.get_all_bookmarks()
            current = bookmarks.get(self._path, 0)
        except Exception:
            current = 0

        star_buttons: list[QPushButton] = []

        star_row = QHBoxLayout()
        star_row.setSpacing(6)
        star_row.addStretch()

        def _update_stars(rating: int):
            for i, btn in enumerate(star_buttons, start=1):
                btn.setText("★")
                btn.setStyleSheet(
                    f"color: #f5c518; background: transparent; border: none; font-size: {config.FONT_SIZE_BTN_STAR}px;"
                    if i <= rating
                    else f"color: #555555; background: transparent; border: none; font-size: {config.FONT_SIZE_BTN_STAR}px;"
                )

        def _set_rating(rating: int):
            nonlocal current
            current = rating
            _update_stars(current)

        for i in range(1, 6):
            btn = QPushButton("★")
            btn.setFixedSize(32, 32)
            btn.setFlat(True)
            btn.clicked.connect(partial(_set_rating, i))
            star_buttons.append(btn)
            star_row.addWidget(btn)

        star_row.addStretch()
        layout.addLayout(star_row)
        _update_stars(current)

        # ボタン行：保存・削除・キャンセル
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_save = QPushButton("保存")
        btn_save.setFixedWidth(72)
        btn_save.setStyleSheet(
            "background-color: #2d7a2d; color: #ffffff; border: none; border-radius: 4px; padding: 4px 8px;"
        )

        btn_delete = QPushButton("削除")
        btn_delete.setFixedWidth(72)
        btn_delete.setStyleSheet(
            f"background-color: {THEME_COLORS['delete']}; color: #ffffff; border: none; border-radius: 4px; padding: 4px 8px;"
        )

        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setFixedWidth(80)

        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_delete)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        def _apply_and_close():
            try:
                db.set_bookmark(self._path, current)
            except Exception:
                pass
            on_updated = getattr(self._parent_window, "on_book_updated", None)
            if callable(on_updated):
                on_updated(self._path)
            dlg.accept()

        def _delete_and_close():
            try:
                db.set_bookmark(self._path, 0)
            except Exception:
                pass
            on_updated = getattr(self._parent_window, "on_book_updated", None)
            if callable(on_updated):
                on_updated(self._path)
            dlg.accept()

        btn_save.clicked.connect(_apply_and_close)
        btn_delete.clicked.connect(_delete_and_close)
        btn_cancel.clicked.connect(dlg.reject)

        dlg.exec()

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
        """メタデータ取得 → MetaSearchDialog で検索し、適用時は MetaApplyDialog で取捨選択してDB保存"""
        if not self._has_path:
            return
        dlg = MetaSearchDialog(self._parent_window)
        if self._title:
            dlg._e_search.setText(self._title)
        try:
            cur_meta = db.get_book_meta(self._path) or {}
        except Exception:
            cur_meta = {}
        dlg._current_book = self._book
        dlg._current_meta = cur_meta
        if dlg.exec() != QDialog.Accepted:
            return
        on_updated = getattr(self._parent_window, "on_book_updated", None)
        if callable(on_updated):
            on_updated(self._path)

    def _on_delete(self):
        if not self._has_path:
            return
        dlg = DeleteConfirmDialog(self._book, self._parent_window, self._callbacks.get("rescan"))
        dlg.exec()

    @staticmethod
    def _copy_text(text: str):
        if not text:
            return
        import unicodedata

        QApplication.clipboard().setText(unicodedata.normalize("NFKC", text))


class DeleteConfirmDialog(QDialog):
    def __init__(self, book: dict, parent, on_done: Callable[[], None] | None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self._book = book
        self._on_done = on_done
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle(config.APP_TITLE)
        self.setMinimumSize(400, 0)
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {THEME_COLORS["bg_panel"]};
                color: {THEME_COLORS["text_main"]};
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        name = self._book.get("name", "")
        lbl = QLabel(
            f"「{name}」を完全に削除しますか？\n\n"
            "ライブラリから削除するだけでなく、元のファイル（またはフォルダ）もディスクから削除されます。\n"
            "この操作は元に戻せません。"
        )
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(360)
        lbl.setMinimumHeight(80)
        layout.addWidget(lbl)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("削除")
        btn_cancel = QPushButton("キャンセル")
        btn_ok.setStyleSheet(
            f"QPushButton {{ background-color: {THEME_COLORS['delete']}; color: #ffffff; }}"
        )
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._apply)

    def _apply(self):
        import shutil

        path = self._book.get("path", "")
        if not path:
            return
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
                # Windows 等で rmtree 後に空フォルダが残ることがあるため、フォルダごと確実に削除
                if os.path.exists(path) and os.path.isdir(path):
                    try:
                        os.rmdir(path)
                    except Exception:
                        pass
            else:
                os.remove(path)
                # その本が入っていた親フォルダがライブラリ直下で空なら削除する
                parent_dir = os.path.dirname(path)
                lib_folder = (db.get_setting("library_folder") or "").strip()
                if (
                    parent_dir
                    and lib_folder
                    and os.path.isdir(parent_dir)
                    and os.path.normpath(parent_dir).startswith(os.path.normpath(lib_folder))
                    and not os.listdir(parent_dir)
                ):
                    shutil.rmtree(parent_dir)
            db.delete_book(path)
            if self._on_done:
                self._on_done()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "削除エラー", str(e))

