from __future__ import annotations

"""
db.py - SQLiteデータベース管理・バックアップ処理

担当:
  - DBの初期化・マイグレーション
  - books / bookmarks / recent_books / settings の読み書き
  - 起動時の自動バックアップ（直近10件保持）
  - バックアップ一覧取得・復元
"""
import re
import sqlite3
import os
import shutil
import sys
import logging
import time
import unicodedata
import uuid as uuid_lib
import hashlib
from contextlib import contextmanager
from datetime import datetime
import config
from paths import DB_FILE, BACKUP_DIR, to_rel
import cache
from store_file_resolver import ActionResult

_logger = logging.getLogger(__name__)

UNSET = object()

MAX_BACKUPS = 10
LIBRARY_FOLDER_SETTING_KEY = "library_folder"
DEBUG_FORCE_DB_RECREATE_ONCE_ENV_KEY = "NOBLE_SHELF_FORCE_DB_RECREATE_ONCE"
DEBUG_FORCE_DB_RECREATE_ENABLED_VALUE = "1"
_debug_force_db_recreate_consumed = False

# フィルターパネル用 get_all_*_with_count のキャッシュキー（cache.py）
CACHE_KEY_TAGS_WITH_COUNT = "tags_with_count"
CACHE_KEY_CIRCLES_WITH_COUNT = "circles_with_count"
CACHE_KEY_CHARACTERS_WITH_COUNT = "characters_with_count"
CACHE_KEY_AUTHORS_WITH_COUNT = "authors_with_count"
CACHE_KEY_SERIES_WITH_COUNT = "series_with_count"


# ══════════════════════════════════════════════════════
#  接続・初期化
# ══════════════════════════════════════════════════════

def get_conn():
    """DB接続を返す（呼び出し元でclose()すること）"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # 書き込み中でも読み取り可能にする
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={config.DB_BUSY_TIMEOUT_MS}")
    return conn


@contextmanager
def transaction():
    """明示的トランザクション。例外時は自動ロールバック。"""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _new_uuid() -> str:
    """UUID v4文字列を返す。"""
    return str(uuid_lib.uuid4())


def _compute_store_content_hash(abs_path: str) -> str | None:
    try:
        size = os.path.getsize(abs_path)
        with open(abs_path, "rb") as f:
            if size < 2 * 1024 * 1024:
                data = f.read()
            else:
                data = f.read(2 * 1024 * 1024)
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return None


def _get_library_root() -> str:
    """設定済みライブラリルートを返す。未設定時は空文字。"""
    return (get_setting(LIBRARY_FOLDER_SETTING_KEY) or "").strip()


def _to_db_path(abs_path: str) -> str:
    """絶対パスをDB保存用の相対パスへ変換する。"""
    root = _get_library_root()
    if not root:
        raise ValueError("ライブラリルートが未設定です")
    return os.path.normpath(os.path.relpath(abs_path, root))


def to_db_path_from_any(path: str) -> str:
    """ライブラリ配下の絶対パスまたは DB 相対パスを、DB 保存用の相対パスへ統一する。"""
    root = _get_library_root()
    if not root:
        raise ValueError("ライブラリルートが未設定です")
    p = (path or "").strip()
    if not p:
        raise ValueError("パスが空です")
    lr = os.path.normpath(root)
    abs_p = os.path.normpath(p if os.path.isabs(p) else os.path.join(lr, p))
    return _to_db_path(abs_p)


def _from_db_path(rel_path: str) -> str:
    """DB保存用の相対パスを絶対パスへ変換する。"""
    root = _get_library_root()
    if not root:
        raise ValueError("ライブラリルートが未設定です")
    return os.path.normpath(os.path.join(root, rel_path))


def _get_book_uuid(conn: sqlite3.Connection, path: str) -> str | None:
    """pathに対応するbooks.uuidを返す。未登録時はNone。"""
    row = conn.execute("SELECT uuid FROM books WHERE path=?", (path,)).fetchone()
    return (row["uuid"] if row else None) if row is not None else None


def get_book_uuid(path: str) -> str | None:
    """pathに対応するbooks.uuidを返す。未登録時はNone。"""
    if not path or not str(path).strip():
        return None
    conn = get_conn()
    try:
        return _get_book_uuid(conn, path)
    finally:
        conn.close()


def get_book_by_uuid(book_uuid: str) -> dict | None:
    """uuidでbooksレコードを取得する。"""
    if not book_uuid or not str(book_uuid).strip():
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT uuid, name, circle, title, path,
                      COALESCE(NULLIF(cover_custom, ''), cover_path) as cover_path,
                      mtime, COALESCE(is_dlst, 0) as is_dlst
               FROM books WHERE uuid=?""",
            (book_uuid,),
        ).fetchone()
        if not row:
            return None
        # books に media_type 列は無い（新スキーマ）。呼び出し側互換用に既定値を付与する。
        d = dict(row)
        d.setdefault("media_type", config.BOOKS_MEDIA_TYPE_DEFAULT)
        return d
    finally:
        conn.close()


def update_book_path_by_uuid(book_uuid: str, new_path: str) -> bool:
    """uuid指定でbooks.pathを更新する。更新時はTrueを返す。"""
    if not book_uuid or not new_path:
        return False
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE books SET path=?, updated_at=datetime('now','localtime') WHERE uuid=?",
            (new_path, book_uuid),
        )
        if cur.rowcount:
            conn.commit()
            return True
        return False
    finally:
        conn.close()


def upsert_book_by_uuid(
    book_uuid: str,
    name: str,
    circle: str,
    title: str,
    path: str,
    cover_path: str,
    mtime: float | None = None,
    is_dlst: int = 0,
    pages: int | None = None,
    content_hash: str | None = None,
) -> None:
    """uuid指定でbooksをupsertする。pathはUNIQUEで維持する。"""
    if not book_uuid or not path:
        return
    store_cover = _normalize_cover_for_save(cover_path) if cover_path else ""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO books(uuid, name, circle, title, path, cover_path, mtime, is_dlst, content_hash, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,datetime('now','localtime'))
               ON CONFLICT(uuid) DO UPDATE SET
                 name=excluded.name, circle=excluded.circle, title=excluded.title,
                 path=excluded.path, cover_path=excluded.cover_path, mtime=excluded.mtime,
                 is_dlst=excluded.is_dlst,
                 content_hash=COALESCE(excluded.content_hash, books.content_hash),
                 missing_since_date=NULL,
                 updated_at=excluded.updated_at""",
            (book_uuid, name, circle, title, path, store_cover, mtime, is_dlst, content_hash),
        )
        conn.commit()
        if pages is not None:
            set_book_meta(path, pages=pages)
    finally:
        conn.close()
    cache.invalidate()


def apply_action_result(result: ActionResult, book_data: dict) -> None:
    status = (result.status or "").strip()
    if status in {"duplicate", "unchanged", "error"}:
        return

    db_path = (result.db_path or "").strip()
    if not db_path:
        return

    name = (book_data.get("name") or "").strip()
    circle = (book_data.get("circle") or "").strip()
    title = (book_data.get("title") or "").strip()
    cover_path = book_data.get("cover_path") or ""
    mtime = book_data.get("mtime")
    is_dlst = 1 if bool(book_data.get("is_dlst")) else 0
    pages = book_data.get("pages")
    content_hash = (book_data.get("content_hash") or "").strip() or None

    if status == "rename":
        if not (result.existing_path or "").strip():
            return
        rename_book_path(
            result.existing_uuid or "",
            db_path,
            mtime,
            content_hash,
        )
        return

    if status == "updated":
        upsert_book_by_uuid(
            result.existing_uuid or _new_uuid(),
            name,
            circle,
            title,
            db_path,
            cover_path,
            mtime,
            is_dlst,
            pages,
            content_hash=content_hash,
        )
        return

    if status == "created":
        book_uuid = (
            str(uuid_lib.uuid5(uuid_lib.UUID(config.STORE_FILE_NAMESPACE), content_hash))
            if content_hash
            else _new_uuid()
        )
        upsert_book_by_uuid(
            book_uuid,
            name,
            circle,
            title,
            db_path,
            cover_path,
            mtime,
            is_dlst,
            pages,
            content_hash=content_hash,
        )


def rename_book_path(
    uuid: str,
    new_path: str,
    new_mtime: float | None,
    new_content_hash: str | None,
) -> None:
    """rename時は path/mtime/content_hash のみ更新し、表示メタは維持する。"""
    if not uuid or not str(uuid).strip():
        return
    if not new_path or not str(new_path).strip():
        return
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE books
            SET path=?, mtime=?, content_hash=?, missing_since_date=NULL, updated_at=datetime('now','localtime')
            WHERE uuid=?
            """,
            (
                str(new_path).strip(),
                new_mtime,
                (str(new_content_hash).strip() if new_content_hash else None),
                str(uuid).strip(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    cache.invalidate()


def fetch_all_rows_for_index() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                rowid,
                uuid,
                path,
                content_hash,
                mtime,
                missing_since_date,
                COALESCE(is_dlst, 0) AS is_dlst
            FROM books
            """
        ).fetchall()
        return [
            {
                "rowid": r["rowid"],
                "uuid": r["uuid"],
                "path": r["path"],
                "content_hash": r["content_hash"],
                "mtime": r["mtime"],
                "missing_since_date": r["missing_since_date"],
                "file_ext": os.path.splitext(r["path"] or "")[1].lower(),
                "is_dlst": int(r["is_dlst"] or 0),
            }
            for r in rows
            if r["path"]
        ]
    finally:
        conn.close()


def update_content_hash(uuid: str, content_hash: str) -> None:
    """books.content_hash のみ更新する。"""
    if not uuid or not str(uuid).strip():
        return
    if content_hash is None:
        return
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE books SET content_hash=? WHERE uuid=?",
            (str(content_hash).strip(), str(uuid).strip()),
        )
        conn.commit()
    finally:
        conn.close()


def update_cover_hash(uuid: str, cover_hash: str) -> None:
    """books.cover_hash のみ更新する。"""
    if not uuid or not str(uuid).strip():
        return
    if cover_hash is None:
        return
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE books SET cover_hash=? WHERE uuid=?",
            (str(cover_hash).strip(), str(uuid).strip()),
        )
        conn.commit()
    finally:
        conn.close()


def _is_uuid_schema_ready(c: sqlite3.Cursor) -> bool:
    """books/book_metaがuuid基準スキーマならTrue。"""
    book_cols = [r[1] for r in c.execute("PRAGMA table_info(books)").fetchall()]
    meta_cols = [r[1] for r in c.execute("PRAGMA table_info(book_meta)").fetchall()]
    return ("uuid" in book_cols and "path" in book_cols and "uuid" in meta_cols)


def _consume_debug_force_db_recreate_once() -> bool:
    """デバッグ用: 環境変数が有効なら1プロセス中で1回だけTrueを返す。"""
    global _debug_force_db_recreate_consumed
    if _debug_force_db_recreate_consumed:
        return False
    flag = (os.environ.get(DEBUG_FORCE_DB_RECREATE_ONCE_ENV_KEY) or "").strip()
    if flag != DEBUG_FORCE_DB_RECREATE_ENABLED_VALUE:
        return False
    _debug_force_db_recreate_consumed = True
    return True


def init_db():
    """テーブル作成・マイグレーション。起動時に1回呼ぶ。"""
    has_settings = False
    conn_pre = get_conn()
    try:
        has_settings = conn_pre.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'"
        ).fetchone() is not None
    finally:
        conn_pre.close()

    if has_settings:
        from version import VERSION

        last_version = get_last_launch_version()
        if last_version and last_version != VERSION:
            pre_migration_backup_path = os.path.join(
                config.APP_DATA_DIR,
                f"library_v{last_version}_pre_migration.db",
            )
            try:
                backup_pre_migration(pre_migration_backup_path)
            except Exception:
                pass

    conn = get_conn()
    try:
        c = conn.cursor()
        force_recreate = _consume_debug_force_db_recreate_once()

        # 旧path主キー構成なら、v3スキーマへ再作成（既存ユーザーゼロ前提）
        c.execute("CREATE TABLE IF NOT EXISTS books(path TEXT PRIMARY KEY)")
        c.execute("CREATE TABLE IF NOT EXISTS book_meta(path TEXT PRIMARY KEY)")
        if force_recreate or not _is_uuid_schema_ready(c):
            c.execute("DROP TABLE IF EXISTS book_characters")
            c.execute("DROP TABLE IF EXISTS book_tags")
            c.execute("DROP TABLE IF EXISTS book_meta")
            c.execute("DROP TABLE IF EXISTS books")

        # ── books テーブル ──────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS books (
                uuid        TEXT PRIMARY KEY,
                path        TEXT NOT NULL UNIQUE,
                name        TEXT NOT NULL,
                circle      TEXT NOT NULL,
                title       TEXT NOT NULL,
                cover_path  TEXT,
                mtime       REAL,
                content_hash TEXT,
                missing_since_date TEXT DEFAULT NULL,
                updated_at  TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # ── bookmarks テーブル ─────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                path    TEXT PRIMARY KEY,
                rating  INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # ── recent_books テーブル ──────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS recent_books (
                path       TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                opened_at  TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # ── settings テーブル ──────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # ── hidden_paths テーブル（ライブラリ整合性チェックの非表示管理） ──
        c.execute("""
            CREATE TABLE IF NOT EXISTS hidden_paths (
                path TEXT PRIMARY KEY
            )
        """)

        # ── book_meta テーブル（作者・タイプ・シリーズ・作品ID・除外フラグなど）────
        c.execute("""
            CREATE TABLE IF NOT EXISTS book_meta (
                uuid         TEXT PRIMARY KEY,
                author       TEXT DEFAULT '',
                type         TEXT DEFAULT '',
                series       TEXT DEFAULT '',
                dlsite_id    TEXT DEFAULT '',
                excluded     INTEGER DEFAULT 0,
                title_kana   TEXT DEFAULT '',
                circle_kana  TEXT DEFAULT '',
                pages        INTEGER,
                release_date TEXT DEFAULT '',
                price        INTEGER,
                memo         TEXT DEFAULT '',
                store_url    TEXT DEFAULT '',
                meta_source  TEXT DEFAULT '',
                updated_at   TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (uuid) REFERENCES books(uuid) ON DELETE CASCADE
            )
        """)
        # 既存DBに不足カラムがあれば追加（マイグレーション）
        meta_cols = [r[1] for r in c.execute("PRAGMA table_info(book_meta)").fetchall()]
        if "dlsite_id" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN dlsite_id TEXT DEFAULT ''")
        if "excluded" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN excluded INTEGER DEFAULT 0")
        if "title_kana" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN title_kana TEXT DEFAULT ''")
        if "circle_kana" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN circle_kana TEXT DEFAULT ''")
        if "pages" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN pages INTEGER")
        if "release_date" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN release_date TEXT DEFAULT ''")
        if "price" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN price INTEGER")
        if "memo" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN memo TEXT DEFAULT ''")
        if "meta_source" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN meta_source TEXT DEFAULT ''")
        if "store_url" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN store_url TEXT DEFAULT ''")

        # ── book_characters テーブル ───────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS book_characters (
                uuid      TEXT NOT NULL,
                character TEXT NOT NULL,
                PRIMARY KEY (uuid, character),
                FOREIGN KEY (uuid) REFERENCES books(uuid) ON DELETE CASCADE
            )
        """)

        # ── book_tags テーブル ─────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS book_tags (
                uuid TEXT NOT NULL,
                tag  TEXT NOT NULL,
                PRIMARY KEY (uuid, tag),
                FOREIGN KEY (uuid) REFERENCES books(uuid) ON DELETE CASCADE
            )
        """)

        # ── bookmarklet_queue テーブル ─────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS bookmarklet_queue (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                url          TEXT NOT NULL,
                site         TEXT NOT NULL DEFAULT '',
                title        TEXT NOT NULL DEFAULT '',
                circle       TEXT NOT NULL DEFAULT '',
                author       TEXT NOT NULL DEFAULT '',
                dlsite_id    TEXT NOT NULL DEFAULT '',
                tags         TEXT NOT NULL DEFAULT '',
                price        INTEGER,
                release_date TEXT NOT NULL DEFAULT '',
                cover_url    TEXT NOT NULL DEFAULT '',
                store_url    TEXT NOT NULL DEFAULT '',
                status       TEXT NOT NULL DEFAULT 'pending',
                fetched_at   TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # bookmarklet_queue マイグレーション
        bq_cols = [r[1] for r in c.execute("PRAGMA table_info(bookmarklet_queue)").fetchall()]
        if "cover_url" not in bq_cols:
            c.execute("ALTER TABLE bookmarklet_queue ADD COLUMN cover_url TEXT NOT NULL DEFAULT ''")
        if "store_url" not in bq_cols:
            c.execute("ALTER TABLE bookmarklet_queue ADD COLUMN store_url TEXT NOT NULL DEFAULT ''")

        # ── booksテーブルにcover_customカラムを追加（なければ）──
        cols = [r[1] for r in c.execute("PRAGMA table_info(books)").fetchall()]
        if 'cover_custom' not in cols:
            c.execute("ALTER TABLE books ADD COLUMN cover_custom TEXT")
        
        # ── booksテーブルにis_dlstカラムを追加（なければ）──
        if 'is_dlst' not in cols:
            c.execute("ALTER TABLE books ADD COLUMN is_dlst INTEGER DEFAULT 0")
        if "content_hash" not in cols:
            c.execute("ALTER TABLE books ADD COLUMN content_hash TEXT")
        if "cover_hash" not in cols:
            c.execute("ALTER TABLE books ADD COLUMN cover_hash TEXT DEFAULT NULL")
        if "missing_since_date" not in cols:
            c.execute("ALTER TABLE books ADD COLUMN missing_since_date TEXT DEFAULT NULL")

        # ── インデックス ───────────────────────────────
        c.execute("CREATE INDEX IF NOT EXISTS idx_books_circle ON books(circle)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_books_path ON books(path)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_books_content_hash ON books(content_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_books_cover_hash ON books(cover_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_characters_uuid ON book_characters(uuid)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tags_uuid ON book_tags(uuid)")

        conn.commit()

        # 強制終了で残った「保留ドロップ」設定を起動時に消す（起動時にダイアログが出るバグ防止）
        for key in ("pending_drop_paths", "deferred_drop_paths", "drop_paths"):
            c.execute("DELETE FROM settings WHERE key=?", (key,))
        conn.commit()

        # 追加マイグレーション: release_date のフォーマット統一
        migrate_release_date_format()
    finally:
        conn.close()

    from version import VERSION

    try:
        set_last_launch_version(VERSION)
    except Exception:
        pass




def migrate_release_date_format():
    """release_dateを 'yyyy年m月d日' 形式に統一する"""
    import re as _re

    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT m.uuid, m.release_date
               FROM book_meta m
               WHERE m.release_date != ''"""
        ).fetchall()
        for row in rows:
            rd = row["release_date"] or ""
            m = _re.match(r"(\\d{4})[-/\\.](\\d{1,2})[-/\\.](\\d{1,2})", rd)
            if m:
                normalized = f"{m.group(1)}年{int(m.group(2))}月{int(m.group(3))}日"
                conn.execute(
                    "UPDATE book_meta SET release_date = ? WHERE uuid = ?",
                    (normalized, row["uuid"]),
                )
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  bookmarklet_queue
# ══════════════════════════════════════════════════════

def add_bookmarklet_queue(
    url: str,
    site: str,
    title: str,
    circle: str,
    author: str,
    dlsite_id: str,
    tags: str,
    price: int | None,
    release_date: str,
    cover_url: str,
    status: str = "pending",
    store_url: str = "",
) -> int:
    """キューに1件追加してidを返す"""
    conn = get_conn()
    try:
        c = conn.execute(
            """INSERT INTO bookmarklet_queue
               (url, site, title, circle, author, dlsite_id, tags, price, release_date, cover_url, status, store_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, site, title, circle, author, dlsite_id, tags, price, release_date, cover_url, status, store_url),
        )
        conn.commit()
        return c.lastrowid
    finally:
        conn.close()


def get_bookmarklet_queue() -> list[dict]:
    """キュー全件を新しい順で返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM bookmarklet_queue ORDER BY fetched_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_bookmarklet_status(id: int, status: str) -> None:
    """ステータスを更新する"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE bookmarklet_queue SET status = ? WHERE id = ?",
            (status, id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_bookmarklet_queue_by_status(status: str) -> None:
    """指定ステータスの件を一括削除する"""
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM bookmarklet_queue WHERE status = ?", (status,)
        )
        conn.commit()
    finally:
        conn.close()


def delete_bookmarklet_queue_all() -> None:
    """キューを全削除する"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM bookmarklet_queue")
        conn.commit()
    finally:
        conn.close()


def delete_bookmarklet_queue_by_id(id: int) -> None:
    """個別削除する"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM bookmarklet_queue WHERE id = ?", (id,))
        conn.commit()
    finally:
        conn.close()


def get_bookmarklet_queue_by_id(row_id: int) -> dict | None:
    conn = get_conn()
    try:
        c = conn.execute(
            "SELECT id, url, site, title, circle, author, dlsite_id, tags, price, release_date, cover_url, status, fetched_at, store_url "
            "FROM bookmarklet_queue WHERE id = ?",
            (row_id,),
        )
        row = c.fetchone()
        if not row:
            return None
        keys = [
            "id",
            "url",
            "site",
            "title",
            "circle",
            "author",
            "dlsite_id",
            "tags",
            "price",
            "release_date",
            "cover_url",
            "status",
            "fetched_at",
            "store_url",
        ]
        return dict(zip(keys, row))
    finally:
        conn.close()


def update_bookmarklet_queue_status(row_id: int, status: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE bookmarklet_queue SET status = ? WHERE id = ?",
            (status, row_id),
        )
        conn.commit()
    finally:
        conn.close()


def find_book_by_bookmarklet(dlsite_id: str, title: str, url: str = "") -> dict | None:
    """
    ブックマークレットのメタデータからライブラリの作品を探す。
    検索順:
      ① book_meta.dlsite_id 完全一致
      ② books.name にID含む部分一致（URLからも抽出）
      ③ NFKC正規化後のタイトル完全一致
    """
    import unicodedata
    import re

    def normalize(s: str) -> str:
        return unicodedata.normalize("NFKC", (s or "").strip()).lower()

    conn = get_conn()
    try:
        # ① dlsite_id 完全一致
        if dlsite_id:
            row = conn.execute(
                "SELECT b.path, b.name, b.title, b.circle FROM books b "
                "LEFT JOIN book_meta m ON b.uuid = m.uuid "
                "WHERE m.dlsite_id = ?",
                (dlsite_id,),
            ).fetchone()
            if row:
                return dict(row)

        # URLからIDを抽出して追加で検索
        ids_to_check: set[str] = set()
        if dlsite_id:
            ids_to_check.add(dlsite_id)
        if url:
            m = re.search(r"(RJ|BJ|VJ|\d{6,})", url, re.IGNORECASE)
            if m:
                ids_to_check.add(m.group(0).upper())

        # ② books.name にID含む部分一致
        for id_str in ids_to_check:
            row = conn.execute(
                "SELECT path, name, title, circle FROM books WHERE name LIKE ?",
                (f"%{id_str}%",),
            ).fetchone()
            if row:
                return dict(row)

        # ③ NFKC正規化タイトル完全一致
        if title:
            norm_title = normalize(title)
            rows = conn.execute("SELECT path, name, title, circle FROM books").fetchall()
            for row in rows:
                if normalize(row["title"]) == norm_title or normalize(row["name"]) == norm_title:
                    return dict(row)

        return None
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  バックアップ
# ══════════════════════════════════════════════════════

def backup_on_startup() -> None:
    """
    起動時に自動バックアップを取る。
    BACKUP_DIR に library_YYYYMMDD_HHMMSS.db を作成し、
    設定の backup_max_count を超えた古いファイルを削除する。
    """
    if not os.path.exists(DB_FILE):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"library_{ts}.db")
    shutil.copy2(DB_FILE, dst)
    _trim_backups_with_setting()


def _safe_backup(backup_path: str) -> None:
    """アトミックなバックアップ。tmp出力後にos.replaceで移動する。"""
    tmp_path = backup_path + ".tmp"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    safe_path = tmp_path.replace("'", "''")
    conn = get_conn()
    try:
        conn.execute(f"VACUUM INTO '{safe_path}'")
    finally:
        conn.close()
    for _ in range(3):
        try:
            os.replace(tmp_path, backup_path)
            break
        except PermissionError:
            time.sleep(0.5)


def backup_daily(backup_path: str) -> None:
    """通常終了時の24時間バックアップ。"""
    _safe_backup(backup_path)


def backup_pre_migration(backup_path: str) -> None:
    """バージョンアップ前のマイグレーション保険バックアップ。"""
    _safe_backup(backup_path)


def get_last_backup_time() -> float:
    try:
        return float(get_setting("last_backup_time") or 0)
    except Exception:
        return 0.0


def set_last_backup_time(t: float) -> None:
    set_setting("last_backup_time", str(t))


def get_last_launch_version() -> str:
    """settings テーブルが存在しない初回起動時は空文字を返す。"""
    try:
        return get_setting("last_launch_version") or ""
    except Exception:
        return ""


def set_last_launch_version(version: str) -> None:
    set_setting("last_launch_version", version)


def _trim_backups_with_setting() -> None:
    """バックアップ件数が上限を超えたら古いものから削除する（backup_max_count 設定を優先）。"""
    try:
        max_count = int(get_setting("backup_max_count") or MAX_BACKUPS)
    except (TypeError, ValueError):
        max_count = MAX_BACKUPS
    backups = list_backups()  # 既存の list_backups() は新しい順の dict リストを返す
    for info in backups[max_count:]:
        path = info.get("path")
        if not path:
            continue
        try:
            os.remove(path)
        except OSError:
            pass


# ══════════════════════════════════════════════════════
#  settings 読み書き
# ══════════════════════════════════════════════════════

def get_setting(key, default=None):
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key, value):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value) if value is not None else None)
        )
        conn.commit()
    finally:
        conn.close()


def add_hidden_path(path: str):
    """非表示パスを追加する。"""
    if not path or not str(path).strip():
        return
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO hidden_paths(path) VALUES(?)",
            (path,),
        )
        conn.commit()
    finally:
        conn.close()


def remove_hidden_path(path: str):
    """非表示パスを削除する。"""
    if not path or not str(path).strip():
        return
    conn = get_conn()
    try:
        conn.execute("DELETE FROM hidden_paths WHERE path=?", (path,))
        conn.commit()
    finally:
        conn.close()


def get_hidden_paths() -> list[str]:
    """非表示パス一覧を返す。"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT path FROM hidden_paths").fetchall()
        return [r["path"] for r in rows]
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  books 読み書き
# ══════════════════════════════════════════════════════

def get_all_books():
    """全booksを (name, circle, title, path, cover_path, is_dlst, uuid) のリストで返す
    cover_customが設定されていればそちらを優先"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT uuid, name, circle, title, path,
               COALESCE(NULLIF(cover_custom, ''), cover_path) as cover_path,
               COALESCE(is_dlst, 0) as is_dlst
               FROM books ORDER BY name"""
        ).fetchall()
        return [
            (r["name"], r["circle"], r["title"], r["path"], r["cover_path"], r["is_dlst"], r["uuid"])
            for r in rows
        ]
    finally:
        conn.close()


def clear_missing_since_for_paths(paths: list[str]) -> None:
    """再検出されたパスの missing_since_date を NULL に戻す。"""
    targets = [str(p).strip() for p in (paths or []) if str(p).strip()]
    if not targets:
        return
    conn = get_conn()
    try:
        try:
            conn.executemany(
                "UPDATE books SET missing_since_date=NULL WHERE path=?",
                [(p,) for p in targets],
            )
            conn.commit()
        except sqlite3.OperationalError:
            # 旧スキーマ環境（missing_since_date未追加）では何もしない。
            pass
    finally:
        conn.close()


def mark_missing_since_if_null(path: str, iso_utc: str) -> None:
    """初回missing時のみ missing_since_date を記録する。"""
    p = (path or "").strip()
    ts = (iso_utc or "").strip()
    if not p or not ts:
        return
    conn = get_conn()
    try:
        try:
            conn.execute(
                """
                UPDATE books
                SET missing_since_date=?
                WHERE path=? AND (missing_since_date IS NULL OR missing_since_date='')
                """,
                (ts, p),
            )
            conn.commit()
        except sqlite3.OperationalError:
            # 旧スキーマ環境（missing_since_date未追加）では何もしない。
            pass
    finally:
        conn.close()


def delete_books_by_paths(paths: list[str]) -> None:
    """path 指定で books と bookmarks を削除する。"""
    unique_paths = [str(p).strip() for p in (paths or []) if str(p).strip()]
    if not unique_paths:
        return
    conn = get_conn()
    try:
        conn.executemany("DELETE FROM books WHERE path=?", [(p,) for p in unique_paths])
        conn.executemany("DELETE FROM bookmarks WHERE path=?", [(p,) for p in unique_paths])
        conn.commit()
    finally:
        conn.close()
    cache.invalidate()


def get_missing_books() -> list[dict]:
    """missing_since_date が記録された books を返す。"""
    conn = get_conn()
    try:
        try:
            rows = conn.execute(
                """
                SELECT uuid, name, title, path, missing_since_date
                FROM books
                WHERE missing_since_date IS NOT NULL AND missing_since_date <> ''
                ORDER BY missing_since_date ASC
                """
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []
    finally:
        conn.close()


def get_missing_books_count() -> int:
    """missing_since_date が記録された件数を返す。"""
    conn = get_conn()
    try:
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM books
                WHERE missing_since_date IS NOT NULL AND missing_since_date <> ''
                """
            ).fetchone()
            return int(row["cnt"] if row else 0)
        except sqlite3.OperationalError:
            return 0
    finally:
        conn.close()


def get_all_books_order_by_added_desc():
    """全booksを追加順（updated_at 降順）で返す。get_all_books と同じ形式。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT uuid, name, circle, title, path,
               COALESCE(NULLIF(cover_custom, ''), cover_path) as cover_path,
               COALESCE(is_dlst, 0) as is_dlst
               FROM books ORDER BY updated_at DESC, name"""
        ).fetchall()
        return [
            (r["name"], r["circle"], r["title"], r["path"], r["cover_path"], r["is_dlst"], r["uuid"])
            for r in rows
        ]
    finally:
        conn.close()


def repair_folder_covers():
    """
    フォルダ型書籍で cover_path が未設定または存在しない場合、
    フォルダ内の先頭画像をカバーとして設定する。
    """
    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
    conn = get_conn()
    try:
        rows = conn.execute("SELECT path, cover_path FROM books").fetchall()
        updated = 0
        for r in rows:
            path = r["path"] or ""
            raw_cover = r["cover_path"] or ""
            cover_path = resolve_cover_stored_value(raw_cover) if raw_cover else ""
            if not path or not os.path.isdir(path):
                continue
            if cover_path and os.path.isfile(cover_path):
                continue
            try:
                images = sorted(
                    name
                    for name in os.listdir(path)
                    if os.path.splitext(name)[1].lower() in IMAGE_EXTS
                )
            except Exception:
                continue
            if not images:
                continue
            new_cover = os.path.join(path, images[0])
            if not os.path.isfile(new_cover):
                continue
            store = _normalize_cover_for_save(new_cover)
            conn.execute(
                "UPDATE books SET cover_path=?, updated_at=datetime('now','localtime') WHERE path=?",
                (store, path),
            )
            updated += 1
        if updated:
            conn.commit()
        return updated
    finally:
        conn.close()


def update_book_cover_path(path: str, cover_path: str) -> bool:
    """指定 path の書籍の cover_path を更新する。cover_cache 内は ID のみ保存。戻り値: 更新したら True。"""
    if not path or not str(path).strip():
        return False
    store = _normalize_cover_for_save(cover_path) if cover_path else ""
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE books SET cover_path=?, updated_at=datetime('now','localtime') WHERE path=?",
            (store, path),
        )
        if cur.rowcount:
            conn.commit()
            return True
        return False
    finally:
        conn.close()


def get_known_paths():
    """DB登録済みのpathセットを返す（差分スキャン用）"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT path, mtime FROM books").fetchall()
        return {r["path"]: r["mtime"] for r in rows}
    finally:
        conn.close()


def get_paths_missing_content_hash() -> set[str]:
    """content_hash 未設定の books.path を正規化キー集合で返す。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT path FROM books WHERE content_hash IS NULL OR content_hash=''"
        ).fetchall()
        return {
            os.path.normcase(os.path.normpath(r["path"] or ""))
            for r in rows
            if r["path"]
        }
    finally:
        conn.close()


def get_store_upsert_seed(path: str) -> dict | None:
    """store再upsert用に既存books/book_metaの値を返す。pathはDB保存形式。"""
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT
                b.name AS name,
                b.circle AS circle,
                b.title AS title,
                COALESCE(NULLIF(b.cover_custom, ''), b.cover_path, '') AS cover_path,
                COALESCE(b.is_dlst, 0) AS is_dlst,
                b.mtime AS mtime,
                bm.pages AS pages
            FROM books b
            LEFT JOIN book_meta bm ON bm.uuid = b.uuid
            WHERE b.path=?
            LIMIT 1
            """,
            (path,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_book_by_content_hash(content_hash: str) -> dict | None:
    """content_hash 一致の books 行（先頭1件）を返す。"""
    if not content_hash:
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT uuid, path, name, circle, title, cover_path, mtime, COALESCE(is_dlst, 0) AS is_dlst
            FROM books
            WHERE content_hash=?
            ORDER BY rowid ASC
            LIMIT 1
            """,
            (content_hash,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_book_by_cover_hash(cover_hash: str) -> dict | None:
    """cover_hash 一致の books 行（先頭1件）を返す。"""
    if not cover_hash:
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT uuid, path, name, circle, title, cover_path, mtime,
                   COALESCE(is_dlst, 0) AS is_dlst, updated_at
            FROM books
            WHERE cover_hash=?
            ORDER BY rowid ASC
            LIMIT 1
            """,
            (cover_hash,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_books_updated_at_map() -> dict[str, float]:
    """path -> updated_at のマップを返す（追加順ソート用）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT path, COALESCE(CAST(strftime('%s', updated_at) AS REAL), mtime, 0) AS v FROM books"
        ).fetchall()
        return {r["path"]: r["v"] for r in rows}
    finally:
        conn.close()


def is_path_registered(path: str) -> bool:
    """指定パスが books に登録済みなら True（二重登録防止用）。"""
    if not path or not str(path).strip():
        return False
    try:
        db_path = to_db_path_from_any(path)
    except ValueError:
        return False
    conn = get_conn()
    try:
        row = conn.execute("SELECT 1 FROM books WHERE path=?", (db_path,)).fetchone()
        return row is not None
    finally:
        conn.close()


def upsert_book(
    name,
    circle,
    title,
    path,
    cover_path,
    mtime=None,
    is_dlst=0,
    pages=None,
    uuid=None,
    cover_hash=None,
):
    if not path:
        return
    try:
        path = to_db_path_from_any(path)
        if cover_path:
            cover_path = to_db_path_from_any(cover_path)
    except ValueError as e:
        _logger.warning("upsert_book: パス変換失敗、登録をスキップ: path=%s err=%s", path, e)
        return
    store_cover = _normalize_cover_for_save(cover_path) if cover_path else ""
    cover_hash_store = None
    if cover_hash is not None:
        ch = str(cover_hash).strip()
        cover_hash_store = ch if ch else None
    conn = get_conn()
    try:
        row = conn.execute("SELECT uuid FROM books WHERE path=?", (path,)).fetchone()
        if row:
            book_uuid = row["uuid"]
        elif uuid is not None:
            book_uuid = uuid
        else:
            book_uuid = _new_uuid()
        conn.execute(
            """INSERT INTO books(uuid, name, circle, title, path, cover_path, mtime, is_dlst, cover_hash, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,datetime('now','localtime'))
               ON CONFLICT(path) DO UPDATE SET
                 uuid=excluded.uuid,
                 name=excluded.name, circle=excluded.circle, title=excluded.title,
                 cover_path=excluded.cover_path, mtime=excluded.mtime, is_dlst=excluded.is_dlst,
                 cover_hash=COALESCE(excluded.cover_hash, books.cover_hash),
                 updated_at=excluded.updated_at""",
            (book_uuid, name, circle, title, path, store_cover, mtime, is_dlst, cover_hash_store)
        )
        conn.commit()
        if pages is not None:
            set_book_meta(path, pages=pages)
    finally:
        conn.close()
    cache.invalidate()


def bulk_upsert_books(records):
    """
    books テーブルへの upsert をまとめて1トランザクションで実行する。
    records: [(name, circle, title, path, cover_path, mtime, is_dlst), ...]
    または末尾に cover_hash を省略（NULL）／指定する 8 要素タプル。
    cover_path は保存時に正規化（cover_cache 内は ID のみ）される。
    path は INSERT 前に to_db_path_from_any で DB 用相対パスへ揃える。
    """
    if not records:
        return
    normalized: list[tuple] = []
    conn = get_conn()
    try:
        for r in records:
            try:
                db_path = to_db_path_from_any(r[3])
            except ValueError as exc:
                _logger.warning("bulk_upsert_books: 行をスキップしました: %s", exc)
                continue
            existing = conn.execute("SELECT uuid FROM books WHERE path=?", (db_path,)).fetchone()
            book_uuid = existing["uuid"] if existing else _new_uuid()
            ch: str | None = None
            if len(r) > 7 and r[7] is not None:
                ch_s = str(r[7]).strip()
                ch = ch_s if ch_s else None
            normalized.append(
                (
                    book_uuid,
                    r[0],
                    r[1],
                    r[2],
                    db_path,
                    _normalize_cover_for_save(r[4]) if r[4] else "",
                    r[5],
                    r[6],
                    ch,
                )
            )
    finally:
        conn.close()
    if not normalized:
        return
    conn = get_conn()
    try:
        conn.executemany(
            """INSERT INTO books(uuid, name, circle, title, path, cover_path, mtime, is_dlst, cover_hash, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,datetime('now','localtime'))
               ON CONFLICT(path) DO UPDATE SET
                 uuid=excluded.uuid,
                 name=excluded.name, circle=excluded.circle, title=excluded.title,
                 cover_path=excluded.cover_path, mtime=excluded.mtime, is_dlst=excluded.is_dlst,
                 cover_hash=COALESCE(excluded.cover_hash, books.cover_hash),
                 updated_at=excluded.updated_at""",
            normalized,
        )
        conn.commit()
    finally:
        conn.close()
    cache.invalidate()


def delete_book(path):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM books WHERE path=?", (path,))
        conn.execute("DELETE FROM bookmarks WHERE path=?", (path,))
        conn.execute("DELETE FROM recent_books WHERE path=?", (path,))
        conn.commit()
    finally:
        conn.close()
    cache.invalidate()


def bulk_delete_books(paths):
    """
    複数 path の books / bookmarks レコードをまとめて削除する。
    """
    if not paths:
        return
    # 重複を排除
    unique_paths = list(set(paths))
    conn = get_conn()
    try:
        conn.executemany("DELETE FROM books WHERE path=?", [(p,) for p in unique_paths])
        conn.executemany("DELETE FROM bookmarks WHERE path=?", [(p,) for p in unique_paths])
        conn.commit()
    finally:
        conn.close()
    cache.invalidate()


def bulk_upsert_and_delete_books(
    upsert_records: list[tuple],
    delete_paths: list[str],
) -> None:
    """
    upsertとdeleteを1トランザクションで実行する。
    upsert_records: (uuid, name, circle, title, path, cover_path, mtime, is_dlst, cover_hash) のタプルリスト
    delete_paths: 削除対象のpathリスト
    """
    if not upsert_records and not delete_paths:
        return
    conn = get_conn()
    try:
        for args in upsert_records:
            conn.execute(
                """INSERT INTO books(uuid, name, circle, title, path, cover_path, mtime, is_dlst, cover_hash, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,datetime('now','localtime'))
                   ON CONFLICT(uuid) DO UPDATE SET
                     name=excluded.name, circle=excluded.circle, title=excluded.title,
                     path=excluded.path, cover_path=excluded.cover_path, mtime=excluded.mtime,
                     is_dlst=excluded.is_dlst,
                     cover_hash=COALESCE(excluded.cover_hash, books.cover_hash),
                     missing_since_date=NULL,
                     updated_at=excluded.updated_at""",
                args,
            )
        if delete_paths:
            unique_paths = list(set(delete_paths))
            conn.executemany(
                "DELETE FROM books WHERE path=?", [(p,) for p in unique_paths]
            )
            conn.executemany(
                "DELETE FROM bookmarks WHERE path=?", [(p,) for p in unique_paths]
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    cache.invalidate()


def rename_book(old_path, new_path, new_name, new_circle, new_title, new_cover_path):
    if not old_path:
        return
    try:
        old_rel = to_db_path_from_any(old_path)
        new_rel = to_db_path_from_any(new_path)
    except ValueError as exc:
        _logger.warning("rename_book: パス相対化に失敗したため中止: %s", exc)
        return
    conn = get_conn()
    try:
        # 新しいパスに既存のエントリがある場合は先に削除（UNIQUE制約エラー回避）
        conn.execute("DELETE FROM books WHERE path=? AND path!=?", (new_rel, old_rel))
        conn.execute("DELETE FROM bookmarks WHERE path=? AND path!=?", (new_rel, old_rel))
        conn.execute("DELETE FROM recent_books WHERE path=? AND path!=?", (new_rel, old_rel))

        # cover_custom が旧パス配下なら新パスに差し替え（参照切れ防止）。ID のみの場合はそのまま。
        row = conn.execute("SELECT cover_custom FROM books WHERE path=?", (old_rel,)).fetchone()
        new_cover_custom = None
        if row and row["cover_custom"]:
            cc = row["cover_custom"].strip()
            if os.sep in cc or (len(cc) >= 2 and cc[1] == ":"):
                try:
                    old_fs = _from_db_path(old_rel)
                    new_fs = _from_db_path(new_rel)
                except ValueError:
                    old_fs = ""
                    new_fs = ""
                if old_fs and new_fs:
                    ob = os.path.normpath(old_fs if os.path.isdir(old_fs) else os.path.dirname(old_fs))
                    nb = os.path.normpath(new_fs if os.path.isdir(new_fs) else os.path.dirname(new_fs))
                    cc_norm = os.path.normpath(cc)
                    if cc_norm == ob or cc_norm.startswith(ob + os.sep):
                        new_cover_custom = nb + cc_norm[len(ob) :]
            if new_cover_custom is None:
                new_cover_custom = row["cover_custom"]
        if new_cover_custom is None and row:
            new_cover_custom = row["cover_custom"]

        if new_cover_path:
            cover_path_store = _normalize_cover_for_save(new_cover_path)
            conn.execute(
                """UPDATE books SET path=?, name=?, circle=?, title=?, cover_path=?,
                   updated_at=datetime('now','localtime') WHERE path=?""",
                (new_rel, new_name, new_circle, new_title, cover_path_store, old_rel),
            )
        else:
            conn.execute(
                """UPDATE books SET path=?, name=?, circle=?, title=?,
                   updated_at=datetime('now','localtime') WHERE path=?""",
                (new_rel, new_name, new_circle, new_title, old_rel),
            )
        if new_cover_custom:
            conn.execute(
                "UPDATE books SET cover_custom=? WHERE path=?",
                (new_cover_custom, new_rel),
            )
        # pathを持つ関連テーブルのみ更新
        conn.execute("UPDATE bookmarks SET path=? WHERE path=?", (new_rel, old_rel))
        conn.execute("UPDATE recent_books SET path=? WHERE path=?", (new_rel, old_rel))
        conn.commit()
    finally:
        conn.close()
    cache.invalidate()


def repair_wrong_paths(library_folder: str, on_progress=None):
    """
    パスが「フォルダ名だけ」など誤って登録されているブックを修復する。
    path が絶対パスでない、または実在しない場合に、library_folder 配下で
    名前・サークル/タイトルが一致するフォルダ/ファイルを探して path を正す。
    戻り値: (修復数, エラーメッセージ or None, [(old_path, new_path), ...])
    """
    lib = (library_folder or "").strip()
    if not lib or not os.path.isdir(lib):
        return (0, "ライブラリフォルダが設定されていません。", [])

    def _path_is_wrong(p, lib_root):
        if not p:
            return True
        if os.path.isabs(p):
            return not (os.path.isdir(p) or os.path.isfile(p))
        p = os.path.join(lib_root, p)
        return not (os.path.isdir(p) or os.path.isfile(p))

    def _find_correct_path(name, circle, title, wrong_path):
        """library_folder 配下で name / [circle]title / circle - title に一致する実在パスを返す。"""
        candidates = [
            name,
            format_book_name(circle or "", title or ""),
            f"{circle or ''} - {title or ''}".strip(" -"),
            wrong_path.strip(),
        ]
        try:
            entries = os.listdir(lib)
        except OSError:
            return None
        for entry in entries:
            full = os.path.join(lib, entry)
            if not os.path.isdir(full) and not os.path.isfile(full):
                continue
            # 完全一致
            if entry in candidates or full == os.path.normpath(os.path.abspath(wrong_path)):
                return full
            # サークル・タイトルで一致（フォルダ名をパース）
            c, t = parse_display_name(entry)
            if (c or "", t or "") == (circle or "", title or ""):
                return full
        # 誤った path をフォルダ名としてパースし、作品名が一致するフォルダが1件だけなら採用（例: path="すわショタ - すわショタ" → 実フォルダ"[100円外務省]すわショタ"）
        wrong_c, wrong_t = parse_display_name(wrong_path.strip())
        if wrong_t:
            matches = []
            for entry in entries:
                full = os.path.join(lib, entry)
                if not os.path.isdir(full) and not os.path.isfile(full):
                    continue
                c, t = parse_display_name(entry)
                if (t or "").strip() == wrong_t.strip():
                    matches.append(full)
            if len(matches) == 1:
                return matches[0]
        return None

    rows = get_all_books()
    repaired = []
    for i, r in enumerate(rows):
        name, circle, title, path, cover_path, _ = r[0], r[1], r[2], r[3], r[4], r[5]
        if on_progress:
            on_progress(i + 1, len(rows), path)
        if not _path_is_wrong(path, lib):
            continue
        found_path = _find_correct_path(name, circle, title, path)
        if not found_path:
            continue
        try:
            new_path = to_rel(found_path, lib)
            rename_book(path, new_path, name, circle or "", title or "", cover_path or "")
            repaired.append((path, new_path))
        except Exception as e:
            return (len(repaired), str(e), repaired)
    return (len(repaired), None, repaired)


def resolve_book_path(library_folder: str, name: str, circle: str, title: str, wrong_path: str = ""):
    """
    実在しない path（フォルダ名だけなど）に対して、library_folder 配下で
    名前・サークル/タイトルが一致する実在フォルダ/ファイルのフルパスを返す。
    見つからなければ None。
    """
    lib = (library_folder or "").strip()
    if not lib or not os.path.isdir(lib):
        return None
    candidates = [
        (name or "").strip(),
        format_book_name(circle or "", title or ""),
        f"{circle or ''} - {title or ''}".strip(" -"),
        (wrong_path or "").strip(),
    ]
    try:
        entries = os.listdir(lib)
    except OSError:
        return None
    for entry in entries:
        full = os.path.join(lib, entry)
        if not os.path.isdir(full) and not os.path.isfile(full):
            continue
        if entry in candidates:
            return full
        c, t = parse_display_name(entry)
        if (c or "", t or "") == (circle or "", title or ""):
            return full
    # 誤った path をパースして作品名が一致するフォルダが1件だけなら採用
    _, wrong_t = parse_display_name((wrong_path or "").strip())
    if wrong_t:
        wrong_t = wrong_t.strip()
        matches = []
        for entry in entries:
            full = os.path.join(lib, entry)
            if not os.path.isdir(full) and not os.path.isfile(full):
                continue
            _, t = parse_display_name(entry)
            if (t or "").strip() == wrong_t:
                matches.append(full)
        if len(matches) == 1:
            return matches[0]
    return None


def format_book_name(circle: str, title: str) -> str:
    """
    表示名を組み立て: サークルなし→作品名のみ、あり→[サークル名]作品名。
    """
    c = (circle or "").strip()
    t = (title or "").strip()
    if not c:
        return t
    return f"[{c}]{t}"


def parse_display_name(name: str) -> tuple[str, str]:
    """
    表示名・フォルダ名を (サークル名, 作品名) に分解。
    [サークル名]作品名 または 旧形式の サークル名 - 作品名 に対応。どちらでもなければ ( "", 全体 )。
    """
    if not name or not str(name).strip():
        return ("", "")
    s = str(name).strip()
    m = re.match(r"^\[([^\]]*)\](.*)$", s)
    if m:
        return (m.group(1).strip(), m.group(2).strip())
    parts = s.split(" - ", 1)
    if len(parts) > 1:
        return (parts[0].strip(), parts[1].strip())
    return ("", s)


def bulk_rename_to_current_format(library_folder: str, on_progress=None):
    """
    全書籍のフォルダ/ファイル名を [サークル名]作品名 に一括リネーム。DBの circle/title は保持。
    失敗したものはスキップして続行し、最後に失敗一覧を返す。
    on_progress(current, total, path) を呼ぶ。
    戻り値: (成功数, 初期エラーメッセージ or None, 失敗リスト [(path, 希望した新名, エラー文字列), ...])
    """
    lib = (library_folder or "").strip()
    if not lib or not os.path.isdir(lib):
        return (0, "ライブラリフォルダが設定されていません。", [])

    def _is_lib_root(p):
        if not p:
            return False
        return os.path.normpath(os.path.abspath(p)) == os.path.normpath(os.path.abspath(lib))

    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT path, name, circle, title,
                      COALESCE(NULLIF(cover_custom,''), cover_path) AS cover
               FROM books"""
        ).fetchall()
    finally:
        conn.close()

    renamed = 0
    failed = []
    for i, r in enumerate(rows):
        path = r["path"]
        name = r["name"]
        circle = r["circle"] or ""
        title = r["title"] or ""
        cover = r["cover"] or ""
        if on_progress:
            on_progress(i + 1, len(rows), path)
        new_name = format_book_name(circle, title)
        if new_name == name:
            continue
        if not os.path.exists(path):
            failed.append((path, new_name, "ファイル・フォルダが存在しません"))
            continue
        def _updated_cover(old_base: str, new_base: str, cover_path: str) -> str:
            """リネームに伴い、カバーが旧パス配下なら新パスに差し替える"""
            if not cover_path:
                return cover_path
            ob = os.path.normpath(old_base)
            nb = os.path.normpath(new_base)
            cp = os.path.normpath(cover_path)
            if cp == ob or cp.startswith(ob + os.sep):
                return nb + cp[len(ob):]
            return cover_path

        try:
            if os.path.isdir(path):
                if _is_lib_root(path):
                    continue
                base_dir = os.path.dirname(path)
                new_path = os.path.join(base_dir, new_name)
                if new_path != path:
                    os.rename(path, new_path)
                    new_cover = _updated_cover(path, new_path, cover)
                    rename_book(path, new_path, new_name, circle, title, new_cover)
                    renamed += 1
            else:
                parent_dir = os.path.dirname(path)
                if _is_lib_root(parent_dir):
                    ext = os.path.splitext(path)[1]
                    new_path = os.path.join(parent_dir, new_name + ext)
                    if new_path != path:
                        os.rename(path, new_path)
                        rename_book(path, new_path, new_name, circle, title, cover)
                        renamed += 1
                else:
                    grand = os.path.dirname(parent_dir)
                    new_parent = os.path.join(grand, new_name)
                    if new_parent != parent_dir:
                        os.rename(parent_dir, new_parent)
                    # フォルダ内の元ファイルも新名＋拡張子にリネーム
                    ext = os.path.splitext(path)[1]
                    current_file = os.path.join(new_parent, os.path.basename(path))
                    new_path = os.path.join(new_parent, new_name + ext)
                    if current_file != new_path and os.path.isfile(current_file):
                        os.rename(current_file, new_path)
                    new_cover = _updated_cover(parent_dir, new_parent, cover)
                    rename_book(path, new_path, new_name, circle, title, new_cover)
                    renamed += 1
        except Exception as e:
            failed.append((path, new_name, str(e)))
    cache.invalidate()
    return (renamed, None, failed)


def update_book_display(path: str, circle: str | None = None, title: str | None = None, name: str | None = None):
    """books テーブルの表示用フィールドのみ更新（フォルダのリネームは行わない）。一括編集用。"""
    if not path:
        return
    lib_root = os.path.normpath((get_setting("library_folder") or "").strip())
    path = to_rel(path, lib_root)
    conn = get_conn()
    try:
        row = conn.execute("SELECT name, circle, title FROM books WHERE path=?", (path,)).fetchone()
        if not row:
            return
        cur_name = row["name"] or ""
        cur_circle = row["circle"] or ""
        cur_title = row["title"] or ""
        new_name = name if name is not None else cur_name
        new_circle = circle if circle is not None else cur_circle
        new_title = title if title is not None else cur_title
        if new_name == cur_name and new_circle == cur_circle and new_title == cur_title:
            return
        if name is None and (circle is not None or title is not None):
            new_name = format_book_name(new_circle, new_title)
        conn.execute(
            """UPDATE books SET name=?, circle=?, title=?, updated_at=datetime('now','localtime') WHERE path=?""",
            (new_name, new_circle, new_title, path),
        )
        conn.commit()
        cache.invalidate()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  bookmarks 読み書き
# ══════════════════════════════════════════════════════

def get_all_bookmarks():
    """{ path: rating } の dict を返す"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT path, rating FROM bookmarks").fetchall()
        return {r["path"]: r["rating"] for r in rows}
    finally:
        conn.close()


def set_bookmark(path, rating):
    if not path:
        return
    lib_root = os.path.normpath((get_setting("library_folder") or "").strip())
    path = to_rel(path, lib_root)
    conn = get_conn()
    try:
        if rating == 0:
            conn.execute("DELETE FROM bookmarks WHERE path=?", (path,))
        else:
            conn.execute(
                """INSERT INTO bookmarks(path, rating, updated_at)
                   VALUES(?,?,datetime('now','localtime'))
                   ON CONFLICT(path) DO UPDATE SET
                     rating=excluded.rating, updated_at=excluded.updated_at""",
                (path, rating)
            )
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  recent_books 読み書き
# ══════════════════════════════════════════════════════

def get_recent_books(limit=10):
    """[(name, path), ...] を新しい順で返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT name, path FROM recent_books ORDER BY opened_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [(r["name"], r["path"]) for r in rows]
    finally:
        conn.close()


def add_recent_book(name, path):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO recent_books(path, name, opened_at)
               VALUES(?,?,datetime('now','localtime'))
               ON CONFLICT(path) DO UPDATE SET
                 name=excluded.name, opened_at=excluded.opened_at""",
            (path, name)
        )
        # 11件目以降を削除
        conn.execute("""
            DELETE FROM recent_books WHERE path NOT IN (
                SELECT path FROM recent_books ORDER BY opened_at DESC LIMIT 10
            )
        """)
        conn.commit()
    finally:
        conn.close()


def remove_recent_book(path):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM recent_books WHERE path=?", (path,))
        conn.commit()
    finally:
        conn.close()


def get_book_name_by_path(path: str):
    """path に対応する books の name（表示名）を返す。無ければ None。"""
    if not path:
        return None
    conn = get_conn()
    try:
        row = conn.execute("SELECT name FROM books WHERE path=?", (path,)).fetchone()
        return row["name"] if row else None
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  バックアップ
# ══════════════════════════════════════════════════════

def create_backup():
    """
    起動時に呼ぶ。library.dbをバックアップフォルダにコピーし、
    MAX_BACKUPS件を超えた古いものを削除する。
    DBが存在しない場合は何もしない。
    """
    if not os.path.exists(DB_FILE):
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"library_{timestamp}.db")
    shutil.copy2(DB_FILE, backup_path)

    # 古いバックアップを削除
    _cleanup_backups()
    return backup_path


def _cleanup_backups():
    """MAX_BACKUPSを超えた古いバックアップを削除"""
    if not os.path.exists(BACKUP_DIR):
        return
    files = sorted([
        f for f in os.listdir(BACKUP_DIR)
        if f.startswith("library_") and f.endswith(".db")
    ])
    while len(files) > MAX_BACKUPS:
        old = os.path.join(BACKUP_DIR, files.pop(0))
        try:
            os.remove(old)
        except Exception:
            pass


def list_backups():
    """
    バックアップ一覧を新しい順で返す。
    [{"filename": str, "path": str, "datetime": str, "size_kb": int}, ...]
    """
    if not os.path.exists(BACKUP_DIR):
        return []
    result = []
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if f.startswith("library_") and f.endswith(".db"):
            full = os.path.join(BACKUP_DIR, f)
            # ファイル名から日時をパース: library_YYYYMMDD_HHMMSS.db
            try:
                ts = f[len("library_"):-len(".db")]
                dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
                dt_str = dt.strftime("%Y/%m/%d %H:%M:%S")
            except Exception:
                dt_str = f
            size_kb = os.path.getsize(full) // 1024
            result.append({
                "filename": f,
                "path":     full,
                "datetime": dt_str,
                "size_kb":  size_kb,
            })
    return result


def restore_backup(backup_path):
    """
    指定バックアップをlibrary.dbに上書き復元する。
    復元前に現在のDBをbackups/pre_restore_*.dbとして保存する。
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"バックアップが見つかりません: {backup_path}")

    os.makedirs(BACKUP_DIR, exist_ok=True)

    # 復元前の現DBを保存
    if os.path.exists(DB_FILE):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pre = os.path.join(BACKUP_DIR, f"library_pre_restore_{timestamp}.db")
        shutil.copy2(DB_FILE, pre)

    shutil.copy2(backup_path, DB_FILE)
    _cleanup_backups()


# ══════════════════════════════════════════════════════
#  book_meta 読み書き（作者・タイプ・シリーズ）
# ══════════════════════════════════════════════════════

def get_book_meta(path):
    """
    1冊分のメタ情報を dict で返す。
    {
        "author": "", "type": "", "series": "", "dlsite_id": "",
        "title_kana": "", "circle_kana": "",
        "pages": int | None, "release_date": "", "price": int | None, "memo": "",
        "characters": [...], "tags": [...]
    }
    """
    conn = get_conn()
    try:
        lookup_path = path
        # 絶対パスで渡された場合はDB保存形式（相対パス）に揃えて検索する
        if isinstance(path, str):
            if os.path.isabs(path):
                try:
                    lookup_path = _to_db_path(path)
                except ValueError:
                    lookup_path = path
            elif os.path.dirname(path) == "":
                # ストアファイル名のみ（例: .dlst）で渡るケースはそのまま検索
                lookup_path = path
        book_uuid = _get_book_uuid(conn, lookup_path)
        if not book_uuid:
            return {
                "author": "",
                "type": "",
                "series": "",
                "dlsite_id": "",
                "title_kana": "",
                "circle_kana": "",
                "pages": None,
                "release_date": "",
                "price": None,
                "memo": "",
                "store_url": "",
                "characters": [],
                "tags": [],
            }
        row = conn.execute(
            "SELECT author, type, series, dlsite_id, title_kana, circle_kana, "
            "pages, release_date, price, memo, store_url "
            "FROM book_meta WHERE uuid=?",
            (book_uuid,)
        ).fetchone()
        meta = {
            "author":      row["author"]      if row else "",
            "type":        row["type"]        if row else "",
            "series":      row["series"]      if row else "",
            "dlsite_id":   row["dlsite_id"]   if row and row["dlsite_id"] else "",
            "title_kana":  row["title_kana"]  if row and row["title_kana"] is not None else "",
            "circle_kana": row["circle_kana"] if row and row["circle_kana"] is not None else "",
            "pages":       row["pages"]       if row is not None else None,
            "release_date": row["release_date"] if row and row["release_date"] is not None else "",
            "price":        row["price"]        if row is not None else None,
            "memo":         row["memo"]         if row and row["memo"] is not None else "",
            "store_url":    row["store_url"]    if row and row["store_url"] is not None else "",
        }
        chars = conn.execute(
            "SELECT character FROM book_characters WHERE uuid=? ORDER BY character", (book_uuid,)
        ).fetchall()
        tags = conn.execute(
            "SELECT tag FROM book_tags WHERE uuid=? ORDER BY tag", (book_uuid,)
        ).fetchall()
        meta["characters"] = [r["character"] for r in chars]
        meta["tags"]        = [r["tag"]       for r in tags]
        return meta
    finally:
        conn.close()


def get_all_book_metas() -> dict[str, dict]:
    """全書籍のメタデータを {path: meta_dict} で返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT b.path, m.uuid, m.author, m.type, m.series, m.dlsite_id, m.title_kana, m.circle_kana, "
            "m.pages, m.release_date, m.price, m.memo FROM books b LEFT JOIN book_meta m ON b.uuid = m.uuid"
        ).fetchall()
        chars = conn.execute(
            "SELECT b.path, c.character FROM books b INNER JOIN book_characters c ON b.uuid = c.uuid ORDER BY b.path, c.character"
        ).fetchall()
        tags = conn.execute(
            "SELECT b.path, t.tag FROM books b INNER JOIN book_tags t ON b.uuid = t.uuid ORDER BY b.path, t.tag"
        ).fetchall()

        meta_map: dict[str, dict] = {}
        for r in rows:
            path = r["path"]
            meta_map[path] = {
                "author":      r["author"]      or "",
                "type":        r["type"]        or "",
                "series":      r["series"]      or "",
                "dlsite_id":   r["dlsite_id"]   or "",
                "title_kana":  r["title_kana"]  or "",
                "circle_kana": r["circle_kana"] or "",
                "pages":       r["pages"],
                "release_date": r["release_date"] or "",
                "price":        r["price"],
                "memo":         r["memo"] or "",
                "characters": [],
                "tags": [],
            }

        for r in chars:
            path = r["path"]
            if path not in meta_map:
                meta_map[path] = {
                    "author": "", "type": "", "series": "", "dlsite_id": "",
                    "title_kana": "", "circle_kana": "",
                    "pages": None, "release_date": "", "price": None, "memo": "",
                    "characters": [], "tags": [],
                }
            meta_map[path]["characters"].append(r["character"])

        for r in tags:
            path = r["path"]
            if path not in meta_map:
                meta_map[path] = {
                    "author": "", "type": "", "series": "", "dlsite_id": "",
                    "title_kana": "", "circle_kana": "",
                    "pages": None, "release_date": "", "price": None, "memo": "",
                    "characters": [], "tags": [],
                }
            meta_map[path]["tags"].append(r["tag"])

        return meta_map
    finally:
        conn.close()


def has_metadata(path):
    """
    メタデータが設定されているか（DLSite IDがあるか）
    """
    conn = get_conn()
    try:
        book_uuid = _get_book_uuid(conn, path)
        if not book_uuid:
            return False
        row = conn.execute(
            "SELECT dlsite_id FROM book_meta WHERE uuid=? AND dlsite_id != ''", (book_uuid,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_paths_with_metadata():
    """メタデータが設定されている（作品IDあり・除外でない）book pathのセットを返す（booksテーブルに存在するもののみ）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT b.path FROM books b
               INNER JOIN book_meta m ON b.uuid = m.uuid
               WHERE m.dlsite_id != '' AND m.excluded = 0"""
        ).fetchall()
        return {r["path"] for r in rows}
    finally:
        conn.close()


def get_paths_excluded():
    """除外されているbook pathのセットを返す（booksテーブルに存在するもののみ）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT b.path FROM books b
               INNER JOIN book_meta m ON b.uuid = m.uuid
               WHERE m.excluded = 1"""
        ).fetchall()
        return {r["path"] for r in rows}
    finally:
        conn.close()


def set_excluded(path, excluded=True):
    """除外フラグを設定"""
    conn = get_conn()
    try:
        book_uuid = _get_book_uuid(conn, path)
        if not book_uuid:
            return
        conn.execute(
            """INSERT INTO book_meta(uuid, excluded, updated_at)
               VALUES(?, ?, datetime('now','localtime'))
               ON CONFLICT(uuid) DO UPDATE SET
                 excluded=excluded.excluded, updated_at=excluded.updated_at""",
            (book_uuid, 1 if excluded else 0)
        )
        conn.commit()
    finally:
        conn.close()


def is_excluded(path):
    """除外されているか"""
    conn = get_conn()
    try:
        book_uuid = _get_book_uuid(conn, path)
        if not book_uuid:
            return False
        row = conn.execute("SELECT excluded FROM book_meta WHERE uuid=?", (book_uuid,)).fetchone()
        return row is not None and row["excluded"] == 1
    finally:
        conn.close()


def _effective_meta_source(meta_source: str, dlsite_id: str) -> str:
    """meta_source が空なら dlsite_id から推定。戻り値: dlsite, fanza, とらのあな, 同人DB, other のいずれか。
    - URL に dojindb.net を含む → 同人DB
    - 作品IDが 040/042 始まり → とらのあな（DLSite API とらのあな）
    - RJ/BJ/VJ → dlsite、D_ → fanza
    """
    if (meta_source or "").strip():
        return (meta_source or "").strip()
    raw = (dlsite_id or "").strip()
    if not raw:
        return ""
    # URL 参照: dojindb.net を含む → 同人DB
    if "dojindb.net" in raw:
        return "同人DB"
    did = raw.upper()
    if did.startswith("RJ") or did.startswith("BJ") or did.startswith("VJ"):
        return "dlsite"
    if did.startswith("D_"):
        return "fanza"
    # 作品ID 040/042 始まり → とらのあな（DLSite API）
    if raw.startswith("040") or raw.startswith("042"):
        return "とらのあな"
    return "other"


def get_meta_source_counts():
    """メタデータ取得状況を作品ID（dlsite_id）欄で集計。(source_key, label, count) のリスト。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT b.path, m.dlsite_id, m.excluded
               FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid"""
        ).fetchall()
        from collections import Counter
        excluded_count = sum(1 for r in rows if r["excluded"] == 1)
        acquired = [r for r in rows if r["excluded"] != 1]
        source_counts = Counter()
        for r in acquired:
            # 作品ID（dlsite_id）のみで取得元を判定
            dlsite_id = (r["dlsite_id"] or "").strip()
            if not dlsite_id:
                continue  # 未取得は別枠で数える
            src = _effective_meta_source("", dlsite_id)
            if not src:
                src = "other"
            source_counts[src] += 1
        not_acquired_count = conn.execute(
            """SELECT COUNT(*) FROM books b
               LEFT JOIN book_meta m ON b.uuid = m.uuid
               WHERE (m.uuid IS NULL OR ((m.dlsite_id IS NULL OR m.dlsite_id = '') AND COALESCE(m.excluded,0) = 0))"""
        ).fetchone()[0]
        label_map = {
            "not_acquired": "未取得",
            "dlsite": "DLSite",
            "fanza": "FANZA",
            "とらのあな": "とらのあな",
            "同人DB": "同人DB",
            "other": "その他",
            "excluded": "除外",
        }
        result = [("not_acquired", "未取得", not_acquired_count)]
        for key in ("dlsite", "fanza", "とらのあな", "同人DB", "other"):
            result.append((key, label_map[key], source_counts.get(key, 0)))
        result.append(("excluded", "除外", excluded_count))
        return result
    finally:
        conn.close()


def get_books_by_meta_source(source_key: str):
    """メタデータ取得元でフィルタ。(name, circle, title, path, cover_path) のタプルリスト。source_key: not_acquired, dlsite, fanza, とらのあな, 同人DB, other, excluded."""
    conn = get_conn()
    try:
        if source_key == "excluded":
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path,
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                WHERE m.excluded = 1 ORDER BY b.name
            """).fetchall()
            return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
        if source_key == "not_acquired":
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path,
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                FROM books b LEFT JOIN book_meta m ON b.uuid = m.uuid
                WHERE (m.uuid IS NULL OR (COALESCE(m.dlsite_id,'') = '' AND COALESCE(m.excluded,0) = 0))
                ORDER BY b.name
            """).fetchall()
            return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
        # 取得済みのうち作品ID（dlsite_id）の形式で絞り込み
        if source_key == "とらのあな":
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path,
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                WHERE m.excluded = 0 AND (m.dlsite_id LIKE '040%%' OR m.dlsite_id LIKE '042%%')
                ORDER BY b.name
            """).fetchall()
            return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
        elif source_key == "同人DB":
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path,
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                WHERE m.excluded = 0 AND m.dlsite_id LIKE '%%dojindb.net%%'
                ORDER BY b.name
            """).fetchall()
            return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
        else:
            if source_key == "dlsite":
                # RJ / BJ / VJ は DLSite 形式（DLSITE_API 対応）
                rows = conn.execute("""
                    SELECT b.name, b.circle, b.title, b.path,
                           COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                    FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                    WHERE m.excluded = 0 AND (
                        m.dlsite_id LIKE 'RJ%' OR m.dlsite_id LIKE 'BJ%' OR m.dlsite_id LIKE 'VJ%'
                    )
                    ORDER BY b.name
                """).fetchall()
            elif source_key == "fanza":
                rows = conn.execute("""
                    SELECT b.name, b.circle, b.title, b.path,
                           COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                    FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                    WHERE m.excluded = 0 AND m.dlsite_id LIKE 'D_%'
                    ORDER BY b.name
                """).fetchall()
            else:  # other（作品IDの形式で other になるもの）
                rows = conn.execute("""
                    SELECT b.name, b.circle, b.title, b.path,
                           COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path,
                           m.dlsite_id
                    FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                    WHERE m.excluded = 0 AND m.dlsite_id != '' AND m.dlsite_id IS NOT NULL
                    ORDER BY b.name
                """).fetchall()
                filtered = []
                for r in rows:
                    if _effective_meta_source("", r["dlsite_id"] or "") == "other":
                        filtered.append((r["name"], r["circle"], r["title"], r["path"], r["cover_path"]))
                return filtered
        return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
    finally:
        conn.close()


def get_books_by_metadata_status(status):
    """
    メタデータ取得状況でブックをフィルタリング
    status: "acquired" (取得済み), "not_acquired" (未取得), "excluded" (除外)
    返り値: (name, circle, title, path, cover_path) のタプルリスト
    """
    conn = get_conn()
    try:
        if status == "acquired":
            # 作品IDあり、除外でない
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path, 
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path 
                FROM books b
                INNER JOIN book_meta m ON b.uuid = m.uuid
                WHERE m.dlsite_id != '' AND m.excluded = 0
                ORDER BY b.name
            """).fetchall()
        elif status == "excluded":
            # 除外フラグあり
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path, 
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path 
                FROM books b
                INNER JOIN book_meta m ON b.uuid = m.uuid
                WHERE m.excluded = 1
                ORDER BY b.name
            """).fetchall()
        else:  # not_acquired
            # 作品IDなし、除外でない（または book_meta にエントリなし）
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path, 
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path 
                FROM books b
                LEFT JOIN book_meta m ON b.uuid = m.uuid
                WHERE (m.uuid IS NULL OR (m.dlsite_id = '' AND m.excluded = 0))
                ORDER BY b.name
            """).fetchall()
        return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
    finally:
        conn.close()


def set_book_meta(
    path,
    author: str = "",
    type_: str = "",
    series: str = "",
    characters=None,
    tags=None,
    dlsite_id=UNSET,
    title_kana: str | None = UNSET,
    circle_kana: str | None = UNSET,
    pages: int | None = UNSET,
    release_date: str | None = UNSET,
    price: int | None = UNSET,
    memo: str | None = UNSET,
    meta_source: str | None = UNSET,
    store_url: str | None = UNSET,
):
    """
    メタ情報を保存。characters/tagsはリスト。
    dlsite_id / title_kana / circle_kana / pages / release_date / price / memo / meta_source / store_url が
    UNSET の場合は既存値を維持する。None を渡すと明示的に NULL で上書きする。
    meta_source は dlsite, fanza, とらのあな, 同人DB, other のいずれか（取得元の振り分け用）。
    同時にbooksテーブルのcover_customも必要なら別途set_cover_custom()を呼ぶ。
    """
    if not path:
        return
    lib_root = os.path.normpath((get_setting("library_folder") or "").strip())
    path = to_rel(path, lib_root)
    conn = get_conn()
    try:
        lookup_path = path
        # 絶対パスで渡された場合はDB保存形式（相対パス）に揃えて検索する
        if isinstance(path, str):
            if os.path.isabs(path):
                try:
                    lookup_path = _to_db_path(path)
                except ValueError:
                    lookup_path = path
            elif os.path.dirname(path) == "":
                # ストアファイル名のみ（例: .dlst）で渡るケースはそのまま検索
                lookup_path = path
        book_uuid = _get_book_uuid(conn, lookup_path)
        if not book_uuid:
            return
        # 既存値を取得して、None のフィールドは既存値を維持
        cur = conn.execute(
            "SELECT dlsite_id, title_kana, circle_kana, pages, release_date, price, memo, meta_source, store_url "
            "FROM book_meta WHERE uuid=?",
            (book_uuid,),
        ).fetchone()

        cur_dlsite_id   = cur["dlsite_id"]   if cur else ""
        cur_title_kana  = cur["title_kana"]  if cur else ""
        cur_circle_kana = cur["circle_kana"] if cur else ""
        cur_pages       = cur["pages"]       if cur else None
        cur_release     = cur["release_date"] if cur else ""
        cur_price       = cur["price"]        if cur else None
        cur_memo        = cur["memo"]         if cur else ""
        cur_meta_source = (cur["meta_source"] or "") if cur else ""
        cur_store_url   = (cur["store_url"] or "") if cur else ""

        new_dlsite_id   = dlsite_id   if dlsite_id   is not UNSET else cur_dlsite_id
        new_title_kana  = title_kana  if title_kana  is not UNSET else cur_title_kana
        new_circle_kana = circle_kana if circle_kana is not UNSET else cur_circle_kana
        new_pages       = pages       if pages       is not UNSET else cur_pages
        new_release     = release_date if release_date is not UNSET else cur_release
        new_price       = price       if price       is not UNSET else cur_price
        new_memo        = memo        if memo        is not UNSET else cur_memo
        new_meta_source = (meta_source.strip() if meta_source is not UNSET and meta_source and meta_source.strip() else cur_meta_source or "")
        new_store_url   = store_url   if store_url   is not UNSET else cur_store_url

        conn.execute(
            """INSERT INTO book_meta(
                   uuid, author, type, series,
                   dlsite_id, title_kana, circle_kana,
                   pages, release_date, price, memo, meta_source, store_url,
                   updated_at
               )
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))
               ON CONFLICT(uuid) DO UPDATE SET
                 author=excluded.author,
                 type=excluded.type,
                 series=excluded.series,
                 dlsite_id=excluded.dlsite_id,
                 title_kana=excluded.title_kana,
                 circle_kana=excluded.circle_kana,
                 pages=excluded.pages,
                 release_date=excluded.release_date,
                 price=excluded.price,
                 memo=excluded.memo,
                 meta_source=excluded.meta_source,
                 store_url=excluded.store_url,
                 updated_at=excluded.updated_at""",
            (
                book_uuid,
                author or "",
                type_ or "",
                series or "",
                new_dlsite_id or "",
                new_title_kana or "",
                new_circle_kana or "",
                new_pages,
                new_release or "",
                new_price,
                new_memo or "",
                new_meta_source or "",
                new_store_url or "",
            ),
        )
        # キャラクター・タグは全削除→再挿入（None のときはスキップ）
        if characters is not None:
            conn.execute("DELETE FROM book_characters WHERE uuid=?", (book_uuid,))
            for c in characters:
                c = c.strip()
                if c:
                    conn.execute(
                        "INSERT OR IGNORE INTO book_characters(uuid, character) VALUES(?,?)", (book_uuid, c)
                    )
        if tags is not None:
            conn.execute("DELETE FROM book_tags WHERE uuid=?", (book_uuid,))
            for t in tags:
                t = t.strip()
                if t:
                    conn.execute(
                        "INSERT OR IGNORE INTO book_tags(uuid, tag) VALUES(?,?)", (book_uuid, t)
                    )
        conn.commit()
    finally:
        conn.close()
    cache.invalidate()


def set_cover_custom(path, cover_path):
    """カスタムカバー画像パスをbooksテーブルに保存。cover_cache 内は ID のみ保存する。"""
    if not path:
        return
    lib_root = os.path.normpath((get_setting("library_folder") or "").strip())
    path = to_rel(path, lib_root)
    store = _normalize_cover_for_save(cover_path) if cover_path else ""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE books SET cover_custom=? WHERE path=?", (store, path)
        )
        conn.commit()
    finally:
        conn.close()


def get_cover_custom(path):
    """カスタムカバーパスを返す（未設定ならNone）"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT cover_custom FROM books WHERE path=?", (path,)
        ).fetchone()
        return row["cover_custom"] if row else None
    finally:
        conn.close()


def cleanup_invalid_cover_custom():
    """存在しないファイルを指すcover_customをクリアする。DB値は ID の場合は resolve してから存在チェック。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT path, cover_custom FROM books WHERE cover_custom != '' AND cover_custom IS NOT NULL"
        ).fetchall()
        cleared_count = 0
        for row in rows:
            if not row["cover_custom"]:
                continue
            resolved = resolve_cover_stored_value(row["cover_custom"])
            if resolved and not os.path.exists(resolved):
                conn.execute("UPDATE books SET cover_custom='' WHERE path=?", (row["path"],))
                cleared_count += 1
        if cleared_count > 0:
            conn.commit()
    finally:
        conn.close()


def clear_all_caches():
    """
    thumb_cache（グリッド用サムネPNG）のみ全削除。
    cover_cache（PDF/dmme/dlst/切り抜き等の元画像）は参照されているものは残し、未使用のみ削除。
    戻り値: (削除したファイル数, エラーメッセージ or None)。
    """
    try:
        import config
    except ImportError:
        return (0, "config の読み込みに失敗しました")
    removed = 0
    # グリッド用サムネキャッシュのみ全削除（カード表示用に再生成される）
    if os.path.isdir(config.CACHE_DIR):
        try:
            for name in os.listdir(config.CACHE_DIR):
                full = os.path.join(config.CACHE_DIR, name)
                if os.path.isfile(full):
                    os.remove(full)
                    removed += 1
        except Exception as e:
            return (removed, str(e))
    # cover_cache は未使用ファイルだけ削除（PDF/dmme/dlst/切り抜き画像は保持）
    cleanup_unused_cover_cache()
    return (removed, None)


def _normalize_cover_for_save(cover_path: str) -> str:
    """
    カバーパスをDB保存用に正規化する。
    cover_cache 配下のパスは ID（ファイル名）のみ保存し、それ以外はそのまま保存する。
    これにより cleanup はフルパスに依存せず、COVER_CACHE_DIR + ID で一意に判定できる。
    """
    if not cover_path or not str(cover_path).strip():
        return ""
    try:
        import config
    except ImportError:
        return cover_path.strip()
    v = str(cover_path).strip()
    # すでに ID のみ（パス区切り・ドライブレターなし）の場合はそのまま
    if os.sep not in v and (len(v) < 2 or v[1] != ":"):
        return v
    full = os.path.normpath(os.path.abspath(v))
    cover_dir_norm = os.path.normpath(os.path.abspath(config.COVER_CACHE_DIR))
    if full.startswith(cover_dir_norm):
        return os.path.basename(full)
    return v


def resolve_cover_stored_value(stored: str) -> str:
    """
    DBに保存された cover_path / cover_custom を表示・参照用のフルパスに解決する。
    - 空 → 空文字
    - ID のみ（パス区切りなし）→ COVER_CACHE_DIR 内のファイルとして結合
    - 絶対パス → そのまま正規化
    - 相対パス → APP_BASE 基準で解決
    """
    if not stored or not str(stored).strip():
        return ""
    try:
        import config
    except ImportError:
        return stored.strip()
    p = str(stored).strip()
    # ID のみ（cover_cache 内のファイル名だけ保存されている場合）
    if os.sep not in p and (len(p) < 2 or p[1] != ":"):
        resolved = os.path.normpath(os.path.join(config.COVER_CACHE_DIR, p))
        return os.path.abspath(resolved)
    if os.path.isabs(p):
        return os.path.normpath(os.path.abspath(p))
    app_base = getattr(config, "APP_BASE", os.path.dirname(config.COVER_CACHE_DIR))
    resolved = os.path.normpath(os.path.join(app_base, p))
    return os.path.abspath(resolved)


def _resolve_cover_path_for_cleanup(p: str) -> str | None:
    """DBに保存されたカバーパスを、cleanup 用の絶対パスに変換。ID の場合は cover_cache と結合。"""
    resolved = resolve_cover_stored_value(p) if p else ""
    return resolved if resolved else None


def cleanup_unused_cover_cache():
    """cover_cache内の、どの書籍からも参照されていない画像を削除する。使用中のサムネは絶対に削除しない。"""
    try:
        import config
    except ImportError:
        return
    cover_dir = config.COVER_CACHE_DIR
    if not os.path.isdir(cover_dir):
        return
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT cover_path, cover_custom FROM books"
        ).fetchall()
    finally:
        conn.close()
    used = set()
    for row in rows:
        for i, key in enumerate(("cover_path", "cover_custom")):
            try:
                p = row[i]
            except (IndexError, TypeError):
                p = None
            resolved = _resolve_cover_path_for_cleanup(p)
            if resolved:
                used.add(resolved)
    try:
        for name in os.listdir(cover_dir):
            full = os.path.join(cover_dir, name)
            if not os.path.isfile(full):
                continue
            try:
                full_norm = os.path.normpath(os.path.abspath(full))
                if full_norm not in used:
                    os.remove(full)
            except Exception:
                pass
    except Exception:
        pass


def cleanup_invalid_paths():
    """存在しないフォルダを指すブックをDBから削除する"""
    import os
    conn = get_conn()
    try:
        rows = conn.execute("SELECT path FROM books").fetchall()
        deleted_count = 0
        for row in rows:
            if row["path"] and not os.path.exists(row["path"]):
                # books削除時にbook_meta/tag/characterはFK CASCADEで削除
                conn.execute("DELETE FROM books WHERE path=?", (row["path"],))
                conn.execute("DELETE FROM bookmarks WHERE path=?", (row["path"],))
                conn.execute("DELETE FROM recent_books WHERE path=?", (row["path"],))
                deleted_count += 1
        if deleted_count > 0:
            conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  ショートカット設定 読み書き
# ══════════════════════════════════════════════════════

# デフォルトショートカット定義
DEFAULT_SHORTCUTS = {
    "open":        "o",
    "bookmark":    "f",
    "rename":      "m",
    "properties":  "r",
    "explorer":    "i",
    "go_circle":   "g",
    "go_all":      "ctrl+a",
    "delete":      "d",
}

def get_shortcuts():
    """現在のショートカット設定を dict で返す。未設定はデフォルト値を使用。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE 'shortcut_%'"
        ).fetchall()
        saved = {r["key"].replace("shortcut_", ""): r["value"] for r in rows}
        # デフォルトとマージ（保存済み優先）
        result = dict(DEFAULT_SHORTCUTS)
        result.update(saved)
        return result
    finally:
        conn.close()


def set_shortcuts(shortcuts: dict):
    """ショートカット設定を一括保存。空文字は「未割り当て」として保存。"""
    conn = get_conn()
    try:
        for action, key in shortcuts.items():
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (f"shortcut_{action}", key.lower().strip() if key else "")
            )
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  検索バー用候補取得
# ══════════════════════════════════════════════════════

def get_all_tags():
    """登録済みタグを重複なしで返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT DISTINCT t.tag
               FROM book_tags t
               INNER JOIN books b ON t.uuid = b.uuid
               ORDER BY t.tag"""
        ).fetchall()
        return [r["tag"] for r in rows]
    finally:
        conn.close()


def get_all_tags_with_count():
    """(タグ, 作品数) のリストを作品数の多い順で返す（booksテーブルに存在するもののみ）"""
    return cache.get(CACHE_KEY_TAGS_WITH_COUNT, _fetch_tags_with_count)


def _fetch_tags_with_count():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT t.tag, COUNT(DISTINCT t.uuid) AS cnt 
               FROM book_tags t
               INNER JOIN books b ON t.uuid = b.uuid
               GROUP BY t.tag ORDER BY cnt DESC, t.tag"""
        ).fetchall()
        return [(r["tag"], r["cnt"]) for r in rows]
    finally:
        conn.close()


def get_all_circles_with_count():
    """(サークル名, 作品数) のリストを作品数の多い順で返す"""
    return cache.get(CACHE_KEY_CIRCLES_WITH_COUNT, _fetch_circles_with_count)


def _fetch_circles_with_count():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT circle, COUNT(*) as cnt FROM books
               WHERE circle IS NOT NULL AND circle != ''
               GROUP BY circle ORDER BY cnt DESC, circle"""
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()


def get_all_characters():
    """登録済みキャラクターを重複なしで返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT DISTINCT c.character
               FROM book_characters c
               INNER JOIN books b ON c.uuid = b.uuid
               ORDER BY c.character"""
        ).fetchall()
        return [r["character"] for r in rows]
    finally:
        conn.close()


def get_all_characters_with_count():
    """(キャラクター, 作品数) のリストを作品数の多い順で返す（booksテーブルに存在するもののみ）"""
    return cache.get(CACHE_KEY_CHARACTERS_WITH_COUNT, _fetch_characters_with_count)


def _fetch_characters_with_count():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT c.character, COUNT(DISTINCT c.uuid) AS cnt 
               FROM book_characters c
               INNER JOIN books b ON c.uuid = b.uuid
               GROUP BY c.character ORDER BY cnt DESC, c.character"""
        ).fetchall()
        return [(r["character"], r["cnt"]) for r in rows]
    finally:
        conn.close()


def get_all_authors():
    """登録済み作者を重複なしで返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT author FROM book_meta WHERE author != '' ORDER BY author"
        ).fetchall()
        return [r["author"] for r in rows]
    finally:
        conn.close()


def get_all_authors_with_count():
    """(作者, 作品数) のリストを作品数の多い順で返す（booksテーブルに存在するもののみ）"""
    return cache.get(CACHE_KEY_AUTHORS_WITH_COUNT, _fetch_authors_with_count)


def _fetch_authors_with_count():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT m.author, COUNT(m.uuid) AS cnt 
               FROM book_meta m
               INNER JOIN books b ON m.uuid = b.uuid
               WHERE m.author != '' 
               GROUP BY m.author ORDER BY cnt DESC, m.author"""
        ).fetchall()
        return [(r["author"], r["cnt"]) for r in rows]
    finally:
        conn.close()


def get_paths_with_author():
    """authorが設定されているbookのpathリストを返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT b.path
               FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
               WHERE m.author != ''"""
        ).fetchall()
        return [r["path"] for r in rows]
    finally:
        conn.close()


def get_paths_with_tag():
    """タグが1件以上あるbookのpathリストを返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT DISTINCT b.path
               FROM books b INNER JOIN book_tags t ON b.uuid = t.uuid"""
        ).fetchall()
        return [r["path"] for r in rows]
    finally:
        conn.close()


def get_paths_with_character():
    """キャラクターが1件以上あるbookのpathリストを返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT DISTINCT b.path
               FROM books b INNER JOIN book_characters c ON b.uuid = c.uuid"""
        ).fetchall()
        return [r["path"] for r in rows]
    finally:
        conn.close()


def get_all_series():
    """登録済みシリーズを重複なしで返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT series FROM book_meta WHERE series != '' ORDER BY series"
        ).fetchall()
        return [r["series"] for r in rows]
    finally:
        conn.close()


def get_all_circles():
    """登録済みサークル名を重複なしで返す（検索バー・スマートモード用）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT circle FROM books WHERE circle != '' ORDER BY circle"
        ).fetchall()
        return [r["circle"] for r in rows]
    finally:
        conn.close()


def get_all_series_with_count():
    """(シリーズ, 作品数) のリストを作品数の多い順で返す"""
    return cache.get(CACHE_KEY_SERIES_WITH_COUNT, _fetch_series_with_count)


def _fetch_series_with_count():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT m.series, COUNT(m.uuid) AS cnt
               FROM book_meta m INNER JOIN books b ON m.uuid = b.uuid
               WHERE m.series != ''
               GROUP BY m.series ORDER BY cnt DESC, m.series"""
        ).fetchall()
        return [(r["series"], r["cnt"]) for r in rows]
    finally:
        conn.close()


def get_paths_with_series():
    """シリーズが設定されている path のセットを返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT b.path
               FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
               WHERE m.series != ''"""
        ).fetchall()
        return {r["path"] for r in rows}
    finally:
        conn.close()


def search_books(conditions, operator="AND"):
    """
    conditions: [{"field": "title"|"circle"|"author"|"series"|"character"|"tag", "value": str}, ...]
    operator: "AND" | "OR"
    全booksを (name, circle, title, path, cover_path, is_dlst, uuid) のリストで返す（get_all_books と同形式）
    検索語・DB側とも NFKC 正規化して比較する（全角/半角・異体字などを同一視）
    """
    if not conditions:
        return get_all_books()

    def _nfkc(s):
        return unicodedata.normalize("NFKC", s or "") if s else ""

    conn = get_conn()
    try:
        conn.create_function("nfkc", 1, lambda s: _nfkc(s))
        path_sets = []
        for cond in conditions:
            field = cond["field"]
            val_raw = cond["value"].strip()
            if not val_raw:
                continue
            val = _nfkc(val_raw).lower()
            pattern = f"%{val}%"

            if field == "all":
                all_paths = set()
                rows = conn.execute(
                    "SELECT path FROM books WHERE lower(nfkc(title)) LIKE ?", (pattern,)
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                rows = conn.execute(
                    "SELECT path FROM books WHERE lower(nfkc(circle)) LIKE ?", (pattern,)
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                rows = conn.execute(
                    """SELECT b.path
                       FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                       WHERE lower(nfkc(m.author)) LIKE ?""",
                    (pattern,),
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                rows = conn.execute(
                    """SELECT b.path
                       FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                       WHERE lower(nfkc(m.series)) LIKE ?""",
                    (pattern,),
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                rows = conn.execute(
                    """SELECT b.path
                       FROM books b INNER JOIN book_characters c ON b.uuid = c.uuid
                       WHERE lower(nfkc(c.character)) LIKE ?""",
                    (pattern,),
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                rows = conn.execute(
                    """SELECT b.path
                       FROM books b INNER JOIN book_tags t ON b.uuid = t.uuid
                       WHERE lower(nfkc(t.tag)) LIKE ?""",
                    (pattern,),
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                path_sets.append(all_paths)
                continue
            elif field == "title":
                rows = conn.execute(
                    "SELECT path FROM books WHERE lower(nfkc(title)) LIKE ?", (pattern,)
                ).fetchall()
            elif field == "circle":
                rows = conn.execute(
                    "SELECT path FROM books WHERE lower(nfkc(circle)) LIKE ?", (pattern,)
                ).fetchall()
            elif field == "author":
                rows = conn.execute(
                    """SELECT b.path
                       FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                       WHERE lower(nfkc(m.author)) LIKE ?""",
                    (pattern,),
                ).fetchall()
            elif field == "series":
                rows = conn.execute(
                    """SELECT b.path
                       FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                       WHERE lower(nfkc(m.series)) LIKE ?""",
                    (pattern,),
                ).fetchall()
            elif field == "character":
                rows = conn.execute(
                    """SELECT b.path
                       FROM books b INNER JOIN book_characters c ON b.uuid = c.uuid
                       WHERE lower(nfkc(c.character)) LIKE ?""",
                    (pattern,),
                ).fetchall()
            elif field == "tag":
                rows = conn.execute(
                    """SELECT b.path
                       FROM books b INNER JOIN book_tags t ON b.uuid = t.uuid
                       WHERE lower(nfkc(t.tag)) LIKE ?""",
                    (pattern,),
                ).fetchall()
            elif field == "metadata":
                if "取得" in val or "済" in val:
                    rows = conn.execute("""
                        SELECT b.path FROM books b
                        INNER JOIN book_meta m ON b.uuid = m.uuid
                        WHERE m.dlsite_id != '' AND m.dlsite_id IS NOT NULL AND m.excluded = 0
                    """).fetchall()
                elif "未" in val:
                    acquired = conn.execute("""
                        SELECT b.path
                        FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                        WHERE m.dlsite_id != '' AND m.dlsite_id IS NOT NULL AND m.excluded = 0
                    """).fetchall()
                    excluded = conn.execute("""
                        SELECT b.path
                        FROM books b INNER JOIN book_meta m ON b.uuid = m.uuid
                        WHERE m.excluded = 1
                    """).fetchall()
                    all_paths = {r["path"] for r in conn.execute("SELECT path FROM books").fetchall()}
                    path_sets.append(all_paths - {r["path"] for r in acquired} - {r["path"] for r in excluded})
                    continue
                else:
                    continue
                path_sets.append({r["path"] for r in rows})
                continue
            elif field == "added_date":
                rows = conn.execute(
                    "SELECT path FROM books WHERE date(updated_at) = ? OR strftime('%Y-%m-%d', updated_at) LIKE ?",
                    (val, val + "%")
                ).fetchall()
                path_sets.append({r["path"] for r in rows})
                continue
            else:
                continue

            path_sets.append({r["path"] for r in rows})

        if not path_sets:
            return get_all_books()

        if operator == "AND":
            matched_paths = path_sets[0]
            for s in path_sets[1:]:
                matched_paths &= s
        else:  # OR
            matched_paths = set()
            for s in path_sets:
                matched_paths |= s

        if not matched_paths:
            return []

        placeholders = ",".join("?" * len(matched_paths))
        rows = conn.execute(
            f"SELECT uuid, name, circle, title, path, "
            f"COALESCE(NULLIF(cover_custom, ''), cover_path) as cover_path, "
            f"COALESCE(is_dlst, 0) as is_dlst FROM books "
            f"WHERE path IN ({placeholders}) ORDER BY name",
            list(matched_paths)
        ).fetchall()
        return [
            (r["name"], r["circle"], r["title"], r["path"], r["cover_path"], r["is_dlst"], r["uuid"])
            for r in rows
        ]
    finally:
        conn.close()


def get_added_dates_with_count():
    """追加日（updated_atの日付）ごとの件数を返す。[(日付文字列, 件数), ...] 新しい順"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT date(updated_at) as d, COUNT(*) as cnt
               FROM books WHERE updated_at IS NOT NULL AND updated_at != ''
               GROUP BY d ORDER BY d DESC"""
        ).fetchall()
        return [(r["d"], r["cnt"]) for r in rows]
    finally:
        conn.close()


def get_books_by_added_date(date_str):
    """指定した追加日（YYYY-MM-DD）の書籍を追加順（updated_at 降順）で返す。get_all_books と同じ形式"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT name, circle, title, path,
               COALESCE(NULLIF(cover_custom, ''), cover_path) as cover_path,
               COALESCE(is_dlst, 0) as is_dlst
               FROM books WHERE date(updated_at) = ? ORDER BY updated_at DESC""",
            (date_str,)
        ).fetchall()
        return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"], r["is_dlst"]) for r in rows]
    finally:
        conn.close()
