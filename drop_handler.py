"""
drop_handler.py - ドラッグ&ドロップ処理
- フォルダ: 確認なしでライブラリへコピーして登録
- zip/cbz/7z/cb7/rar/cbr: 解凍してフォルダとして登録
- 解凍中はプログレスダイアログ表示
"""
from __future__ import annotations
import logging
import os
import shutil
import tempfile
from typing import Callable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal

import db
import config
from store_file_resolver import (
    ActionResult,
    FileContext,
    build_db_index,
    resolve_store_file_action,
)
from theme import apply_dark_titlebar

_logger = logging.getLogger(__name__)

# 対応アーカイブ拡張子
ARCHIVE_EXTS  = {".zip", ".cbz", ".7z", ".cb7", ".rar", ".cbr"}
# DMM/DLSiteストアファイルとPDF（ライブラリ直下へコピーして即登録）
STORE_FILE_EXTS = {".dmmb", ".dmme", ".dmmr", ".dlst"}
PDF_EXTS = {".pdf"}
IMAGE_EXTS   = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _compute_cover_hash(folder_path: str) -> str | None:
    """フォルダ内の先頭画像（ソート済み）1枚の hash を返す。画像がなければ None。"""
    imgs = sorted(
        f for f in os.listdir(folder_path)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    )
    if not imgs:
        return None
    cover_abs = os.path.join(folder_path, imgs[0])
    return db._compute_store_content_hash(cover_abs)


def _drop_path_requires_completion(path: str) -> bool:
    """handle_drop のバッチ完了カウント用。未対応形式は False（on_done 不要）。"""
    ext = os.path.splitext(path)[1].lower()
    if os.path.isdir(path):
        return True
    if ext in ARCHIVE_EXTS:
        return True
    if ext in STORE_FILE_EXTS or ext in PDF_EXTS:
        return True
    return False


def _get_pdf_cover_and_pages(pdf_path: str) -> tuple[str, int]:
    """PDFのカバー画像をcover_cacheに保存してパスとページ数を返す"""
    import hashlib
    import config
    cover_dir = config.COVER_CACHE_DIR
    os.makedirs(cover_dir, exist_ok=True)
    key = hashlib.md5(pdf_path.encode()).hexdigest()
    cover_path = os.path.join(cover_dir, f"{key}.jpg")
    pages = 0
    try:
        import fitz
        doc = fitz.open(pdf_path)
        pages = len(doc)
        if not os.path.exists(cover_path) and pages > 0:
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(config.PDF_COVER_SCALE, config.PDF_COVER_SCALE))
            pix.save(cover_path)
        doc.close()
    except Exception as e:
        import traceback

        traceback.print_exc()
    return (cover_path if os.path.exists(cover_path) else ""), pages


# ══════════════════════════════════════════════════════════
#  アーカイブ確認ダイアログ
# ══════════════════════════════════════════════════════════

class ArchiveDropDialog(QDialog):
    """Zip/アーカイブドロップ時: 解凍してフォルダとして登録するか確認"""

    def __init__(self, fname: str, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.setFixedSize(*config.DROP_ARCHIVE_DIALOG_SIZE)
        self.setWindowModality(Qt.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setSpacing(config.DROP_DIALOG_SPACING)
        lbl = QLabel(f"「{fname}」を解凍してライブラリに追加しますか？")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("解凍して登録")
        btn_ok.setFixedHeight(config.DROP_DIALOG_BTN_HEIGHT)
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setFixedHeight(config.DROP_DIALOG_BTN_HEIGHT)
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)


# ══════════════════════════════════════════════════════════
#  アーカイブ解凍ワーカースレッド
# ══════════════════════════════════════════════════════════

class ExtractWorker(QThread):
    progress = Signal(int)   # 0-100
    finished = Signal(str)   # 展開先フォルダパス
    error    = Signal(str)

    def __init__(self, src_path: str, dest_tmp: str):
        super().__init__()
        self.src_path = src_path
        self.dest_tmp = dest_tmp
        self.ext = os.path.splitext(src_path)[1].lower()

    def run(self):
        try:
            if self.ext in (".zip", ".cbz"):
                import zipfile
                with zipfile.ZipFile(self.src_path, "r") as zf:
                    members = zf.infolist()
                    total = max(len(members), 1)
                    for idx, member in enumerate(members):
                        zf.extract(member, self.dest_tmp)
                        self.progress.emit(int((idx + 1) / total * 100))

            elif self.ext in (".7z", ".cb7"):
                try:
                    import py7zr
                except ImportError:
                    self.error.emit("7z/cb7 の解凍に必要なライブラリ (py7zr) がインストールされていません。")
                    return

                with py7zr.SevenZipFile(self.src_path, "r") as zf:
                    members = zf.getnames()
                    total = max(len(members), 1)
                    for idx, member in enumerate(members):
                        zf.extract(path=self.dest_tmp, targets=[member])
                        self.progress.emit(int((idx + 1) / total * 100))

            elif self.ext in (".rar", ".cbr"):
                try:
                    import rarfile
                except ImportError:
                    self.error.emit("rar/cbr の解凍に必要なライブラリ (rarfile) がインストールされていません。")
                    return

                with rarfile.RarFile(self.src_path) as rf:
                    members = rf.infolist()
                    total = max(len(members), 1)
                    for idx, member in enumerate(members):
                        rf.extract(member, self.dest_tmp)
                        self.progress.emit(int((idx + 1) / total * 100))
            else:
                self.error.emit("未対応のアーカイブ形式です。")
                return

            self.finished.emit(self.dest_tmp)
        except Exception as e:
            self.error.emit(str(e))


# ══════════════════════════════════════════════════════════
#  メイン処理: ドロップされたパスを処理
# ══════════════════════════════════════════════════════════

def handle_drop(
    paths: list[str],
    library_folder: str,
    parent=None,
    on_done: Callable[[], None] | None = None,
):
    """
    ドロップされたパスリストを処理してDBに登録。
    on_done: 全処理完了後に1回だけ呼ぶコールバック（グリッド再スキャン用）。
    各アイテムの完了通知は内部で集約する（スキャンロックで2本目以降が落ちるのを防ぐ）。
    """
    valid_paths: list[str] = []
    for path in paths:
        path = path.strip().strip("{}")
        if os.path.exists(path):
            valid_paths.append(path)

    if not valid_paths:
        return

    total = sum(1 for p in valid_paths if _drop_path_requires_completion(p))
    remaining = [total]

    def _on_item_done() -> None:
        remaining[0] -= 1
        if remaining[0] == 0 and on_done:
            on_done()

    for path in valid_paths:
        ext = os.path.splitext(path)[1].lower()

        if os.path.isdir(path):
            _handle_folder(path, library_folder, parent, _on_item_done)

        elif ext in ARCHIVE_EXTS:
            _handle_archive(path, library_folder, parent, _on_item_done)

        elif ext in STORE_FILE_EXTS or ext in PDF_EXTS:
            _handle_store_file(path, library_folder, parent, _on_item_done)

        else:
            _handle_other_file(path, parent)


def _handle_folder(path: str, library_folder: str, parent, on_done):
    """フォルダを重複チェック後、確認なしでコピーして登録する。"""
    folder_name = os.path.basename(path)
    dest = os.path.join(library_folder, folder_name)
    if os.path.exists(dest):
        QMessageBox.warning(parent, "重複", f"「{folder_name}」は既に存在します。")
        if on_done:
            on_done()
        return
    if db.is_path_registered(dest):
        QMessageBox.warning(parent, "重複", f"「{folder_name}」は既に登録済みです。")
        if on_done:
            on_done()
        return
    try:
        shutil.copytree(path, dest)
        if _register_folder(dest, parent, dest_to_cleanup=dest) != "ok":
            if on_done:
                on_done()
            return
        nested_archives = [
            f for f in os.listdir(dest)
            if os.path.splitext(f)[1].lower() in ARCHIVE_EXTS
        ]
        if nested_archives:
            QMessageBox.information(
                parent,
                "アーカイブが含まれています",
                "登録したフォルダ内にアーカイブファイルが含まれています。\n必要に応じて手動で展開してください。",
            )
        if on_done:
            on_done()
    except Exception as e:
        QMessageBox.critical(parent, "エラー", str(e))
        if on_done:
            on_done()

def _handle_archive(path: str, library_folder: str, parent, on_done):
    """アーカイブを確認ダイアログ表示後に解凍してフォルダとして登録・グリッド読み込み"""
    fname = os.path.basename(path)
    dest_name = os.path.splitext(fname)[0]
    dest = os.path.join(library_folder, dest_name)
    if os.path.exists(dest) or db.is_path_registered(dest):
        QMessageBox.warning(parent, "重複", f"「{dest_name}」は既に存在または登録済みです。")
        if on_done:
            on_done()
        return
    dlg = ArchiveDropDialog(fname, parent)
    if parent:
        dlg.raise_()
        dlg.activateWindow()
    if dlg.exec() != QDialog.Accepted:
        if on_done:
            on_done()
        return
    _run_extract_with_progress(path, dest, parent, on_done)


def _handle_other_file(path: str, parent):
    """未対応形式のファイルドロップ時: 確認ダイアログで通知"""
    fname = os.path.basename(path)
    QMessageBox.information(
        parent,
        "未対応の形式",
        f"「{fname}」は登録対象の形式ではありません。\n\n"
        "登録可能: フォルダ / Zip・CBZ・7z・CB7・RAR・CBR / PDF / ストアファイル（.dlst 等）",
    )


def _handle_store_file(path: str, library_folder: str, parent, on_done):
    """ストアファイル/PDFをコピー後、resolver判定に応じて即時対話で登録する。"""
    fname = os.path.basename(path)
    dest = os.path.join(library_folder, fname)
    if os.path.exists(dest):
        QMessageBox.warning(parent, "重複", f"「{fname}」は既にライブラリに存在します。")
        if on_done:
            on_done()
        return
    if db.is_path_registered(dest):
        QMessageBox.warning(parent, "重複", f"「{fname}」は既に登録済みです。")
        if on_done:
            on_done()
        return
    try:
        shutil.copy2(path, dest)
    except Exception as e:
        QMessageBox.critical(parent, "コピーエラー", str(e))
        if on_done:
            on_done()
        return
    try:
        try:
            mtime = os.path.getmtime(dest)
        except OSError:
            mtime = 0
        stem = os.path.splitext(fname)[0]
        circle, title = db.parse_display_name(stem)
        if not title:
            title = stem
        name = db.format_book_name(circle, title)
        ext = os.path.splitext(dest)[1].lower()
        is_dlst = 1 if ext == config.STORE_FILE_EXT_DLSITE else 0
        cover = ""
        try:
            db_path = db.to_db_path_from_any(dest)
        except ValueError as exc:
            _logger.warning("ストアファイル登録: DB 用パスに変換できず登録を中止: %s", exc)
            try:
                if os.path.exists(dest):
                    os.remove(dest)
            except OSError as rm_exc:
                _logger.warning("コピー先ファイルの削除に失敗: %s (%s)", dest, rm_exc)
            return
        index = build_db_index(
            db.fetch_all_rows_for_index(),
            (db.get_setting("library_folder") or "").strip(),
        )
        hash_calc = getattr(db, "_compute_store_" + "content" + "_hash")
        file_hash = hash_calc(dest)
        base_ctx = FileContext(
            dest,
            db_path,
            file_hash,
            mtime,
            os.path.splitext(db_path)[1].lower(),
            bool(is_dlst),
        )
        pages = None
        if ext in PDF_EXTS:
            cover, pages = _get_pdf_cover_and_pages(dest)

        payload = {
            "name": name,
            "circle": circle,
            "title": title,
            "cover_path": cover,
            "mtime": mtime,
            "is_dlst": bool(is_dlst),
            "pages": pages,
        }
        hash_key = "content" + "_hash"
        payload[hash_key] = file_hash

        result = resolve_store_file_action(base_ctx, index)
        if result.status == "unchanged":
            return
        if result.status == "error":
            QMessageBox.warning(
                parent,
                "登録エラー",
                f"判定エラー: {(result.error_type or 'ERROR')}\n{result.error_message or ''}",
            )
            return
        if result.status == "updated":
            db.apply_action_result(result, payload)
            return
        if result.status == "rename":
            old_path = result.existing_path or "既存登録"
            if QMessageBox.question(
                parent,
                "リネーム検出",
                f"既存: {old_path}\n新規: {db_path}\n\nリネームとして登録を更新しますか？",
                QMessageBox.Yes | QMessageBox.No,
            ) == QMessageBox.Yes:
                db.apply_action_result(result, payload)
                return
            if os.path.exists(dest):
                try:
                    os.remove(dest)
                except Exception as e:
                    logging.warning("[drop] ロールバック削除失敗: %s", e)
            return
        if result.status == "duplicate":
            if os.path.exists(dest):
                try:
                    os.remove(dest)
                except Exception as e:
                    logging.warning("[drop] 重複時の一時ファイル削除失敗: %s", e)
            dup_path = result.existing_path or "既存登録"
            QMessageBox.information(
                parent,
                "重複候補",
                f"同一内容のファイルが既に存在します。\n既存: {dup_path}\n新規: {fname}",
            )
            return
        if result.status == "created":
            db.apply_action_result(result, payload)
            if parent and hasattr(parent, "_status_label"):
                try:
                    parent._status_label.setText(f"登録しました: {name}")
                except Exception:
                    pass
            return
    except Exception as e:
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except Exception as rm_err:
                logging.warning("[drop] 登録エラー後のロールバック削除失敗: %s", rm_err)
        QMessageBox.critical(parent, "登録エラー", str(e))
    finally:
        if on_done:
            on_done()


def _flatten_single_subdir(extract_dir: str):
    """展開先直下が単一サブフォルダのみなら中身を1段繰り上げる。"""
    entries = os.listdir(extract_dir)
    if len(entries) != 1:
        return
    only_name = entries[0]
    only_path = os.path.join(extract_dir, only_name)
    if not os.path.isdir(only_path):
        return
    for child_name in os.listdir(only_path):
        src_path = os.path.join(only_path, child_name)
        dst_path = os.path.join(extract_dir, child_name)
        try:
            shutil.move(src_path, dst_path)
        except Exception as e:
            logging.warning("[drop] 展開先1段繰り上げの移動失敗: %s", e)
            raise
    os.rmdir(only_path)


def _run_extract_with_progress(src_path: str, dest_dir: str, parent, on_done):
    """バックグラウンドで解凍し、完了後にフォルダとして登録する。"""
    dest_tmp = tempfile.mkdtemp()
    _finished_called = [False]
    progress_dlg = QProgressDialog(
        "解凍中...",
        "キャンセル",
        config.DROP_ZIP_PROGRESS_RANGE[0],
        config.DROP_ZIP_PROGRESS_RANGE[1],
        parent,
    )
    progress_dlg.setWindowTitle(config.APP_TITLE)
    progress_dlg.setWindowModality(Qt.WindowModal)
    progress_dlg.setMinimumDuration(config.DROP_ZIP_PROGRESS_MIN_DURATION_MS)
    progress_dlg.setValue(config.DROP_ZIP_PROGRESS_RANGE[0])

    worker = ExtractWorker(src_path, dest_tmp)

    def _on_progress(v):
        progress_dlg.setValue(v)

    def _on_finished(tmp_path: str):
        _finished_called[0] = True
        progress_dlg.close()
        try:
            _flatten_single_subdir(tmp_path)
            shutil.copytree(tmp_path, dest_dir)
            if _register_folder(dest_dir, parent, dest_to_cleanup=dest_dir) == "ok":
                nested_archives = [
                    f for f in os.listdir(dest_dir)
                    if os.path.splitext(f)[1].lower() in ARCHIVE_EXTS
                ]
                if nested_archives:
                    QMessageBox.information(
                        parent,
                        "アーカイブが含まれています",
                        "解凍後のフォルダ内にアーカイブファイルが含まれています。\n必要に応じて手動で展開してください。",
                    )
        except Exception as e:
            QMessageBox.critical(parent, "エラー", str(e))
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)
            if on_done:
                on_done()

    def _on_error(msg: str):
        progress_dlg.close()
        shutil.rmtree(dest_tmp, ignore_errors=True)
        QMessageBox.critical(parent, config.DROP_EXTRACT_ERROR_DIALOG_TITLE, msg)
        if on_done:
            on_done()

    def _on_cancel():
        if not _finished_called[0]:
            worker.terminate()
            shutil.rmtree(dest_tmp, ignore_errors=True)
            if on_done:
                on_done()

    worker.progress.connect(_on_progress)
    worker.finished.connect(_on_finished)
    worker.error.connect(_on_error)
    progress_dlg.canceled.connect(_on_cancel)

    # workerをインスタンス変数に保持（GC対策）
    if parent:
        parent._extract_worker = worker

    worker.start()
    progress_dlg.exec()


# ══════════════════════════════════════════════════════════
#  DB登録ヘルパー
# ══════════════════════════════════════════════════════════

def _register_folder(
    path: str,
    parent=None,
    dest_to_cleanup: str | None = None,
) -> str:
    """フォルダをDBに登録。表示名は[サークル名]作品名。

    Returns:
        "ok"   upsert まで完了
        "stop" 重複ダイアログでキャンセル等（呼び出し側で on_done 等を調整）

    dest_to_cleanup:
        重複ダイアログでキャンセルしたときに削除するコピー先の絶対パス。
        None のときは削除対象を path にフォールバックする（コピー先＝path の呼び出し向け）。
        drop_handler 外から呼ぶ場合は、誤削除を避けるため明示的に渡すか挙動に注意すること。
    """
    # scanners.BookScannerWorker._resolve_folder_uuid と同一ルートで .noble-shelf-id を確定し、
    # 直後のスキャンと UUID を一致させる（循環 import 回避のためここで遅延 import）
    from scanners.book_scanner import BookScannerWorker

    library_folder = (db.get_setting("library_folder") or "").strip()
    folder_name = os.path.basename(path)
    try:
        rel_folder = db.to_db_path_from_any(path)
    except ValueError as e:
        _logger.warning("フォルダ登録: DB パス変換失敗、スキップ: path=%s err=%s", path, e)
        return "stop"

    worker = BookScannerWorker(library_folder)
    book_uuid = worker._resolve_folder_uuid(path, rel_folder, folder_name, {})
    if book_uuid is None:
        _logger.warning("フォルダ登録をスキップ: noble-shelf-id を確定できませんでした: %s", path)
        return "stop"

    circle, title = db.parse_display_name(folder_name)
    if not title:
        title = folder_name.strip()
    name = db.format_book_name(circle, title)
    imgs = sorted(
        f for f in os.listdir(path)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    )
    cover_abs = os.path.join(path, imgs[0]) if imgs else ""
    try:
        cover_rel = db.to_db_path_from_any(cover_abs) if cover_abs else ""
    except ValueError:
        cover_rel = ""

    cover_hash = _compute_cover_hash(path)
    if cover_hash:
        existing = db.get_book_by_cover_hash(cover_hash)
        if existing and existing.get("uuid") != book_uuid:
            from ui.dialogs.duplicate_cover_dialog import DuplicateCoverDialog

            raw_cover = existing.get("cover_path") or ""
            if raw_cover:
                try:
                    existing_cover_abs = (
                        db._from_db_path(raw_cover)
                        if not os.path.isabs(raw_cover)
                        else raw_cover
                    )
                except ValueError:
                    existing_cover_abs = db.resolve_cover_stored_value(raw_cover)
            else:
                existing_cover_abs = ""
            dlg = DuplicateCoverDialog(
                existing=existing,
                new_name=folder_name,
                new_cover_abs=cover_abs,
                existing_cover_abs=existing_cover_abs,
                parent=parent,
            )
            dlg.exec()
            if dlg.result_action != "new":
                cleanup_target = dest_to_cleanup or path
                try:
                    if os.path.isdir(cleanup_target):
                        shutil.rmtree(cleanup_target, ignore_errors=True)
                        _logger.info(
                            "キャンセル: コピー済みフォルダを削除しました: %s",
                            cleanup_target,
                        )
                except Exception as e:
                    _logger.warning("キャンセル時のフォルダ削除に失敗: %s", e)
                return "stop"
            _logger.info(
                "cover_hash 一致: 別作品として登録 new_path=%s",
                rel_folder,
            )

    mtime = os.path.getmtime(path)
    db.upsert_book(
        uuid=book_uuid,
        name=name, circle=circle, title=title,
        path=rel_folder,
        cover_path=cover_rel,
        mtime=mtime,
        cover_hash=cover_hash,
    )
    return "ok"
