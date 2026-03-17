"""
paths.py - アプリのファイルパスを一元管理

- APP_BASE     : アセット・アイコン等（実行ファイルと同じフォルダ）
- APP_DATA_DIR : ユーザーデータ（DB・キャッシュ・バックアップ）
- PLUGINS_DIR  : ユーザープラグイン（%APPDATA%\\NobleShelf\\plugins）
"""
import os
import sys

# アセット用ベース（exe と同じフォルダ）
_app_base = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    _app_base = os.path.dirname(sys.executable)
APP_BASE = _app_base

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
os.makedirs(PLUGINS_DIR, exist_ok=True)

"""
paths.py - アプリのファイルパスを一元管理

- APP_BASE     : アセット・アイコン等（実行ファイルと同じフォルダ）
- APP_DATA_DIR : ユーザーデータ（DB・キャッシュ・バックアップ）
- PLUGINS_DIR  : ユーザープラグイン（%APPDATA%\\NobleShelf\\plugins）
"""
import os
import sys

# アセット用ベース（exe と同じフォルダ）
_app_base = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    _app_base = os.path.dirname(sys.executable)
APP_BASE = _app_base

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
os.makedirs(PLUGINS_DIR, exist_ok=True)

"""
paths.py - アプリのファイルパスを一元管理

- APP_BASE  : アセット・アイコン等（実行ファイルと同じフォルダ）
- APP_DATA_DIR : ユーザーデータ（DB・キャッシュ・バックアップ）
"""
import os
import sys

# アセット用ベース（exe と同じフォルダ）
_app_base = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    _app_base = os.path.dirname(sys.executable)
APP_BASE = _app_base

# ユーザーデータ用ベース（%APPDATA%\NobleShelf）
APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", APP_BASE), "NobleShelf")
os.makedirs(APP_DATA_DIR, exist_ok=True)

# DB・バックアップ
DB_FILE    = os.path.join(APP_DATA_DIR, "library.db")
BACKUP_DIR = os.path.join(APP_DATA_DIR, "backups")

# キャッシュ
CACHE_DIR       = os.path.join(APP_DATA_DIR, "thumb_cache")
COVER_CACHE_DIR = os.path.join(APP_DATA_DIR, "cover_cache")

# プラグイン
PLUGINS_DIR = os.path.join(APP_DATA_DIR, "plugins")
PLUGINS_SCAN_DIR = os.path.join(PLUGINS_DIR, "get_api")
os.makedirs(PLUGINS_DIR, exist_ok=True)

# プラグインの依存モジュールをどの実行環境からでもimportできるよう sys.path に追加
for _plugin_path in (PLUGINS_SCAN_DIR, PLUGINS_DIR):
    if _plugin_path and os.path.isdir(_plugin_path) and _plugin_path not in sys.path:
        sys.path.insert(0, _plugin_path)

