"""
scanners パッケージ - メディア種別ごとのライブラリスキャン
"""
from __future__ import annotations

import os

import config
from scanners.book_scanner import BookScanner

SCANNERS: dict[str, type] = {
    "book": BookScanner,
    # "music": SoundScanner,  # 将来
    # "video": VideoScanner,  # 将来
}

# scan_library の二重起動防止（非同期スキャン完了／エラーまで True）
_scanning = False


def _resolve_scan_subfolder(library_folder: str, folder_name: str) -> str | None:
    """library_folder 配下のメディア用サブフォルダの実パスを返す。見つからなければ None。"""
    sub = os.path.join(library_folder, folder_name)
    if os.path.isdir(sub):
        return sub
    base = os.path.basename(os.path.normpath(library_folder))
    if base.lower() == folder_name.lower():
        return library_folder
    if folder_name == config.BOOKS_MEDIA_TYPE_DEFAULT and os.path.isdir(library_folder):
        return library_folder
    return None


def scan_library(
    library_folder: str,
    on_finished,
    on_progress=None,
    on_error=None,
    on_store_files_pending=None,
    on_uuid_duplicate_toast=None,
) -> None:
    """library_folder 直下の各メディアサブフォルダを対応するスキャナで非同期スキャンする。
    全スキャナ完了後に on_finished を1回だけ呼ぶ。"""
    global _scanning
    if _scanning:
        return

    targets = []
    for scanner_cls in SCANNERS.values():
        scanner = scanner_cls()
        sub = _resolve_scan_subfolder(library_folder, scanner.folder_name)
        if sub is not None:
            targets.append((scanner, sub))

    if not targets:
        _scanning = True
        try:
            if on_finished is not None:
                on_finished([])
        finally:
            _scanning = False
        return

    _scanning = True

    def _on_error_wrapped(msg: str) -> None:
        global _scanning
        _scanning = False
        if on_error is not None:
            on_error(msg)

    # 全スキャナ完了後に1回だけ on_finished を呼ぶための集約
    total = len(targets)
    pending = [total]
    merged: list[list] = [[]]  # ミュータブルな集約バッファ

    def _on_one_finished(books: list) -> None:
        global _scanning
        merged[0] = merged[0] + books
        pending[0] -= 1
        if pending[0] == 0:
            try:
                if on_finished is not None:
                    on_finished(merged[0])
            finally:
                _scanning = False

    try:
        for scanner, sub in targets:
            scanner.scan(
                sub,
                on_finished=_on_one_finished,
                on_progress=on_progress,
                on_error=_on_error_wrapped,
                on_store_files_pending=on_store_files_pending,
                on_uuid_duplicate_toast=on_uuid_duplicate_toast,
            )
    except Exception:
        _scanning = False
        raise
