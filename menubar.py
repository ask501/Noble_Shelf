"""menubar.py - メニューバーセットアップ"""
import os
import subprocess
import sys
from PySide6.QtGui import QAction, QKeySequence, QFont
from PySide6.QtWidgets import QMenu, QWidgetAction, QLabel
import db
import config
from paths import APP_DATA_DIR
from theme import (
    DANGER_MENU_ITEM_STYLE_NORMAL,
    DANGER_MENU_ITEM_STYLE_HOVER,
)


class _DangerMenuLabel(QLabel):
    """危険項目用ラベル。enter/leave でホバー背景を切り替え。theme のスタイルを参照。"""
    _NORMAL = DANGER_MENU_ITEM_STYLE_NORMAL
    _HOVER = DANGER_MENU_ITEM_STYLE_HOVER

    def enterEvent(self, event):
        self.setStyleSheet(self._HOVER)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self._NORMAL)
        super().leaveEvent(event)


def _open_plugin_folder():
    """APPDATAのプラグインフォルダを開く。"""
    from paths import PLUGINS_DIR
    if sys.platform == "win32":
        os.startfile(PLUGINS_DIR)
    elif sys.platform == "darwin":
        subprocess.run(["open", PLUGINS_DIR], check=False)
    else:
        subprocess.run(["xdg-open", PLUGINS_DIR], check=False)


def _refresh_plugin_menu(plugin_menu: QMenu, window):
    """プラグインメニューを開く直前に、読み込み済みプラグイン一覧をチェック可能項目で再構成する。"""
    plugin_menu.clear()
    try:
        from plugin_loader import get_all_plugins, is_plugin_enabled, set_plugin_enabled
        for plugin in get_all_plugins():
            name = getattr(plugin, "PLUGIN_NAME", "?")
            source_key = getattr(plugin, "PLUGIN_SOURCE_KEY", "")
            act = QAction(name, window)
            act.setCheckable(True)
            act.setChecked(is_plugin_enabled(source_key))
            act.toggled.connect(lambda checked, sk=source_key: set_plugin_enabled(sk, checked))
            plugin_menu.addAction(act)
        plugin_menu.addSeparator()
        act_open = QAction("プラグインフォルダを開く", window)
        act_open.triggered.connect(_open_plugin_folder)
        plugin_menu.addAction(act_open)
    except Exception:
        pass


def _get_shortcut(key: str) -> str:
    """設定のショートカットを返す。未設定なら DEFAULT_SHORTCUTS。空ならショートカットなし。"""
    val = db.get_setting(f"shortcut_{key}")
    if val is not None:
        return (val or "").strip()
    return (config.DEFAULT_SHORTCUTS.get(key) or "").strip()


def _apply_shortcut(action: QAction, key: str):
    seq = _get_shortcut(key)
    if seq:
        action.setShortcut(QKeySequence(seq))
    else:
        action.setShortcut(QKeySequence())


def _add_danger_item(menu: QMenu, action: QAction, window=None):
    """危険項目を他項目と同じ余白・フォントで赤文字表示。enter/leave でホバー背景。window を渡すと _wa_file_quit に保持し refresh_shortcuts で更新できる。"""
    wa = QWidgetAction(menu)
    lbl = _DangerMenuLabel(action.text())
    lbl.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_CONTEXT_MENU))
    lbl.setStyleSheet(_DangerMenuLabel._NORMAL)
    wa.setDefaultWidget(lbl)
    wa.triggered.connect(action.trigger)
    wa.setShortcut(action.shortcut())
    menu.addAction(wa)
    if window is not None:
        window._wa_file_quit = wa


def setup_menubar(window):
    """MainWindowのメニューバーを構築する"""
    menubar = window.menuBar()

    # ── ファイルメニュー ──
    file_menu = menubar.addMenu("ファイル(&F)")
    file_menu.aboutToShow.connect(lambda: getattr(window, "_on_file_menu_about_to_show", lambda: None)())

    # 開く
    window._act_file_open = QAction("開く", window)
    _apply_shortcut(window._act_file_open, "file_open")
    window._act_file_open.triggered.connect(window._file_open_selected)
    file_menu.addAction(window._act_file_open)

    # 最近開いたブック（トリガーでポップアップメニュー表示）
    window._act_file_recent = QAction("最近開いたブック", window)
    _apply_shortcut(window._act_file_recent, "file_recent")
    window._act_file_recent.triggered.connect(window._file_show_recent_popup)
    file_menu.addAction(window._act_file_recent)

    # すべて閉じる
    window._act_file_close_all = QAction("すべて閉じる", window)
    _apply_shortcut(window._act_file_close_all, "file_close_all")
    window._act_file_close_all.triggered.connect(window._file_close_all_viewers)
    file_menu.addAction(window._act_file_close_all)

    # ライブラリを開く
    window._act_file_open_library = QAction("ライブラリを開く", window)
    _apply_shortcut(window._act_file_open_library, "file_open_library")
    window._act_file_open_library.triggered.connect(window._file_open_library_folder)
    file_menu.addAction(window._act_file_open_library)

    file_menu.addSeparator()

    # コピー
    window._act_file_copy = QAction("コピー", window)
    _apply_shortcut(window._act_file_copy, "file_copy")
    window._act_file_copy.triggered.connect(window._file_copy_selected)
    file_menu.addAction(window._act_file_copy)

    # 貼り付け
    window._act_file_paste = QAction("貼り付け", window)
    _apply_shortcut(window._act_file_paste, "file_paste")
    window._act_file_paste.triggered.connect(window._file_paste)
    file_menu.addAction(window._act_file_paste)

    # 印刷
    window._act_file_print = QAction("印刷", window)
    _apply_shortcut(window._act_file_print, "file_print")
    window._act_file_print.triggered.connect(window._file_print_selected)
    file_menu.addAction(window._act_file_print)

    file_menu.addSeparator()

    # ライブラリの再スキャン
    window._act_file_rescan = QAction("ライブラリの再スキャン", window)
    _apply_shortcut(window._act_file_rescan, "file_rescan")
    window._act_file_rescan.triggered.connect(window._rescan_library)
    file_menu.addAction(window._act_file_rescan)

    # キャッシュをリセット
    window._act_file_reset_cache = QAction("キャッシュをリセット", window)
    window._act_file_reset_cache.triggered.connect(window._clear_caches)
    file_menu.addAction(window._act_file_reset_cache)

    # バックアップを復元
    window._act_file_restore_backup = QAction("バックアップを復元", window)
    window._act_file_restore_backup.triggered.connect(window._on_restore_backup)
    file_menu.addAction(window._act_file_restore_backup)

    # ライブラリフォルダを設定
    window._act_file_set_library = QAction("ライブラリフォルダを設定", window)
    window._act_file_set_library.triggered.connect(window._select_library_folder)
    file_menu.addAction(window._act_file_set_library)

    file_menu.addSeparator()

    # 終了（危険項目・赤文字・確認ダイアログ）
    window._act_file_quit = QAction("終了", window)
    window._act_file_quit.setObjectName("menu_danger")
    _apply_shortcut(window._act_file_quit, "file_quit")
    window._act_file_quit.triggered.connect(window._file_quit_with_confirm)
    _add_danger_item(file_menu, window._act_file_quit, window)

    # 終了ショートカットをウィンドウに追加（メニューを開いていなくても有効）
    window.addAction(window._act_file_quit)

    # ── 表示メニュー ──
    view_menu = menubar.addMenu("表示(&V)")

    window._act_menubar = QAction("メニューバー", window)
    window._act_menubar.setCheckable(True)
    window._act_menubar.triggered.connect(
        lambda checked: window._set_menubar_visible(checked, save=True)
    )
    view_menu.addAction(window._act_menubar)

    window._act_searchbar = QAction("検索バー(&S)", window)
    window._act_searchbar.setShortcut("Ctrl+F")
    window._act_searchbar.setCheckable(True)
    window._act_searchbar.triggered.connect(
        lambda checked: window._set_searchbar_visible(checked, save=True)
    )
    view_menu.addAction(window._act_searchbar)

    window._act_sidebar = QAction("サイドバー", window)
    window._act_sidebar.setCheckable(True)
    window._act_sidebar.triggered.connect(
        lambda checked: window._set_sidebar_visible(checked, save=True)
    )
    view_menu.addAction(window._act_sidebar)

    window._act_infobar = QAction("情報バー", window)
    window._act_infobar.setCheckable(True)
    window._act_infobar.triggered.connect(
        lambda checked: window._set_infobar_visible(checked, save=True)
    )
    view_menu.addAction(window._act_infobar)

    view_menu.addSeparator()
    window._act_filter_dlsite = QAction("DLSiteのファイルのみ", window)
    window._act_filter_dlsite.setCheckable(True)
    window._act_filter_dlsite.setChecked(getattr(window, "_filter_dlsite_only", False))
    window._act_filter_dlsite.triggered.connect(window._set_filter_dlsite_only)
    view_menu.addAction(window._act_filter_dlsite)

    window._act_filter_fanza = QAction("FANZA/DMMのファイルのみ", window)
    window._act_filter_fanza.setCheckable(True)
    window._act_filter_fanza.setChecked(getattr(window, "_filter_fanza_only", False))
    window._act_filter_fanza.triggered.connect(window._set_filter_fanza_only)
    view_menu.addAction(window._act_filter_fanza)

    view_menu.addSeparator()
    window._act_filter_no_cover = QAction("サムネイル未設定", window)
    window._act_filter_no_cover.setCheckable(True)
    window._act_filter_no_cover.setChecked(getattr(window, "_filter_no_cover_only", False))
    window._act_filter_no_cover.triggered.connect(window._set_filter_no_cover_only)
    view_menu.addAction(window._act_filter_no_cover)

    # ── ツールメニュー（ふりがな・PDF修復）──
    tool_menu = menubar.addMenu("ツール(&L)")
    act_kana = QAction("ふりがな一括取得", window)
    act_kana.triggered.connect(window._bulk_update_kana)
    tool_menu.addAction(act_kana)
    act_repair_pdf = QAction("PDFサムネを修復", window)
    act_repair_pdf.triggered.connect(window._repair_pdf_covers)
    tool_menu.addAction(act_repair_pdf)
    tool_menu.addSeparator()
    act_bookmarklet = QAction("ブックマークレットキュー", window)
    act_bookmarklet.triggered.connect(window._open_bookmarklet_window)
    tool_menu.addAction(act_bookmarklet)
    window._act_tool_library_check = QAction("ライブラリ整合性チェック...", window)
    tool_menu.addAction(window._act_tool_library_check)

    # ── 設定メニュー ──
    setting_menu = menubar.addMenu("設定(&T)")
    act_settings = QAction("設定(&P)", window)
    act_settings.triggered.connect(window._on_open_settings)
    setting_menu.addAction(act_settings)

    # ── プラグインメニュー（メタデータ取得プラグインのON/OFF・フォルダを開く）。ツール・設定の直後に並ぶ ──
    plugin_menu = menubar.addMenu("プラグイン(&G)")
    plugin_menu.aboutToShow.connect(lambda: _refresh_plugin_menu(plugin_menu, window))

    # ── デバッグメニュー（開発時のみ使用） ──
    debug_menu = menubar.addMenu("デバッグ(&D)")

    def _open_first_run_overlay():
        try:
            from debug_tools import show_first_run_overlay
            show_first_run_overlay(window)
        except Exception:
            # デバッグ用途なので、失敗時は何もせず黙って無視
            pass

    act_first_run = QAction("初回起動オーバーレイをテスト", window)
    act_first_run.triggered.connect(_open_first_run_overlay)
    debug_menu.addAction(act_first_run)

    def _open_appdata_folder():
        path = APP_DATA_DIR
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)

    act_open_appdata = QAction("ユーザーデータフォルダを開く", window)
    act_open_appdata.triggered.connect(_open_appdata_folder)
    debug_menu.addAction(act_open_appdata)


# 設定で変更したショートカットをメニューに再反映する（設定ダイアログ保存後に呼ぶ）
SHORTCUT_KEYS = (
    ("file_open", "_act_file_open"),
    ("file_recent", "_act_file_recent"),
    ("file_close_all", "_act_file_close_all"),
    ("file_open_library", "_act_file_open_library"),
    ("file_copy", "_act_file_copy"),
    ("file_paste", "_act_file_paste"),
    ("file_print", "_act_file_print"),
    ("file_rescan", "_act_file_rescan"),
    ("file_quit", "_act_file_quit"),
)


def refresh_shortcuts(window):
    """DB に保存されたショートカットをメニューアクションに再適用する。"""
    for key, attr in SHORTCUT_KEYS:
        action = getattr(window, attr, None)
        if action is not None:
            _apply_shortcut(action, key)
    if getattr(window, "_wa_file_quit", None) is not None:
        window._wa_file_quit.setShortcut(window._act_file_quit.shortcut())
