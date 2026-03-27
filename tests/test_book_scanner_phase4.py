"""Phase4: _apply_changes のユニットテスト（DB・resolver をモック）"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from noble_shelf.store_file_resolver import ActionResult
from scanners.book_scanner import BookScannerWorker


class TestPhase4DBApply(unittest.TestCase):
    def setUp(self) -> None:
        self.worker = BookScannerWorker("/tmp/phase4_lib")

    def test_rename_calls_rename_book_path_not_resolver(self) -> None:
        """rename → rename_book_path を呼ぶ。resolve_store_file_action は呼ばない。"""
        fs = {
            "path": "new.dmmb",
            "hash": "h",
            "size": 1,
            "mtime": 1.0,
            "abs_path": "/n.dmmb",
            "is_pdf": False,
        }
        row = {
            "uuid": "uu",
            "path": "old.dmmb",
            "mtime": 2.0,
        }
        dup: list = []
        ren: list = []
        err: list = []
        del_paths: list = []

        with (
            patch("scanners.book_scanner.resolve_store_file_action") as mock_res,
            patch("scanners.book_scanner.db.rename_book_path") as mock_rename,
            patch("scanners.book_scanner.db.apply_action_result") as mock_apply,
            patch("scanners.book_scanner.db.fetch_all_rows_for_index", return_value=[]),
        ):
            self.worker._apply_changes(
                [(row, fs)],
                [],
                [],
                [],
                {},
                duplicate_out=dup,
                rename_out=ren,
                error_out=err,
                delete_paths_root=del_paths,
            )
            mock_rename.assert_called_once()
            mock_res.assert_not_called()
            mock_apply.assert_not_called()

    def test_created_calls_resolver_then_insert(self) -> None:
        """created → resolve_store_file_action → apply_action_result の順。"""
        fs = {
            "path": "c.dmmb",
            "hash": "ch",
            "size": 3,
            "mtime": 1.0,
            "abs_path": "/c.dmmb",
            "is_pdf": False,
        }
        dup: list = []
        ren: list = []
        err: list = []
        del_paths: list = []
        calls: list[str] = []

        def _res(*_a, **_k):
            calls.append("resolve")
            return ActionResult(status="created", db_path="c.dmmb")

        def _apply(*_a, **_k):
            calls.append("apply")

        with (
            patch(
                "scanners.book_scanner.resolve_store_file_action",
                side_effect=_res,
            ),
            patch(
                "scanners.book_scanner.db.apply_action_result",
                side_effect=_apply,
            ),
            patch(
                "scanners.book_scanner.db.fetch_all_rows_for_index",
                return_value=[],
            ),
            patch("scanners.book_scanner.db.rename_book_path") as mock_rename,
            patch(
                "scanners.book_scanner.store_resolver.build_db_index",
                return_value=MagicMock(),
            ),
            patch(
                "scanners.book_scanner._get_pdf_cover_and_pages",
                return_value=("", None),
            ),
        ):
            self.worker._apply_changes(
                [],
                [fs],
                [],
                [],
                {},
                duplicate_out=dup,
                rename_out=ren,
                error_out=err,
                delete_paths_root=del_paths,
            )
            mock_rename.assert_not_called()
        self.assertEqual(calls, ["resolve", "apply"])

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

    def test_existing_no_db_call(self) -> None:
        """renames/created/updated/remaining がすべて空なら SQLite 取得・更新を行わない。"""
        dup: list = []
        ren: list = []
        err: list = []
        del_paths: list = []

        with (
            patch("scanners.book_scanner.db.rename_book_path") as mock_rename,
            patch("scanners.book_scanner.db.apply_action_result") as mock_apply,
            patch(
                "scanners.book_scanner.db.fetch_all_rows_for_index",
            ) as mock_fetch,
            patch("scanners.book_scanner.resolve_store_file_action") as mock_res,
        ):
            self.worker._apply_changes(
                [],
                [],
                [],
                [],
                {},
                duplicate_out=dup,
                rename_out=ren,
                error_out=err,
                delete_paths_root=del_paths,
            )
            mock_rename.assert_not_called()
            mock_apply.assert_not_called()
            mock_fetch.assert_not_called()
            mock_res.assert_not_called()

    def test_rename_applied_before_other_writes(self) -> None:
        """rename が updated より先に DB 適用される。"""
        fs_new = {
            "path": "r.dmmb",
            "hash": "rh",
            "size": 1,
            "mtime": 1.0,
            "abs_path": "/r.dmmb",
            "is_pdf": False,
        }
        row_r = {"uuid": "r1", "path": "old_r.dmmb", "mtime": 1.0}
        fs_u = {
            "path": "u.dmmb",
            "hash": "uh",
            "size": 2,
            "mtime": 50.0,
            "abs_path": "/u.dmmb",
            "is_pdf": False,
        }
        row_u = {"uuid": "u1", "path": "u.dmmb", "mtime": 4.0}
        order: list[str] = []

        def _rename(*_a, **_k):
            order.append("rename")

        def _apply(*_a, **_k):
            order.append("apply")

        dup: list = []
        ren: list = []
        err: list = []
        del_paths: list = []

        with (
            patch(
                "scanners.book_scanner.db.rename_book_path",
                side_effect=_rename,
            ),
            patch(
                "scanners.book_scanner.db.apply_action_result",
                side_effect=_apply,
            ),
            patch(
                "scanners.book_scanner.db.fetch_all_rows_for_index",
                return_value=[],
            ),
            patch(
                "scanners.book_scanner._get_pdf_cover_and_pages",
                return_value=("", None),
            ),
        ):
            self.worker._apply_changes(
                [(row_r, fs_new)],
                [],
                [],
                [(row_u, fs_u)],
                {},
                duplicate_out=dup,
                rename_out=ren,
                error_out=err,
                delete_paths_root=del_paths,
            )
        self.assertEqual(order[0], "rename")
        self.assertEqual(order[1], "apply")


if __name__ == "__main__":
    unittest.main()
