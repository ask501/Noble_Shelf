"""settings_dialog.py - 設定ダイアログ"""
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QDialogButtonBox,
    QApplication,
    QMessageBox,
    QProgressDialog,
    QTabWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import os

import db
import config
from theme import apply_dark_titlebar
from ui.dialogs.properties._utils import BTN_CANCEL_STYLE, BTN_SAVE_STYLE


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.setModal(True)
        self.setMinimumSize(*config.SETTINGS_DIALOG_MIN_SIZE)
        self.resize(*config.SETTINGS_DIALOG_DEFAULT_SIZE)
        self._setup_ui()
        self._load()

    def closeEvent(self, event):
        ts = getattr(self, "_tab_shortcut", None)
        if ts is not None and getattr(ts, "_active_shortcut_id", None) is not None:
            ts._end_shortcut_capture(cancel=True)
        super().closeEvent(event)

    def reject(self):
        ts = getattr(self, "_tab_shortcut", None)
        if ts is not None and getattr(ts, "_active_shortcut_id", None) is not None:
            ts._end_shortcut_capture(cancel=True)
        super().reject()

    def _setup_ui(self):
        from ui.dialogs.settings.tab_general import TabGeneral
        from ui.dialogs.settings.tab_shortcut import TabShortcut
        from ui.dialogs.settings.tab_card import TabCard
        from ui.dialogs.settings.tab_backup import TabBackup

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*config.SETTINGS_DIALOG_MARGINS)
        layout.setSpacing(config.SETTINGS_DIALOG_SPACING)

        tabs = QTabWidget()
        # ── タブ1: 一般 ──
        self._tab_general = TabGeneral(self)
        self._tab_general.bulk_rename_btn.clicked.connect(self._on_bulk_rename)
        self._tab_general.repair_paths_btn.clicked.connect(self._on_repair_paths)
        tabs.addTab(self._tab_general, "一般")

        self._tab_shortcut = TabShortcut(self)
        self._tab_card = TabCard(self)
        self._tab_backup = TabBackup(self)
        tabs.addTab(self._tab_shortcut, "ショートカット")
        tabs.addTab(self._tab_card, "カード表示")
        tabs.addTab(self._tab_backup, "バックアップ")

        layout.addWidget(tabs)

        # 保存 / キャンセル（プロパティ系ダイアログと同じ BTN_SAVE_STYLE / BTN_CANCEL_STYLE）
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        btn_ok = btn_box.button(QDialogButtonBox.Ok)
        btn_cancel = btn_box.button(QDialogButtonBox.Cancel)
        btn_ok.setText(config.SETTINGS_DIALOG_BTN_SAVE_TEXT)
        btn_cancel.setText(config.SETTINGS_DIALOG_BTN_CANCEL_TEXT)
        btn_ok.setStyleSheet(BTN_SAVE_STYLE)
        btn_cancel.setStyleSheet(BTN_CANCEL_STYLE)
        layout.addWidget(btn_box)
        self._tab_shortcut.set_ok_button(btn_ok)

    def _load(self):
        self._tab_general.load()
        self._tab_shortcut.load()
        self._tab_card.load()
        self._tab_backup.load()

    def _save(self):
        invalid = self._tab_general.save()
        if invalid:
            msg = QMessageBox(self)
            msg.setWindowTitle(config.APP_TITLE)
            msg.setIcon(QMessageBox.Warning)
            msg.setText("次の項目を確認してください。")
            msg.setInformativeText(
                "・外部ビュアー: パスが存在するか、ショートカットのリンク先が有効か確認してください。\n"
                "・DMMビュアー: DMMBooks.exe または DMMbookviewer.exe を指定してください。\n"
                "・DLSiteビュアー: DLSitePlay.exe または DLsiteViewer.exe を指定してください。\n\n"
                "該当: " + " / ".join(invalid)
            )
            msg.setStandardButtons(QMessageBox.Save | QMessageBox.Cancel)
            msg.setDefaultButton(QMessageBox.Cancel)
            msg.button(QMessageBox.Save).setText("このまま保存する")
            msg.button(QMessageBox.Cancel).setText("キャンセル")
            if msg.exec() != QMessageBox.Save:
                return
            self._tab_general.save(force_save=True)

        self._tab_shortcut.save()
        self._tab_card.save()
        self._tab_backup.save()

        self.accept()

    def _on_bulk_rename(self):
        """[サークル名]作品名でフォルダ・ファイルを一括リネームし、一覧を更新する。"""
        library_folder = db.get_setting("library_folder") or ""
        if not library_folder or not os.path.isdir(library_folder):
            QMessageBox.warning(
                self,
                "一括リネーム",
                "先にライブラリフォルダを設定してください。",
            )
            return
        total = len(db.get_all_books())
        if total == 0:
            QMessageBox.information(self, "一括リネーム", "登録されている本がありません。")
            return

        progress = QProgressDialog("リネーム中...", "キャンセル", 0, total, self)
        progress.setWindowTitle(config.APP_TITLE)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        def on_progress(current, total_count, path):
            progress.setMaximum(total_count)
            progress.setValue(current)
            progress.setLabelText(os.path.basename(path) or path)
            QApplication.processEvents()
            if progress.wasCanceled():
                raise InterruptedError("canceled")

        try:
            renamed, err, failed = db.bulk_rename_to_current_format(library_folder, on_progress=on_progress)
        except InterruptedError:
            progress.close()
            return
        progress.close()

        if err:
            QMessageBox.critical(self, "一括リネーム エラー", err)
            return

        # 結果メッセージ
        if failed:
            summary = f"リネーム成功: {renamed} 件\nスキップ（失敗）: {len(failed)} 件"
            detail = "\n\n".join(
                f"[{i + 1}] {os.path.basename(path)}\n  → {new_name}\n  {msg}"
                for i, (path, new_name, msg) in enumerate(failed)
            )
            msgbox = QMessageBox(self)
            msgbox.setWindowTitle(config.APP_TITLE)
            msgbox.setIcon(QMessageBox.Warning)
            msgbox.setText(summary)
            msgbox.setInformativeText("失敗した項目はスキップしました。詳細は「詳細表示」を押して確認してください。")
            msgbox.setDetailedText(detail)
            msgbox.setStandardButtons(QMessageBox.Ok)
            msgbox.exec()
        else:
            QMessageBox.information(
                self,
                "一括リネーム",
                f"{renamed} 件のフォルダ・ファイルを [サークル名]作品名 に合わせてリネームしました。",
            )

        # 親がメインウィンドウなら一覧を再読み込み
        parent = self.parent()
        if parent is not None and hasattr(parent, "_load_library"):
            parent._load_library()

    def _on_repair_paths(self):
        """パスがフォルダ名だけなど誤って登録されているブックを、ライブラリ配下の実在パスに修復する。"""
        library_folder = db.get_setting("library_folder") or ""
        if not library_folder or not os.path.isdir(library_folder):
            QMessageBox.warning(
                self,
                "パス修復",
                "先にライブラリフォルダを設定してください。",
            )
            return
        total = len(db.get_all_books())
        if total == 0:
            QMessageBox.information(self, "パス修復", "登録されている本がありません。")
            return

        progress = QProgressDialog("パスを確認中...", None, 0, total, self)
        progress.setWindowTitle(config.APP_TITLE)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        def on_progress(current, total_count, path):
            progress.setMaximum(total_count)
            progress.setValue(current)
            progress.setLabelText(os.path.basename(path) or path or "(不明)")
            QApplication.processEvents()

        try:
            count, err, repaired = db.repair_wrong_paths(library_folder, on_progress=on_progress)
        finally:
            progress.close()

        if err:
            QMessageBox.critical(self, "パス修復 エラー", err)
            return
        if count == 0:
            QMessageBox.information(self, "パス修復", "修復対象のブックはありませんでした。")
            return
        detail = "\n".join(f"  {old!r} → {new!r}" for old, new in repaired[:20])
        if len(repaired) > 20:
            detail += f"\n  ... 他 {len(repaired) - 20} 件"
        msgbox = QMessageBox(self)
        msgbox.setWindowTitle(config.APP_TITLE)
        msgbox.setIcon(QMessageBox.Information)
        msgbox.setText(f"{count} 件のブックのパスを修復しました。")
        msgbox.setDetailedText(detail)
        msgbox.setStandardButtons(QMessageBox.Ok)
        msgbox.exec()

        parent = self.parent()
        if parent is not None and hasattr(parent, "_refresh_books_from_db"):
            parent._refresh_books_from_db()
        elif parent is not None and hasattr(parent, "_load_library"):
            parent._load_library()

