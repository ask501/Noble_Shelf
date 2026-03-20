"""
debug_tools.py - 開発・デバッグ用ユーティリティ

本番ビルドではメニューを隠す前提の、開発者向け機能だけをここにまとめる。
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout

from first_run import LibrarySetupOverlay
from library_folder_dialog import LibraryFolderDialog
import config


def show_first_run_overlay(parent=None) -> None:
    """
    「初回起動」用の LibrarySetupOverlay を単体で表示して見た目を確認する。
    MainWindow とは独立した小さめのモーダルダイアログで開く。
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(config.DEBUG_FIRST_RUN_DIALOG_TITLE)
    dlg.resize(*config.DEBUG_FIRST_RUN_DIALOG_SIZE)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(*config.DEBUG_FIRST_RUN_DIALOG_MARGINS)

    overlay = LibrarySetupOverlay()
    layout.addWidget(overlay)

    def _on_setup_clicked() -> None:
        picker = LibraryFolderDialog(dlg)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        dlg.accept()

    overlay.setupClicked.connect(_on_setup_clicked)

    dlg.exec()

