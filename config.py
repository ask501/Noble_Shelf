# config.py - アプリ全体で共有する定数・設定の一元管理
# 全モジュールはここを参照し、マジックナンバーを排除する。
import os
import sys
from paths import APP_BASE, CACHE_DIR, COVER_CACHE_DIR

# ── UIスタイル共通定数 ────────────────────────────────────
BORDER_RADIUS = 6        # ウィジェット共通の角丸半径(px)
BORDER_WIDTH  = 1       # ボーダー幅(px)

# ── アプリ名（全ウィンドウのタイトルに使用）─────────────────
APP_TITLE = "Noble Shelf"

# ── ウィンドウ・キャッシュ ─────────────────────────────────
# アイコン（いずれも無くても起動はする）
# ウィンドウ用: タイトルバー・タスクバーに表示（PNG可）
WINDOW_ICON_PATH = os.path.join(APP_BASE, "assets", "icon.png")
# デスクトップ用: ショートカットや .exe に使う（.ico 推奨。PyInstaller の --icon やショートカットの「アイコンの変更」で指定）
DESKTOP_ICON_PATH = os.path.join(APP_BASE, "assets", "desktop_icon.ico")

# グリッド右上バッジ用: DMMブックス / DLSite ビュアー形式でページ数の代わりに表示（無ければ従来の XXP 表示）
BADGE_ICON_DMM_PATH    = os.path.join(APP_BASE, "assets", "dmm_badge.png")
BADGE_ICON_DLSITE_PATH = os.path.join(APP_BASE, "assets", "dlsite_badge.png")

WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 900

# ── フォント設定 ──────────────────────────────────────────
# フォントファミリーはここで一元管理。個別に "Meiryo UI" 等を書かないこと。
# 使用箇所: grid(app), sidebar, filter_popover, properties, settings_dialog, theme(StyledComboBox矢印), main.py デフォルト
FONT_FAMILY          = "Yu Gothic UI"
# 使用箇所: grid の星★・メタ取得チェック✓（記号用）
FONT_FAMILY_SYMBOL   = "Segoe UI Symbol"
FONT_SIZE_XXS      = 6
FONT_SIZE_SM       = 8
FONT_SIZE_XS       = 9   # 補助UI・ヒント等（QSSで使用）
FONT_SIZE_DEFAULT  = 10
FONT_SIZE_MD       = 12
FONT_SIZE_LG       = 14
FONT_SIZE_XL       = 18
FONT_SIZE_GHOSTBAR = 24
GHOSTBAR_HEIGHT    = 70

# ══════════════════════════════════════════════════════════
# 役割への割り当て（セマンティック層）
# 「どこで何を使うか」をここで一元管理する。
# プリミティブ定数を直接参照せず、このセマンティック名を使うこと。
# ══════════════════════════════════════════════════════════

# ── フォントサイズ・役割別 ────────────────────────────────
FONT_SIZE_CARD_TITLE      = FONT_SIZE_DEFAULT   # グリッドカードのタイトル
FONT_SIZE_CARD_CIRCLE     = FONT_SIZE_SM        # グリッドカードのサークル名
FONT_SIZE_CARD_BADGE      = FONT_SIZE_DEFAULT   # グリッドカードのバッジ（ページ数等）
FONT_SIZE_SIDEBAR_ITEM    = FONT_SIZE_DEFAULT   # サイドバーリスト項目
FONT_SIZE_SIDEBAR_BADGE   = FONT_SIZE_DEFAULT   # サイドバーの件数バッジ
FONT_SIZE_DIALOG_LABEL    = FONT_SIZE_DEFAULT   # ダイアログ・プロパティのラベル
FONT_SIZE_DIALOG_INPUT    = FONT_SIZE_DEFAULT   # ダイアログの入力欄
FONT_SIZE_BTN_DEFAULT     = FONT_SIZE_DEFAULT   # 通常ボタン
FONT_SIZE_BTN_ACTION      = FONT_SIZE_MD        # 保存・キャンセル・取得等のアクションボタン（QSS）
FONT_SIZE_BTN_LARGE       = FONT_SIZE_LG        # 主要ボタン（より大きくしたい場合）
FONT_SIZE_BTN_STAR        = FONT_SIZE_XL        # 星評価ボタン（コンテキストメニュー等）
FONT_SIZE_RATING_UI       = FONT_SIZE_XL        # プロパティパネル内の星評価ボタン（QSS）
FONT_SIZE_SORT_LABEL      = FONT_SIZE_GHOSTBAR  # ゴーストバーのソートラベル
FONT_SIZE_SORT_BTN        = FONT_SIZE_DEFAULT   # ゴーストバーのボタン（昇順・フィルター・クリア）
FONT_SIZE_SEARCH_INPUT    = FONT_SIZE_DEFAULT   # 検索バー入力欄（setFont用）
FONT_SIZE_SEARCHBAR       = FONT_SIZE_MD        # 検索バー入力欄（QSS font-size）
FONT_SIZE_SEARCHBAR_BTN   = FONT_SIZE_LG        # 検索バー検索ボタン（QSS）
FONT_SIZE_STATUS_BAR      = FONT_SIZE_DEFAULT   # ステータスバー
FONT_SIZE_VIEWER_UI       = FONT_SIZE_XS        # ビューワー：ツールバーボタン・ページラベル（QSS）
FONT_SIZE_VIEWER_SEEK     = FONT_SIZE_DEFAULT   # ビューワー：シークバーラベル（QSS）
FONT_SIZE_PROP_HINT       = FONT_SIZE_XS        # プロパティ・ダイアログの補助テキスト（QSS）
FONT_SIZE_CONTEXT_MENU    = FONT_SIZE_MD        # コンテキストメニュー（QSS）
FONT_SIZE_CONTEXT_MENU_SHORTCUT = FONT_SIZE_XS  # コンテキストメニュー右側ショートカット表示（QSS）
FONT_SIZE_STAR_UI         = FONT_SIZE_XL        # 星評価ボタン等（QSS）
FONT_SIZE_APP_GLOBAL      = FONT_SIZE_MD        # アプリ全体QSSのデフォルト（QWidget等）



# ── レイアウト ────────────────────────────────────────────
SIDEBAR_WIDTH       = 250
SIDEBAR_SPACING     = 6
SIDEBAR_MARGINS     = (6, 8, 6, 8)
SEARCHBAR_HEIGHT       = 40
SEARCH_INPUT_MAX_WIDTH = 400   # 検索入力欄の最大幅(px)。検索バー幅はそのまま

# メインウィンドウ・タイトルバー（app.py）
TITLE_BAR_DBLCLICK_HEIGHT = 50  # この高さ未満のダブルクリックで最大化

# ゴーストバー（ソートバー）（app.py）
SORT_BAR_BUTTON_HEIGHT = 32
SORT_BAR_MARGIN_LEFT = 16
SORT_BAR_MARGIN_RIGHT = 8
SORT_BAR_SPACING = 12
SORT_BAR_BADGE_SPACING = 4

# ── カード・サムネイル（グリッド）────────────────────────────
# スライダー用の幅範囲（情報バーのカードサイズスライダーで使用）
SLIDER_MIN_WIDTH = 100
SLIDER_MAX_WIDTH = 400
DEFAULT_CARD_WIDTH = 180

# サムネイルキャッシュ解像度（スライダー最大値でもボヤけない幅・フェーズ12）
THUMB_CACHE_WIDTH = 500
THUMB_CACHE_HEIGHT = int(500 * 170 / 120)  # アスペクト比維持

CARD_SIZE_MIN = SLIDER_MIN_WIDTH
CARD_SIZE_MAX = SLIDER_MAX_WIDTH
CARD_SIZE_DEFAULT = DEFAULT_CARD_WIDTH

THUMB_WIDTH_BASE = 120
THUMB_HEIGHT_BASE = 170
CARD_WIDTH_BASE = 150
CARD_HEIGHT_BASE = 220
HEADER_HEIGHT = 55

# カード描画の余白・オフセット（Ver 16.1: 左右マージン半分で表示領域を拡大）
CARD_GRID_MARGIN_X = 8
CARD_GRID_MARGIN_Y = 4
CARD_RECT_PADDING = 10
CARD_TITLE_OFFSET_Y = 20
CARD_BADGE_PAD = 8
BADGE_HEIGHT   = 16
CARD_BADGE_HEIGHT = BADGE_HEIGHT
CARD_HEADER_INSET = 10
CARD_HEADER_ACCENT_LEFT = 10
CARD_HEADER_ACCENT_WIDTH = 4
CARD_HEADER_TEXT_LEFT = 24
CARD_IMAGE_OFFSET_Y = 5
CARD_TEXT_WIDTH_INSET = 4
CARD_GRID_BOTTOM_MARGIN = 20
# 装飾パーツのオフセット（カード枠からの相対・config 一元化でハードコード排除）
# ページ数バッジ（XXP）：カード端からの余白とバッジ内テキストの左右余白
PAGE_BADGE_PAD = 5       # ページ数バッジ内のテキスト左右余白(px)
PAGE_BADGE_BG_OVERLAY = 1  # ページ数バッジの背景がテキスト領域からはみ出す量(px)。1なら上下左右に1pxずつオーバーレイ
CARD_BADGE_OFFSET_X = 5   # ページ数バッジ：カード右端から(px)
CARD_BADGE_OFFSET_Y = 4   # ページ数バッジ：カード上端から(px)

# DMM/DLSiteバッジ画像表示時：表示高さ(px)。幅は画像アスペクト比で自動計算
BADGE_ICON_HEIGHT = 24
# DMM/DLSiteバッジ画像表示時：アイコンと背景の間の余白（左右・上下ともこの値で固定）
BADGE_ICON_PAD = 5
# ストアファイル拡張子（メニュー「DLSiteのみ／FANZAのみ」フィルタ等で使用）
STORE_FILE_EXT_DLSITE = ".dlst"
STORE_FILE_EXTS_DMM = (".dmmb", ".dmme", ".dmmr")

CARD_STAR_OFFSET_RIGHT = 2   # 星評価：サムネイル右端から
CARD_STAR_OFFSET_BOTTOM = 2  # 星評価：サムネイル下端から
CARD_META_OFFSET_X = 0   # メタ/除外マーク：カード左端から（サムネ左と揃える）
CARD_META_OFFSET_Y = 4   # メタ/除外マーク：カード上端から
# 列数計算用: カード幅＋最小余白（Ver 16.0: 黄金比に近づけるため 16px）
CARD_MIN_GAP = 16

# カード描画（grid.py）用の寸法・余白
CARD_TEXT_HEIGHT_FIXED = 40      # テキスト領域の固定高さ（2行分）
CARD_GRADIENT_HEIGHT = 20        # サムネ下端グラデーションの高さ
CARD_META_BADGE_SIZE = 18        # メタバッジ（✓）の一辺
CARD_INSET = 4                   # カード内の基本余白（px）
CARD_PLACEHOLDER_CROSS_HALF = 8  # プレースホルダー十字の半幅
CARD_STAR_BADGE_PADDING = 6      # 星バッジの左右パディング
CARD_BADGE_RADIUS = 4            # ページ数・星バッジの角丸
CARD_META_BADGE_RADIUS = 5       # メタバッジの角丸
GRID_SCROLL_SINGLE_STEP = 20     # グリッド縦スクロールの単步

# ── カード表示設定キー ──────────────────────────────────────
CARD_SETTING_META_BADGE   = "card_show_meta_badge"    # "1"/"0"
CARD_SETTING_PAGES_BADGE  = "card_show_pages_badge"   # "1"/"0"
CARD_SETTING_STAR         = "card_show_star"          # "1"/"0"
CARD_SETTING_SUB_INFO     = "card_sub_info"           # "none"/"circle"/"author"/"series"/"character"/"tag"
CARD_SETTING_SUB_INFO_DEFAULT = "circle"
CARD_SETTING_STORE_ICON = "card_show_store_icon"  # "1"/"0"

# ── 右クリックメニュー（コンテキストメニュー）────────────────
CONTEXT_MENU_DEBOUNCE_MS = 300
CONTEXT_MENU_CREATE_DELAY_MS = 50
CONTEXT_MENU_FOCUSOUT_BIND_DELAY_MS = 100
CONTEXT_MENU_FOCUSOUT_CLOSE_DELAY_MS = 50

CONTEXT_MENU_BG = "#2b2b2b"
CONTEXT_MENU_HOVER_BG = "#0078d4"
CONTEXT_MENU_SEP_COLOR = "#444444"
CONTEXT_MENU_TEXT_FG = "#f0f0f0"
CONTEXT_MENU_DELETE_FG = "#ff6b6b"
CONTEXT_MENU_DELETE_HOVER = "#c0392b"
CONTEXT_MENU_DIM_FG = "#888888"
CONTEXT_MENU_ITEM_HEIGHT = 28
CONTEXT_MENU_SEP_HEIGHT = 9
CONTEXT_MENU_WIDTH = 240

# ── プルダウン・ドロップダウン（サイドバー・コンテキスト・設定で統一）────────────────
DROPDOWN_HEIGHT = 48
DROPDOWN_ITEM_HEIGHT = 30
DROPDOWN_ITEM_GAP = 2
DROPDOWN_PADDING_X = 12
# 使用箇所: コンテキストメニューQSS、UI_DROPDOWN_STYLE（プルダウン・メニュー系）
DROPDOWN_FONT_FAMILY = "Meiryo UI"
DROPDOWN_FONT_SIZE = 10
DROPDOWN_WIDTH = 168

# プルダウン／コンテキストメニュー共通スタイル（出自を config に一元化）
UI_DROPDOWN_STYLE = {
    "height": 48,
    "item_height": 30,
    "item_gap": 2,
    "padding_x": 12,
    "font_family": DROPDOWN_FONT_FAMILY,
    "font_size": 10,
    "font_size_shortcut": 8,
    "width": 168,
    "border_width": 1,
    "inner_inset": 1,
    "vertical_margin": 4,
    "sep_height": 9,
    "context_menu_width": 240,
    "context_item_height": 28,
}

# ── 検索バー・チップ ───────────────────────────────────────
SEARCH_BAR_BG = "#1a1a1a"
SEARCH_CHIP_BG = "#2a475e"
SEARCH_CHIP_HOVER = "#1e3a52"
SEARCH_CHIP_FG = "#e0e0e0"
SEARCH_DROPDOWN_BG = "#252525"
SEARCH_DROPDOWN_HOVER = "#0078d4"
SEARCH_SEP_COLOR = "#3a3a3a"

CHIP_COLOR_SORT = "#444444"
CHIP_COLOR_PATH = "#2b579a"
CHIP_COLOR_TAG = "#1e7145"
CHIP_COLOR_AUTHOR = "#b91d47"

SEARCH_TYPING_DELAY_MS = 150

# ── リサイズ・レイアウト ────────────────────────────────────
RESIZE_RELAYOUT_DELAY_MS = 100
ADDRESSBAR_EXIT_EDIT_DELAY_MS = 100
# グリッドの Configure は待機なしで即時応答（フェーズ9.6）
RESIZE_GRID_IMMEDIATE = True

# ── グリッド描画の軽量化（フェーズ11）────────────────────────────
GRID_RENDER_THROTTLE_MS = 10   # スクロール時のスロットル間隔。10ms≒100FPS相当の追従性。キャッシュとafter(0)で負荷を抑える
VIEWPORT_MARGIN_PX = 0        # ビューポート外の余白（px）。0でビュー内のみ描画
# オーバースキャン: 上下に何画面分を先行描画するか（フェーズ15）
VIEWPORT_OVERSCAN_SCREENS = 1.5
SLIDER_DRAG_DEBOUNCE_MS = 280 # スライダー操作終了とみなす無操作時間（この時間後に高画質に切替）
SCROLL_END_MS = 120           # スクロール終了とみなす無操作時間（この時間後に画像リフレッシュ）

# サイドバー用: バッジ右余白(px)
SIDEBAR_BADGE_MARGIN_RIGHT = 10

# ── プロパティ・ストアファイル登録ダイアログ ─────────────────────
PROP_LABEL_WIDTH = 70           # ラベル列の幅(px)
PROP_DIALOG_MIN_WIDTH = 480     # ダイアログ最小幅(px)
PROP_BUTTON_HEIGHT = 32         # ダイアログ内ボタン高さ(px)（メタデータ検索など）
PROP_MEMO_HEIGHT_SMALL = 50     # ストアファイル登録のメモ欄高さ(px)
PROP_BTN_FETCH_WIDTH = 60       # 取得ボタン幅(px)
PROP_MEMO_LINE_HEIGHT = 24      # プロパティのメモ行高(px)。3行 = 3 * PROP_MEMO_LINE_HEIGHT

# 起動直後のスキャンでストアファイル入力ダイアログを出さない時間(秒)
INITIAL_SCAN_SUPPRESS_DIALOG_SEC = 3.0

# ── フィルターポップオーバー（ゴーストバー🔧）────────────────────────
FILTER_POPOVER_WIDTH = 380        # ポップオーバー幅(px)
FILTER_POPOVER_ROW_HEIGHT = 26    # 1行の高さ(px)。コンボ・入力欄・追加/クリアボタンの基準（表示時は左コンボに同期）
FILTER_POPOVER_LIST_HEIGHT = 120   # 条件リストの高さ(px)
FILTER_POPOVER_MARGINS = 8         # レイアウト余白(px)
FILTER_POPOVER_SPACING = 6        # レイアウト間隔(px)
FILTER_POPOVER_ROW_SPACING = 4     # 条件追加行内の間隔(px)
FILTER_POPOVER_RADIO_INDICATOR = 12   # ラジオボタンインジケータの幅・高さ(px)
FILTER_POPOVER_BORDER_RADIUS = 6  # ダイアログ・ボタン角丸(px)
FILTER_POPOVER_LIST_RADIUS = 4    # 条件リストの角丸(px)
FILTER_POPOVER_APPLY_BTN_WIDTH = 72   # 下部「適用」ボタンの幅(px)
FILTER_POPOVER_CLEAR_BTN_WIDTH = 72   # 下部「クリア」ボタンの幅(px)

# ── フォルダ名・表示名の命名規則 ─────────────────────────────
# 形式: [サークル名]作品名（サークルなしのときは作品名のみ）

# ── レイアウト・役割別 ────────────────────────────────────
DIALOG_LABEL_WIDTH        = PROP_LABEL_WIDTH        # ダイアログ共通ラベル幅
DIALOG_MIN_WIDTH          = PROP_DIALOG_MIN_WIDTH   # ダイアログ共通最小幅
DIALOG_BUTTON_HEIGHT      = PROP_BUTTON_HEIGHT      # ダイアログ共通ボタン高さ
DIALOG_FETCH_BTN_WIDTH    = PROP_BTN_FETCH_WIDTH    # 取得系ボタン幅

# ── ファイルメニュー等ショートカット（設定で変更可）────────────────
# db settings のキー: shortcut_<id>。値は QKeySequence に渡す文字列（例: "Ctrl+O"）
DEFAULT_SHORTCUTS = {
    "file_open": "Ctrl+Return",
    "file_recent": "Ctrl+R",
    "file_close_all": "",
    "file_open_library": "Ctrl+Shift+O",
    "file_copy": "Ctrl+C",
    "file_paste": "Ctrl+V",
    "file_print": "Ctrl+P",
    "file_rescan": "F5",
    "file_quit": "Ctrl+Q",
}
