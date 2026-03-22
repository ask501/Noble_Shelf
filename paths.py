"""
paths.py - アプリのファイルパスを一元管理

- APP_BASE     : アセット・アイコン等（開発時はソース直下、PyInstaller frozen 時は exe 隣の _internal）
- APP_DATA_DIR : ユーザーデータ（DB・キャッシュ・バックアップ）
- PLUGINS_DIR  : ユーザープラグイン（%APPDATA%\\NobleShelf\\plugins）
"""
import os
import sys

# アセット用ベース（開発時はソースツリー、frozen 時は PyInstaller --onedir の _internal）
_app_base = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    _app_base = os.path.join(os.path.dirname(sys.executable), "_internal")
APP_BASE = _app_base

# ── UIアイコン（ツールバー・バッジ等） ─────────────────
ICON_DMM_BADGE = os.path.join(APP_BASE, "assets", "dmm_badge.png")
ICON_DLSITE_BADGE = os.path.join(APP_BASE, "assets", "dlsite_badge.png")
ICON_HAMBURGER = os.path.join(APP_BASE, "assets", "hamburger-button.png")
ICON_FILTER = os.path.join(APP_BASE, "assets", "filter.png")
ICON_SIDEBAR = os.path.join(APP_BASE, "assets", "sidebar.png")
ICON_RANDOM = os.path.join(APP_BASE, "assets", "random.png")
ICON_SEARCH = os.path.join(APP_BASE, "assets", "search.png")
ICON_AUTO_SCROLL = os.path.join(APP_BASE, "assets", "auto_scroll.png")
# toolbar.py: ブックマークレット用アイコン（現状はツールバー表示のみ・クリック処理は未接続）
ICON_TOOLBAR_TITLE = os.path.join(APP_BASE, "assets", "title.png")
ICON_TOOLBAR_BOOKMARKLET = os.path.join(APP_BASE, "assets", "bookmarklet.png")
# toolbar.py: 設定（歯車）アイコン（表示のみ・処理未接続）
ICON_TOOLBAR_SETTINGS = os.path.join(APP_BASE, "assets", "toolbar_settings.png")

# ── アプリアイコン（ウィンドウ・exe） ──────────────────
APP_ICON = os.path.join(APP_BASE, "assets", "icon.png")
APP_ICON_ICO = os.path.join(APP_BASE, "assets", "desktop_icon.ico")
# ui/bookmarklet_help_dialog.py: ブックマークレットコピー手順のスクリーンショット
BOOKMARKLET_HELP_COPY_SCREENSHOT = os.path.join(APP_BASE, "assets", "bookmarklet_help_copy.png")
# ui/bookmarklet_help_dialog.py: ブラウザにブックマーク登録する手順のスクリーンショット
BOOKMARKLET_HELP_BROWSER_SCREENSHOT = os.path.join(APP_BASE, "assets", "bookmarklet_help_browser.png")

# ユーザーデータ用ベース（%APPDATA%\NobleShelf）
APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", APP_BASE), "NobleShelf")
os.makedirs(APP_DATA_DIR, exist_ok=True)

# DB・バックアップ
DB_FILE    = os.path.join(APP_DATA_DIR, "library.db")
BACKUP_DIR = os.path.join(APP_DATA_DIR, "backups")

# キャッシュ
CACHE_DIR       = os.path.join(APP_DATA_DIR, "thumb_cache")
COVER_CACHE_DIR = os.path.join(APP_DATA_DIR, "cover_cache")

# プラグイン（サブフォルダ構成はplugin_loaderが管理）
PLUGINS_DIR = os.path.join(APP_DATA_DIR, "plugins")
PLUGINS_SCAN_DIR = os.path.join(PLUGINS_DIR, "get_api")
os.makedirs(PLUGINS_DIR, exist_ok=True)

# プラグインの依存モジュールをどの実行環境からでもimportできるよう sys.path に追加
for _plugin_path in (PLUGINS_SCAN_DIR, PLUGINS_DIR):
    if _plugin_path and os.path.isdir(_plugin_path) and _plugin_path not in sys.path:
        sys.path.insert(0, _plugin_path)
