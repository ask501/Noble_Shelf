"""
ワンショット: .noble-shelf-id の UUID と DB books.uuid の不一致を検出・修正する。

実行: プロジェクトルートで python tools/fix_uuid_mismatch.py
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys

# プロジェクトルートを import パスに追加
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import cache  # noqa: E402
import config  # noqa: E402
import db  # noqa: E402
from paths import DB_FILE  # noqa: E402

_UUID_PATTERN = re.compile(config.NOBLE_SHELF_UUID_V4_REGEX)


def _read_file_uuid(id_path: str) -> str | None:
    """`.noble-shelf-id` の先頭行を UUIDv4 として読む。"""
    try:
        with open(id_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return None
    text = raw.replace("\ufeff", "").strip()
    lines = text.splitlines()
    first = lines[0].strip() if lines else ""
    if not first:
        return None
    if _UUID_PATTERN.fullmatch(first):
        return first
    return None


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _collect_mismatches(
    library_folder: str,
) -> list[tuple[str, str, str, str]]:
    """
    (folder_path, db_path, file_uuid, db_uuid) のリスト。
    不一致は file_uuid != db_uuid かつ DB に行がある場合のみ。
    """
    id_name = config.NOBLE_SHELF_ID_FILENAME
    out: list[tuple[str, str, str, str]] = []
    try:
        names = os.listdir(library_folder)
    except OSError as e:
        print(f"ライブラリフォルダを開けません: {e}", file=sys.stderr)
        return []

    for name in names:
        folder_path = os.path.normpath(os.path.join(library_folder, name))
        if not os.path.isdir(folder_path):
            continue
        id_path = os.path.join(folder_path, id_name)
        if not os.path.isfile(id_path):
            continue
        file_uuid = _read_file_uuid(id_path)
        if not file_uuid:
            print(f"スキップ（ID 読み取り不可）: {folder_path}", file=sys.stderr)
            continue
        try:
            db_path = db.to_db_path_from_any(folder_path)
        except ValueError as e:
            print(f"スキップ（パス変換失敗）: {folder_path} ({e})", file=sys.stderr)
            continue
        
        conn = db.get_conn()
        try:
            row = conn.execute("SELECT uuid FROM books WHERE path=?", (db_path,)).fetchone()
        finally:
            conn.close()

        if not row:
            continue
        db_uuid = (row["uuid"] or "").strip()
        if db_uuid != file_uuid:
            out.append((folder_path, db_path, file_uuid, db_uuid))
    return out


def _apply_fixes(
    rows: list[tuple[str, str, str, str]],
) -> None:
    """file_uuid に DB を合わせる（book_meta / book_characters / book_tags も uuid 連動）。"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        for _folder_path, db_path, file_uuid, db_uuid in rows:
            if file_uuid == db_uuid:
                continue
            other = conn.execute(
                "SELECT path FROM books WHERE uuid=? AND path!=?",
                (file_uuid, db_path),
            ).fetchone()
            if other:
                print(
                    f"中止: uuid 衝突（file の UUID が既に別 path で使用）: "
                    f"path={db_path!r} target_uuid={file_uuid!r} other={other['path']!r}",
                    file=sys.stderr,
                )
                return

        conn.execute("PRAGMA foreign_keys=OFF")
        for _folder_path, db_path, file_uuid, db_uuid in rows:
            if file_uuid == db_uuid:
                continue
            conn.execute(
                "UPDATE book_characters SET uuid=? WHERE uuid=?",
                (file_uuid, db_uuid),
            )
            conn.execute(
                "UPDATE book_tags SET uuid=? WHERE uuid=?",
                (file_uuid, db_uuid),
            )
            if _table_has_column(conn, "book_meta", "uuid"):
                conn.execute(
                    "UPDATE book_meta SET uuid=? WHERE uuid=?",
                    (file_uuid, db_uuid),
                )
            if _table_has_column(conn, "bookmarks", "uuid"):
                conn.execute(
                    "UPDATE bookmarks SET uuid=? WHERE uuid=?",
                    (file_uuid, db_uuid),
                )
            cur = conn.execute(
                "UPDATE books SET uuid=? WHERE path=?",
                (file_uuid, db_path),
            )
            if cur.rowcount != 1:
                print(
                    f"警告: books 更新行数が 1 ではない: path={db_path!r} rowcount={cur.rowcount}",
                    file=sys.stderr,
                )
        conn.execute("PRAGMA foreign_keys=ON")
        conn.commit()
        cache.invalidate()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    db.init_db()
    library_folder = (db.get_setting("library_folder") or "").strip()
    if not library_folder or not os.path.isdir(library_folder):
        print("ライブラリフォルダが未設定または存在しません。", file=sys.stderr)
        return 1

    print(f"DB: {DB_FILE}")
    print(f"ライブラリ: {library_folder}")
    print("走査中…")

    mismatches = _collect_mismatches(library_folder)
    if not mismatches:
        print("不一致はありません。終了します。")
        return 0

    print("--- 不一致一覧 ---")
    for folder_path, db_path, file_uuid, db_uuid in mismatches:
        print(f"  path={db_path!r}")
        print(f"    file(.noble-shelf-id)={file_uuid!r}")
        print(f"    db(books.uuid)     ={db_uuid!r}")
        print(f"    folder={folder_path}")

    answer = input(
        f"\n上記 {len(mismatches)} 件を DB の uuid をファイル側に合わせて更新しますか？ [yes/N]: "
    ).strip().lower()
    if answer not in ("yes", "y"):
        print("キャンセルしました。")
        return 0

    _apply_fixes(mismatches)
    print("更新完了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
