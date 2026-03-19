"""
drop_handler.py - ドラッグ&ドロップ処理
- フォルダ: 確認ダイアログ（そのまま登録 or キャンセル）
- zip/cbz/7z/cb7/rar/cbr: 解凍してフォルダとして登録
- 解凍中はプログレスダイアログ表示
"""
from __future__ import annotations
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
from theme import apply_dark_titlebar
from properties import StoreFileInputDialog

# 対応アーカイブ拡張子
ARCHIVE_EXTS  = {".zip", ".cbz", ".7z", ".cb7", ".rar", ".cbr"}
# 新フォルダを作って中に格納する形式（PDFのみ。ストアファイルは STORE_FILE_EXTS で入力ダイアログ）
SUBFOLDER_EXTS = {".pdf"}
# DMM/DLSite ストアファイル（ルートにコピーして入力ダイアログで登録）
STORE_FILE_EXTS = {".dmmb", ".dmme", ".dmmr", ".dlst"}
IMAGE_EXTS   = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


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
    except Exception:
        pass
    return (cover_path if os.path.exists(cover_path) else ""), pages


# ══════════════════════════════════════════════════════════
#  フォルダ確認ダイアログ
# ══════════════════════════════════════════════════════════

class FolderDropDialog(QDialog):
    """フォルダドロップ時: そのまま登録 or キャンセルを選択"""

    def __init__(self, folder_name: str, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.setFixedSize(*config.DROP_FOLDER_DIALOG_SIZE)
        self.setWindowModality(Qt.ApplicationModal)
        self.choice = None  # "copy" | None(cancel)

        layout = QVBoxLayout(self)
        layout.setSpacing(config.DROP_DIALOG_SPACING)

        lbl = QLabel(f"「{folder_name}」をどのように追加しますか？")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("そのまま登録")
        btn_cancel = QPushButton("キャンセル")

        btn_copy.setFixedHeight(config.DROP_DIALOG_BTN_HEIGHT)
        btn_cancel.setFixedHeight(config.DROP_DIALOG_BTN_HEIGHT)

        btn_copy.clicked.connect(lambda: self._choose("copy"))
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_copy)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _choose(self, choice: str):
        self.choice = choice
        self.accept()


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
    on_done: 全処理完了後に呼ぶコールバック（グリッド再スキャン用）
    """
    for path in paths:
        path = path.strip().strip("{}")
        if not os.path.exists(path):
            continue

        ext = os.path.splitext(path)[1].lower()

        if os.path.isdir(path):
            _handle_folder(path, library_folder, parent, on_done)

        elif ext in ARCHIVE_EXTS:
            _handle_archive(path, library_folder, parent, on_done)

        elif ext in SUBFOLDER_EXTS:
            _handle_subfolder_file(path, library_folder, parent, on_done)

        elif ext in STORE_FILE_EXTS:
            _handle_store_file(path, library_folder, parent, on_done)

        else:
            _handle_other_file(path, parent)


def _handle_folder(path: str, library_folder: str, parent, on_done):
    folder_name = os.path.basename(path)
    dlg = FolderDropDialog(folder_name, parent)
    if parent:
        dlg.raise_()
        dlg.activateWindow()
    if dlg.exec() != QDialog.Accepted:
        return

    if dlg.choice == "copy":
        dest = os.path.join(library_folder, folder_name)
        if os.path.exists(dest):
            QMessageBox.warning(parent, "重複", f"「{folder_name}」は既に存在します。")
            return
        if db.is_path_registered(dest):
            QMessageBox.warning(parent, "重複", f"「{folder_name}」は既に登録済みです。")
            return
        try:
            shutil.copytree(path, dest)
            _register_folder(dest)
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

def _handle_archive(path: str, library_folder: str, parent, on_done):
    """アーカイブを確認ダイアログ表示後に解凍してフォルダとして登録・グリッド読み込み"""
    fname = os.path.basename(path)
    dest_name = os.path.splitext(fname)[0]
    dest = os.path.join(library_folder, dest_name)
    if os.path.exists(dest) or db.is_path_registered(dest):
        QMessageBox.warning(parent, "重複", f"「{dest_name}」は既に存在または登録済みです。")
        return
    dlg = ArchiveDropDialog(fname, parent)
    if parent:
        dlg.raise_()
        dlg.activateWindow()
    if dlg.exec() != QDialog.Accepted:
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


def _handle_subfolder_file(path: str, library_folder: str, parent, on_done):
    """pdf/dlst/dmme: DLSTなどと同じStoreFileInputDialogで名前・メタを入力し、決定時にフォルダを作ってコピーして登録。"""
    fname = os.path.basename(path)
    ext = os.path.splitext(fname)[1].lower()
    stem = os.path.splitext(fname)[0]
    suggested_circle, suggested_title = db.parse_display_name(stem)
    if not suggested_title:
        suggested_title = stem
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    placeholder_path = os.path.join(library_folder, fname)
    dlg = StoreFileInputDialog(
        placeholder_path, fname, mtime, suggested_circle, suggested_title, parent
    )
    if dlg.exec() != QDialog.Accepted or not dlg.result:
        return
    book_tuple, meta = dlg.result
    name = book_tuple[0]
    circle = book_tuple[1]
    title = book_tuple[2]
    dest_dir = os.path.join(library_folder, name)
    dest_file = os.path.join(dest_dir, name + ext)
    if os.path.exists(dest_dir):
        QMessageBox.warning(parent, "重複", f"「{name}」は既に存在します。")
        return
    try:
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(path, dest_file)
    except Exception as e:
        QMessageBox.critical(parent, "コピーエラー", str(e))
        return
    try:
        mtime = os.path.getmtime(dest_file)
        if ext == ".pdf":
            cover, pages = _get_pdf_cover_and_pages(dest_file)
        else:
            cover, pages = "", (meta.get("pages") if meta else None)
        final_tuple = (name, circle, title, dest_file, cover, mtime, 0)
        db.bulk_upsert_books([final_tuple])
        if meta:
            meta_src = db._effective_meta_source("", (meta.get("dlsite_id") or "").strip())
            db.set_book_meta(
                dest_file,
                author=meta.get("author", ""),
                series=meta.get("series", ""),
                characters=meta.get("characters"),
                tags=meta.get("tags"),
                pages=meta.get("pages") if ext != ".pdf" else None,
                release_date=meta.get("release_date") or None,
                price=meta.get("price"),
                memo=meta.get("memo") or None,
                dlsite_id=meta.get("dlsite_id") or None,
                meta_source=meta_src,
            )
        # PDFのページ数はファイルから取得した値を最後に設定（ダイアログの値で上書きされないようにする）
        if ext == ".pdf" and pages is not None:
            db.set_book_meta(dest_file, pages=pages)
        if on_done:
            on_done()
    except Exception as e:
        if os.path.exists(dest_file):
            try:
                os.remove(dest_file)
            except Exception:
                pass
        QMessageBox.critical(parent, "登録エラー", str(e))


def _handle_store_file(path: str, library_folder: str, parent, on_done):
    """ストアファイルを入力ダイアログで登録。OKで保存するタイミングでライブラリへコピー（キャンセル時は何も追加しない）。"""
    fname = os.path.basename(path)
    dest = os.path.join(library_folder, fname)
    if os.path.exists(dest):
        QMessageBox.warning(parent, "重複", f"「{fname}」は既にライブラリに存在します。")
        return
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    stem = os.path.splitext(fname)[0]
    suggested_circle, suggested_title = db.parse_display_name(stem)
    if not suggested_title:
        suggested_title = stem
    dlg = StoreFileInputDialog(
        dest, fname, mtime, suggested_circle, suggested_title, parent
    )
    if dlg.exec() != QDialog.Accepted or not dlg.result:
        return
    try:
        shutil.copy2(path, dest)
    except Exception as e:
        QMessageBox.critical(parent, "コピーエラー", str(e))
        return
    try:
        book_tuple, meta = dlg.result
        db.bulk_upsert_books([book_tuple])
        if meta:
            meta_src = db._effective_meta_source("", (meta.get("dlsite_id") or "").strip())
            db.set_book_meta(
                dest,
                author=meta.get("author", ""),
                series=meta.get("series", ""),
                characters=meta.get("characters"),
                tags=meta.get("tags"),
                pages=meta.get("pages"),
                release_date=meta.get("release_date") or None,
                price=meta.get("price"),
                memo=meta.get("memo") or None,
                dlsite_id=meta.get("dlsite_id") or None,
                meta_source=meta_src,
            )
            if meta.get("cover_path"):
                db.set_cover_custom(dest, meta["cover_path"])
        if on_done:
            on_done()
    except Exception as e:
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except Exception:
                pass
        QMessageBox.critical(parent, "登録エラー", str(e))


def _register_subfolder_file(file_path: str, folder_path: str):
    """pdf/dlst/dmmeをDBに登録（pathはファイル、coverはキャッシュから）。表示名は[サークル名]作品名。"""
    fname = os.path.basename(file_path)
    raw_name = os.path.splitext(fname)[0]
    circle, title = db.parse_display_name(raw_name)
    if not title:
        title = raw_name.strip()
    name = db.format_book_name(circle, title)
    ext = os.path.splitext(fname)[1].lower()

    # サムネ: PDFはcover_cacheに保存してページ数取得、dlst/dmmeはなし
    cover = ""
    pages = 0
    if ext == ".pdf":
        cover, pages = _get_pdf_cover_and_pages(file_path)

    mtime = os.path.getmtime(file_path)
    db.upsert_book(
        name=name, circle=circle, title=title,
        path=file_path, cover_path=cover, mtime=mtime, pages=pages
    )


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
        shutil.move(src_path, dst_path)
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
            _register_folder(dest_dir)
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
            if on_done:
                on_done()
        except Exception as e:
            QMessageBox.critical(parent, "エラー", str(e))
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    def _on_error(msg: str):
        progress_dlg.close()
        shutil.rmtree(dest_tmp, ignore_errors=True)
        QMessageBox.warning(parent, "解凍できません", msg)

    def _on_cancel():
        if not _finished_called[0]:
            worker.terminate()
            shutil.rmtree(dest_tmp, ignore_errors=True)

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

def _register_folder(path: str):
    """フォルダをDBに登録。表示名は[サークル名]作品名。"""
    raw_name = os.path.basename(path)
    circle, title = db.parse_display_name(raw_name)
    if not title:
        title = raw_name.strip()
    name = db.format_book_name(circle, title)
    imgs   = sorted(
        f for f in os.listdir(path)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    )
    cover  = os.path.join(path, imgs[0]) if imgs else ""
    mtime  = os.path.getmtime(path)
    db.upsert_book(
        name=name, circle=circle, title=title,
        path=path, cover_path=cover, mtime=mtime
    )
