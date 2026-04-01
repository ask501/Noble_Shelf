"""db_migrations.py の動作を一時 DB で検証する。"""
from __future__ import annotations

import sqlite3

import db_migrations as mig


def test_new_install_applies_baseline() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        assert mig._is_legacy_db(conn) is False
        mig.run_migrations(conn)
        row = conn.execute(
            f"SELECT 1 FROM {mig.MIGRATIONS_TABLE_NAME} WHERE version=?",
            (mig.BASELINE_VERSION,),
        ).fetchone()
        assert row is not None
        books_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='books'"
        ).fetchone()
        assert books_exists is not None
    finally:
        conn.close()


def test_legacy_db_marks_baseline_without_running_000() -> None:
    conn = sqlite3.connect(":memory:")
    original_migrations = mig._MIGRATIONS
    try:
        conn.execute("CREATE TABLE books(path TEXT PRIMARY KEY)")
        assert mig._is_legacy_db(conn) is True

        def _migrate_000(_conn: sqlite3.Connection) -> None:
            raise AssertionError("legacy DB で baseline が実行されてはいけない")

        mig._MIGRATIONS = [(mig.BASELINE_VERSION, _migrate_000)]
        mig.run_migrations(conn)

        row = conn.execute(
            f"SELECT 1 FROM {mig.MIGRATIONS_TABLE_NAME} WHERE version=?",
            (mig.BASELINE_VERSION,),
        ).fetchone()
        assert row is not None
    finally:
        mig._MIGRATIONS = original_migrations
        conn.close()


def test_v1plus_applies_only_new_migration() -> None:
    conn = sqlite3.connect(":memory:")
    original_migrations = mig._MIGRATIONS
    try:
        mig._ensure_migrations_table(conn)
        mig._mark_applied(conn, mig.BASELINE_VERSION)
        conn.commit()

        applied: list[str] = []

        def _migrate_000(_conn: sqlite3.Connection) -> None:
            applied.append("000")

        def _migrate_001(_conn: sqlite3.Connection) -> None:
            _conn.execute("CREATE TABLE IF NOT EXISTS migration_001_probe(id INTEGER)")
            applied.append("001")

        mig._MIGRATIONS = [
            (mig.BASELINE_VERSION, _migrate_000),
            (1, _migrate_001),
        ]
        mig.run_migrations(conn)

        assert applied == ["001"]
        v0 = conn.execute(
            f"SELECT 1 FROM {mig.MIGRATIONS_TABLE_NAME} WHERE version=?",
            (mig.BASELINE_VERSION,),
        ).fetchone()
        v1 = conn.execute(
            f"SELECT 1 FROM {mig.MIGRATIONS_TABLE_NAME} WHERE version=?",
            (1,),
        ).fetchone()
        assert v0 is not None
        assert v1 is not None
    finally:
        mig._MIGRATIONS = original_migrations
        conn.close()
