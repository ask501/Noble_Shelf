"""
scanners/book_scanner.py - 同人誌（book）ライブラリのスキャン
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid as uuid_lib

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

import config
import db
from scanners.base_scanner import BaseScanner


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")

# DMM/DLSiteの専用ファイル形式
STORE_FILE_EXTS = (".dmmb", ".dmme", ".dmmr", ".dlst")


class ScannerSignals(QObject):
    progress = Signal(int, int)  # scanned, total_found
    finished = Signal(list)  # books (list of dict)
    storeFilesPending = Signal(list)  # [{"path", "name", "mtime", ...}, ...]
    error = Signal(str)
    # UUID重複（先勝ちで後から来たフォルダを振り直した）ときのトースト用
    uuidDuplicateToast = Signal(str)


def _atomic_write_noble_shelf_id(folder_path: str, uid: str) -> bool:
    """`.noble-shelf-id` を tmp→rename で原子書き込みする。"""
    id_file = os.path.join(folder_path, config.NOBLE_SHELF_ID_FILENAME)
    tmp_file = id_file + config.NOBLE_SHELF_ID_TMP_SUFFIX
    with open(tmp_file, "w", encoding="utf-8") as f:
        f.write(uid)
    delays_ms = config.NOBLE_SHELF_ID_WRITE_RETRY_DELAY_MS
    attempts = len(delays_ms)
    for attempt in range(attempts):
        try:
            os.replace(tmp_file, id_file)
            return True
        except PermissionError as e:
            if attempt < attempts - 1:
                time.sleep(delays_ms[attempt] / 1000.0)
                continue
            logging.warning(
                "noble-shelf-id の書き込みに失敗しました（リトライ後スキップ）: %s (%s)",
                id_file,
                e,
            )
            return False
        except OSError as e:
            logging.warning("noble-shelf-id の書き込みに失敗しました: %s (%s)", id_file, e)
            return False
    return False


def _cleanup_tmp_id_files(library_folder: str) -> None:
    """library_folder直下のサブフォルダに残った .tmp を削除する。"""
    try:
        entries = os.listdir(library_folder)
    except OSError:
        return
    for name in entries:
        sub = os.path.join(library_folder, name)
        if not os.path.isdir(sub):
            continue
        tmp_path = os.path.join(
            sub, config.NOBLE_SHELF_ID_FILENAME + config.NOBLE_SHELF_ID_TMP_SUFFIX
        )
        if not os.path.isfile(tmp_path):
            continue
        try:
            os.remove(tmp_path)
        except OSError as e:
            logging.warning("tmp ID ファイルの削除に失敗しました: %s (%s)", tmp_path, e)


def _read_noble_shelf_id(id_path: str) -> tuple[str | None, str | None]:
    """
    `.noble-shelf-id` を読む。IOエラーは指数バックオフでリトライする。
    戻り値: (uuid, None) 成功 / (None, 'io') / (None, 'corrupt')
    """
    delays_ms = config.NOBLE_SHELF_ID_READ_BACKOFF_MS
    pattern = re.compile(config.NOBLE_SHELF_UUID_V4_REGEX)
    attempts = len(delays_ms)
    for attempt in range(attempts):
        try:
            with open(id_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            if attempt < attempts - 1:
                time.sleep(delays_ms[attempt] / 1000.0)
                continue
            logging.warning(
                "noble-shelf-id の読み取りに失敗しました（リトライ後スキップ）: %s (%s)",
                id_path,
                e,
            )
            return None, "io"

        text = raw.replace("\ufeff", "").strip()
        lines = text.splitlines()
        first = lines[0].strip() if lines else ""
        if not first:
            return None, "corrupt"
        if pattern.fullmatch(first):
            return first, None
        return None, "corrupt"

    return None, "io"


def _library_abs_path(library_root: str, rel_or_abs: str) -> str:
    """DBの path（相対または絶対）をライブラリ基準の絶対パスに揃える。"""
    p = (rel_or_abs or "").strip()
    if not p:
        return ""
    if os.path.isabs(p):
        return os.path.normpath(p)
    return os.path.normpath(os.path.join(library_root, p))


class BookScannerWorker(QRunnable):
    """
    指定フォルダ直下を差分スキャンしてDBを更新するワーカー。
    ルール:
      - サブフォルダ1階層のみ
      - フォルダ名 "サークル - タイトル" 形式でパース
      - 画像ファイルがないフォルダはスキップ
      - 消えたフォルダはDBから削除（本スキャンルート配下のみ）
      - 各作品フォルダに `.noble-shelf-id`（UUID v4）を保持
    """

    def __init__(self, library_folder: str):
        super().__init__()
        self.library_folder = library_folder
        self.signals = ScannerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            books = self._scan()
            self.signals.finished.emit(books)
        except Exception as e:
            self.signals.error.emit(str(e))

    def _resolve_folder_uuid(
        self,
        abs_folder: str,
        rel_folder: str,
        folder_entry_name: str,
        uuid_first_rel: dict[str, str],
    ) -> str | None:
        """
        フォルダの UUID を確定する。
        - IDなし: 新規生成＋原子書き込み
        - 読取IO失敗: None（スキップ）
        - 破損: 新規UUIDで上書き
        - 重複（先勝ち）: 後から来たフォルダを新UUIDに振り直し、トースト用シグナル発火
        """
        id_path = os.path.join(abs_folder, config.NOBLE_SHELF_ID_FILENAME)
        norm_rel = os.path.normpath(rel_folder)
        book_uuid: str

        if not os.path.isfile(id_path):
            book_uuid = str(uuid_lib.uuid4())
            if not _atomic_write_noble_shelf_id(abs_folder, book_uuid):
                return None
        else:
            read_uuid, err = _read_noble_shelf_id(id_path)
            if err == "io":
                return None
            if err == "corrupt":
                logging.warning("noble-shelf-id が不正です。再生成します: %s", id_path)
                book_uuid = str(uuid_lib.uuid4())
                if not _atomic_write_noble_shelf_id(abs_folder, book_uuid):
                    return None
            else:
                book_uuid = (read_uuid or "").strip()
                if not book_uuid:
                    book_uuid = str(uuid_lib.uuid4())
                    if not _atomic_write_noble_shelf_id(abs_folder, book_uuid):
                        return None

        if book_uuid in uuid_first_rel:
            if os.path.normpath(uuid_first_rel[book_uuid]) != norm_rel:
                new_uuid = str(uuid_lib.uuid4())
                if not _atomic_write_noble_shelf_id(abs_folder, new_uuid):
                    return None
                msg = config.SCAN_UUID_DUPLICATE_TOAST_TEMPLATE.format(name=folder_entry_name)
                self.signals.uuidDuplicateToast.emit(msg)
                book_uuid = new_uuid

        uuid_first_rel[book_uuid] = norm_rel
        return book_uuid

    def _maybe_sync_db_path_for_move(self, book_uuid: str, rel_folder: str) -> None:
        """DB上の path とディスク上の相対パスがずれていれば更新（移動・リネーム）。"""
        row = db.get_book_by_uuid(book_uuid)
        if not row:
            return
        db_path = (row.get("path") or "").strip()
        if os.path.normpath(db_path) == os.path.normpath(rel_folder):
            return
        db.update_book_path_by_uuid(book_uuid, rel_folder)

    def _scan(self) -> list[dict]:
        folder = self.library_folder
        if not os.path.isdir(folder):
            raise RuntimeError(f"ライブラリフォルダが見つかりません（外付けHDD切断等）: {folder}")
        t_start = time.perf_counter()
        _cleanup_tmp_id_files(folder)
        t1 = time.perf_counter()
        logging.info("[SCAN] phase=cleanup_tmp %.3fs", t1 - t_start)
        raw_known = db.get_known_paths()
        t2 = time.perf_counter()
        logging.info("[SCAN] phase=get_known_paths %.3fs", t2 - t1)
        known = {os.path.normcase(os.path.normpath(k)): v for k, v in raw_known.items()}
        found_paths: set[str] = set()
        pending_store_files: list[dict] = []
        uuid_first_rel: dict[str, str] = {}
        upsert_queue: list[tuple] = []

        entries = []
        try:
            entries = [e for e in os.listdir(folder)]
        except PermissionError as e:
            raise RuntimeError(f"フォルダを開けません: {e}")

        total = len(entries)
        t3 = time.perf_counter()
        logging.info("[SCAN] phase=listdir_root entries=%d %.3fs", total, t3 - t2)

        def _emit_progress(current: int) -> None:
            """進捗通知を間引いて発火する。"""
            if (
                current % config.SCAN_PROGRESS_EMIT_INTERVAL == 0
                or current == total
            ):
                self.signals.progress.emit(current, total)

        for i, name in enumerate(entries):
            path = os.path.join(folder, name)
            if not os.path.isdir(path):
                if name.lower().endswith(STORE_FILE_EXTS):
                    try:
                        rel_store = os.path.normpath(db._to_db_path(path))
                    except ValueError:
                        rel_store = os.path.normpath(os.path.relpath(path, folder))
                    rel_store_key = os.path.normcase(os.path.normpath(rel_store))
                    found_paths.add(rel_store_key)
                    try:
                        mtime = os.path.getmtime(path)
                    except OSError:
                        _emit_progress(i + 1)
                        continue
                    if rel_store_key not in known or known.get(rel_store_key) != mtime:
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
                    _emit_progress(i + 1)
                elif name.lower().endswith(".pdf"):
                    try:
                        rel_pdf = os.path.normpath(db._to_db_path(path))
                    except ValueError:
                        rel_pdf = os.path.normpath(os.path.relpath(path, folder))
                    rel_pdf_key = os.path.normcase(os.path.normpath(rel_pdf))
                    found_paths.add(rel_pdf_key)
                    try:
                        mtime = os.path.getmtime(path)
                    except OSError:
                        _emit_progress(i + 1)
                        continue
                    known_key = os.path.normcase(os.path.normpath(rel_pdf))
                    if (
                        known_key in known
                        and abs((known.get(known_key) or 0) - mtime) < config.MTIME_TOLERANCE
                    ):
                        _emit_progress(i + 1)
                        continue
                    # PDF登録処理
                    from drop_handler import _get_pdf_cover_and_pages
                    abs_path = path  # すでに絶対パスで構築済み
                    cover, pages = _get_pdf_cover_and_pages(abs_path)
                    stem = os.path.splitext(name)[0]
                    circle, title = db.parse_display_name(stem)
                    if not title:
                        title = stem
                    book_name = db.format_book_name(circle, title)
                    db.upsert_store_file_book(rel_pdf, book_name, circle, title, cover, mtime, 0, pages)
                    _emit_progress(i + 1)
                    continue
                continue
            try:
                rel_path = db._to_db_path(path)
            except ValueError:
                rel_path = os.path.normpath(os.path.relpath(path, folder))
            rel_path = os.path.normpath(rel_path)
            rel_path_key = os.path.normcase(rel_path)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                found_paths.add(rel_path_key)
                _emit_progress(i + 1)
                continue

            # ディスク上にある作品フォルダはすべて「スキャンで見つかった」扱い（画像なしも削除判定用）
            found_paths.add(rel_path_key)

            try:
                child_entries = os.listdir(path)
            except PermissionError:
                _emit_progress(i + 1)
                continue

            images = sorted(
                f for f in child_entries
                if f.lower().endswith(IMAGE_EXTS)
            )

            if not images:
                _emit_progress(i + 1)
                continue

            book_uuid = self._resolve_folder_uuid(path, rel_path, name, uuid_first_rel)
            if book_uuid is None:
                _emit_progress(i + 1)
                continue

            self._maybe_sync_db_path_for_move(book_uuid, rel_path)

            if rel_path_key in known and known.get(rel_path_key) == mtime:
                _emit_progress(i + 1)
                continue

            cover_abs = os.path.join(path, images[0])
            try:
                cover_rel = db._to_db_path(cover_abs)
            except ValueError:
                cover_rel = os.path.normpath(os.path.join(rel_path, images[0]))

            circle, title = db.parse_display_name(name)
            if not title:
                title = name.strip()
            display_name = db.format_book_name(circle, title)

            if rel_path_key not in known or known.get(rel_path_key) != mtime:
                upsert_queue.append(
                    (
                        book_uuid,
                        display_name,
                        circle,
                        title,
                        rel_path,
                        cover_rel,
                        mtime,
                        0,
                    )
                )

            _emit_progress(i + 1)

        t_after_walk = time.perf_counter()
        logging.info("[SCAN] phase=walk_loop %.3fs", t_after_walk - t3)
        if pending_store_files:
            self.signals.storeFilesPending.emit(pending_store_files)
        scan_root_norm = os.path.normcase(os.path.normpath(folder))
        all_books = db.get_all_books()
        t4 = time.perf_counter()
        logging.info("[SCAN] phase=get_all_books %.3fs", t4 - t_after_walk)
        delete_paths: list[str] = []
        under_scan_root_count = 0
        for row in all_books:
            path = row[3]
            if not path:
                continue
            abs_row = _library_abs_path(folder, path)
            p_norm = os.path.normcase(os.path.normpath(abs_row))
            if p_norm != scan_root_norm and not p_norm.startswith(scan_root_norm + os.sep):
                continue
            under_scan_root_count += 1
            norm_key = os.path.normcase(os.path.normpath(path))
            if os.path.isdir(abs_row):
                if norm_key not in found_paths:
                    delete_paths.append(path)
            else:
                if not os.path.exists(abs_row):
                    delete_paths.append(path)

        t5 = time.perf_counter()
        logging.info("[SCAN] phase=delete_check %.3fs", t5 - t4)
        if (
            delete_paths
            and under_scan_root_count > 0
            and len(delete_paths) * config.SCAN_STALE_DELETE_SKIP_FRACTION_DENOMINATOR
            >= under_scan_root_count * config.SCAN_STALE_DELETE_SKIP_FRACTION_NUMERATOR
        ):
            logging.warning(
                "スキャンでの一括DB削除を見送りました（削除候補が多すぎます）。"
                " 候補=%s件 / ルート配下の登録=%s件。ライブラリフォルダの指定を確認してください。",
                len(delete_paths),
                under_scan_root_count,
            )
            delete_paths = []

        db.bulk_upsert_and_delete_books(upsert_queue, delete_paths)
        t6 = time.perf_counter()
        logging.info(
            "[SCAN] phase=bulk_db upsert=%d delete=%d %.3fs",
            len(upsert_queue),
            len(delete_paths),
            t6 - t5,
        )

        t_after_db = time.perf_counter()
        logging.info(
            "[SCAN] 完了: 総時間=%.2fs / 件数=%d件 / 平均=%.1fms/件 | "
            "FS走査=%.2fs / DB適用=%.2fs",
            t_after_db - t_start,
            total,
            (t_after_db - t_start) / max(total, 1) * 1000,
            t_after_walk - t_start,
            t_after_db - t_after_walk,
        )

        rows = db.get_all_books()
        t7 = time.perf_counter()
        logging.info("[SCAN] phase=final_fetch %.3fs", t7 - t_after_db)
        return [
            {
                "path": row[3],
                "name": row[0],
                "title": row[2] or row[0],
                "circle": row[1] or "",
                "cover": row[4] or "",
                "pages": 0,
                "rating": 0,
            }
            for row in rows
            if row[3]
        ]


class BookScanner(BaseScanner):
    media_type = config.BOOKS_MEDIA_TYPE_DEFAULT
    folder_name = config.BOOKS_MEDIA_TYPE_DEFAULT
    display_name_ja = "書籍・同人誌"
    target_exts = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".pdf",
        ".zip",
        ".cbz",
        ".dmmb",
        ".dmme",
        ".dmmr",
        ".dlst",
    }

    def __init__(self):
        self._active_workers: list[BookScannerWorker] = []

    def scan(
        self,
        folder,
        on_finished,
        on_progress=None,
        on_error=None,
        on_store_files_pending=None,
        on_uuid_duplicate_toast=None,
    ) -> None:
        worker = BookScannerWorker(folder)

        def _on_finished_and_release(books: list) -> None:
            if worker in self._active_workers:
                self._active_workers.remove(worker)
            on_finished(books)

        def _on_error_and_release(msg: str) -> None:
            if worker in self._active_workers:
                self._active_workers.remove(worker)
            if on_error:
                on_error(msg)

        worker.signals.finished.connect(_on_finished_and_release)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        worker.signals.error.connect(_on_error_and_release)
        if on_store_files_pending:
            worker.signals.storeFilesPending.connect(on_store_files_pending)
        if on_uuid_duplicate_toast:
            worker.signals.uuidDuplicateToast.connect(on_uuid_duplicate_toast)
        self._active_workers.append(worker)
        QThreadPool.globalInstance().start(worker)
