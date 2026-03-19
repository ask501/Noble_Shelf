"""
theme.py - アプリ全体のテーマ・スタイル定義
旧 ui_common.py の移植。PySide6用QSSに対応。
"""

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

# ── 設定ダイアログ（settings_dialog.py）用カラー/QSS ───────────
# ※settings_dialog.py の直書きスタイルを同値で定数化（見た目維持）
SETTINGS_SHORTCUT_CAPTURE_BORDER = "#00aa77"     # "#0a7"
SETTINGS_SHORTCUT_CAPTURE_BORDER_OK = "#00cc99"  # "#0c9"
SETTINGS_SHORTCUT_CAPTURE_BG = "#1a2a28"
SETTINGS_SHORTCUT_CONFIRMED_BG = "#0d3d38"
SETTINGS_CARD_PREVIEW_THUMB_BG = "#2a2a38"       # カード表示タブのプレビュー用サムネ背景
SETTINGS_CARD_PREVIEW_META_OK_BG = "#4caf50"     # プレビューのメタバッジ(✓)背景

# ── properties/meta_apply_dialog.py 用カラー/QSS ──────────────
# ※meta_apply_dialog.py の直書き #xxxxxx を同値で定数化（見た目維持）
META_APPLY_THUMB_BG = "#222"
META_APPLY_THUMB_BORDER = "#444"
META_APPLY_TEXT_DIM = "#666"
META_APPLY_TEXT_SUB = "#888"
META_APPLY_RADIO_TEXT = "#ccc"
META_APPLY_RADIO_BORDER = "#888"

# ── properties/meta_search_dialog.py 用カラー ────────────────
# ※meta_search_dialog.py の直書き #xxx を同値で定数化（見た目維持）
META_SEARCH_SITE_DEFAULT = "#888"
META_SEARCH_ITEM_DIM_FG = "#666666"

# ── properties/meta_apply_dialog.py 用カラー（追加）────────────
META_APPLY_TOGGLE_TEXT = "#aaa"
META_APPLY_TOGGLE_DIM_TEXT = "#555"

# ── properties/properties_dialog.py 用カラー ────────────────
# ※properties_dialog.py の直書き #xxxxxx を同値で定数化（見た目維持）
PROPERTY_BULK_HINT_FG = "#ee6666"    # "#e66"
PROPERTY_BORDER = "#444"
PROPERTY_THUMB_BG = "#111111"        # サムネ枠背景（theme.COLOR_THUMB_BG と同値）
PROPERTY_FOLDER_BG = "#2a2a2a"       # フォルダ名ラベル背景（theme.COLOR_FOLDER_BG と同値）
PROPERTY_FOLDER_FG = "#ccc"
PROPERTY_FOLDER_HOVER_BORDER = "#666"
PROPERTY_STAR_OFF_FG = "#888"        # 未選択の星色

# ── context_menu/actions_bookmark.py 用カラー ────────────────
# ※actions_bookmark.py の直書き #xxxxxx を同値で定数化（見た目維持）
BOOKMARK_STAR_ON_FG = "#f5c518"
BOOKMARK_STAR_OFF_FG = "#555555"
BOOKMARK_SAVE_BG = "#2d7a2d"

# ── bookmarklet_window.py 用カラー ─────────────────────────
# ※bookmarklet_window.py の直書き #xxxxxx を同値で定数化（見た目維持）
BOOKMARKLET_THUMB_BG = "#1a1a1a"
BOOKMARKLET_THUMB_BORDER = "#333333"

# ── thumbnail_crop_dialog.py 用カラー ──────────────────────
# ※thumbnail_crop_dialog.py の直書き #xxxxxx を同値で定数化（見た目維持）
THUMB_CROP_HINT_FG = "#aaa"
THUMB_CROP_VIEW_BG = "#1a1a1a"
THUMB_CROP_BTN_FG = "#aaa"
THUMB_CROP_FRAME_COLOR = (255, 80, 80)  # QPainter overlay（赤枠）
THUMB_CROP_FRAME_PEN_W = 2
# 「切り抜き」ボタン（既存の保存ボタン配色と同系統）
THUMB_CROP_BTN_CROP_BG = "#2d6a2d"
THUMB_CROP_BTN_CROP_BORDER = "#3a8a3a"
THUMB_CROP_BTN_CROP_PAD_Y = 6
THUMB_CROP_BTN_CROP_PAD_X = 16

# ── app.py 用カラー/QSS ───────────────────────────────────
# ※app.py のQSS直書き値を同値で定数化（見た目維持）
APP_BAR_SEPARATOR_RGBA = "rgba(255, 255, 255, 0.15)"  # ソートバー/ステータスバーの細い境界線

CONTEXT_MENU_SEP_COLOR = "#444444"

# ── ビューワー（viewer.py）用カラー ───────────────────────────
# ※見た目維持のため、viewer.py の直書き #xxxxxx を同値で定数化
VIEWER_BG = "#111111"              # ページキャンバス/ビューワー背景
VIEWER_TOOLBAR_BG = "#1a1a1a"      # 上部ツールバー背景・シークバー背景
VIEWER_BTN_BG = "#2a2a2a"          # ツールバーボタン背景
VIEWER_BTN_FG = "#cccccc"          # ツールバーボタン文字色
VIEWER_BTN_BORDER = "#444444"      # ツールバーボタン枠
VIEWER_BTN_HOVER_BG = "#3a3a3a"    # ツールバーボタン hover 背景
VIEWER_BTN_PRESSED_BG = "#9A7FFF"  # ツールバーボタン pressed 背景（アクセント）
VIEWER_BTN_PRESSED_FG = "#ffffff"  # ツールバーボタン pressed 文字色
VIEWER_TEXT_SUB = "#aaaaaa"        # ページ表示ラベル等の補助文字色
VIEWER_SLIDER_GROOVE_BG = "#444444"  # シークバー溝背景

# カード描画用アルファ値（0–255）
CARD_BADGE_OVERLAY_ALPHA   = 160
CARD_SHADOW_ALPHA         = 120
CARD_RATING_BG_ALPHA      = 115
CARD_TITLE_SHADOW_ALPHA   = 180

# ── 設定ダイアログ（settings_dialog.py）用QSS（ローカル適用）──────
SETTINGS_SHORTCUT_HINT_STYLE = (
    f"color: {COLOR_CHECK_MAN}; font-size: 9px;"
)
SETTINGS_SHORTCUT_DISPLAY_STYLE_NORMAL = (
    f"padding: 4px 8px; min-width: 140px; "
    f"border: 1px solid {COLOR_MENU_DISABLED}; border-radius: 4px; "
    f"background: {COLOR_FOLDER_BG}; font-size: 10px;"
)
SETTINGS_SHORTCUT_DISPLAY_STYLE_CAPTURE = (
    f"padding: 4px 8px; min-width: 140px; "
    f"border: 2px solid {SETTINGS_SHORTCUT_CAPTURE_BORDER}; border-radius: 4px; "
    f"background: {SETTINGS_SHORTCUT_CAPTURE_BG}; font-size: 10px;"
)
SETTINGS_SHORTCUT_DISPLAY_STYLE_CONFIRMED = (
    f"padding: 4px 8px; min-width: 140px; "
    f"border: 2px solid {SETTINGS_SHORTCUT_CAPTURE_BORDER_OK}; border-radius: 4px; "
    f"background: {SETTINGS_SHORTCUT_CONFIRMED_BG}; font-size: 10px;"
)

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

# ホバー = テーマのグレー（COLOR_HOVER）。選択/確定時用の紫（COLOR_ACCENT）とは分離。
# メニュー上でマウスを乗せたときは MENU_ITEM_HOVER_*（グレー）、全項目で共通。
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

# ── グローバルQSS ─────────────────────────────────────────
APP_QSS = f"""
QWidget {{
    background-color: {COLOR_BG_BASE};
    color: {COLOR_TEXT_MAIN};
    font-size: 12px;
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
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 12px;
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
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 12px;
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
    border-radius: 6px 6px 0 0;
    padding: 8px 20px;
    margin-right: 2px;
    font-size: 10px;
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
    font-size: 24px;
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