"""
updater.py - 自動アップデート処理
"""
import os
import sys
import zipfile
import tempfile
import urllib.request
import json
from PySide6.QtWidgets import QProgressDialog, QMessageBox, QApplication
from PySide6.QtCore import Qt
from version import VERSION

GITHUB_API_URL = "https://api.github.com/repos/ask501/Noble_Shelf/releases/latest"


def fetch_latest_version() -> tuple[str, str] | None:
    """
    GitHub API から最新リリースのバージョンとダウンロードURLを取得する。
    戻り値: (latest_version, zip_url) または None（取得失敗時）
    latest_version は "0.1.0" 形式（"v" を除いた文字列）
    """
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"User-Agent": "Noble-Shelf-Updater"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode())
        tag = data.get("tag_name", "")
        latest = tag.lstrip("v")
        assets = data.get("assets", [])
        zip_url = next(
            (a["browser_download_url"] for a in assets if a["name"].endswith(".zip")),
            None
        )
        if not latest or not zip_url:
            return None
        return latest, zip_url
    except Exception:
        return None


def is_newer(latest: str, current: str) -> bool:
    """latest が current より新しければ True を返す。"""
    def to_tuple(v):
        try:
            return tuple(int(x) for x in v.split("."))
        except ValueError:
            return (0,)
    return to_tuple(latest) > to_tuple(current)


def download_zip(url: str, dest_path: str, progress_callback=None) -> bool:
    """
    ZipをダウンロードしてDest_pathに保存する。
    progress_callback(downloaded_bytes, total_bytes) で進捗を通知。
    成功すればTrue、失敗すればFalseを返す。
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Noble-Shelf-Updater"})
        with urllib.request.urlopen(req, timeout=30) as res:
            total = int(res.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 8192
            with open(dest_path, "wb") as f:
                while True:
                    chunk = res.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)
        return True
    except Exception:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


def extract_zip(zip_path: str, extract_dir: str) -> str | None:
    """
    Zipを展開してexe本体のパスを返す。
    Zip内の構造: Noble Shelfvx.x.x/ 以下にexeがある想定。
    成功すれば展開先フォルダパス、失敗すればNoneを返す。
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)
        # 展開されたフォルダを探す（Noble Shelfv* という名前）
        for name in os.listdir(extract_dir):
            full = os.path.join(extract_dir, name)
            if os.path.isdir(full) and (name.startswith("Noble Shelf") or name.startswith("Noble_Shelf")):
                return full
        return None
    except Exception:
        return None


def get_app_dir() -> str:
    """現在のexe（またはスクリプト）があるフォルダを返す。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def apply_update(new_folder: str) -> bool:
    """
    new_folder（展開済みの新バージョンフォルダ）の内容を
    現在のexeフォルダに適用するバッチファイルを生成して起動する。
    バッチが処理を引き継いだ後、呼び出し元はアプリを終了すること。
    成功すればTrue、失敗すればFalseを返す。
    """
    import subprocess
    app_dir = get_app_dir()
    exe_name = os.path.basename(sys.executable) if getattr(sys, "frozen", False) else "Noble Shelf.exe"
    old_exe = os.path.join(app_dir, exe_name)
    bat_path = os.path.join(app_dir, "_updater.bat")

    bat_lines = [
        "@echo off",
        # プロセスが完全に終了するまで待つ
        ":wait",
        f'tasklist | find "{exe_name}" >nul',
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul && goto :wait)",
        # 旧.oldが残ってれば削除
        f'if exist "{old_exe}.old" del /f /q "{old_exe}.old"',
        # リネーム失敗時はリストア
        f'rename "{old_exe}" "{exe_name}.old"',
        "if errorlevel 1 goto :restore",
        # 新フォルダの内容をコピー
        f'xcopy /e /y /i "{new_folder}\\*" "{app_dir}\\"',
        "if errorlevel 1 goto :restore",
        # 起動
        f'start "" "{old_exe}"',
        # 残骸削除
        f'del /f /q "{old_exe}.old"',
        f'del /f /q "{bat_path}"',
        "exit",
        ":restore",
        f'if exist "{old_exe}.old" rename "{old_exe}.old" "{exe_name}"',
        f'del /f /q "{bat_path}"',
        "exit",
    ]

    try:
        with open(bat_path, "w", encoding="cp932") as f:
            f.write("\r\n".join(bat_lines))
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
        return True
    except Exception:
        return False


def cleanup_on_startup() -> None:
    """
    起動時に前回アップデートの残骸をクリーンアップする。
    - Noble Shelf.exe.old が残ってる → 削除
    - Noble Shelf_new.exe が残ってる → 削除
    - Noble Shelf.exe がない + .old がある → リカバリー（.oldを.exeに戻す）
    """
    app_dir = get_app_dir()
    exe_name = "Noble Shelf.exe"
    exe_path = os.path.join(app_dir, exe_name)
    old_path = exe_path + ".old"
    new_path = os.path.join(app_dir, "Noble Shelf_new.exe")

    # リカバリー: exeがなくて.oldがある
    if not os.path.exists(exe_path) and os.path.exists(old_path):
        try:
            os.rename(old_path, exe_path)
        except Exception:
            pass
        return

    # 残骸削除
    for p in [old_path, new_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass


def check_and_prompt_update(parent=None) -> None:
    import db
    if db.get_setting("disable_auto_update") == "1":
        return

    result = fetch_latest_version()
    if result is None:
        return
    latest, zip_url = result
    if not is_newer(latest, VERSION):
        return

    ans = QMessageBox.question(
        parent,
        "アップデートがあります",
        f"新しいバージョン v{latest} が利用可能です。\n今すぐアップデートしますか？",
        QMessageBox.Yes | QMessageBox.No
    )
    if ans != QMessageBox.Yes:
        return

    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, f"Noble_Shelf_v{latest}.zip")

    progress_dlg = QProgressDialog("ダウンロード中...", "キャンセル", 0, 100, parent)
    progress_dlg.setWindowTitle("アップデート")
    progress_dlg.setWindowModality(Qt.WindowModal)
    progress_dlg.setMinimumDuration(0)
    progress_dlg.setValue(0)
    progress_dlg.show()
    QApplication.processEvents()

    cancelled = [False]

    def on_progress(dl, total):
        if progress_dlg.wasCanceled():
            cancelled[0] = True
            raise Exception("cancelled")
        if total > 0:
            progress_dlg.setValue(int(dl / total * 100))
        QApplication.processEvents()

    success = download_zip(zip_url, zip_path, on_progress)
    progress_dlg.close()

    if cancelled[0] or not success:
        if not cancelled[0]:
            QMessageBox.warning(parent, "アップデート失敗", "ダウンロードに失敗しました。後でもう一度お試しください。")
        return

    extracted = extract_zip(zip_path, tmp_dir)
    if not extracted:
        QMessageBox.warning(parent, "アップデート失敗", "ファイルの展開に失敗しました。")
        return

    if not apply_update(extracted):
        QMessageBox.warning(parent, "アップデート失敗", "アップデートの適用に失敗しました。")
        return

    QMessageBox.information(parent, "アップデート", "アップデートを開始します。アプリを再起動します。")
    from PySide6.QtCore import QTimer
    QTimer.singleShot(500, QApplication.quit)




