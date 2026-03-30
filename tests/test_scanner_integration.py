"""BookScannerWorker._scan() を実ファイルで検証する（QtCore のみロード、イベントループなし）。"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta

import config

import db as db_mod
from scanners.book_scanner import BookScannerWorker


class TestScannerIntegration(unittest.TestCase):
    _orig_db: str
    _orig_backup: str

    @classmethod
    def setUpClass(cls) -> None:
        cls._orig_db = db_mod.DB_FILE
        cls._orig_backup = db_mod.BACKUP_DIR

    @classmethod
    def tearDownClass(cls) -> None:
        db_mod.DB_FILE = cls._orig_db
        db_mod.BACKUP_DIR = cls._orig_backup

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        root = self._td.name
        db_mod.DB_FILE = os.path.join(root, "library.db")
        db_mod.BACKUP_DIR = os.path.join(root, "backups")
        os.makedirs(db_mod.BACKUP_DIR, exist_ok=True)
        self.lib = os.path.join(root, "library")
        os.makedirs(self.lib, exist_ok=True)
        db_mod.init_db()
        db_mod.set_setting(db_mod.LIBRARY_FOLDER_SETTING_KEY, self.lib)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _updated_at(self, rel_path: str) -> str | None:
        conn = db_mod.get_conn()
        try:
            row = conn.execute(
                "SELECT updated_at FROM books WHERE path=?",
                (rel_path,),
            ).fetchone()
            return row["updated_at"] if row else None
        finally:
            conn.close()

    def test_new_file_registered(self) -> None:
        fp = os.path.join(self.lib, "new.dmmb")
        with open(fp, "wb") as f:
            f.write(b"scanner-new-file-body")
        BookScannerWorker(self.lib)._scan()
        self.assertEqual(len(db_mod.get_all_books()), 1)

    def test_renamed_file_updates_path(self) -> None:
        old_p = os.path.join(self.lib, "old.dmmb")
        new_p = os.path.join(self.lib, "new.dmmb")
        body = b"same-bytes-rename-scan"
        with open(old_p, "wb") as f:
            f.write(body)
        BookScannerWorker(self.lib)._scan()
        self.assertEqual(len(db_mod.get_all_books()), 1)
        os.replace(old_p, new_p)
        BookScannerWorker(self.lib)._scan()
        rows = db_mod.get_all_books()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][3], "new.dmmb")

    def test_deleted_file_sets_missing(self) -> None:
        fp = os.path.join(self.lib, "gone.dmmb")
        with open(fp, "wb") as f:
            f.write(b"missing-test-bytes")
        BookScannerWorker(self.lib)._scan()
        os.remove(fp)
        BookScannerWorker(self.lib)._scan()
        miss = db_mod.get_missing_books()
        rel = "gone.dmmb"
        paths = {m["path"] for m in miss}
        self.assertIn(rel, paths)

    def test_ttl_expired_book_flagged(self) -> None:
        fp = os.path.join(self.lib, "ttl.dmmb")
        with open(fp, "wb") as f:
            f.write(b"ttl-expire-body")
        BookScannerWorker(self.lib)._scan()
        os.remove(fp)
        old = (
            datetime.now(UTC) - timedelta(days=config.MISSING_BOOK_TTL_DAYS + 5)
        ).isoformat()
        conn = db_mod.get_conn()
        try:
            conn.execute(
                "UPDATE books SET missing_since_date=? WHERE path=?",
                (old, "ttl.dmmb"),
            )
            conn.commit()
        finally:
            conn.close()
        BookScannerWorker(self.lib)._scan()
        self.assertEqual(len(db_mod.get_all_books()), 0)

    def test_no_change_no_db_write(self) -> None:
        fp = os.path.join(self.lib, "stable.dmmb")
        with open(fp, "wb") as f:
            f.write(b"stable-content")
        BookScannerWorker(self.lib)._scan()
        u1 = self._updated_at("stable.dmmb")
        self.assertIsNotNone(u1)
        BookScannerWorker(self.lib)._scan()
        u2 = self._updated_at("stable.dmmb")
        self.assertEqual(u1, u2)


if __name__ == "__main__":
    unittest.main()
