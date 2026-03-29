"""
cover_paths.py - DBに保存された cover 値を絶対パスに解決するユーティリティ
"""
from __future__ import annotations

import os

import db


def resolve_cover_path(stored: str) -> str:
    """
    DBに保存された cover 値を絶対パスに解決する。

    優先順位:
    1. 空 → ""
    2. 絶対パス → そのまま返す
    3. 区切りを含む相対パス → db._from_db_path
    4. その他 → db.resolve_cover_stored_value
    """
    p = (stored or "").strip()
    if not p:
        return ""

    if os.path.isabs(p):
        return p

    if "/" in p or "\\" in p:
        try:
            return db._from_db_path(p)
        except ValueError:
            pass

    return db.resolve_cover_stored_value(p)


def resolve_cover_path_fast(stored: str, library_folder: str) -> str:
    """
    I/Oゼロ版。ロード時の全件解決用。
    library_folder は呼び出し元で1回だけ取得して渡す。
    DBアクセスなし・ファイル存在確認なし。
    """
    p = (stored or "").strip()
    if not p:
        return ""
    if os.path.isabs(p):
        return p
    if ("/" in p or "\\" in p) and library_folder:
        return os.path.normpath(os.path.join(library_folder, p))
    return db.resolve_cover_stored_value(p)
