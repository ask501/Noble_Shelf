from __future__ import annotations

import logging
import os

import db

_logger = logging.getLogger(__name__)


class BookUpdateError(Exception):
    """book_updater の操作失敗を示す例外"""

    pass


def _rel_for_db(path: str) -> str:
    """DB 用の相対パスへ揃える。絶対パスのみ to_db_path_from_any を使う。"""
    p = (path or "").strip()
    if not p:
        raise BookUpdateError("パスが空です")
    if os.path.isabs(p):
        try:
            return db.to_db_path_from_any(p)
        except ValueError as exc:
            raise BookUpdateError(str(exc)) from exc
    return os.path.normpath(p)


def _adjust_cover_after_rename(old_path: str, new_path: str, cover: str) -> str:
    """FS リネーム後にカバー参照パスを付け替える（rename_dialog と同じルール）。"""
    if not cover:
        return ""
    if os.path.isdir(old_path) and cover.startswith(old_path):
        return cover.replace(old_path, new_path, 1)
    if not os.path.isdir(old_path) and cover.startswith(old_path):
        return new_path if old_path == cover else cover.replace(old_path, new_path, 1)
    parent_dir_old = os.path.dirname(old_path)
    if cover.startswith(parent_dir_old):
        return cover.replace(parent_dir_old, os.path.dirname(new_path), 1)
    return cover


def _cover_rel_for_set_custom(cover_path: str | None) -> str:
    """
    set_cover_custom に渡す cover_path を DB 保存形式へ揃える。
    空文字のときは呼び出し側で set_cover_custom をスキップする。
    - ライブラリ内 → 相対パス（to_db_path_from_any）
    - ライブラリ外（別ドライブ等）→ 絶対パスを正規化してそのまま保存
    """
    if not cover_path or not str(cover_path).strip():
        return ""
    p = str(cover_path).strip()
    try:
        return db.to_db_path_from_any(p)
    except ValueError:
        return os.path.normpath(p)


def rename_book(
    old_abs_path: str,
    new_abs_path: str,
    new_name: str,
    new_circle: str,
    new_title: str,
    cover_path: str | None = None,
    *,
    db_old_path: str | None = None,
    skip_fs_rename: bool = False,
) -> None:
    """
    FS rename + DB更新を一括で行う。
    - os.rename(old_abs_path, new_abs_path)（同一パスならスキップ。skip_fs_rename 時は呼び出し側で済ませた前提で省略）
    - db.rename_book(old_rel, new_rel, new_name, new_circle, new_title, cover_rel)
    - db.clear_missing_since_for_paths([new_rel])
    DB更新失敗時は os.rename をロールバック（ベストエフォート。完全保証しない）。
    db_old_path: DB 上の旧キーが実ファイルパスと異なる場合（path 修復時など）
    skip_fs_rename: True のとき FS は触らない（親フォルダのリネームのみなど、呼び出し側で済んだ場合）
    """
    old_abs = os.path.normpath(old_abs_path)
    new_abs = os.path.normpath(new_abs_path)
    old_key_src = db_old_path if db_old_path is not None else old_abs_path
    try:
        old_rel = _rel_for_db(old_key_src)
        new_rel = _rel_for_db(new_abs_path)
    except BookUpdateError:
        raise
    if skip_fs_rename:
        cover_arg = (cover_path or "").strip()
    else:
        did_local_fs = old_abs != new_abs
        if did_local_fs:
            try:
                os.rename(old_abs, new_abs)
            except OSError as exc:
                raise BookUpdateError(str(exc)) from exc
        cover_arg = _adjust_cover_after_rename(old_abs_path, new_abs_path, (cover_path or "").strip())
    did_fs_rename = (not skip_fs_rename) and (old_abs != new_abs)
    try:
        db.rename_book(old_rel, new_rel, new_name, new_circle, new_title, cover_arg)
        db.clear_missing_since_for_paths([new_rel])
    except Exception as exc:
        if did_fs_rename:
            try:
                os.rename(new_abs, old_abs)
            except OSError as rb_exc:
                _logger.warning(
                    "rename_book: FS ロールバックを試みましたが失敗しました（ベストエフォート）: %s",
                    rb_exc,
                )
        raise BookUpdateError(str(exc)) from exc


def update_book_meta(
    path: str,
    new_name: str,
    new_circle: str,
    new_title: str,
    cover_path: str | None = None,
    *,
    books_row_cover_path: str | None = None,
) -> None:
    """
    FS は触らず DB の name/circle/title/cover_path のみ更新。
    - 通常: db.update_book_display(path, ...)
    - books_row_cover_path 指定時: db.rename_book(rel, rel, ...) で books 行の cover_path もまとめて更新（メタ検索の path 据え置き更新用）
    - cover_path が指定されていれば db.set_cover_custom(path, cover_rel)
    - db.clear_missing_since_for_paths([rel])
    """
    try:
        rel = _rel_for_db(path)
    except BookUpdateError:
        raise
    try:
        if books_row_cover_path is not None:
            db.rename_book(rel, rel, new_name, new_circle, new_title, (books_row_cover_path or "").strip())
        else:
            db.update_book_display(rel, circle=new_circle, title=new_title, name=new_name)
        cover_rel = _cover_rel_for_set_custom(cover_path)
        if cover_rel:
            db.set_cover_custom(rel, cover_rel)
        db.clear_missing_since_for_paths([rel])
    except Exception as exc:
        raise BookUpdateError(str(exc)) from exc
