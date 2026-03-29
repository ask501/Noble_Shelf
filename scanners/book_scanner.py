"""
scanners/book_scanner.py - 同人誌（book）ライブラリのスキャン
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid as uuid_lib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

import config
import db
from db import _normalize_cover_for_save
import store_file_resolver as store_resolver
from drop_handler import _get_pdf_cover_and_pages
from store_file_resolver import ActionResult, FileContext, resolve_store_file_action
from scanners.base_scanner import BaseScanner


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def _compute_cover_hash_for_folder(folder_path: str, images: list[str]) -> str | None:
    """フォルダ内の先頭画像（ソート済みリスト先頭）の hash を返す。"""
    if not images:
        return None
    cover_abs = os.path.join(folder_path, images[0])
    return db._compute_store_content_hash(cover_abs)


def _preview_path_list(paths: list[str], limit: int) -> str:
    """診断ログ用に path リストを短く整形する。"""
    if not paths:
        return "[]"
    sorted_paths = sorted(paths)
    if len(sorted_paths) <= limit:
        return repr(sorted_paths)
    head = sorted_paths[:limit]
    return repr(head) + f" ... (+{len(sorted_paths) - limit} 件)"

# DMM/DLSiteの専用ファイル形式
STORE_FILE_EXTS = (".dmmb", ".dmme", ".dmmr", ".dlst")

_logger = logging.getLogger(__name__)


class ScannerSignals(QObject):
    progress = Signal(int, int)  # scanned, total_found
    finished = Signal(list, list)  # books, duplicate_results
    storeActionSummary = Signal(list, list)  # rename_results, error_results
    error = Signal(str)
    # UUID重複（先勝ちで後から来たフォルダを振り直した）ときのトースト用
    uuidDuplicateToast = Signal(str)


@dataclass(frozen=True)
class RootFsEntry:
    """ライブラリ直下のストアファイル／PDF（Phase1 の列挙結果）。"""

    abs_path: str
    db_path: str
    content_hash: str
    size: int
    mtime: float
    is_pdf: bool


def _fs_dict_to_root_entry(d: dict) -> RootFsEntry:
    """Phase1 の dict を RootFsEntry に変換する。"""
    return RootFsEntry(
        abs_path=str(d["abs_path"]),
        db_path=os.path.normpath(str(d["path"])),
        content_hash=str(d["hash"]),
        size=int(d["size"]),
        mtime=float(d["mtime"]),
        is_pdf=bool(d.get("is_pdf", False)),
    )


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


def _is_root_level_store_or_pdf(db_path: str) -> bool:
    """DB path がライブラリ直下のストア拡張子／PDF か。"""
    p = os.path.normpath(db_path)
    if os.path.dirname(p) not in ("", "."):
        return False
    base = os.path.basename(p).lower()
    if base.endswith(STORE_FILE_EXTS):
        return True
    return base.endswith(".pdf")


def _row_under_scan_library(library_folder: str, path: str) -> bool:
    """path が当該スキャンルート配下のブックとして扱うか。"""
    path = (path or "").strip()
    if not path:
        return False
    abs_row = _library_abs_path(library_folder, path)
    scan_root_norm = os.path.normcase(os.path.normpath(library_folder))
    p_norm = os.path.normcase(os.path.normpath(abs_row))
    return p_norm == scan_root_norm or p_norm.startswith(scan_root_norm + os.sep)


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
            books, duplicate_candidates = self._scan()
            self.signals.finished.emit(books, duplicate_candidates)
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
            # 初回登録前のウォークでは行が無い（正常）。初回 bulk 後は DB に載る。
            return
        db_path = (row.get("path") or "").strip()
        if os.path.normpath(db_path) == os.path.normpath(rel_folder):
            return
        logging.info(
            "[SCAN] path_sync_move APPLY uuid=%s old_path=%s new_rel=%s",
            book_uuid,
            db_path,
            rel_folder,
        )
        db.update_book_path_by_uuid(book_uuid, rel_folder)

    def _collect_fs_files(
        self, library_path: str
    ) -> tuple[list[dict], set[str], list[ActionResult]]:
        """
        Phase1: ライブラリ直下の対象ファイルを列挙し path・hash・size を計算する（SQLite に触らない）。
        戻り値の各 dict は path / hash / size / mtime / abs_path / is_pdf を含む。
        """
        try:
            entries = [e for e in os.listdir(library_path)]
        except PermissionError as e:
            raise RuntimeError(f"フォルダを開けません: {e}")
        out: list[dict] = []
        hash_failed_paths: set[str] = set()
        error_results: list[ActionResult] = []

        for name in entries:
            path = os.path.join(library_path, name)
            if os.path.isdir(path):
                continue
            low = name.lower()
            if not (low.endswith(STORE_FILE_EXTS) or low.endswith(".pdf")):
                continue
            rel = os.path.normpath(os.path.relpath(path, library_path))
            try:
                st = os.stat(path)
                size = int(st.st_size)
                mtime = float(st.st_mtime)
            except OSError as e:
                error_results.append(
                    ActionResult(
                        status="error",
                        db_path=rel,
                        error_type="IO_ERROR",
                        error_message=str(e),
                    )
                )
                continue
            content_hash = db._compute_store_content_hash(path)
            if not content_hash:
                hash_failed_paths.add(rel)
                error_results.append(
                    ActionResult(
                        status="error",
                        db_path=rel,
                        error_type="HASH_ERROR",
                        error_message="content hash unavailable",
                    )
                )
                continue
            out.append(
                {
                    "path": rel,
                    "hash": content_hash,
                    "size": size,
                    "mtime": mtime,
                    "abs_path": path,
                    "is_pdf": low.endswith(".pdf"),
                }
            )
        return out, hash_failed_paths, error_results

    def _classify(
        self,
        fs_files: list[dict],
        db_rows: list[dict],
        library_folder: str,
        hash_failed_paths: set[str],
    ) -> tuple[
        dict[str, list[dict]],
        list[dict],
        list[tuple[dict, dict]],
        list[tuple[dict, dict]],
    ]:
        """
        Phase2: メモリ上の DB 行と FS 一覧を path キーで比較（SQLite に触らない）。
        戻り値: missing_map, created_candidates, existing, updated
        """
        fs_by_path: dict[str, dict] = {}
        for d in fs_files:
            fs_by_path[os.path.normpath(str(d["path"]))] = d

        root_rows_by_path: dict[str, dict] = {}
        for row in db_rows:
            p = (row.get("path") or "").strip()
            if not p:
                continue
            if not _row_under_scan_library(library_folder, p):
                continue
            np = os.path.normpath(p)
            if not _is_root_level_store_or_pdf(np):
                continue
            root_rows_by_path[np] = row

        missing_map: dict[str, list[dict]] = defaultdict(list)
        for db_path, row in root_rows_by_path.items():
            if db_path in fs_by_path:
                continue
            if db_path in hash_failed_paths:
                continue
            h = (row.get("content_hash") or "").strip() or None
            key = h if h else config.SCAN_MISSING_HASH_MAP_KEY
            missing_map[key].append(row)
        for key in list(missing_map.keys()):
            missing_map[key].sort(key=lambda r: int(r.get("rowid") or 0))

        created_candidates: list[dict] = []
        for db_path, d in fs_by_path.items():
            if db_path not in root_rows_by_path:
                created_candidates.append(d)

        existing: list[tuple[dict, dict]] = []
        updated_pairs: list[tuple[dict, dict]] = []
        for db_path, d in fs_by_path.items():
            row = root_rows_by_path.get(db_path)
            if not row:
                continue
            db_hash = (row.get("content_hash") or "").strip() or None
            fs_hash = str(d.get("hash") or "")
            if db_hash and fs_hash == db_hash:
                existing.append((row, d))
                continue
            if not db_hash and fs_hash:
                updated_pairs.append((row, d))
                continue
            if db_hash and fs_hash and db_hash != fs_hash:
                updated_pairs.append((row, d))
                continue
            if not db_hash and not fs_hash:
                rm = row.get("mtime")
                if rm is not None and abs(float(rm) - float(d["mtime"])) < config.MTIME_TOLERANCE:
                    existing.append((row, d))
                    continue
                updated_pairs.append((row, d))

        return dict(missing_map), created_candidates, existing, updated_pairs

    def _resolve_renames(
        self,
        created_candidates: list[dict],
        missing_map: dict[str, list[dict]],
    ) -> tuple[list[tuple[dict, dict]], list[dict], dict[str, list[dict]]]:
        """
        Phase3: created と missing を hash で突き合わせ rename を解決する。
        missing_map は破壊せずコピーして消費する。
        """
        mm = {k: list(v) for k, v in missing_map.items()}
        renames: list[tuple[dict, dict]] = []
        true_created: list[dict] = []

        for c in sorted(created_candidates, key=lambda x: str(x["path"])):
            h = str(c.get("hash") or "")
            if h in mm and mm[h]:
                row = mm[h].pop(0)
                renames.append((row, c))
                if not mm[h]:
                    del mm[h]
            else:
                true_created.append(c)
        return renames, true_created, mm

    def _apply_missing_ttl_for_rows(
        self,
        rows: list[dict],
        delete_paths_out: list[str],
    ) -> None:
        """missing_since_date と MISSING_BOOK_TTL_DAYS に基づき、TTL 経過分の path を delete_paths_out に追加する。

        - missing が未記録 → mark_missing_since_if_null のみ（削除しない）
        - TTL 未満 → 何もしない
        - TTL 以上 → delete_paths_out に path を追加
        """
        now_iso = datetime.utcnow().isoformat()
        for r in rows:
            p = (r.get("path") or "").strip()
            if not p:
                continue
            missing_since = (r.get("missing_since_date") or "").strip()
            if not missing_since:
                db.mark_missing_since_if_null(p, now_iso)
                continue
            try:
                dt_missing = datetime.fromisoformat(missing_since)
                elapsed_days = (datetime.utcnow() - dt_missing).days
            except Exception:
                elapsed_days = config.MISSING_BOOK_TTL_DAYS
            if elapsed_days >= config.MISSING_BOOK_TTL_DAYS:
                delete_paths_out.append(p)

    def _apply_changes(
        self,
        renames: list[tuple[dict, dict]],
        created: list[dict],
        existing: list[tuple[dict, dict]],
        updated: list[tuple[dict, dict]],
        remaining_missing: dict[str, list[dict]],
        *,
        duplicate_out: list[ActionResult],
        rename_out: list[ActionResult],
        error_out: list[ActionResult],
        delete_paths_root: list[str],
    ) -> None:
        """Phase4: ルートストア／PDF の DB 一括適用（rename → updated → created → missing TTL）。"""
        folder = self.library_folder

        # FS上で再検出された行は missing_since_date をクリアする。
        rediscovered_paths = {
            os.path.normpath((row.get("path") or "").strip())
            for row, _ in (existing + updated)
            if (row.get("path") or "").strip()
        }
        if rediscovered_paths:
            db.clear_missing_since_for_paths(sorted(rediscovered_paths))

        for row, fs_dict in renames:
            fs_entry = _fs_dict_to_root_entry(fs_dict)
            uuid = str(row.get("uuid") or "").strip()
            old_path = (row.get("path") or "").strip()
            new_path = fs_entry.db_path
            db_mtime = float(row["mtime"]) if row.get("mtime") is not None else None
            db.rename_book_path(
                uuid,
                new_path,
                db_mtime,
                fs_entry.content_hash,
            )
            rename_out.append(
                ActionResult(
                    status="rename",
                    db_path=new_path,
                    existing_uuid=uuid,
                    existing_path=old_path,
                )
            )

        for row, fs_dict in updated:
            fs_entry = _fs_dict_to_root_entry(fs_dict)
            db_path = os.path.normpath((row.get("path") or "").strip())
            uuid = str(row.get("uuid") or "").strip()
            db_mtime = float(row["mtime"]) if row.get("mtime") is not None else None
            is_dlst = 1 if db_path.lower().endswith(config.STORE_FILE_EXT_DLSITE) else 0
            stem = os.path.splitext(os.path.basename(db_path))[0]
            suggested_circle, suggested_title = db.parse_display_name(stem)
            if not suggested_title:
                suggested_title = stem
            display_name = db.format_book_name(suggested_circle, suggested_title) or stem

            if fs_entry.is_pdf:
                cover_raw, pages = _get_pdf_cover_and_pages(fs_entry.abs_path)
                cover = _normalize_cover_for_save(cover_raw) if cover_raw else ""
            else:
                cover, pages = "", None

            result = ActionResult(
                status="updated",
                db_path=db_path,
                existing_uuid=uuid,
                existing_path=db_path,
            )
            db.apply_action_result(
                result,
                {
                    "name": display_name,
                    "circle": suggested_circle,
                    "title": suggested_title,
                    "cover_path": cover,
                    "mtime": db_mtime,
                    "is_dlst": bool(is_dlst),
                    "pages": pages,
                    "content_hash": fs_entry.content_hash,
                },
            )

        if created:
            index_rows = db.fetch_all_rows_for_index()
            store_index = store_resolver.build_db_index(index_rows, library_root=folder)

            for fs_dict in created:
                fs_entry = _fs_dict_to_root_entry(fs_dict)
                mtime = fs_entry.mtime
                stem = os.path.splitext(os.path.basename(fs_entry.db_path))[0]
                is_dlst = 1 if fs_entry.db_path.lower().endswith(config.STORE_FILE_EXT_DLSITE) else 0
                if fs_entry.is_pdf:
                    cover_raw, pages = _get_pdf_cover_and_pages(fs_entry.abs_path)
                    cover = _normalize_cover_for_save(cover_raw) if cover_raw else ""
                    circle, title = db.parse_display_name(stem)
                    if not title:
                        title = stem
                    book_name = db.format_book_name(circle, title)
                    result = resolve_store_file_action(
                        FileContext(
                            abs_path=fs_entry.abs_path,
                            db_path=fs_entry.db_path,
                            content_hash=fs_entry.content_hash,
                            mtime=mtime,
                            file_ext=os.path.splitext(fs_entry.db_path)[1].lower(),
                            is_dlst=False,
                        ),
                        store_index,
                    )
                    book_data = {
                        "name": book_name,
                        "circle": circle,
                        "title": title,
                        "cover_path": cover,
                        "mtime": mtime,
                        "is_dlst": False,
                        "pages": pages,
                        "content_hash": fs_entry.content_hash,
                    }
                else:
                    suggested_circle, suggested_title = db.parse_display_name(stem)
                    if not suggested_title:
                        suggested_title = stem
                    display_name = (
                        db.format_book_name(suggested_circle, suggested_title)
                        or os.path.basename(fs_entry.db_path)
                    )
                    result = resolve_store_file_action(
                        FileContext(
                            abs_path=fs_entry.abs_path,
                            db_path=fs_entry.db_path,
                            content_hash=fs_entry.content_hash,
                            mtime=mtime,
                            file_ext=os.path.splitext(fs_entry.db_path)[1].lower(),
                            is_dlst=bool(is_dlst),
                        ),
                        store_index,
                    )
                    book_data = {
                        "name": display_name,
                        "circle": suggested_circle,
                        "title": suggested_title,
                        "cover_path": "",
                        "mtime": mtime,
                        "is_dlst": bool(is_dlst),
                        "pages": None,
                        "content_hash": fs_entry.content_hash,
                    }

                if result.status == "duplicate":
                    duplicate_out.append(result)
                elif result.status == "error":
                    error_out.append(result)
                elif result.status in {"created", "updated"}:
                    db.apply_action_result(result, book_data)
                elif result.status == "rename":
                    rename_out.append(result)
                elif result.status == "unchanged":
                    pass

                if result.status in {"created", "updated", "rename"}:
                    index_rows = db.fetch_all_rows_for_index()
                    store_index = store_resolver.build_db_index(index_rows, library_root=folder)

        flat_remaining: list[dict] = []
        for _key, rows in remaining_missing.items():
            flat_remaining.extend(rows)
        self._apply_missing_ttl_for_rows(flat_remaining, delete_paths_root)

    def _scan(self) -> tuple[list[dict], list[ActionResult]]:
        folder = self.library_folder
        if not os.path.isdir(folder):
            raise RuntimeError(f"ライブラリフォルダが見つかりません（外付けHDD切断等）: {folder}")
        t_start = time.perf_counter()
        _cleanup_tmp_id_files(folder)
        t1 = time.perf_counter()
        logging.info("[SCAN] phase=cleanup_tmp %.3fs", t1 - t_start)

        duplicate_results: list[ActionResult] = []
        rename_results: list[ActionResult] = []
        error_results: list[ActionResult] = []
        uuid_first_rel: dict[str, str] = {}
        upsert_queue: list[tuple] = []

        try:
            entries = [e for e in os.listdir(folder)]
        except PermissionError as e:
            raise RuntimeError(f"フォルダを開けません: {e}")

        fs_files, hash_failed_paths, phase1_errors = self._collect_fs_files(folder)
        error_results.extend(phase1_errors)

        try:
            db_rows = db.fetch_all_rows_for_index()
        except Exception as e:
            raise RuntimeError(f"DB行の取得に失敗しました: {e}")

        missing_map, created_candidates, existing_pairs, updated_pairs = self._classify(
            fs_files, db_rows, folder, hash_failed_paths
        )
        renames, true_created, missing_remainder = self._resolve_renames(
            created_candidates, missing_map
        )
        delete_paths_root: list[str] = []
        self._apply_changes(
            renames,
            true_created,
            existing_pairs,
            updated_pairs,
            missing_remainder,
            duplicate_out=duplicate_results,
            rename_out=rename_results,
            error_out=error_results,
            delete_paths_root=delete_paths_root,
        )

        total = len(entries)
        t3 = time.perf_counter()
        logging.info("[SCAN] phase=listdir_root entries=%d %.3fs", total, t3 - t1)

        def _emit_progress(current: int) -> None:
            if (
                current % config.SCAN_PROGRESS_EMIT_INTERVAL == 0
                or current == total
            ):
                self.signals.progress.emit(current, total)

        found_paths: set[str] = set()
        fs_by_path_keys = {os.path.normpath(str(f["path"])) for f in fs_files}

        index_rows = db.fetch_all_rows_for_index()
        store_index = store_resolver.build_db_index(index_rows, library_root=folder)

        cover_hash_by_path: dict[str, str | None] = {}
        try:
            ch_conn = db.get_conn()
            try:
                for row in ch_conn.execute("SELECT path, cover_hash FROM books").fetchall():
                    p = os.path.normpath((row["path"] or "").strip())
                    if p:
                        cover_hash_by_path[p] = row["cover_hash"]
            finally:
                ch_conn.close()
        except Exception:
            pass

        for i, name in enumerate(entries):
            path = os.path.join(folder, name)
            if not os.path.isdir(path):
                if name.lower().endswith(STORE_FILE_EXTS) or name.lower().endswith(".pdf"):
                    try:
                        rel_store = os.path.normpath(db.to_db_path_from_any(path))
                    except ValueError as e:
                        _logger.warning(
                            "スキャン: ストアファイルのパス変換失敗、スキップ: path=%s err=%s",
                            path,
                            e,
                        )
                        _emit_progress(i + 1)
                        continue
                    if os.path.normpath(rel_store) in fs_by_path_keys:
                        rel_store_key = os.path.normcase(os.path.normpath(rel_store))
                        found_paths.add(rel_store_key)
                _emit_progress(i + 1)
                continue
            try:
                rel_path = os.path.normpath(db.to_db_path_from_any(path))
            except ValueError as e:
                _logger.warning(
                    "スキャン: フォルダのパス変換失敗、スキップ: path=%s err=%s",
                    path,
                    e,
                )
                _emit_progress(i + 1)
                continue
            rel_path_key = os.path.normcase(rel_path)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                found_paths.add(rel_path_key)
                _emit_progress(i + 1)
                continue

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

            meta_folder = store_index.meta_by_path.get(rel_path)
            if meta_folder and meta_folder[0] == mtime:
                _emit_progress(i + 1)
                continue

            cover_abs = os.path.join(path, images[0])
            try:
                cover_rel = db.to_db_path_from_any(cover_abs)
            except ValueError:
                cover_rel = ""

            circle, title = db.parse_display_name(name)
            if not title:
                title = name.strip()
            display_name = db.format_book_name(circle, title)

            if not meta_folder or meta_folder[0] != mtime:
                existing_ch = cover_hash_by_path.get(rel_path)
                if existing_ch and str(existing_ch).strip():
                    cover_hash_value = None
                else:
                    cover_hash_value = _compute_cover_hash_for_folder(path, images)
                    if cover_hash_value:
                        cover_hash_by_path[rel_path] = cover_hash_value
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
                        cover_hash_value,
                    )
                )

            _emit_progress(i + 1)

        t_after_walk = time.perf_counter()
        logging.info("[SCAN] phase=walk_loop %.3fs", t_after_walk - t3)
        if rename_results or error_results:
            self.signals.storeActionSummary.emit(rename_results, error_results)
        scan_root_norm = os.path.normcase(os.path.normpath(folder))
        # ウォークの upsert（移動後の path 含む）と Phase4 削除を先に反映してから index を取る。
        # fetch を先にやると古い path の行で判定し、移動直後に else 側の即削除に落ちる。
        logging.info(
            "[SCAN] bulk_db_upsert_phase4 delete_paths_root (%d): %s",
            len(delete_paths_root),
            _preview_path_list(list(delete_paths_root), config.SCAN_LOG_PATH_LIST_MAX),
        )
        db.bulk_upsert_and_delete_books(upsert_queue, delete_paths_root)
        t_bulk1 = time.perf_counter()
        logging.info(
            "[SCAN] phase=bulk_db_upsert_phase4 upsert=%d delete_phase4=%d %.3fs",
            len(upsert_queue),
            len(delete_paths_root),
            t_bulk1 - t_after_walk,
        )

        try:
            index_rows = db.fetch_all_rows_for_index()
        except Exception as e:
            raise RuntimeError(f"DB行の取得に失敗しました: {e}")
        t4 = time.perf_counter()
        logging.info("[SCAN] phase=fetch_index_rows %.3fs", t4 - t_bulk1)

        # フォルダ作品が found_paths に戻った場合は missing_since_date をリセット（ルートストア/PDFと同様）
        folder_rediscovered: list[str] = []
        for r in index_rows:
            path = (r.get("path") or "").strip()
            if not path:
                continue
            abs_row = _library_abs_path(folder, path)
            p_norm = os.path.normcase(os.path.normpath(abs_row))
            if p_norm != scan_root_norm and not p_norm.startswith(scan_root_norm + os.sep):
                continue
            if not os.path.isdir(abs_row):
                continue
            norm_key = os.path.normcase(os.path.normpath(path))
            if norm_key in found_paths:
                folder_rediscovered.append(path)
        if folder_rediscovered:
            db.clear_missing_since_for_paths(sorted(set(folder_rediscovered)))

        # Phase4 削除は既に bulk 済み。ここからはフォルダ欠落TTL・ファイル欠落のみ。
        delete_paths: list[str] = []
        under_scan_root_count = 0
        folder_missing_candidates: list[dict] = []
        cnt_isdir_in_found = 0
        cnt_isdir_missing = 0
        cnt_file_root_skip = 0
        cnt_file_immediate = 0
        immediate_file_paths: list[str] = []
        for r in index_rows:
            path = (r.get("path") or "").strip()
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
                    folder_missing_candidates.append(r)
                    cnt_isdir_missing += 1
                else:
                    cnt_isdir_in_found += 1
            else:
                # ルート直下のストア/PDFは missing_since_date による遅延削除で扱う。
                if _is_root_level_store_or_pdf(path):
                    cnt_file_root_skip += 1
                    continue
                if not os.path.exists(abs_row):
                    delete_paths.append(path)
                    immediate_file_paths.append(path)
                    cnt_file_immediate += 1

        fm_paths = [(x.get("path") or "").strip() for x in folder_missing_candidates]
        logging.info(
            "[SCAN] delete_loop branch_counts under_scan_root=%d isdir_in_found=%d "
            "isdir_missing_ttl=%d file_root_store_skip=%d file_immediate=%d",
            under_scan_root_count,
            cnt_isdir_in_found,
            cnt_isdir_missing,
            cnt_file_root_skip,
            cnt_file_immediate,
        )
        logging.info(
            "[SCAN] folder_missing_candidates (%d): %s",
            len(fm_paths),
            _preview_path_list(fm_paths, config.SCAN_LOG_PATH_LIST_MAX),
        )
        logging.info(
            "[SCAN] immediate_file_delete_paths (%d): %s",
            len(immediate_file_paths),
            _preview_path_list(immediate_file_paths, config.SCAN_LOG_PATH_LIST_MAX),
        )

        self._apply_missing_ttl_for_rows(folder_missing_candidates, delete_paths)

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

        logging.info(
            "[SCAN] bulk_db_delete_folder_file delete_paths (%d, TTL含む): %s",
            len(delete_paths),
            _preview_path_list(delete_paths, config.SCAN_LOG_PATH_LIST_MAX),
        )
        db.bulk_upsert_and_delete_books([], delete_paths)
        t6 = time.perf_counter()
        logging.info(
            "[SCAN] phase=bulk_db_delete_folder_file done delete=%d %.3fs",
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
        books = [
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
        return books, duplicate_results


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
        on_store_action_summary=None,
        on_uuid_duplicate_toast=None,
    ) -> None:
        worker = BookScannerWorker(folder)

        def _on_finished_and_release(books: list, duplicate_candidates: list) -> None:
            if worker in self._active_workers:
                self._active_workers.remove(worker)
            on_finished(books, duplicate_candidates)

        def _on_error_and_release(msg: str) -> None:
            if worker in self._active_workers:
                self._active_workers.remove(worker)
            if on_error:
                on_error(msg)

        worker.signals.finished.connect(_on_finished_and_release)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        worker.signals.error.connect(_on_error_and_release)
        if on_store_action_summary:
            worker.signals.storeActionSummary.connect(on_store_action_summary)
        if on_uuid_duplicate_toast:
            worker.signals.uuidDuplicateToast.connect(on_uuid_duplicate_toast)
        self._active_workers.append(worker)
        QThreadPool.globalInstance().start(worker)
