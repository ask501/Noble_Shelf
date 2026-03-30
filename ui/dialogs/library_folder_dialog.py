from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import config
import paths
from theme import THEME_COLORS, apply_dark_titlebar


def _svg_abs_path_to_pixmap(abs_svg_path: str, size_px: int) -> QPixmap:
    """SVG を指定ピクセル角の QPixmap に描画する。"""
    renderer = QSvgRenderer(abs_svg_path)
    pm = QPixmap(size_px, size_px)
    pm.fill(Qt.GlobalColor.transparent)
    if not renderer.isValid():
        return pm
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return pm


def _add_warning_icon_text_row(
    parent_layout: QVBoxLayout,
    pixmap: QPixmap,
    text: str,
    qss_color: str,
) -> None:
    """アイコン QLabel + テキスト QLabel の1行を parent_layout に追加する。"""
    row_widget = QWidget()
    row_widget.setStyleSheet(config.LIBRARY_FOLDER_DIALOG_WARNING_ROW_QSS)
    row = QHBoxLayout(row_widget)
    row.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
    row.setSpacing(config.RENAME_DIALOG_SPACING)
    sz = config.LIBRARY_FOLDER_DIALOG_WARNING_ICON_DISPLAY_PX
    icon_lbl = QLabel()
    icon_lbl.setPixmap(pixmap)
    icon_lbl.setFixedSize(sz, sz)
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    text_lbl = QLabel(text)
    text_lbl.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
    text_lbl.setStyleSheet(f"color: {qss_color};")
    text_lbl.setWordWrap(True)
    text_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(text_lbl, 1, Qt.AlignmentFlag.AlignVCenter)
    parent_layout.addWidget(row_widget)


def _default_library_path() -> str:
    """ライブラリの推奨パス（OS 依存の動的値）。"""
    return os.path.join(os.path.expanduser("~"), "Documents", "NobleShelf")


class LibraryFolderDialog(QDialog):
    """テキスト入力と参照でライブラリフォルダを選ぶ／新規作成するダイアログ。"""

    def __init__(self, parent=None, current_path: str = ""):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self._selected_path: str = ""
        self._current_path = current_path
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle(config.LIBRARY_FOLDER_DIALOG_TITLE)
        self.resize(*config.LIBRARY_FOLDER_DIALOG_SIZE)
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {THEME_COLORS["bg_panel"]};
                color: {THEME_COLORS["text_main"]};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(*config.RENAME_DIALOG_MARGINS)
        root.setSpacing(config.RENAME_DIALOG_SPACING)

        row = QHBoxLayout()
        row.setSpacing(config.RENAME_DIALOG_SPACING)
        self._line_edit = QLineEdit(
            self._current_path if self._current_path else _default_library_path()
        )
        self._line_edit.setMinimumHeight(config.DIALOG_BUTTON_HEIGHT)
        self._browse_btn = QPushButton("参照...")
        self._browse_btn.setFixedHeight(config.DIALOG_BUTTON_HEIGHT)
        self._browse_btn.setMinimumWidth(config.DIALOG_FETCH_BTN_WIDTH)
        row.addWidget(self._line_edit, stretch=1)
        row.addWidget(self._browse_btn, stretch=0)
        root.addLayout(row)

        warn_rows = QVBoxLayout()
        warn_rows.setSpacing(config.LIBRARY_FOLDER_DIALOG_WARNING_ROWS_SPACING_PX)
        icon_px = config.LIBRARY_FOLDER_DIALOG_WARNING_ICON_DISPLAY_PX
        red_path = paths.ICON_LIBRARY_FOLDER_RED_DANGER_SVG
        yellow_path = paths.ICON_LIBRARY_FOLDER_YELLOW_HELP_SVG
        _add_warning_icon_text_row(
            warn_rows,
            _svg_abs_path_to_pixmap(red_path, icon_px),
            config.LIBRARY_FOLDER_DIALOG_CHANGE_WARNING_LINE1_TEXT,
            THEME_COLORS["delete"],
        )
        _add_warning_icon_text_row(
            warn_rows,
            _svg_abs_path_to_pixmap(yellow_path, icon_px),
            config.LIBRARY_FOLDER_DIALOG_CHANGE_WARNING_LINE2_TEXT,
            THEME_COLORS["card_star_on"],
        )
        root.addLayout(warn_rows)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._ok_btn = QPushButton("OK")
        self._cancel_btn = QPushButton("キャンセル")
        self._ok_btn.setFixedHeight(config.DIALOG_BUTTON_HEIGHT)
        self._cancel_btn.setFixedHeight(config.DIALOG_BUTTON_HEIGHT)
        btn_row.addWidget(self._ok_btn)
        btn_row.addWidget(self._cancel_btn)
        root.addLayout(btn_row)

        self._browse_btn.clicked.connect(self._on_browse)
        self._ok_btn.clicked.connect(self._on_ok)
        self._cancel_btn.clicked.connect(self.reject)

    @staticmethod
    def _normalize_path(raw: str) -> str:
        t = raw.strip()
        if not t:
            return ""
        return os.path.normpath(os.path.expanduser(t))

    @staticmethod
    def _selected_path_conflicts_with_app_data_dir(normalized_path: str) -> bool:
        """ライブラリ候補がアプリデータディレクトリと同一、またはその配下なら True。"""
        app_data = os.path.normpath(os.path.abspath(config.APP_DATA_DIR))
        selected = os.path.normpath(os.path.abspath(normalized_path))
        if os.path.normcase(selected) == os.path.normcase(app_data):
            return True
        try:
            common = os.path.commonpath([selected, app_data])
        except ValueError:
            return False
        return os.path.normcase(common) == os.path.normcase(app_data)

    def _on_browse(self) -> None:
        # 入力欄 → ダイアログ表示時の保存パス → 既定の順で、存在するフォルダを起点にする
        browse_start = _default_library_path()
        for raw in (self._line_edit.text(), self._current_path):
            normalized = self._normalize_path(raw)
            if normalized and os.path.isdir(normalized):
                browse_start = normalized
                break
            parent_dir = os.path.dirname(normalized) if normalized else ""
            if parent_dir and os.path.isdir(parent_dir):
                browse_start = parent_dir
                break
        chosen = QFileDialog.getExistingDirectory(
            self,
            "ライブラリフォルダを選択",
            browse_start,
        )
        if chosen:
            self._line_edit.setText(chosen)

    def _on_ok(self) -> None:
        path = self._normalize_path(self._line_edit.text())
        if not path:
            return
        if self._selected_path_conflicts_with_app_data_dir(path):
            QMessageBox.warning(
                self,
                config.LIBRARY_FOLDER_DIALOG_TITLE,
                config.LIBRARY_FOLDER_DIALOG_APP_DATA_CONFLICT_MESSAGE,
            )
            return
        if os.path.isdir(path):
            self._selected_path = path
            self.accept()
            return
        if os.path.exists(path):
            QMessageBox.critical(
                self,
                config.LIBRARY_FOLDER_DIALOG_TITLE,
                "選択したパスはフォルダではありません。",
            )
            return
        reply = QMessageBox.question(
            self,
            config.LIBRARY_FOLDER_DIALOG_TITLE,
            "フォルダが存在しません。新規作成しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        os.makedirs(path, exist_ok=True)
        self._selected_path = path
        self.accept()

    @property
    def selected_path(self) -> str:
        """OK 確定後のパス（未確定時は空文字）。"""
        return self._selected_path
