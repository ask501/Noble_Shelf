"""drop_handler.handle_drop をモックで GUI なしに近い形で検証する。"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

import db as db_mod
import drop_handler


def _min_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _sync_extract(src_path: str, dest_dir: str, parent, on_done) -> None:
    """テスト用: 解凍＋登録を同期的に行う（QThread・プログレスなし）。"""
    from drop_handler import _flatten_single_subdir, _register_folder

    tmp = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(src_path, "r") as zf:
            zf.extractall(tmp)
        _flatten_single_subdir(tmp)
        if os.path.isdir(dest_dir):
            shutil.rmtree(dest_dir)
        shutil.copytree(tmp, dest_dir)
        _register_folder(dest_dir, parent=None, dest_to_cleanup=dest_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if on_done:
        on_done()


class TestDropIntegration(unittest.TestCase):
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

    def _make_zip(self, zip_path: str, folder: str, png_name: str, png_bytes: bytes) -> None:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{folder}/{png_name}", png_bytes)

    def test_zip_drop_registers_one_book(self) -> None:
        zpath = os.path.join(self._td.name, "one.zip")
        self._make_zip(zpath, "BookOne", "a.png", _min_png())
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = 1
        mock_mb = MagicMock()
        mock_mb.question.return_value = 1
        with (
            patch.object(drop_handler, "ArchiveDropDialog", return_value=mock_dlg),
            patch.object(drop_handler, "_run_extract_with_progress", side_effect=_sync_extract),
            patch.object(drop_handler, "QMessageBox", mock_mb),
        ):
            drop_handler.handle_drop([zpath], self.lib, parent=None, on_done=None)
        self.assertEqual(len(db_mod.get_all_books()), 1)

    def test_same_zip_redrop_is_duplicate(self) -> None:
        zpath = os.path.join(self._td.name, "twice.zip")
        self._make_zip(zpath, "DupBox", "p.png", _min_png())
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = 1
        mock_mb = MagicMock()
        mock_mb.question.return_value = 1
        with (
            patch.object(drop_handler, "ArchiveDropDialog", return_value=mock_dlg),
            patch.object(drop_handler, "_run_extract_with_progress", side_effect=_sync_extract),
            patch.object(drop_handler, "QMessageBox", mock_mb),
        ):
            drop_handler.handle_drop([zpath], self.lib, parent=None, on_done=None)
            n1 = len(db_mod.get_all_books())
            drop_handler.handle_drop([zpath], self.lib, parent=None, on_done=None)
            n2 = len(db_mod.get_all_books())
        self.assertEqual(n1, 1)
        self.assertEqual(n2, 1)

    def test_different_content_same_filename(self) -> None:
        """同名 zip（別パス）・別内容: 1 回目削除後に 2 回目は新規として登録される。"""
        d1 = os.path.join(self._td.name, "d1")
        d2 = os.path.join(self._td.name, "d2")
        os.makedirs(d1)
        os.makedirs(d2)
        z1 = os.path.join(d1, "pack.zip")
        z2 = os.path.join(d2, "pack.zip")
        self._make_zip(z1, "SameRoot", "a.png", _min_png())
        self._make_zip(z2, "SameRoot", "a.png", _min_png() + b"x")

        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = 1
        mock_mb = MagicMock()
        mock_mb.question.return_value = 1
        with (
            patch.object(drop_handler, "ArchiveDropDialog", return_value=mock_dlg),
            patch.object(drop_handler, "_run_extract_with_progress", side_effect=_sync_extract),
            patch.object(drop_handler, "QMessageBox", mock_mb),
        ):
            drop_handler.handle_drop([z1], self.lib, parent=None, on_done=None)
            self.assertEqual(len(db_mod.get_all_books()), 1)
            dest_folder = os.path.join(self.lib, "pack")
            shutil.rmtree(dest_folder, ignore_errors=True)
            conn = db_mod.get_conn()
            try:
                conn.execute("DELETE FROM books")
                conn.commit()
            finally:
                conn.close()
            drop_handler.handle_drop([z2], self.lib, parent=None, on_done=None)
            self.assertEqual(len(db_mod.get_all_books()), 1)

    def test_drop_during_scan_rejected(self) -> None:
        zpath = os.path.join(self._td.name, "blocked.zip")
        self._make_zip(zpath, "B", "p.png", _min_png())
        n0 = len(db_mod.get_all_books())
        drop_handler.handle_drop(
            [zpath],
            self.lib,
            parent=None,
            on_done=None,
            scan_blocked=True,
        )
        self.assertEqual(len(db_mod.get_all_books()), n0)


if __name__ == "__main__":
    unittest.main()
