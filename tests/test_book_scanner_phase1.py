"""Phase1: _collect_fs_files のユニットテスト"""
from __future__ import annotations

import os
import tempfile
import unittest

from scanners.book_scanner import BookScannerWorker


class TestPhase1FSScan(unittest.TestCase):
    def test_returns_path_hash_size(self) -> None:
        """各エントリに path・hash・size（および mtime 等）が含まれる。"""
        with tempfile.TemporaryDirectory() as tmp:
            lib = os.path.join(tmp, "lib")
            os.makedirs(lib)
            fp = os.path.join(lib, "sample.dmmb")
            payload = b"noble-shelf-phase1-test-bytes"
            with open(fp, "wb") as f:
                f.write(payload)

            worker = BookScannerWorker(lib)
            fs_files, failed, errs = worker._collect_fs_files(lib)
            self.assertEqual(errs, [])
            self.assertEqual(failed, set())
            self.assertEqual(len(fs_files), 1)
            d = fs_files[0]
            self.assertIn("path", d)
            self.assertIn("hash", d)
            self.assertIn("size", d)
            self.assertEqual(d["size"], len(payload))
            self.assertEqual(os.path.normpath(d["path"]), "sample.dmmb")
            self.assertTrue(d["hash"])
            self.assertIn("mtime", d)
            self.assertIn("abs_path", d)
            self.assertIn("is_pdf", d)

    def test_excluded_extensions_not_listed(self) -> None:
        """対象外拡張子のファイルはリストに含まれない。"""
        with tempfile.TemporaryDirectory() as tmp:
            lib = os.path.join(tmp, "lib")
            os.makedirs(lib)
            with open(os.path.join(lib, "note.txt"), "w", encoding="utf-8") as f:
                f.write("x")
            with open(os.path.join(lib, "ok.dmmb"), "wb") as f:
                f.write(b"y" * 50)

            worker = BookScannerWorker(lib)
            fs_files, _failed, _errs = worker._collect_fs_files(lib)
            self.assertEqual(len(fs_files), 1)
            self.assertTrue(fs_files[0]["path"].endswith(".dmmb"))


if __name__ == "__main__":
    unittest.main()
