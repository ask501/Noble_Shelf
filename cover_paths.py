"""
cover_paths.py - DBに保存された cover 値を絶対パスに解決するユーティリティ
"""
from __future__ import annotations

import os

import db


def to_cover_db_path(absolute_or_any: str) -> str:
    """
    カバーパスをDBに保存する形式（相対パス）に変換する。
    - 空文字 → "" を返す
    - ライブラリ内の絶対パス → 相対パスに変換
    - ライブラリ外の絶対パス → 正規化してそのまま返す
    - すでに相対パス → そのまま返す
    内部で db.to_db_path_from_any() を使う。
    """
    import sys

    print(f"[DEBUG] to_cover_db_path input: {absolute_or_any!r}", file=sys.stderr)
    p = (absolute_or_any or "").strip()
    if not p:
        return ""
    try:
        result = db.to_db_path_from_any(p)
        print(f"[DEBUG] to_cover_db_path result: {result!r}", file=sys.stderr)
        return result
    except ValueError:
        result = os.path.normpath(p)
        print(f"[DEBUG] to_cover_db_path fallback: {result!r}", file=sys.stderr)
        return result


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
