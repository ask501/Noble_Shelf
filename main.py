"""
main.py - エントリーポイント
起動のみ。ロジックはapp.pyに委譲。
"""
import os
import sys
import logging
from PySide6.QtCore import QLoggingCategory
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon
from app import MainWindow
from theme import APP_QSS
import config
import db


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


def main():
    logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s: %(message)s", stream=sys.stderr)
    # libpng の ICC プロファイル警告（GRAY on RGB PNG 等）を抑止
    QLoggingCategory.setFilterRules("qt.gui.imageio.warning=false")
    app = QApplication(sys.argv)
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
    icon = QIcon(config.WINDOW_ICON_PATH) if (config.WINDOW_ICON_PATH and os.path.isfile(config.WINDOW_ICON_PATH)) else QIcon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    _apply_dark_titlebar(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()