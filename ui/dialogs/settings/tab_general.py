"""tab_general.py - 設定ダイアログ「一般」タブ"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QFontComboBox,
    QCheckBox,
    QFileDialog,
    QApplication,
    QScrollArea,
    QFrame,
)
from PySide6.QtGui import QFont, QFontDatabase
import os

import db
import config
from ui.widgets.sidebar import SIDEBAR_MODES
from theme import (
    SETTINGS_STARTUP_SORT_COMBO_QSS,
    SETTINGS_STARTUP_SORT_LABEL_QSS,
)
from context_menu import resolve_shortcut, is_valid_store_viewer_path

VIEWER_FILE_FILTER = "ビュアー (*.exe *.lnk);;実行ファイル (*.exe);;ショートカット (*.lnk);;すべてのファイル (*.*)"


def _find_viewer_dir_on_any_drive(relative_paths: list[str]) -> str:
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = letter + ":\\"
        try:
            if not os.path.exists(drive):
                continue
        except OSError:
            continue
        for rel in relative_paths:
            p = os.path.join(drive, rel)
            if os.path.isdir(p):
                return p
    return ""


class TabGeneral(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        # スクロールエリアで全体を包む
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner_widget = QWidget()
        layout = QVBoxLayout(inner_widget)
        layout.setSpacing(config.SETTINGS_DIALOG_SPACING)

        # 綴じ方向
        direction_row = QHBoxLayout()
        direction_label = QLabel("ビューアー綴じ方向")
        direction_label.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        direction_row.addWidget(direction_label)
        self._direction_combo = QComboBox()
        self._direction_combo.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        self._direction_combo.addItem("右綴じで表示する", config.VIEWER_DIRECTION_DATA_RTL)
        self._direction_combo.addItem("左綴じで表示する", config.VIEWER_DIRECTION_DATA_LTR)
        direction_row.addWidget(self._direction_combo)
        layout.addLayout(direction_row)

        # 外部ビュアー
        lbl = QLabel("外部ビュアー (未設定なら既定のアプリで開く)")
        lbl.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        layout.addWidget(lbl)
        row = QHBoxLayout()
        self._viewer_edit = QLineEdit()
        self._viewer_edit.setMinimumHeight(config.SETTINGS_INPUT_MIN_HEIGHT)
        self._viewer_edit.setPlaceholderText(r"例: C:\Program Files\Honeyview\Honeyview.exe")
        self._viewer_edit.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row.addWidget(self._viewer_edit)
        btn_browse = QPushButton("参照...")
        btn_browse.setFixedWidth(config.SETTINGS_BROWSE_BTN_WIDTH)
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        layout.addLayout(row)

        # DMMビュアー
        lbl_dmm = QLabel("DMMビュアー (dmmb/dmme/dmmr用)")
        lbl_dmm.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        layout.addWidget(lbl_dmm)
        row_dmm = QHBoxLayout()
        self._dmm_viewer_edit = QLineEdit()
        self._dmm_viewer_edit.setMinimumHeight(config.SETTINGS_INPUT_MIN_HEIGHT)
        self._dmm_viewer_edit.setPlaceholderText(r"例: C:\Program Files\DMMブックス\DMMBooks.exe")
        self._dmm_viewer_edit.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_dmm.addWidget(self._dmm_viewer_edit)
        btn_dmm = QPushButton("参照...")
        btn_dmm.setFixedWidth(config.SETTINGS_BROWSE_BTN_WIDTH)
        btn_dmm.clicked.connect(self._browse_dmm)
        row_dmm.addWidget(btn_dmm)
        layout.addLayout(row_dmm)

        # DLSiteビュアー
        lbl_dlsite = QLabel("DLSiteビュアー (dlst用)")
        lbl_dlsite.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        layout.addWidget(lbl_dlsite)
        row_dlsite = QHBoxLayout()
        self._dlsite_viewer_edit = QLineEdit()
        self._dlsite_viewer_edit.setMinimumHeight(config.SETTINGS_INPUT_MIN_HEIGHT)
        self._dlsite_viewer_edit.setPlaceholderText(r"例: C:\Program Files\DLSite\DLSitePlay.exe")
        self._dlsite_viewer_edit.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_dlsite.addWidget(self._dlsite_viewer_edit)
        btn_dlsite = QPushButton("参照...")
        btn_dlsite.setFixedWidth(config.SETTINGS_BROWSE_BTN_WIDTH)
        btn_dlsite.clicked.connect(self._browse_dlsite)
        row_dlsite.addWidget(btn_dlsite)
        layout.addLayout(row_dlsite)

        # フォント
        font_row = QHBoxLayout()
        font_label = QLabel("フォント")
        font_label.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        font_row.addWidget(font_label)
        self._font_combo = QFontComboBox()
        self._font_combo.setWritingSystem(QFontDatabase.WritingSystem.Japanese)
        current_family = db.get_setting("font_family") or config.FONT_FAMILY
        raw_size = db.get_setting("font_size")
        try:
            pt = int(raw_size) if raw_size is not None else config.FONT_SIZE_DEFAULT
        except (TypeError, ValueError):
            pt = config.FONT_SIZE_DEFAULT
        if pt <= 0:
            pt = config.FONT_SIZE_DEFAULT
        self._font_combo.setCurrentFont(QFont(current_family, pt))
        self._font_combo.currentFontChanged.connect(lambda f: self._apply_font(f.family()))
        font_row.addWidget(self._font_combo)
        self._direction_combo.setSizePolicy(self._font_combo.sizePolicy())
        layout.addLayout(font_row)
        layout.addSpacing(config.SETTINGS_DIALOG_SPACING)

        # 一括リネーム・パス修復ボタン（シグナルはSettingsDialogから接続するため、ここではウィジェットのみ作成）
        self.bulk_rename_btn = QPushButton("[サークル名]作品名に一括リネーム")
        self.bulk_rename_btn.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_BTN_DEFAULT))
        layout.addWidget(self.bulk_rename_btn)

        self.repair_paths_btn = QPushButton("誤ったパスを修復")
        self.repair_paths_btn.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_BTN_DEFAULT))
        layout.addWidget(self.repair_paths_btn)

        # 起動時ソート
        self._chk_startup_sort_restore = QCheckBox(config.STARTUP_SORT_RESTORE_CHECKBOX_LABEL)
        self._chk_startup_sort_restore.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        self._chk_startup_sort_restore.stateChanged.connect(self._on_startup_sort_restore_changed)
        layout.addWidget(self._chk_startup_sort_restore)

        startup_sort_row = QHBoxLayout()
        self._lbl_startup_sort = QLabel(config.STARTUP_SORT_COMBO_ROW_LABEL)
        self._lbl_startup_sort.setObjectName("SettingsStartupSortLabel")
        self._lbl_startup_sort.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        self._lbl_startup_sort.setStyleSheet(SETTINGS_STARTUP_SORT_LABEL_QSS)
        startup_sort_row.addWidget(self._lbl_startup_sort)
        self._combo_startup_sort = QComboBox()
        self._combo_startup_sort.setObjectName("SettingsStartupSortCombo")
        self._combo_startup_sort.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        for _sk, _sl in SIDEBAR_MODES:
            self._combo_startup_sort.addItem(_sl, _sk)
        self._combo_startup_sort.setStyleSheet(SETTINGS_STARTUP_SORT_COMBO_QSS)
        startup_sort_row.addWidget(self._combo_startup_sort)
        startup_sort_row.addStretch()
        layout.addLayout(startup_sort_row)

        layout.addStretch()
        scroll.setWidget(inner_widget)
        outer.addWidget(scroll)

    def _on_startup_sort_restore_changed(self, _state: int) -> None:
        on = self._chk_startup_sort_restore.isChecked()
        self._combo_startup_sort.setEnabled(not on)
        self._lbl_startup_sort.setEnabled(not on)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "ビュアーを選択", "", VIEWER_FILE_FILTER)
        if path:
            self._viewer_edit.setText(path)

    def _browse_dmm(self):
        start = _find_viewer_dir_on_any_drive([os.path.join("Program Files", "DMM", "DMMbookviewer")])
        path, _ = QFileDialog.getOpenFileName(self, "DMMビュアーを選択", start, VIEWER_FILE_FILTER)
        if path:
            self._dmm_viewer_edit.setText(path)

    def _browse_dlsite(self):
        start = _find_viewer_dir_on_any_drive([
            os.path.join("Program Files (x86)", "DLsiteViewer"),
            os.path.join("Program Files", "DLsiteViewer"),
        ])
        path, _ = QFileDialog.getOpenFileName(self, "DLSiteビュアーを選択", start, VIEWER_FILE_FILTER)
        if path:
            self._dlsite_viewer_edit.setText(path)

    def _is_valid_viewer_path(self, path: str) -> bool:
        p = (path or "").strip()
        if not p:
            return True
        if not os.path.isfile(p):
            return False
        resolved = resolve_shortcut(p)
        if not resolved:
            return False
        if os.path.splitext(p)[1].lower() == ".lnk":
            return resolved != p and os.path.isfile(resolved)
        return os.path.isfile(resolved)

    def _apply_font(self, family: str):
        db.set_setting("font_family", family)
        raw_size = db.get_setting("font_size")
        try:
            pt = int(raw_size) if raw_size is not None else config.FONT_SIZE_DEFAULT
        except (TypeError, ValueError):
            pt = config.FONT_SIZE_DEFAULT
        if pt <= 0:
            pt = config.FONT_SIZE_DEFAULT
        font = QFont(family, pt)
        app = QApplication.instance()
        if app is not None:
            app.setFont(font)
            for widget in app.allWidgets():
                widget.setFont(font)
                widget.update()

    def load(self):
        direction = db.get_setting(config.VIEWER_DIRECTION_SETTING_KEY) or config.VIEWER_DIRECTION_DEFAULT
        idx = self._direction_combo.findData(direction)
        if idx >= 0:
            self._direction_combo.setCurrentIndex(idx)
        self._viewer_edit.setText(db.get_setting("external_viewer") or "")
        self._dmm_viewer_edit.setText(db.get_setting("dmm_viewer") or "")
        self._dlsite_viewer_edit.setText(db.get_setting("dlsite_viewer") or "")
        rr = db.get_setting(config.STARTUP_SORT_RESTORE_LAST_SETTING_KEY)
        self._chk_startup_sort_restore.setChecked(rr != "0" if rr is not None else True)
        saved_default = (
            db.get_setting(config.STARTUP_SORT_DEFAULT_KEY_SETTING_KEY)
            or config.STARTUP_SORT_DEFAULT_KEY_FALLBACK
        )
        idx = self._combo_startup_sort.findData(saved_default)
        if idx >= 0:
            self._combo_startup_sort.setCurrentIndex(idx)
        self._on_startup_sort_restore_changed(0)

    def save(self, force_save: bool = False) -> list[str]:
        """保存処理。バリデーションエラーがあればエラー名リストを返す。正常時は空リスト。"""
        external = self._viewer_edit.text().strip()
        dmm = self._dmm_viewer_edit.text().strip()
        dlsite = self._dlsite_viewer_edit.text().strip()

        if not force_save:
            invalid = []
            if external and not self._is_valid_viewer_path(external):
                invalid.append("外部ビュアー")
            if dmm and not is_valid_store_viewer_path(dmm, for_dmm=True):
                invalid.append("DMMビュアー（DMMBooks.exe / DMMbookviewer.exe を指定してください）")
            if dlsite and not is_valid_store_viewer_path(dlsite, for_dmm=False):
                invalid.append("DLSiteビュアー（DLSitePlay.exe / DLsiteViewer.exe を指定してください）")
            if invalid:
                return invalid

        db.set_setting("external_viewer", external)
        db.set_setting("dmm_viewer", dmm)
        db.set_setting("dlsite_viewer", dlsite)
        db.set_setting(config.VIEWER_DIRECTION_SETTING_KEY, self._direction_combo.currentData())
        db.set_setting(
            config.STARTUP_SORT_RESTORE_LAST_SETTING_KEY,
            "1" if self._chk_startup_sort_restore.isChecked() else "0",
        )
        _sdk = self._combo_startup_sort.currentData()
        db.set_setting(
            config.STARTUP_SORT_DEFAULT_KEY_SETTING_KEY,
            (_sdk if _sdk is not None else "") or config.STARTUP_SORT_DEFAULT_KEY_FALLBACK,
        )
        return []
