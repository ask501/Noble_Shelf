from __future__ import annotations

import os


def scan_unregistered(library_path: str, db) -> list[dict]:
    """ライブラリ直下の未登録項目を取得する（再帰なし）。"""
    base = os.path.normcase(os.path.normpath(os.path.abspath(library_path or "")))
    if not base or not os.path.isdir(base):
        return []

    registered_paths = {
        os.path.normcase(os.path.normpath(os.path.abspath(path)))
        for _, _, _, path, _, _ in db.get_all_books()
        if path
    }
    hidden_paths = {
        os.path.normcase(os.path.normpath(os.path.abspath(path)))
        for path in db.get_hidden_paths()
        if path
    }

    results: list[dict] = []
    with os.scandir(base) as it:
        for entry in it:
            full_path = os.path.normpath(os.path.abspath(entry.path))
            norm_path = os.path.normcase(full_path)
            is_hidden = norm_path in hidden_paths
            # 未登録のみ表示。ただし hidden_paths にあるものは表示対象に残す。
            if norm_path in registered_paths and not is_hidden:
                continue
            results.append(
                {
                    "path": full_path,
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "hidden": is_hidden,
                }
            )
    results.sort(key=lambda x: x["name"].lower())
    return results

