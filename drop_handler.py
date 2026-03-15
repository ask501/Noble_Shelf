"""
drop_handler.py - ドラッグ&ドロップ処理
- フォルダ: 確認ダイアログ（そのまま登録 or Zip化）
- zip/cbz/7z/cb7/rar/cbr: そのまま登録
- 変換中はプログレスダイアログ表示
"""
from __future__ import annotations
import os
import shutil
import zipfile
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


# ══════════════════════════════════════════════════════════
#  アーカイブ内サムネ取得ユーティリティ
# ══════════════════════════════════════════════════════════

def _get_archive_cover(path: str) -> str | None:
    """アーカイブ内の1枚目画像を cover_cache に展開してパスを返す（キャッシュ削除で消えない）"""
    ext = os.path.splitext(path)[1].lower()
    try:
        import config
        import hashlib
        h = hashlib.md5(path.encode()).hexdigest()
        cover_path = os.path.join(config.COVER_CACHE_DIR, f"archive_{h}.jpg")
        if os.path.exists(cover_path):
            return cover_path
        os.makedirs(config.COVER_CACHE_DIR, exist_ok=True)

        if ext in (".zip", ".cbz"):
            with zipfile.ZipFile(path, "r") as zf:
                imgs = sorted(
                    n for n in zf.namelist()
                    if os.path.splitext(n)[1].lower() in IMAGE_EXTS
                    and not os.path.basename(n).startswith(".")
                )
                if imgs:
                    data = zf.read(imgs[0])
                    with open(cover_path, "wb") as f:
                        f.write(data)
                    return cover_path

        elif ext in (".7z", ".cb7"):
            try:
                import py7zr
                with py7zr.SevenZipFile(path, "r") as zf:
                    names = sorted(
                        n for n in zf.getnames()
                        if os.path.splitext(n)[1].lower() in IMAGE_EXTS
                    )
                    if names:
                        zf.extract(targets=[names[0]], path=os.path.dirname(cover_path))
                        extracted = os.path.join(os.path.dirname(cover_path), names[0])
                        if os.path.exists(extracted):
                            shutil.move(extracted, cover_path)
                        return cover_path
            except ImportError:
                pass

        elif ext in (".rar", ".cbr"):
            try:
                import rarfile
                with rarfile.RarFile(path) as rf:
                    imgs = sorted(
                        n for n in rf.namelist()
                        if os.path.splitext(n)[1].lower() in IMAGE_EXTS
                    )
                    if imgs:
                        data = rf.read(imgs[0])
                        with open(cover_path, "wb") as f:
                            f.write(data)
                        return cover_path
            except (ImportError, Exception):
                pass

    except Exception:
        pass
    return None


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
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            pix.save(cover_path)
        doc.close()
    except Exception:
        pass
    return (cover_path if os.path.exists(cover_path) else ""), pages


# ══════════════════════════════════════════════════════════
#  フォルダ確認ダイアログ
# ══════════════════════════════════════════════════════════

class FolderDropDialog(QDialog):
    """フォルダドロップ時: そのまま登録 or Zip化を選択"""

    def __init__(self, folder_name: str, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.setFixedSize(360, 160)
        self.setWindowModality(Qt.ApplicationModal)
        self.choice = None  # "copy" | "zip" | None(cancel)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        lbl = QLabel(f"「{folder_name}」をどのように追加しますか？")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("そのまま登録")
        btn_zip  = QPushButton("Zip化して登録")
        btn_cancel = QPushButton("キャンセル")

        btn_copy.setFixedHeight(32)
        btn_zip.setFixedHeight(32)
        btn_cancel.setFixedHeight(32)

        btn_copy.clicked.connect(lambda: self._choose("copy"))
        btn_zip.clicked.connect(lambda:  self._choose("zip"))
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_copy)
        btn_layout.addWidget(btn_zip)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _choose(self, choice: str):
        self.choice = choice
        self.accept()


class ArchiveDropDialog(QDialog):
    """Zip/アーカイブドロップ時: コピーして登録するか確認"""

    def __init__(self, fname: str, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.setFixedSize(400, 140)
        self.setWindowModality(Qt.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        lbl = QLabel(f"「{fname}」をライブラリに追加しますか？")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("コピーして登録")
        btn_ok.setFixedHeight(32)
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setFixedHeight(32)
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)


# ══════════════════════════════════════════════════════════
#  Zip変換ワーカースレッド
# ══════════════════════════════════════════════════════════

class ZipWorker(QThread):
    progress = Signal(int)   # 0-100
    finished = Signal(str)   # 完成したzipのパス
    error    = Signal(str)

    def __init__(self, src_folder: str, dest_zip: str):
        super().__init__()
        self.src_folder = src_folder
        self.dest_zip   = dest_zip

    def run(self):
        try:
            files = []
            for root, _, fnames in os.walk(self.src_folder):
                for fn in fnames:
                    files.append(os.path.join(root, fn))
            total = max(len(files), 1)
            with zipfile.ZipFile(self.dest_zip, "w", zipfile.ZIP_STORED) as zf:
                for i, fp in enumerate(files):
                    arcname = os.path.relpath(fp, self.src_folder)
                    zf.write(fp, arcname)
                    self.progress.emit(int((i + 1) / total * 100))
            self.finished.emit(self.dest_zip)
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
            if on_done:
                on_done()
        except Exception as e:
            QMessageBox.critical(parent, "エラー", str(e))

    elif dlg.choice == "zip":
        dest_zip = os.path.join(library_folder, folder_name + ".zip")
        if os.path.exists(dest_zip):
            QMessageBox.warning(parent, "重複", f"「{folder_name}.zip」は既に存在します。")
            return
        if db.is_path_registered(dest_zip):
            QMessageBox.warning(parent, "重複", f"「{folder_name}.zip」は既に登録済みです。")
            return
        _run_zip_with_progress(path, dest_zip, parent, on_done)


def _handle_archive(path: str, library_folder: str, parent, on_done):
    """アーカイブファイルを確認ダイアログ表示後にライブラリにコピーしてDB登録・グリッド読み込み"""
    fname = os.path.basename(path)
    dest = os.path.join(library_folder, fname)
    if os.path.exists(dest):
        QMessageBox.warning(parent, "重複", f"「{fname}」は既に存在します。")
        return
    if db.is_path_registered(dest):
        QMessageBox.warning(parent, "重複", f"「{fname}」は既に登録済みです。")
        return
    dlg = ArchiveDropDialog(fname, parent)
    if parent:
        dlg.raise_()
        dlg.activateWindow()
    if dlg.exec() != QDialog.Accepted:
        return
    try:
        shutil.copy2(path, dest)
        _register_archive(dest)
        if on_done:
            on_done()
    except Exception as e:
        QMessageBox.critical(parent, "エラー", str(e))


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


def _run_zip_with_progress(src_folder: str, dest_zip: str, parent, on_done):
    """バックグラウンドでZip化しながらプログレスダイアログ表示"""
    progress_dlg = QProgressDialog("Zip化中...", "キャンセル", 0, 100, parent)
    progress_dlg.setWindowTitle(config.APP_TITLE)
    progress_dlg.setWindowModality(Qt.WindowModal)
    progress_dlg.setMinimumDuration(0)
    progress_dlg.setValue(0)

    worker = ZipWorker(src_folder, dest_zip)

    def _on_progress(v):
        progress_dlg.setValue(v)

    def _on_finished(zip_path):
        progress_dlg.close()
        _register_archive(zip_path)
        if on_done:
            on_done()

    def _on_error(msg):
        progress_dlg.close()
        QMessageBox.critical(parent, "Zip化エラー", msg)

    def _on_cancel():
        worker.terminate()
        if os.path.exists(dest_zip):
            os.remove(dest_zip)

    worker.progress.connect(_on_progress)
    worker.finished.connect(_on_finished)
    worker.error.connect(_on_error)
    progress_dlg.canceled.connect(_on_cancel)

    # workerをインスタンス変数に保持（GC対策）
    if parent:
        parent._zip_worker = worker

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


def _register_archive(path: str):
    """アーカイブをDBに登録（サムネはキャッシュから）。表示名は[サークル名]作品名。"""
    raw_name = os.path.splitext(os.path.basename(path))[0]
    circle, title = db.parse_display_name(raw_name)
    if not title:
        title = raw_name.strip()
    name = db.format_book_name(circle, title)
    cover  = _get_archive_cover(path) or ""
    mtime  = os.path.getmtime(path)
    db.upsert_book(
        name=name, circle=circle, title=title,
        path=path, cover_path=cover, mtime=mtime
    )
