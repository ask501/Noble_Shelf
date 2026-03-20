"""
scanner.py - ライブラリフォルダのスキャン・DB登録
旧mainの _scan_and_cache を独立モジュール化。
バックグラウンドスレッドで実行し、完了をシグナルで通知する。
"""
from __future__ import annotations
import os

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

import db


# ══════════════════════════════════════════════════════════
#  スキャンワーカー
# ══════════════════════════════════════════════════════════

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")

# DMM/DLSiteの専用ファイル形式
STORE_FILE_EXTS = (".dmmb", ".dmme", ".dmmr", ".dlst")


class ScannerSignals(QObject):
    progress = Signal(int, int)   # scanned, total_found
    finished = Signal(list)       # books (list of dict)
    storeFilesPending = Signal(list)  # [{"path", "name", "mtime", "suggested_circle", "suggested_title"}, ...]
    error    = Signal(str)


class ScannerWorker(QRunnable):
    """
    ライブラリフォルダを差分スキャンしてDBを更新するワーカー。
    ルール:
      - サブフォルダ1階層のみ
      - フォルダ名 "サークル - タイトル" 形式でパース
      - 画像ファイルがないフォルダはスキップ
      - 消えたフォルダはDBから削除
    """

    def __init__(self, library_folder: str):
        super().__init__()
        self.library_folder = library_folder
        self.signals = ScannerSignals()
        self.setAutoDelete(True)

    def run(self):
        try:
            books = self._scan()
            self.signals.finished.emit(books)
        except Exception as e:
            self.signals.error.emit(str(e))

    def _scan(self) -> list[dict]:
        folder = self.library_folder
        known = db.get_known_paths()
        found_paths: set[str] = set()
        upserts: list[tuple] = []
        pending_store_files: list[dict] = []

        entries = []
        try:
            entries = [e for e in os.listdir(folder)]
        except PermissionError as e:
            raise RuntimeError(f"フォルダを開けません: {e}")

        total = len(entries)
        for i, name in enumerate(entries):
            path = os.path.join(folder, name)
            if not os.path.isdir(path):
                # ストアファイル（.dmmb/.dmme/.dmmr/.dlst）を直接登録
                if name.lower().endswith(STORE_FILE_EXTS):
                    found_paths.add(path)
                    try:
                        mtime = os.path.getmtime(path)
                    except OSError:
                        continue
                    if path not in known or known[path] != mtime:
                        stem = os.path.splitext(name)[0]
                        suggested_circle, suggested_title = db.parse_display_name(stem)
                        if not suggested_title:
                            suggested_title = stem
                        pending_store_files.append({
                            "path": path,
                            "name": name,
                            "mtime": mtime,
                            "suggested_circle": suggested_circle,
                            "suggested_title": suggested_title,
                        })
                    self.signals.progress.emit(i + 1, total)
                continue
            # まず mtime を取得し、既知＆変更なしのフォルダは中身の列挙自体をスキップする
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue

            found_paths.add(path)

            if path in known and known.get(path) == mtime:
                # 既知かつ mtime も同一 → フォルダ内容に変更なしとみなしてスキップ
                self.signals.progress.emit(i + 1, total)
                continue

            # 変更があったフォルダのみ中身をチェックしてDB更新
            try:
                child_entries = os.listdir(path)
            except PermissionError:
                continue

            images = sorted(
                f for f in child_entries
                if f.lower().endswith(IMAGE_EXTS)
            )

            if not images:
                self.signals.progress.emit(i + 1, total)
                continue
            cover_path = os.path.join(path, images[0])

            # 表示名は [サークル名]作品名。parse_display_name で分解（旧形式 サークル - 作品 も読める）
            circle, title = db.parse_display_name(name)
            if not title:
                title = name.strip()
            display_name = db.format_book_name(circle, title)

            if path not in known or known[path] != mtime:
                upserts.append((display_name, circle, title, path, cover_path, mtime, 0))

            self.signals.progress.emit(i + 1, total)

        # ここまでの upsert を一括で反映
        if upserts:
            db.bulk_upsert_books(upserts)

        # ストアファイルは登録せず pending としてメインスレッドに渡す（入力ダイアログ用）
        if pending_store_files:
            self.signals.storeFilesPending.emit(pending_store_files)

        # 消えたパスをDBから削除
        # フォルダ → found_pathsにないもの
        # ファイル系（pdf/dlst/dmme等）→ os.path.exists()で個別チェック
        all_books = db.get_all_books()
        delete_paths: list[str] = []
        for row in all_books:
            path = row[3]
            if not path:
                continue
            if os.path.isdir(path):
                # フォルダ: スキャンで見つからなかったら削除
                if path not in found_paths:
                    delete_paths.append(path)
            else:
                # ファイル: 実際に存在しなければ削除
                if not os.path.exists(path):
                    delete_paths.append(path)

        if delete_paths:
            db.bulk_delete_books(delete_paths)

        # 最新のDBデータを返す
        rows = db.get_all_books()
        return [
            {
                "path":   row[3],
                "name":   row[0],
                "title":  row[2] or row[0],
                "circle": row[1] or "",
                "cover":  row[4] or "",
                "pages":  0,
                "rating": 0,
            }
            for row in rows
            if row[3]
        ]


# ══════════════════════════════════════════════════════════
#  公開API
# ══════════════════════════════════════════════════════════

def scan_library(
    library_folder: str,
    on_finished,          # callable(list[dict])
    on_progress=None,     # callable(int, int) | None
    on_error=None,        # callable(str) | None
    on_store_files_pending=None,  # callable(list[dict]) | None  # ストアファイル入力ダイアログ用
):
    """
    ライブラリフォルダを非同期スキャンする。
    on_finished(books) はメインスレッドで呼ばれる（Qt シグナル経由）。
    新規 .dmmb/.dmme/.dmmr/.dlst は on_store_files_pending(pending_list) で渡す。
    """
    worker = ScannerWorker(library_folder)
    worker.signals.finished.connect(on_finished)
    if on_progress:
        worker.signals.progress.connect(on_progress)
    if on_error:
        worker.signals.error.connect(on_error)
    if on_store_files_pending:
        worker.signals.storeFilesPending.connect(on_store_files_pending)
    QThreadPool.globalInstance().start(worker)
