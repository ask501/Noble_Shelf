"""db.py の CRUD を一時 DB で検証する（テストごとに tempfile で隔離）。"""
from __future__ import annotations

import os
import re
import tempfile
import unittest

import config

import db as db_mod


def _set_library_folder(path: str) -> None:
    db_mod.set_setting(db_mod.LIBRARY_FOLDER_SETTING_KEY, path)


def _get_library_folder() -> str:
    return (db_mod.get_setting(db_mod.LIBRARY_FOLDER_SETTING_KEY) or "").strip()


class TestDbIsolated(unittest.TestCase):
    """各テストで db.DB_FILE / BACKUP_DIR を一時ディレクトリに差し替える。"""

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
        db_mod.init_db()

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_upsert_and_search(self) -> None:
        lib = os.path.join(self._td.name, "lib")
        os.makedirs(lib, exist_ok=True)
        _set_library_folder(lib)
        fp = os.path.join(lib, "only.dmmb")
        with open(fp, "wb") as f:
            f.write(b"scan-db-upsert-search")
        db_mod.upsert_book("n", "c", "UniqueSearchTitleX", fp, "", mtime=1.0)
        rows = db_mod.search_books(
            [{"field": "title", "value": "UniqueSearchTitleX"}],
            operator="AND",
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        title = row["title"]
        path = row["path"]
        uuid_val = row["uuid"]
        self.assertEqual(title, "UniqueSearchTitleX")
        self.assertTrue(uuid_val)
        self.assertTrue(path)

    def test_upsert_overwrite(self) -> None:
        lib = os.path.join(self._td.name, "lib2")
        os.makedirs(lib, exist_ok=True)
        _set_library_folder(lib)
        fp = os.path.join(lib, "same.dmmb")
        with open(fp, "wb") as f:
            f.write(b"x")
        uid = "22222222-2222-4222-8222-222222222222"
        db_mod.upsert_book("a1", "c1", "t1", fp, "", mtime=1.0, uuid=uid)
        db_mod.upsert_book("a2", "c2", "t2", fp, "", mtime=2.0, uuid=uid)
        self.assertEqual(len(db_mod.get_all_books()), 1)
        row = db_mod.get_all_books()[0]
        self.assertEqual(row["title"], "t2")
        self.assertEqual(row["uuid"], uid)

    def test_rename_book_path(self) -> None:
        lib = os.path.join(self._td.name, "lib3")
        os.makedirs(lib, exist_ok=True)
        _set_library_folder(lib)
        fp = os.path.join(lib, "old.dmmb")
        with open(fp, "wb") as f:
            f.write(b"y")
        uid = "33333333-3333-4333-8333-333333333333"
        db_mod.upsert_book("n", "c", "t", fp, "", mtime=1.0, uuid=uid)
        db_mod.rename_book_path(uid, "new.dmmb", 2.0, "hashh")
        rows = db_mod.search_books(
            [{"field": "title", "value": "t"}],
            operator="AND",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"], "new.dmmb")

    def test_rename_nonexistent_uuid_no_error(self) -> None:
        lib = os.path.join(self._td.name, "lib4")
        os.makedirs(lib, exist_ok=True)
        _set_library_folder(lib)
        db_mod.rename_book_path(
            "00000000-0000-4000-8000-000000000099",
            "ghost.dmmb",
            1.0,
            "h",
        )

    def test_search_empty_library(self) -> None:
        lib = os.path.join(self._td.name, "lib5")
        os.makedirs(lib, exist_ok=True)
        _set_library_folder(lib)
        rows = db_mod.search_books(
            [{"field": "title", "value": "__no_such_title_xyz__"}],
            operator="AND",
        )
        self.assertEqual(rows, [])

    def test_set_and_get_library_folder(self) -> None:
        lib = os.path.join(self._td.name, "lib6")
        os.makedirs(lib, exist_ok=True)
        _set_library_folder(lib)
        self.assertEqual(os.path.normpath(_get_library_folder()), os.path.normpath(lib))

    def test_backup_created_on_library_change(self) -> None:
        """app.py と同様、ライブラリ変更前後のバックアップでファイルが増える。"""
        lib = os.path.join(self._td.name, "lib7")
        os.makedirs(lib, exist_ok=True)
        _set_library_folder("")
        db_mod.create_backup(config.BACKUP_REASON_MANUAL)
        before = set(os.listdir(db_mod.BACKUP_DIR))
        db_mod.create_backup(config.BACKUP_REASON_LIB_CHANGE_BEFORE)
        _set_library_folder(lib)
        db_mod.create_backup(config.BACKUP_REASON_LIB_CHANGE_AFTER)
        after = os.listdir(db_mod.BACKUP_DIR)
        new_names = [n for n in after if n not in before]
        self.assertGreaterEqual(len(new_names), 1)
        pat = re.compile(config.BACKUP_FILENAME_PATTERN)
        for n in new_names:
            self.assertIsNotNone(pat.match(n), msg=n)
            self.assertTrue(
                re.match(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}-\d{3}_", n),
                msg=n,
            )

    def test_missing_since_date_set(self) -> None:
        """mark_missing_since_if_null で missing_since_date が付く（db に set_missing_since_date は無い）。"""
        lib = os.path.join(self._td.name, "lib8")
        os.makedirs(lib, exist_ok=True)
        _set_library_folder(lib)
        fp = os.path.join(lib, "m.dmmb")
        with open(fp, "wb") as f:
            f.write(b"z")
        uid = "44444444-4444-4444-8444-444444444444"
        db_mod.upsert_book("n", "c", "t", fp, "", mtime=1.0, uuid=uid)
        rel = db_mod.to_db_path_from_any(fp)
        iso = "2026-01-15T12:00:00"
        db_mod.mark_missing_since_if_null(rel, iso)
        miss = db_mod.get_missing_books()
        paths = {m["path"] for m in miss}
        self.assertIn(rel, paths)


if __name__ == "__main__":
    unittest.main()
