"""Phase4: _apply_changes のユニットテスト（DB・resolver をモック）"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from store_file_resolver import ActionResult
from scanners.book_scanner import BookScannerWorker


class TestPhase4DBApply(unittest.TestCase):
    def setUp(self) -> None:
        self.worker = BookScannerWorker("/tmp/phase4_lib")

    def test_updated_updates_hash_not_mtime(self) -> None:
        """updated → apply に渡す mtime は DB 既存値（新ファイル mtime に差し替えない）。"""
        fs = {
            "path": "u.dmmb",
            "hash": "newh",
            "size": 5,
            "mtime": 99.0,
            "abs_path": "/u.dmmb",
            "is_pdf": False,
        }
        row = {
            "uuid": "uid",
            "path": "u.dmmb",
            "mtime": 3.0,
        }
        captured: dict = {}

        def _capture(_r, book_data):
            captured["mtime"] = book_data.get("mtime")
            captured["content_hash"] = book_data.get("content_hash")

        dup: list = []
        ren: list = []
        err: list = []
        del_paths: list = []

        with (
            patch(
                "scanners.book_scanner.db.apply_action_result",
                side_effect=_capture,
            ),
            patch("scanners.book_scanner._get_pdf_cover_and_pages", return_value=("", None)),
            patch("scanners.book_scanner.db.fetch_all_rows_for_index", return_value=[]),
            patch("scanners.book_scanner.db.rename_book_path"),
        ):
            self.worker._apply_changes(
                [],
                [],
                [],
                [(row, fs)],
                {},
                duplicate_out=dup,
                rename_out=ren,
                error_out=err,
                delete_paths_root=del_paths,
            )
        self.assertEqual(captured.get("mtime"), 3.0)
        self.assertEqual(captured.get("content_hash"), "newh")


if __name__ == "__main__":
    unittest.main()
