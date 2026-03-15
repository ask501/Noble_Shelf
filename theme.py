"""
theme.py - アプリ全体のテーマ・スタイル定義
旧 ui_common.py の移植。PySide6用QSSに対応。
"""
import config

# ── カラー定数 ────────────────────────────────────────────
COLOR_BG_BASE    = "#1e1e1e"
COLOR_BG_PANEL   = "#252526"
COLOR_BG_WIDGET  = "#262626"
COLOR_ACCENT     = "#9A7FFF"
COLOR_ACCENT_HOVER = "#8B6FFF"
COLOR_BORDER     = "#404040"
COLOR_TEXT_MAIN  = "#CCCCCC"
COLOR_TEXT_SUB   = "#A5A5A5"
# コンテキストメニュー等の無効項目（選択不可）— 黒に近いグレーで視認性確保
COLOR_MENU_DISABLED = "#555555"
# コンテキストメニュー右側のショートカット表示（明るめグレー）
COLOR_CONTEXT_MENU_SHORTCUT = "#9a9a9a"
COLOR_DELETE     = "#ff6b6b"
COLOR_DELETE_HOVER = "#c0392b"
COLOR_HOVER      = "#333333"
COLOR_SEP        = "#2d2d2d"

# ── UI部品カラー ──
COLOR_SCROLLBAR       = "#505050"
COLOR_SCROLLBAR_HOVER = "#707070"
COLOR_WHITE           = "#ffffff"
COLOR_ARROW           = "#AAAAAA"
COLOR_BADGE_BG        = "#666666"

# ── ボタンカラー ──
COLOR_BTN_SAVE          = "#2d6a2d"
COLOR_BTN_SAVE_BORDER   = "#3a8a3a"
COLOR_BTN_CANCEL        = "#6a2d2d"
COLOR_BTN_CANCEL_BORDER = "#8a3a3a"
COLOR_BTN_FETCH         = "#6a5a1a"
COLOR_BTN_FETCH_BORDER  = "#8a7a2a"
COLOR_STAR_ACTIVE       = "#FFD700"
COLOR_THUMB_BG          = "#111111"
COLOR_FOLDER_BG         = "#2a2a2a"

# ── カード・バッジ ──
COLOR_CARD_HOVER    = "#303030"
COLOR_CARD_HOVER_BORDER = "#6a6a6a"
COLOR_CARD_PLACEHOLDER  = "#2a2a2a"
COLOR_CARD_STAR_OFF     = "#444444"
COLOR_CHECK_OK          = "#44cc66"
COLOR_CHECK_MAN          = "#888888"
COLOR_CARD_TITLE_FG     = "#f5f5f5"
COLOR_CARD_SUB_FG       = "#aaaaaa"
COLOR_BADGE_BG_DARK = "#3a3a3a"
COLOR_BADGE_FG      = "#b0b0b0"

# カード描画用アルファ値（0–255）
CARD_BADGE_OVERLAY_ALPHA   = 160
CARD_SHADOW_ALPHA         = 120
CARD_RATING_BG_ALPHA      = 115
CARD_TITLE_SHADOW_ALPHA   = 180

# ── サイト別カラー ──
SITE_COLORS = {
    "DLSite":   "#4a7aaa",
    "FANZA":    "#aa4a4a",
    "とらのあな": "#aa9a2a",
    "Booth":    "#2a7a4a",
    "同人DB":   "#666666",
}

THEME_COLORS = {
    "bg_base":        COLOR_BG_BASE,
    "bg_panel":       COLOR_BG_PANEL,
    "bg_widget":      COLOR_BG_WIDGET,
    "accent":         COLOR_ACCENT,
    "accent_hover":   COLOR_ACCENT_HOVER,
    "text_main":      COLOR_TEXT_MAIN,
    "text_sub":       COLOR_TEXT_SUB,
    "menu_disabled":  COLOR_MENU_DISABLED,
    "context_menu_shortcut": COLOR_CONTEXT_MENU_SHORTCUT,
    "border":         COLOR_BORDER,
    "hover":          COLOR_HOVER,
    "sep":            COLOR_SEP,
    "delete":         COLOR_DELETE,
    "delete_hover":   COLOR_DELETE_HOVER,
    "card_bg":        COLOR_BG_WIDGET,
    "card_selected":  COLOR_ACCENT,
    "card_hover":     COLOR_CARD_HOVER,
    "card_hover_border": COLOR_CARD_HOVER_BORDER,
    "card_placeholder":   COLOR_CARD_PLACEHOLDER,
    "card_star_off":     COLOR_CARD_STAR_OFF,
    "check_ok":          COLOR_CHECK_OK,
    "check_man":         COLOR_CHECK_MAN,
    "card_title_fg":     COLOR_CARD_TITLE_FG,
    "card_sub_fg":       COLOR_CARD_SUB_FG,
    "card_star_on":      COLOR_STAR_ACTIVE,
    "badge_bg":       COLOR_BADGE_BG_DARK,
    "badge_fg":       COLOR_BADGE_FG,
    "btn_save":       COLOR_BTN_SAVE,
    "btn_save_border": COLOR_BTN_SAVE_BORDER,
    "btn_cancel":     COLOR_BTN_CANCEL,
    "btn_cancel_border": COLOR_BTN_CANCEL_BORDER,
}

# ドロップダウン矢印文字（ここを変えれば全箇所に反映）
DROPDOWN_ARROW = "▼"

# ── メニュー項目（QMenu::item と危険項目ラベルで共通・一元管理）────────────
#
# ホバー = テーマのグレー（COLOR_HOVER）。選択/確定時用の紫（COLOR_ACCENT）とは分離。
# メニュー上でマウスを乗せたときは MENU_ITEM_HOVER_*（グレー）、全項目で共通。
#
MENU_ITEM_PADDING = "6px 24px 6px 12px"
MENU_ITEM_BORDER_RADIUS = "4px"
# メニュー項目ホバー色（グレー。QMenuBar::item:selected や QPushButton:hover と同じ COLOR_HOVER）
MENU_ITEM_HOVER_BG = COLOR_HOVER
MENU_ITEM_HOVER_FG = COLOR_TEXT_MAIN

# 危険項目ラベル用スタイル（通常時は赤文字、ホバーは上記グレーを適用）
DANGER_MENU_ITEM_STYLE_NORMAL = (
    f"color: {COLOR_DELETE}; padding: {MENU_ITEM_PADDING}; "
    f"background: transparent; border-radius: {MENU_ITEM_BORDER_RADIUS};"
)
DANGER_MENU_ITEM_STYLE_HOVER = (
    f"color: {MENU_ITEM_HOVER_FG}; padding: {MENU_ITEM_PADDING}; "
    f"background-color: {MENU_ITEM_HOVER_BG}; border-radius: {MENU_ITEM_BORDER_RADIUS};"
)


def get_theme() -> dict:
    return THEME_COLORS


# ── グローバルQSS ─────────────────────────────────────────
APP_QSS = f"""
QWidget {{
    background-color: {COLOR_BG_BASE};
    color: {COLOR_TEXT_MAIN};
    font-size: {config.FONT_SIZE_APP_GLOBAL}px;
}}

QMainWindow {{
    background-color: {COLOR_BG_BASE};
}}

/* スクロールバー */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_SCROLLBAR};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLOR_SCROLLBAR_HOVER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {COLOR_SCROLLBAR};
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {COLOR_SCROLLBAR_HOVER};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}

/* ボタン */
QPushButton {{
    background-color: {COLOR_BG_WIDGET};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 4px 12px;
}}
QPushButton:hover {{
    background-color: {COLOR_HOVER};
    border-color: {COLOR_ACCENT};
}}
QPushButton:pressed {{
    background-color: {COLOR_ACCENT};
    color: {COLOR_WHITE};
}}

/* 設定ダイアログ OK / キャンセル（QDialogButtonBox、objectName で識別） */
QDialogButtonBox QPushButton#DialogOkButton {{
    background-color: {COLOR_BTN_SAVE};
    color: {COLOR_WHITE};
    border: 1px solid {COLOR_BTN_SAVE_BORDER};
    border-radius: {config.BORDER_RADIUS}px;
    padding: 6px 16px;
    font-size: {config.FONT_SIZE_BTN_ACTION}px;
}}
QDialogButtonBox QPushButton#DialogOkButton:hover {{
    background-color: {COLOR_BTN_SAVE_BORDER};
    border-color: {COLOR_BTN_SAVE_BORDER};
}}
QDialogButtonBox QPushButton#DialogOkButton:pressed {{
    background-color: {COLOR_BTN_SAVE};
}}

QDialogButtonBox QPushButton#DialogCancelButton {{
    background-color: {COLOR_BTN_CANCEL};
    color: {COLOR_WHITE};
    border: 1px solid {COLOR_BTN_CANCEL_BORDER};
    border-radius: {config.BORDER_RADIUS}px;
    padding: 6px 16px;
    font-size: {config.FONT_SIZE_BTN_ACTION}px;
}}
QDialogButtonBox QPushButton#DialogCancelButton:hover {{
    background-color: {COLOR_BTN_CANCEL_BORDER};
    border-color: {COLOR_BTN_CANCEL_BORDER};
}}
QDialogButtonBox QPushButton#DialogCancelButton:pressed {{
    background-color: {COLOR_BTN_CANCEL};
}}

/* 入力欄 */
QLineEdit {{
    background-color: {COLOR_BG_WIDGET};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {COLOR_ACCENT};
}}
QLineEdit:focus {{
    border-color: {COLOR_ACCENT};
}}

/* タブ（設定ダイアログの一般 / ショートカット等） */
QTabWidget::pane {{
    background-color: {COLOR_BG_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-top: none;
    border-radius: 0;
    padding: 12px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {COLOR_BG_BASE};
    color: {COLOR_TEXT_SUB};
    border: 1px solid {COLOR_BORDER};
    border-bottom: none;
    border-radius: {config.BORDER_RADIUS}px {config.BORDER_RADIUS}px 0 0;
    padding: 8px 20px;
    margin-right: 2px;
    font-size: {config.FONT_SIZE_DIALOG_LABEL}px;
}}
QTabBar::tab:selected {{
    background-color: {COLOR_BG_PANEL};
    color: {COLOR_TEXT_MAIN};
    border-color: {COLOR_BORDER};
    border-bottom: 1px solid {COLOR_BG_PANEL};
}}
QTabBar::tab:hover:!selected {{
    background-color: {COLOR_HOVER};
    color: {COLOR_TEXT_MAIN};
}}

/* ラベル */
QLabel {{
    background: transparent;
    color: {COLOR_TEXT_MAIN};
}}
QLabel#SortLabel {{
    font-size: {config.FONT_SIZE_SORT_LABEL}px;
    font-weight: bold;
}}

/* リストビュー（グリッド用） */
QListView {{
border: none;
    outline: none;
}}
QListView::item {{
    border-radius: 6px;
}}
QListView::item:selected {{
    background-color: transparent;
}}
QListView::item:hover:!selected {{
    background-color: transparent;
}}

/* スプリッター */
QSplitter::handle {{
    background-color: {COLOR_SEP};
    width: 1px;
}}

/* メニューバー */
QMenuBar {{
    background-color: {COLOR_BG_PANEL};
    color: {COLOR_TEXT_MAIN};
    border-bottom: 1px solid {COLOR_SEP};
}}
QMenuBar::item:selected {{
    background-color: {COLOR_HOVER};
}}
QMenu {{
    background-color: {COLOR_BG_PANEL};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: {MENU_ITEM_PADDING};
    border-radius: {MENU_ITEM_BORDER_RADIUS};
}}
QMenu::item:selected {{
    background-color: {MENU_ITEM_HOVER_BG};
    color: {MENU_ITEM_HOVER_FG};
}}
QMenu::item:disabled {{
    color: {COLOR_MENU_DISABLED};
}}
QMenu::separator {{
    height: 1px;
    background: {COLOR_SEP};
    margin: 4px 8px;
}}
/* 危険項目（通常時のみ赤文字。ホバーは通常項目と同じグレー MENU_ITEM_HOVER_*） */
QMenu::item#menu_danger {{
    color: {COLOR_DELETE};
}}
QMenu::item#menu_danger:selected {{
    color: {MENU_ITEM_HOVER_FG};
    background-color: {MENU_ITEM_HOVER_BG};
}}

/* コンボボックス */
QComboBox {{
    background-color: {COLOR_BG_WIDGET};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 24px;
}}
QComboBox:hover {{
    border-color: {COLOR_ACCENT};
}}
QComboBox:focus {{
    border-color: {COLOR_ACCENT};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid {COLOR_BORDER};
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background: transparent;
}}
QComboBox::drop-down:hover {{
    background: {COLOR_HOVER};
}}
QComboBox::down-arrow {{
    background: {COLOR_ARROW};
    width: 6px;
    height: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLOR_BG_PANEL};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {COLOR_ACCENT};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 8px;
    border-radius: 4px;
    min-height: 24px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {COLOR_HOVER};
}}

/* スライダー */
QSlider::groove:horizontal {{
    height: 4px;
    background: {COLOR_BORDER};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {COLOR_ACCENT};
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: -5px 0;
}}
QSlider::sub-page:horizontal {{
    background: {COLOR_ACCENT};
    border-radius: 2px;
}}

/* ツールチップ */
QToolTip {{
    background-color: {COLOR_BG_PANEL};
    color: {COLOR_TEXT_MAIN};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 4px 8px;
}}
"""


# ── シェブロン矢印付きコンボボックス ─────────────────────
from PySide6.QtWidgets import QWidget, QComboBox as _QComboBox, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class StyledComboBox(_QComboBox):
    """シェブロン矢印付きのカスタムQComboBox。プロパティの_DropdownEntryと同様、子QLabelで∨を表示する。"""
    _DROP_WIDTH = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QComboBox::drop-down {{
                width: 0;
                border: none;
                background: transparent;
            }}
            QComboBox {{
                padding-right: {self._DROP_WIDTH}px;
            }}
        """)
        self._arrow = QLabel(DROPDOWN_ARROW, self)
        self._arrow.setAttribute(Qt.WA_TransparentForMouseEvents)
        arrow_font = QFont(config.FONT_FAMILY)
        arrow_font.setPixelSize(12)
        self._arrow.setFont(arrow_font)
        # デバッグ: 四角が見えるかでクリップ/Z-order を切り分け（確認後戻す）
        self._arrow.setStyleSheet("background: red; color: white;")
        self._arrow.setAlignment(Qt.AlignCenter)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrow.setGeometry(self.width() - self._DROP_WIDTH, 0, self._DROP_WIDTH, self.height())
        self._arrow.raise_()


def apply_dark_titlebar(window) -> None:
    """ウィンドウのタイトルバーをダークにする（Windows専用）"""
    try:
        import ctypes

        HWND = int(window.winId())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            HWND, 20, ctypes.byref(ctypes.c_int(1)), 4
        )
    except Exception:
        pass