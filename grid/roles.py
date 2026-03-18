"""
grid/roles.py - グリッド用カスタムロール
"""

from __future__ import annotations

# Qt.UserRole (= 0x0100) を基準に固定値で定義（他ファイルへの依存なし）
_USER_ROLE = 0x0100

ROLE_COVER = _USER_ROLE + 1
ROLE_TITLE = _USER_ROLE + 2
ROLE_CIRCLE = _USER_ROLE + 3
ROLE_PAGES = _USER_ROLE + 4
ROLE_PATH = _USER_ROLE + 5
ROLE_THUMB = _USER_ROLE + 6
ROLE_RATING = _USER_ROLE + 7
ROLE_META_ST = _USER_ROLE + 8  # 0=未取得 1=取得済 2=手動

