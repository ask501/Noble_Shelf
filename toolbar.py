"""
toolbar.py - メインウィンドウのメニューバー直下ツールバー（各種アイコンボタン）
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QSizePolicy, QSpacerItem
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
    bookmarkletToggled = Signal(bool)  # True=ブックマークレットキュー表示（紫）, False=非表示
    ghostBarToggled = Signal(bool)  # True=ゴーストバー（ソートバー）表示（紫）, False=非表示

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

        # title.png: ゴーストバー（ソートバー）表示トグル / bookmarklet.png: ブックマークレットキュー
        self._btn_ghostbar = QPushButton()
        self._btn_ghostbar.setFixedSize(
            config.MAIN_TOOLBAR_BTN_SIZE, config.MAIN_TOOLBAR_BTN_SIZE
        )
        self._btn_ghostbar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_ghostbar.setToolTip("ゴーストバー（ソートバー）を表示/非表示")
        _title_path = paths.ICON_TOOLBAR_TITLE
        if os.path.isfile(_title_path):
            self._btn_ghostbar.setIcon(QIcon(_title_path))
            self._btn_ghostbar.setIconSize(
                QSize(config.MAIN_TOOLBAR_ICON_SIZE, config.MAIN_TOOLBAR_ICON_SIZE)
            )
        self._btn_ghostbar.setCheckable(True)
        self._btn_ghostbar.setChecked(True)
        self._btn_ghostbar.setStyleSheet(_toolbar_accent_toggle_button_qss())
        self._btn_ghostbar.toggled.connect(self.ghostBarToggled.emit)

        self._btn_bookmarklet_help = QPushButton()
        self._btn_bookmarklet_help.setFixedSize(
            config.MAIN_TOOLBAR_BTN_SIZE, config.MAIN_TOOLBAR_BTN_SIZE
        )
        self._btn_bookmarklet_help.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_bookmarklet_help.setToolTip("ブックマークレットキューを表示/非表示")
        _bmh_path = paths.ICON_TOOLBAR_BOOKMARKLET
        if os.path.isfile(_bmh_path):
            self._btn_bookmarklet_help.setIcon(QIcon(_bmh_path))
            self._btn_bookmarklet_help.setIconSize(
                QSize(config.MAIN_TOOLBAR_ICON_SIZE, config.MAIN_TOOLBAR_ICON_SIZE)
            )
        self._btn_bookmarklet_help.setCheckable(True)
        self._btn_bookmarklet_help.setChecked(False)
        self._btn_bookmarklet_help.setStyleSheet(_toolbar_accent_toggle_button_qss())
        self._btn_bookmarklet_help.toggled.connect(self.bookmarkletToggled.emit)

        # 設定（歯車）: アイコンのみ。処理は未接続
        self._btn_settings = QPushButton()
        self._btn_settings.setFixedSize(
            config.MAIN_TOOLBAR_BTN_SIZE, config.MAIN_TOOLBAR_BTN_SIZE
        )
        self._btn_settings.setCursor(Qt.CursorShape.ArrowCursor)
        self._btn_settings.setToolTip(config.MAIN_TOOLBAR_SETTINGS_TOOLTIP)
        _settings_path = paths.ICON_TOOLBAR_SETTINGS
        if os.path.isfile(_settings_path):
            self._btn_settings.setIcon(QIcon(_settings_path))
            self._btn_settings.setIconSize(
                QSize(config.MAIN_TOOLBAR_ICON_SIZE, config.MAIN_TOOLBAR_ICON_SIZE)
            )
        self._btn_settings.setStyleSheet(_toolbar_icon_button_qss())

        # ハンバーガー（右端用・旧左端の三本線ボタンは廃止）
        self._btn_hamburger_menu = QPushButton()
        self._btn_hamburger_menu.setFixedSize(
            config.MAIN_TOOLBAR_BTN_SIZE, config.MAIN_TOOLBAR_BTN_SIZE
        )
        self._btn_hamburger_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        _hamburger_menu_path = paths.ICON_HAMBURGER
        if os.path.isfile(_hamburger_menu_path):
            self._btn_hamburger_menu.setIcon(QIcon(_hamburger_menu_path))
            self._btn_hamburger_menu.setIconSize(
                QSize(config.MAIN_TOOLBAR_ICON_SIZE, config.MAIN_TOOLBAR_ICON_SIZE)
            )
        self._btn_hamburger_menu.setStyleSheet(_toolbar_icon_button_qss())
        self._btn_hamburger_menu.clicked.connect(self._on_hamburger_menu_clicked)

        # 固定幅＝アイコン相当（config.MAIN_TOOLBAR_ICON_SIZE）、拡張は QSpacerItem のみ（背景の浮き防止）
        _fixed_icon_w = config.MAIN_TOOLBAR_ICON_SIZE
        _spacer_fixed_leading = QSpacerItem(
            _fixed_icon_w,
            0,
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Minimum,
        )
        _spacer_fixed_middle = QSpacerItem(
            _fixed_icon_w,
            0,
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Minimum,
        )
        _spacer_expanding_before_hamburger = QSpacerItem(
            0,
            0,
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        # [固定][サイド][タイトル][検索][フィルター][固定][ランダム][キュー] [拡張] [ハンバーガー][設定]
        tb_layout.addItem(_spacer_fixed_leading)
        tb_layout.addWidget(self._btn_sidebar)
        tb_layout.addWidget(self._btn_ghostbar)
        tb_layout.addWidget(self._btn_search)
        tb_layout.addWidget(self._btn_filter)
        tb_layout.addItem(_spacer_fixed_middle)
        tb_layout.addWidget(self._btn_random)
        tb_layout.addWidget(self._btn_bookmarklet_help)
        tb_layout.addItem(_spacer_expanding_before_hamburger)
        tb_layout.addWidget(self._btn_hamburger_menu)
        tb_layout.addWidget(self._btn_settings)

    def _on_hamburger_menu_clicked(self) -> None:
        """ハンバーガーメニュー（未実装）"""
        pass

    def _on_random_button_clicked(self) -> None:
        self.randomRequested.emit()
        self._btn_random.setStyleSheet(_toolbar_random_flash_qss())
        QTimer.singleShot(
            config.MAIN_TOOLBAR_RANDOM_BTN_FLASH_MS,
            self._restore_random_button_style,
        )

    def _restore_random_button_style(self) -> None:
        self._btn_random.setStyleSheet(_toolbar_icon_button_qss())

    def set_ghostbar_toggle_checked(self, checked: bool) -> None:
        """ゴーストバートグルの見た目のみ同期（表示メニュー復元用。シグナルは出さない）。"""
        self._btn_ghostbar.blockSignals(True)
        self._btn_ghostbar.setChecked(checked)
        self._btn_ghostbar.blockSignals(False)

    def set_bookmarklet_toggle_checked(self, checked: bool) -> None:
        """ブックマークレットトグルの見た目のみ同期（ウィンドウの×閉じ・メニュー起動用。シグナルは出さない）。"""
        self._btn_bookmarklet_help.blockSignals(True)
        self._btn_bookmarklet_help.setChecked(checked)
        self._btn_bookmarklet_help.blockSignals(False)

    def apply_visibility(self, visible: bool) -> None:
        """表示メニューから ToolBar の show / hide を切り替える。"""
        if visible:
            self.show()
        else:
            self.hide()
