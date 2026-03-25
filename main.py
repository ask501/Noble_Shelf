"""
main.py - エントリーポイント
起動のみ。ロジックはapp.pyに委譲。
"""
import os
import sys
import logging
import json
import time
from PySide6.QtCore import QLoggingCategory
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon
from app import MainWindow
from theme import APP_QSS, THEME_COLORS
import config
import db
import paths


def _apply_dark_titlebar(window):
    """Windows 10 1809以降でタイトルバーをダークモードにする"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value)
        )
    except Exception:
        pass


def main(on_startup=None):
    logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s: %(message)s", stream=sys.stderr)
    db.init_db()  # get_setting より前にテーブルを作っておく（exe を別フォルダで起動したときも必須）
    lock_path = config.APP_LOCK_FILE_PATH
    if os.path.exists(lock_path):
        try:
            with open(lock_path, encoding="utf-8") as f:
                lock_data = json.load(f)
            pid = int(lock_data.get("pid") or 0)
            started_at = float(lock_data.get("started_at") or 0)
            is_zombie = (time.time() - started_at > config.BACKUP_INTERVAL_SEC)
            if not is_zombie and pid > 0:
                try:
                    os.kill(pid, 0)
                except OSError:
                    is_zombie = True
            if not is_zombie:
                pass
        except Exception:
            pass
    try:
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "started_at": time.time()}, f)
    except Exception:
        pass
    # libpng の ICC プロファイル警告（GRAY on RGB PNG 等）を抑止
    QLoggingCategory.setFilterRules("qt.gui.imageio.warning=false")
    app = QApplication(sys.argv)
    app.setStyleSheet(f"QWidget {{ background-color: {THEME_COLORS['bg_base']}; }}")
    app.setApplicationName(config.APP_TITLE)
    # QSS適用後にフォントファミリー・サイズを上書き（ポイントサイズ未指定だと Qt が -1 で警告する）
    saved_font = db.get_setting("font_family") or config.FONT_FAMILY
    raw_size = db.get_setting("font_size")
    try:
        pt = int(raw_size) if raw_size is not None else config.FONT_SIZE_DEFAULT
    except (TypeError, ValueError):
        pt = config.FONT_SIZE_DEFAULT
    if pt <= 0:
        pt = config.FONT_SIZE_DEFAULT
    app.setStyleSheet(APP_QSS)
    app.setFont(QFont(saved_font, pt))
    # ウィンドウ用アイコン（タイトルバー・タスクバー）
    icon = QIcon(paths.APP_ICON) if (paths.APP_ICON and os.path.isfile(paths.APP_ICON)) else QIcon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.setStyleSheet(f"background-color: {THEME_COLORS['bg_base']};")
    window.show()
    _apply_dark_titlebar(window)
    if on_startup:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(config.MAIN_ON_STARTUP_DELAY_MS, lambda: on_startup(window))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()