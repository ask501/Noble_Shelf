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

