from __future__ import annotations

import logging
import re
import sqlite3
from typing import Callable

_logger = logging.getLogger(__name__)

MIGRATIONS_TABLE_NAME = "migrations"
BASELINE_VERSION = 0
MIGRATION_FUNCTION_NAME_PATTERN = r"^_migrate_(\d+)$"
LEGACY_TABLE_NAME = "books"


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE_NAME} (
            version    INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now','localtime'))
        )
        """
    )


def _is_applied(conn: sqlite3.Connection, version: int) -> bool:
    row = conn.execute(
        f"SELECT 1 FROM {MIGRATIONS_TABLE_NAME} WHERE version = ?",
        (version,),
    ).fetchone()
    return row is not None


def _mark_applied(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        f"INSERT OR IGNORE INTO {MIGRATIONS_TABLE_NAME} (version) VALUES (?)",
        (version,),
    )


def _is_legacy_db(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (LEGACY_TABLE_NAME,),
    ).fetchone()
    return row is not None


def _migration_version_from_name(func) -> int:
    match = re.match(MIGRATION_FUNCTION_NAME_PATTERN, func.__name__)
    if not match:
        raise ValueError(f"Invalid migration function name: {func.__name__}")
    return int(match.group(1))


def run_migrations(conn: sqlite3.Connection) -> None:
    _ensure_migrations_table(conn)

    # 既存DBは baseline(000) を実行せず、適用済みとしてのみ記録する。
    if _is_legacy_db(conn) and not _is_applied(conn, BASELINE_VERSION):
        conn.execute("BEGIN")
        try:
            _mark_applied(conn, BASELINE_VERSION)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        _logger.info("Marked baseline migration as applied for legacy DB: %s", BASELINE_VERSION)

    for version, migration in sorted(_MIGRATIONS, key=lambda item: item[0]):
        name_version = _migration_version_from_name(migration)
        if name_version != version:
            raise ValueError(
                f"Migration version mismatch: list={version}, function={name_version}, name={migration.__name__}"
            )
        if _is_applied(conn, version):
            continue
        conn.execute("BEGIN")
        try:
            migration(conn)
            _mark_applied(conn, version)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        _logger.info("Applied migration: %s", version)


def _migrate_000(conn: sqlite3.Connection) -> None:
    # 新規インストール向け baseline スキーマ（既存DBには適用しない）。
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            uuid                TEXT PRIMARY KEY,
            path                TEXT NOT NULL UNIQUE,
            name                TEXT NOT NULL,
            circle              TEXT NOT NULL,
            title               TEXT NOT NULL,
            cover_path          TEXT,
            cover_custom        TEXT,
            mtime               REAL,
            content_hash        TEXT,
            cover_hash          TEXT DEFAULT NULL,
            missing_since_date  TEXT DEFAULT NULL,
            is_dlst             INTEGER DEFAULT 0,
            updated_at          TEXT DEFAULT (datetime('now','localtime'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bookmarks (
            path       TEXT PRIMARY KEY,
            rating     INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recent_books (
            path      TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            opened_at TEXT DEFAULT (datetime('now','localtime'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hidden_paths (
            path TEXT PRIMARY KEY
        )
        """
    )
    conn.execute(
        """
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
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS book_characters (
            uuid      TEXT NOT NULL,
            character TEXT NOT NULL,
            PRIMARY KEY (uuid, character),
            FOREIGN KEY (uuid) REFERENCES books(uuid) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS book_tags (
            uuid TEXT NOT NULL,
            tag  TEXT NOT NULL,
            PRIMARY KEY (uuid, tag),
            FOREIGN KEY (uuid) REFERENCES books(uuid) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
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
        """
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_circle       ON books(circle)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_path         ON books(path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_content_hash ON books(content_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_cover_hash   ON books(cover_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_characters_uuid    ON book_characters(uuid)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_uuid          ON book_tags(uuid)")


_MIGRATIONS: list[tuple[int, object]] = [
    (BASELINE_VERSION, _migrate_000),
]


# def _migrate_001(conn: sqlite3.Connection) -> None:
#     """
#     v1.0以降の最初の差分マイグレーション（雛形）。
#     実装時はこのコメントを削除し、実際のDDL/DMLを書く。
#
#     カラム追加の例:
#         cols = [r[1] for r in conn.execute("PRAGMA table_info(books)").fetchall()]
#         if "new_column" not in cols:
#             conn.execute("ALTER TABLE books ADD COLUMN new_column TEXT DEFAULT ''")
#
#     テーブル追加の例:
#         conn.execute(\"\"\"
#             CREATE TABLE IF NOT EXISTS new_table (
#                 id   INTEGER PRIMARY KEY AUTOINCREMENT,
#                 name TEXT NOT NULL
#             )
#         \"\"\")
#
#     インデックス追加の例:
#         conn.execute("CREATE INDEX IF NOT EXISTS idx_new ON books(new_column)")
#
#     データ変換の例:
#         rows = conn.execute("SELECT uuid, some_col FROM books").fetchall()
#         for row in rows:
#             conn.execute("UPDATE books SET some_col=? WHERE uuid=?", (transform(row[1]), row[0]))
#     """
#     pass
#
#
# _MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]] = [
#     (0, _migrate_000),
#     (1, _migrate_001),  # 雛形。実装前は pass のまま運用しない — 実装時に追加する
# ]
