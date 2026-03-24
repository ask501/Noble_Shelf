"""
tools/library_organizer.py - ライブラリ直下の整理（メディア種別ごとのサブフォルダへ移動）
"""
from __future__ import annotations

import os
import shutil
import stat

from scanners import SCANNERS


def _exts_normalized(exts: set[str]) -> set[str]:
    """拡張子集合を小文字にそろえる（比較用）。"""
    return {e.lower() for e in exts}


def _all_files_match(path: str, exts: set[str]) -> bool:
    """フォルダを再帰走査し、システム・隠しファイルを除いた全ファイルが exts のみなら True"""
    for root, _, files in os.walk(path):
        for f in files:
            full = os.path.join(root, f)
            try:
                attrs = os.stat(full).st_file_attributes
                if attrs & (stat.FILE_ATTRIBUTE_SYSTEM | stat.FILE_ATTRIBUTE_HIDDEN):
                    continue
            except (OSError, AttributeError):
                pass
            ext = os.path.splitext(f)[1].lower()
            if ext not in exts:
                return False
    return True


def _detect_media_type(path: str) -> str | None:
    """
    パスのメディアタイプを判定して返す。
    どのタイプにも該当しなければ None。
    フォルダ: 再帰的に全ファイルが target_exts に一致するか
    ファイル: 拡張子が target_exts に含まれるか
    """
    for media_type, scanner_cls in SCANNERS.items():
        exts = scanner_cls.target_exts
        if os.path.isdir(path):
            if _all_files_match(path, exts):
                return media_type
        else:
            if os.path.splitext(path)[1].lower() in _exts_normalized(exts):
                return media_type
    return None


def scan_for_organize(folder: str) -> dict:
    """
    folder 直下を走査し、メディアタイプ別に分類して返す。
    戻り値:
    {
        "by_type": {
            "book": {"targets": [絶対パス, ...], "dest": str},
            # 将来: "music": {...}
        },
        "skipped": [絶対パス, ...],  # どのタイプにも該当しないアイテム
    }
    dest フォルダ自体はスキャン対象から除外する。
    """
    folder = os.path.normpath(os.path.abspath(folder))

    # すでにメディアサブフォルダを選択している場合はスキップ
    basename = os.path.basename(folder).lower()
    for cls in SCANNERS.values():
        if basename == cls.folder_name.lower():
            return {"by_type": {}, "skipped": []}

    by_type: dict[str, dict] = {
        mt: {
            "targets": [],
            "dest": os.path.normpath(os.path.join(folder, cls.folder_name)),
        }
        for mt, cls in SCANNERS.items()
    }
    dest_paths = {os.path.normpath(v["dest"]) for v in by_type.values()}
    skipped: list[str] = []

    try:
        with os.scandir(folder) as it:
            entries = list(it)
    except OSError:
        return {"by_type": {}, "skipped": []}

    for entry in entries:
        ep = os.path.normpath(entry.path)
        if ep in dest_paths:
            continue
        media_type = _detect_media_type(entry.path)
        if media_type:
            by_type[media_type]["targets"].append(entry.path)
        else:
            skipped.append(entry.path)

    by_type = {mt: v for mt, v in by_type.items() if v["targets"]}

    return {"by_type": by_type, "skipped": skipped}


def organize(folder: str) -> dict:
    """
    scan_for_organize の結果をもとに実際にファイルを移動する。
    dest が存在しなければ作成する。
    移動は shutil.move を使う。
    戻り値は再スキャン後の scan_for_organize 相当に moved_from_to を加えたもの。
    """
    snapshot = scan_for_organize(folder)
    moved_from_to: list[tuple[str, str]] = []
    for v in snapshot["by_type"].values():
        dest = v["dest"]
        if not v["targets"]:
            continue
        os.makedirs(dest, exist_ok=True)
        for path in v["targets"]:
            dest_path = os.path.normpath(os.path.join(dest, os.path.basename(path)))
            shutil.move(path, dest_path)
            moved_from_to.append((os.path.normpath(path), dest_path))

    out = scan_for_organize(folder)
    out["moved_from_to"] = moved_from_to
    return out
