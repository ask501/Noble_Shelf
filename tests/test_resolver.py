import unittest

from store_file_resolver import (
    DBIndex,
    DBRowSummary,
    FileContext,
    build_db_index,
    resolve_store_file_action,
)


class TestResolveStoreFileAction(unittest.TestCase):
    def _make_index(self, rows=None, missing=None):
        rows = rows or []
        rows_by_hash = {}
        for r in rows:
            if r.content_hash:
                rows_by_hash.setdefault(r.content_hash, []).append(r)
        for h in list(rows_by_hash.keys()):
            rows_by_hash[h].sort(key=lambda x: x.rowid)
        return DBIndex(
            row_by_path={r.path: r for r in rows},
            rows_by_content_hash=rows_by_hash,
            missing_path_set=missing or set(),
            meta_by_path={r.path: (r.mtime, r.content_hash) for r in rows},
        )

    def test_unchanged_hash(self):
        row = DBRowSummary("u1", "A.zip", "abc", 1.0, ".zip", False, 1)
        index = self._make_index(rows=[row])
        ctx = FileContext("/lib/A.zip", "A.zip", "abc", 1.0, ".zip", False)
        result = resolve_store_file_action(ctx, index)
        self.assertEqual(result.status, "unchanged")

    def test_updated_hash_changed(self):
        row = DBRowSummary("u1", "A.zip", "abc", 1.0, ".zip", False, 1)
        index = self._make_index(rows=[row])
        ctx = FileContext("/lib/A.zip", "A.zip", "xyz", 1.0, ".zip", False)
        result = resolve_store_file_action(ctx, index)
        self.assertEqual(result.status, "updated")

    def test_created_new_file(self):
        index = self._make_index(rows=[])
        ctx = FileContext("/lib/B.zip", "B.zip", "newhash", 2.0, ".zip", False)
        result = resolve_store_file_action(ctx, index)
        self.assertEqual(result.status, "created")

    def test_rename(self):
        row = DBRowSummary("u1", "old.zip", "abc", 1.0, ".zip", False, 1)
        index = self._make_index(rows=[row], missing={"old.zip"})
        ctx = FileContext("/lib/new.zip", "new.zip", "abc", 1.0, ".zip", False)
        result = resolve_store_file_action(ctx, index)
        self.assertEqual(result.status, "rename")
        self.assertEqual(result.existing_path, "old.zip")

    def test_duplicate(self):
        row = DBRowSummary("u1", "keep.zip", "abc", 1.0, ".zip", False, 1)
        index = self._make_index(rows=[row], missing=set())
        ctx = FileContext("/lib/copy.zip", "copy.zip", "abc", 1.0, ".zip", False)
        result = resolve_store_file_action(ctx, index)
        self.assertEqual(result.status, "duplicate")

    def test_error_io(self):
        index = self._make_index(rows=[])
        ctx = FileContext("/lib/x.zip", "", "abc", 1.0, ".zip", False)
        result = resolve_store_file_action(ctx, index)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_type, "IO_ERROR")

    def test_error_hash(self):
        index = self._make_index(rows=[])
        ctx = FileContext("/lib/x.zip", "x.zip", None, None, ".zip", False)
        result = resolve_store_file_action(ctx, index)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_type, "HASH_ERROR")

    def test_mtime_fallback_unchanged(self):
        row = DBRowSummary("u1", "A.zip", None, 10.0, ".zip", False, 1)
        index = self._make_index(rows=[row])
        ctx = FileContext("/lib/A.zip", "A.zip", None, 10.0, ".zip", False)
        result = resolve_store_file_action(ctx, index)
        self.assertEqual(result.status, "unchanged")

    def test_rename_mismatch_ext_or_dlst_becomes_created(self):
        row = DBRowSummary("u1", "old.dlst", "abc", 1.0, ".dlst", True, 1)
        index = self._make_index(rows=[row], missing={"old.dlst"})
        ctx = FileContext("/lib/new.zip", "new.zip", "abc", 1.0, ".zip", False)
        result = resolve_store_file_action(ctx, index)
        self.assertEqual(result.status, "created")

    def test_build_db_index_orders_by_rowid(self):
        db_rows = [
            {"uuid": "u2", "path": "b.zip", "content_hash": "h", "mtime": 2, "file_ext": ".zip", "is_dlst": 0, "rowid": 2},
            {"uuid": "u1", "path": "a.zip", "content_hash": "h", "mtime": 1, "file_ext": ".zip", "is_dlst": 0, "rowid": 1},
        ]
        index = build_db_index(db_rows, "C:/no/such/root")
        self.assertEqual(index.rows_by_content_hash["h"][0].uuid, "u1")

    def test_build_db_index_missing_path_set(self):
        """missing_since_date 付き行の path が missing_path_set に入る（rename 判定用）。"""
        db_rows = [
            {
                "uuid": "u1",
                "path": "gone.zip",
                "content_hash": "h",
                "mtime": 1,
                "file_ext": ".zip",
                "is_dlst": 0,
                "rowid": 1,
                "missing_since_date": "2024-01-01T00:00:00",
            },
            {
                "uuid": "u2",
                "path": "ok.zip",
                "content_hash": "h2",
                "mtime": 1,
                "file_ext": ".zip",
                "is_dlst": 0,
                "rowid": 2,
                "missing_since_date": None,
            },
        ]
        index = build_db_index(db_rows, "C:/lib")
        self.assertEqual(index.missing_path_set, {"gone.zip"})


if __name__ == "__main__":
    unittest.main()
