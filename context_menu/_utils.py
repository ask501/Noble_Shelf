from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtWidgets import QMessageBox

import config
import db


def _get_shortcut_for_display(key: str) -> str:
    """設定のショートカット文字列を返す（コンテキストメニュー表示用）。menubar と同様の取得だが import 循環を避けるためここで定義。"""
    val = db.get_setting(f"shortcut_{key}")
    if val is not None:
        return (val or "").strip()
    return (config.DEFAULT_SHORTCUTS.get(key) or "").strip()


# DMM/DLSite ストアファイルは独自ビュアーのみで開く（内置ビュアー・外部ビュアーは使わない）
STORE_FILE_EXTS_DMM = (".dmmb", ".dmme", ".dmmr")
STORE_FILE_EXT_DLSITE = ".dlst"

# ストアファイル起動に許可する実行ファイル名（大文字小文字無視）
ALLOWED_DMM_VIEWER_NAMES = ("DMMBooks.exe", "DMMbookviewer.exe")
ALLOWED_DLSITE_VIEWER_NAMES = ("DLSitePlay.exe", "DLsiteViewer.exe")


def resolve_shortcut(path: str) -> str:
    """
    パスが Windows のショートカット(.lnk) の場合、リンク先の実体パスを返す。
    それ以外はそのまま返す。解決に失敗した場合は元の path を返す。
    """
    if not path or not os.path.isfile(path):
        return path or ""
    if sys.platform != "win32" or os.path.splitext(path)[1].lower() != ".lnk":
        return path
    try:
        # PowerShell で .lnk の TargetPath を取得（追加ライブラリ不要）
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "$p = $env:SHORTCUT_PATH; (New-Object -ComObject WScript.Shell).CreateShortcut($p).TargetPath",
        ]
        env = os.environ.copy()
        env["SHORTCUT_PATH"] = os.path.abspath(path)
        r = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=config.SHORTCUT_RESOLVE_TIMEOUT_SEC,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if r.returncode == 0 and r.stdout:
            resolved = r.stdout.strip().strip('"')
            if resolved and os.path.exists(resolved):
                return resolved
    except Exception:
        pass
    return path


def _is_store_file(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    ext = os.path.splitext(path)[1].lower()
    return ext in STORE_FILE_EXTS_DMM or ext == STORE_FILE_EXT_DLSITE


def _get_store_viewer_path(path: str) -> tuple[str, str]:
    """ストアファイル用ビュアーパスと未設定時のラベルを返す。(path, label) 未設定時は ("", "DMMビュアー") など。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in STORE_FILE_EXTS_DMM:
        return (db.get_setting("dmm_viewer") or "").strip(), "DMMビュアー"
    if ext == STORE_FILE_EXT_DLSITE:
        return (db.get_setting("dlsite_viewer") or "").strip(), "DLSiteビュアー"
    return "", ""


def _is_allowed_store_viewer(resolved_exe_path: str, for_dmm: bool) -> bool:
    """ストア用に許可されたビュアー（DMMbookviewer.exe / DLsiteViewer.exe 等）かどうか。"""
    if not resolved_exe_path or not os.path.isfile(resolved_exe_path):
        return False
    name = os.path.basename(resolved_exe_path)
    allowed = ALLOWED_DMM_VIEWER_NAMES if for_dmm else ALLOWED_DLSITE_VIEWER_NAMES
    return name.lower() in (a.lower() for a in allowed)


def is_valid_store_viewer_path(path: str, for_dmm: bool) -> bool:
    """
    設定用: パスが空、または実在し且つストア用に許可された exe（.lnk の場合はリンク先）なら True。
    設定ダイアログの保存時チェックに使用。
    """
    p = (path or "").strip()
    if not p:
        return True
    if not os.path.isfile(p):
        return False
    resolved = resolve_shortcut(p)
    if not resolved or not os.path.isfile(resolved):
        return False
    if os.path.splitext(p)[1].lower() == ".lnk" and resolved == p:
        return False
    return _is_allowed_store_viewer(resolved, for_dmm)


def _show_viewer_not_set_dialog(parent, label: str):
    """ビュアー未設定時に「設定でパスを指定してください」と設定を開くオプションを表示する。"""
    from PySide6.QtWidgets import QMessageBox

    msg = QMessageBox(parent)
    msg.setWindowTitle(config.APP_TITLE)
    msg.setIcon(QMessageBox.Warning)
    msg.setText(f"{label}が未設定です。")
    msg.setInformativeText("設定でパスを指定してください。")
    btn_settings = msg.addButton("設定を開く", QMessageBox.AcceptRole)
    msg.addButton(QMessageBox.Close)
    msg.exec()
    if msg.clickedButton() == btn_settings:
        from ui.dialogs.settings import SettingsDialog

        dlg = SettingsDialog(parent)
        dlg.exec()


def _show_wrong_viewer_dialog(parent, label: str, allowed_names: tuple[str, ...]):
    """ストア用以外のビュアーが指定されているときに、許可 exe 名を案内して設定を開けるようにする。"""
    from PySide6.QtWidgets import QMessageBox

    msg = QMessageBox(parent)
    msg.setWindowTitle(config.APP_TITLE)
    msg.setIcon(QMessageBox.Warning)
    msg.setText(f"{label}には、以下のいずれかを指定してください。")
    msg.setInformativeText("許可: " + " / ".join(allowed_names))
    btn_settings = msg.addButton("設定を開く", QMessageBox.AcceptRole)
    msg.addButton(QMessageBox.Close)
    msg.exec()
    if msg.clickedButton() == btn_settings:
        from ui.dialogs.settings import SettingsDialog

        dlg = SettingsDialog(parent)
        dlg.exec()


def open_book(path: str, parent_window, modal: bool = True) -> bool:
    """
    作品を開く。ストアファイル(.dmmb/.dmme/.dmmr/.dlst)は専用ビュアーのみで開き、
    未設定の場合は「設定してください」ダイアログを表示する。それ以外は内置ビュアーで開く。
    modal: True のとき Viewer は exec()、False のとき show()。
    戻り値: 開いた or 通常の開くを実行したなら True、ビュアー未設定でダイアログ表示したなら False。
    """
    if not path or not os.path.exists(path):
        return True
    if _is_store_file(path):
        viewer_path, label = _get_store_viewer_path(path)
        if not viewer_path:
            _show_viewer_not_set_dialog(parent_window, label)
            return False
        resolved = resolve_shortcut(viewer_path)
        if not os.path.isfile(resolved):
            _show_viewer_not_set_dialog(parent_window, label)
            return False
        is_dmm = os.path.splitext(path)[1].lower() in STORE_FILE_EXTS_DMM
        if not _is_allowed_store_viewer(resolved, is_dmm):
            allowed = ALLOWED_DMM_VIEWER_NAMES if is_dmm else ALLOWED_DLSITE_VIEWER_NAMES
            _show_wrong_viewer_dialog(parent_window, label, allowed)
            return False
        try:
            subprocess.Popen([resolved, path])
        except Exception as e:
            QMessageBox.warning(parent_window, "エラー", f"ビュアーを開けませんでした:\n{e}")
            return False
        name = db.get_book_name_by_path(path) or os.path.basename(path) or path
        db.add_recent_book(name, path)
        return True
    from ui.dialogs.viewer import Viewer

    v = Viewer(parent_window, path)
    if modal:
        v.exec()
    else:
        v.show()
    name = db.get_book_name_by_path(path) or os.path.basename(path) or path
    db.add_recent_book(name, path)
    return True

