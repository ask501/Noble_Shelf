"""Phase2: _classify のユニットテスト"""
from __future__ import annotations

import os
import tempfile
import unittest

from scanners.book_scanner import BookScannerWorker


class TestPhase2Classification(unittest.TestCase):
    def _run_phase2(
        self,
        db_rows: list[dict],
        fs_files: list[dict],
        library_folder: str,
        hash_failed: set[str] | None = None,
    ):
        worker = BookScannerWorker(library_folder)
        return worker._classify(
            fs_files,
            db_rows,
            library_folder,
            hash_failed or set(),
        )

    def test_existing_path_hash_match(self) -> None:
        """path も hash も一致 → existing（missing/created/updated に入らない）。"""
        lib = os.path.normpath("/tmp/phase2_lib")
        h = "abc123hash"
        fs_files = [
            {
                "path": "a.dmmb",
                "hash": h,
                "size": 10,
                "mtime": 1.0,
                "abs_path": "/x/a.dmmb",
                "is_pdf": False,
            }
        ]
        db_rows = [
            {
                "rowid": 1,
                "uuid": "u1",
                "path": "a.dmmb",
                "content_hash": h,
                "mtime": 9.0,
            }
        ]
        mm, created, existing, updated = self._run_phase2(db_rows, fs_files, lib)
        self.assertEqual(mm, {})
        self.assertEqual(created, [])
        self.assertEqual(len(existing), 1)
        self.assertEqual(existing[0][0]["uuid"], "u1")
        self.assertEqual(updated, [])

    def test_missing_in_fs(self) -> None:
        """DB にあって FS にない → missing_map に入る。"""
        lib = os.path.normpath("/tmp/phase2_lib2")
        h = "deadbeef"
        fs_files: list[dict] = []
        db_rows = [
            {
                "rowid": 2,
                "uuid": "u2",
                "path": "gone.dmmb",
                "content_hash": h,
                "mtime": 1.0,
            }
        ]
        mm, created, existing, updated = self._run_phase2(db_rows, fs_files, lib)
        self.assertIn(h, mm)
        self.assertEqual(mm[h][0]["path"], "gone.dmmb")
        self.assertEqual(created, [])
        self.assertEqual(existing, [])
        self.assertEqual(updated, [])

    def test_created_in_fs(self) -> None:
        """FS にあって DB にない → created_candidates に入る。"""
        lib = os.path.normpath("/tmp/phase2_lib3")
        fs_files = [
            {
                "path": "new.dmmb",
                "hash": "nh",
                "size": 5,
                "mtime": 2.0,
                "abs_path": "/x/new.dmmb",
                "is_pdf": False,
            }
        ]
        db_rows: list[dict] = []
        mm, created, existing, updated = self._run_phase2(db_rows, fs_files, lib)
        self.assertEqual(mm, {})
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["path"], "new.dmmb")
        self.assertEqual(existing, [])
        self.assertEqual(updated, [])

    def test_updated_same_path_different_hash(self) -> None:
        """同 path で hash 変化 → updated（rename ではない）。"""
        lib = os.path.normpath("/tmp/phase2_lib4")
        fs_files = [
            {
                "path": "x.dmmb",
                "hash": "newhash",
                "size": 3,
                "mtime": 1.0,
                "abs_path": "/x/x.dmmb",
                "is_pdf": False,
            }
        ]
        db_rows = [
            {
                "rowid": 1,
                "uuid": "u",
                "path": "x.dmmb",
                "content_hash": "oldhash",
                "mtime": 1.0,
            }
        ]
        mm, created, existing, updated = self._run_phase2(db_rows, fs_files, lib)
        self.assertEqual(mm, {})
        self.assertEqual(created, [])
        self.assertEqual(existing, [])
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0][0]["content_hash"], "oldhash")
        self.assertEqual(updated[0][1]["hash"], "newhash")

    def test_other_library_records_excluded(self) -> None:
        """別ライブラリ直下のレコードは missing_map に混入しない。"""
        with tempfile.TemporaryDirectory() as tmp:
            lib_a = os.path.join(tmp, "lib_a")
            lib_b = os.path.join(tmp, "lib_b")
            os.makedirs(lib_a)
            os.makedirs(lib_b)
            other_file = os.path.join(lib_b, "only_b.dmmb")
            with open(other_file, "wb") as f:
                f.write(b"other")

            fs_files: list[dict] = []
            db_rows = [
                {
                    "rowid": 1,
                    "uuid": "u-other",
                    "path": other_file,
                    "content_hash": "hh",
                    "mtime": 1.0,
                }
            ]
            worker = BookScannerWorker(lib_a)
            mm, _c, _e, _u = worker._classify(fs_files, db_rows, lib_a, set())
            self.assertEqual(mm, {})


if __name__ == "__main__":
    unittest.main()
