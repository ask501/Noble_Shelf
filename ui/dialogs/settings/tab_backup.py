"""tab_backup.py - 設定ダイアログ「バックアップ」タブ"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QCheckBox,
    QScrollArea,
    QFrame,
)
from PySide6.QtGui import QFont

import db
import config


class TabBackup(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner_widget = QWidget()
        layout = QVBoxLayout(inner_widget)
        layout.setSpacing(config.SETTINGS_DIALOG_SPACING)

        row = QHBoxLayout()
        lbl = QLabel("バックアップ保持件数")
        lbl.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        row.addWidget(lbl)
        self._backup_count_spin = QSpinBox()
        self._backup_count_spin.setRange(config.SETTINGS_BACKUP_COUNT_MIN, config.SETTINGS_BACKUP_COUNT_MAX)
        self._backup_count_spin.setFixedWidth(config.SETTINGS_BACKUP_SPIN_WIDTH)
        row.addWidget(self._backup_count_spin)
        row.addStretch()
        layout.addLayout(row)

        update_row = QHBoxLayout()
        self._disable_update_check = QCheckBox("自動アップデートを無効にする")
        self._disable_update_check.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        update_row.addWidget(self._disable_update_check)
        update_row.addStretch()
        layout.addLayout(update_row)

        layout.addStretch()
        scroll.setWidget(inner_widget)
        outer.addWidget(scroll)

    def load(self) -> None:
        try:
            val = int(db.get_setting("backup_max_count") or config.SETTINGS_BACKUP_COUNT_DEFAULT)
        except (TypeError, ValueError):
            val = config.SETTINGS_BACKUP_COUNT_DEFAULT
        self._backup_count_spin.setValue(val)
        self._disable_update_check.setChecked(db.get_setting("disable_auto_update") == "1")

    def save(self) -> None:
        db.set_setting("backup_max_count", str(self._backup_count_spin.value()))
        db.set_setting("disable_auto_update", "1" if self._disable_update_check.isChecked() else "0")
