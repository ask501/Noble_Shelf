"""
debug_tools.py - 開発・デバッグ用ユーティリティ

本番ビルドではメニューを隠す前提の、開発者向け機能だけをここにまとめる。
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout

from first_run import LibrarySetupOverlay


def show_first_run_overlay(parent=None) -> None:
    """
    「初回起動」用の LibrarySetupOverlay を単体で表示して見た目を確認する。
    MainWindow とは独立した小さめのモーダルダイアログで開く。
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle("初回起動オーバーレイ（デバッグ）")
    dlg.resize(400, 300)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 16, 16, 16)

    overlay = LibrarySetupOverlay()
    layout.addWidget(overlay)

    # オーバーレイ側のボタンクリック時は単にダイアログを閉じるだけ
    overlay.setupClicked.connect(dlg.accept)

    dlg.exec()

