"""Phase3: _resolve_renames のユニットテスト"""
from __future__ import annotations

import unittest

from scanners.book_scanner import BookScannerWorker


class TestPhase3RenameResolution(unittest.TestCase):
    def setUp(self) -> None:
        self.worker = BookScannerWorker("/tmp/lib_phase3")

    def test_rename_detected_by_hash(self) -> None:
        """created_candidate の hash が missing_map にある → rename 確定。"""
        row = {"path": "old.dmmb", "content_hash": "H", "uuid": "u1", "rowid": 1}
        missing_map = {"H": [row]}
        created = [
            {
                "path": "new.dmmb",
                "hash": "H",
                "size": 1,
                "mtime": 0.0,
                "abs_path": "/n/new.dmmb",
                "is_pdf": False,
            }
        ]
        renames, true_c, rem = self.worker._resolve_renames(created, missing_map)
        self.assertEqual(len(renames), 1)
        self.assertEqual(renames[0][0]["path"], "old.dmmb")
        self.assertEqual(renames[0][1]["path"], "new.dmmb")
        self.assertEqual(true_c, [])
        self.assertEqual(rem, {})

    def test_created_when_no_hash_match(self) -> None:
        """hash が missing_map にない → created 確定。"""
        missing_map: dict[str, list] = {}
        created = [
            {
                "path": "only.dmmb",
                "hash": "Z",
                "size": 1,
                "mtime": 0.0,
                "abs_path": "/o.dmmb",
                "is_pdf": False,
            }
        ]
        renames, true_c, rem = self.worker._resolve_renames(created, missing_map)
        self.assertEqual(renames, [])
        self.assertEqual(len(true_c), 1)
        self.assertEqual(rem, {})

    def test_missing_map_pop_first_win(self) -> None:
        """同一 hash の missing が複数 → pop(0) で先勝ち、余りは missing のまま。"""
        r1 = {"path": "a.dmmb", "content_hash": "H", "uuid": "1", "rowid": 1}
        r2 = {"path": "b.dmmb", "content_hash": "H", "uuid": "2", "rowid": 2}
        missing_map = {"H": [r1, r2]}
        c1 = {
            "path": "n1.dmmb",
            "hash": "H",
            "size": 1,
            "mtime": 0.0,
            "abs_path": "/n1",
            "is_pdf": False,
        }
        c2 = {
            "path": "n2.dmmb",
            "hash": "H",
            "size": 1,
            "mtime": 0.0,
            "abs_path": "/n2",
            "is_pdf": False,
        }
        renames, true_c, rem = self.worker._resolve_renames([c2, c1], missing_map)
        self.assertEqual(len(renames), 2)
        self.assertEqual(true_c, [])
        self.assertEqual(rem, {})

    def test_missing_map_key_deleted_when_empty(self) -> None:
        """消費でリストが空になったら key が削除される。"""
        row = {"path": "old.dmmb", "content_hash": "H", "uuid": "u", "rowid": 1}
        missing_map = {"H": [row]}
        created = [
            {
                "path": "new.dmmb",
                "hash": "H",
                "size": 1,
                "mtime": 0.0,
                "abs_path": "/n",
                "is_pdf": False,
            }
        ]
        _r, _tc, rem = self.worker._resolve_renames(created, missing_map)
        self.assertNotIn("H", rem)

    def test_cross_library_hash_not_matched(self) -> None:
        """Phase2 で missing が空なら同一 hash でも rename にならない（新規扱い）。"""
        missing_map: dict[str, list] = {}
        created = [
            {
                "path": "new.dmmb",
                "hash": "shared",
                "size": 1,
                "mtime": 0.0,
                "abs_path": "/n",
                "is_pdf": False,
            }
        ]
        renames, true_c, rem = self.worker._resolve_renames(created, missing_map)
        self.assertEqual(renames, [])
        self.assertEqual(len(true_c), 1)


if __name__ == "__main__":
    unittest.main()
