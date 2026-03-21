"""
toolbar.py - メインウィンドウのメニューバー直下ツールバー（各種アイコンボタン）
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QIcon

import config
import paths
from theme import THEME_COLORS


def _toolbar_icon_button_qss() -> str:
    """左・右アイコンボタン共通の QSS（ホバーはテーマの hover）。"""
    return f"""
            QPushButton {{
                border: none;
                background: transparent;
                padding: 0;
                margin: 0;
            }}
            QPushButton:hover {{
                background: {THEME_COLORS['hover']};
            }}
        """


def _toolbar_accent_toggle_button_qss() -> str:
    """検索・サイドバー等トグル用。未チェックは透明、チェック時は accent（ホバーはテーマ参照）。"""
    return f"""
            QPushButton {{
                border: none;
                background: transparent;
                padding: 0;
                margin: 0;
            }}
            QPushButton:hover:!checked {{
                background: {THEME_COLORS['hover']};
            }}
            QPushButton:checked {{
                background: {THEME_COLORS['accent']};
            }}
            QPushButton:checked:hover {{
                background: {THEME_COLORS['accent_hover']};
            }}
        """


def _toolbar_random_flash_qss() -> str:
    """ランダムボタン押下時の一瞬の accent 表示用。"""
    return f"""
            QPushButton {{
                border: none;
                background: {THEME_COLORS['accent']};
                padding: 0;
                margin: 0;
            }}
            QPushButton:hover {{
                background: {THEME_COLORS['accent_hover']};
            }}
        """


class ToolBar(QWidget):
    """メインツールバーのアイコンボタンを横並びに配置する（検索入力は app.py 側の SearchBar と別ウィジェット）。"""

    searchToggled = Signal(bool)  # True=SearchBar 行を表示, False=非表示
    sidebarToggled = Signal(bool)  # True=サイドバー表示, False=非表示
    filterToggled = Signal(bool)  # True=フィルターパネル表示, False=非表示
    randomRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(config.MAIN_TOOLBAR_HEIGHT)
        self.setStyleSheet(
            f"background: {THEME_COLORS['bg_panel']}; border-bottom: 1px solid {THEME_COLORS['sep']};"
        )
        tb_layout = QHBoxLayout(self)
        tb_layout.setContentsMargins(*config.MAIN_TOOLBAR_MARGINS)
        tb_layout.setSpacing(config.MAIN_TOOLBAR_SPACING)
        # ボタン一辺が行高より小さいとき、行内で縦中央に置く
        tb_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._btn_hamburger = QPushButton()
        self._btn_hamburger.setFixedSize(
            config.MAIN_TOOLBAR_BTN_SIZE, config.MAIN_TOOLBAR_BTN_SIZE
        )
        self._btn_hamburger.setCursor(Qt.CursorShape.PointingHandCursor)
        _hamburger_path = paths.ICON_HAMBURGER
        if os.path.isfile(_hamburger_path):
            self._btn_hamburger.setIcon(QIcon(_hamburger_path))
            self._btn_hamburger.setIconSize(
                QSize(config.MAIN_TOOLBAR_ICON_SIZE, config.MAIN_TOOLBAR_ICON_SIZE)
            )
        self._btn_hamburger.setStyleSheet(_toolbar_icon_button_qss())

        self._btn_grid = QPushButton()
        self._btn_grid.setFixedSize(
            config.MAIN_TOOLBAR_BTN_SIZE, config.MAIN_TOOLBAR_BTN_SIZE
        )
        self._btn_grid.setCursor(Qt.CursorShape.PointingHandCursor)
        _grid_path = paths.ICON_GRID
        if os.path.isfile(_grid_path):
            self._btn_grid.setIcon(QIcon(_grid_path))
            self._btn_grid.setIconSize(
                QSize(config.MAIN_TOOLBAR_ICON_SIZE, config.MAIN_TOOLBAR_ICON_SIZE)
            )
        self._btn_grid.setStyleSheet(_toolbar_icon_button_qss())

        self._btn_filter = QPushButton()
        self._btn_filter.setFixedSize(
            config.MAIN_TOOLBAR_BTN_SIZE, config.MAIN_TOOLBAR_BTN_SIZE
        )
        self._btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        _filter_path = paths.ICON_FILTER
        if os.path.isfile(_filter_path):
            self._btn_filter.setIcon(QIcon(_filter_path))
            self._btn_filter.setIconSize(
                QSize(config.MAIN_TOOLBAR_ICON_SIZE, config.MAIN_TOOLBAR_ICON_SIZE)
            )
        self._btn_filter.setCheckable(True)
        self._btn_filter.setChecked(False)
        self._btn_filter.setStyleSheet(_toolbar_accent_toggle_button_qss())
        self._btn_filter.toggled.connect(self.filterToggled.emit)

        self._btn_sidebar = QPushButton()
        self._btn_sidebar.setFixedSize(
            config.MAIN_TOOLBAR_BTN_SIZE, config.MAIN_TOOLBAR_BTN_SIZE
        )
        self._btn_sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        _sidebar_path = paths.ICON_SIDEBAR
        if os.path.isfile(_sidebar_path):
            self._btn_sidebar.setIcon(QIcon(_sidebar_path))
            self._btn_sidebar.setIconSize(
                QSize(config.MAIN_TOOLBAR_ICON_SIZE, config.MAIN_TOOLBAR_ICON_SIZE)
            )
        self._btn_sidebar.setCheckable(True)
        self._btn_sidebar.setChecked(True)
        self._btn_sidebar.setStyleSheet(_toolbar_accent_toggle_button_qss())
        self._btn_sidebar.toggled.connect(self.sidebarToggled.emit)

        self._btn_random = QPushButton()
        self._btn_random.setFixedSize(
            config.MAIN_TOOLBAR_BTN_SIZE, config.MAIN_TOOLBAR_BTN_SIZE
        )
        self._btn_random.setCursor(Qt.CursorShape.PointingHandCursor)
        _random_path = paths.ICON_RANDOM
        if os.path.isfile(_random_path):
            self._btn_random.setIcon(QIcon(_random_path))
            self._btn_random.setIconSize(
                QSize(config.MAIN_TOOLBAR_ICON_SIZE, config.MAIN_TOOLBAR_ICON_SIZE)
            )
        self._btn_random.setStyleSheet(_toolbar_icon_button_qss())
        self._btn_random.clicked.connect(self._on_random_button_clicked)

        self._btn_search = QPushButton()
        self._btn_search.setFixedSize(
            config.MAIN_TOOLBAR_BTN_SIZE, config.MAIN_TOOLBAR_BTN_SIZE
        )
        self._btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        _search_path = paths.ICON_SEARCH
        if os.path.isfile(_search_path):
            self._btn_search.setIcon(QIcon(_search_path))
            self._btn_search.setIconSize(
                QSize(config.MAIN_TOOLBAR_ICON_SIZE, config.MAIN_TOOLBAR_ICON_SIZE)
            )
        self._btn_search.setCheckable(True)
        self._btn_search.setChecked(True)
        self._btn_search.setStyleSheet(_toolbar_accent_toggle_button_qss())
        self._btn_search.toggled.connect(self.searchToggled.emit)

        tb_layout.addWidget(self._btn_hamburger)
        tb_layout.addWidget(self._btn_grid)
        tb_layout.addWidget(self._btn_filter)
        tb_layout.addWidget(self._btn_sidebar)
        tb_layout.addWidget(self._btn_random)
        tb_layout.addWidget(self._btn_search)
        tb_layout.addStretch()

    def _on_random_button_clicked(self) -> None:
        self.randomRequested.emit()
        self._btn_random.setStyleSheet(_toolbar_random_flash_qss())
        QTimer.singleShot(
            config.MAIN_TOOLBAR_RANDOM_BTN_FLASH_MS,
            self._restore_random_button_style,
        )

    def _restore_random_button_style(self) -> None:
        self._btn_random.setStyleSheet(_toolbar_icon_button_qss())

    def apply_visibility(self, visible: bool) -> None:
        """表示メニューから ToolBar の show / hide を切り替える。"""
        if visible:
            self.show()
        else:
            self.hide()
