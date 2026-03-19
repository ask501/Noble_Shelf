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
SIDEBAR_HEADER_PAD_X = 6   # サイドバーヘッダー内コンボの左右余白(px)
SIDEBAR_HEADER_PAD_Y = 4   # サイドバーヘッダー内コンボの上下余白(px)
# sidebar.py: ヘッダー内コントロール高さ(px)（モード選択コンボ/フィルタ表示ラベル）
SIDEBAR_HEADER_CONTROL_HEIGHT = 32
# sidebar.py: リスト項目の寸法
SIDEBAR_ITEM_PADDING_Y = 5
SIDEBAR_ITEM_PADDING_X = 8
SIDEBAR_ITEM_RADIUS = 4
# sidebar.py: デリゲートのバッジ寸法
SIDEBAR_BADGE_HEIGHT = 18
SIDEBAR_BADGE_TEXT_PAD = 10       # 件数バッジ内の左右余白(px)（合計ではなく片側込みの既存値）
SIDEBAR_BADGE_MARGIN = 8          # バッジとテキストの間隔(px)
SIDEBAR_TEXT_RIGHT_INSET_NO_BADGE = 4
SIDEBAR_DELEGATE_BG_INSET = 1     # 選択背景のrect調整(inset)px
SIDEBAR_VIEWPORT_FALLBACK_WIDTH = 200
SEARCHBAR_HEIGHT       = 40
SEARCH_INPUT_MAX_WIDTH = 400   # 検索入力欄の最大幅(px)。検索バー幅はそのまま

# searchbar.py（検索バー）: レイアウト/寸法（見た目維持のため直書き値を定数化）
SEARCHBAR_OUTER_MARGINS = (8, 4, 8, 4)   # left, top, right, bottom
SEARCHBAR_CAPSULE_HEIGHT_INSET = 8       # SEARCHBAR_HEIGHT から引く値（上下余白合計）
SEARCHBAR_CAPSULE_RADIUS = 14            # 角丸半径(px)
SEARCHBAR_CAPSULE_BTN_WIDTH = 44         # 右側の検索ボタン幅(px)
SEARCHBAR_INPUT_PADDING_Y = 6
SEARCHBAR_INPUT_PADDING_X = 12
# searchbar.py: 入力→検索発火までの遅延(ms)（見た目/体感維持）
SEARCHBAR_DEBOUNCE_MS = 50

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

# ── オートスクロール（中クリックMixin）────────────────────────
AUTO_SCROLL_DEAD_ZONE = 8        # 基準点からのデッドゾーン(px)
AUTO_SCROLL_TIMER_MS = 8        # スクロール適用タイマー間隔(ms)
AUTO_SCROLL_SPEED_FACTOR = 1     # 差分ピクセル→スクロール量の係数
AUTO_SCROLL_MAX_SPEED = 20       # スクロール速度の上限（ピクセル/ティック）
AUTO_SCROLL_SPEED_RANGE = 512    # 最高速到達距離(px)
AUTO_SCROLL_SPEED_RANGE_SIDEBAR = 512  # サイドバー用最高速到達距離(px)
AUTO_SCROLL_DRAG_THRESHOLD = 8   # ドラッグ判定の移動量(px)
AUTO_SCROLL_ICON_SIZE = 32       # オートスクロールアンカーアイコンの描画サイズ(px)

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

# context_menu/_utils.py: ショートカット(.lnk)解決のタイムアウト(秒)
SHORTCUT_RESOLVE_TIMEOUT_SEC = 5

# context_menu/actions_file.py: 削除確認ダイアログ（見た目維持）
DELETE_CONFIRM_MIN_WIDTH = 400
DELETE_CONFIRM_MARGINS = (20, 20, 20, 20)
DELETE_CONFIRM_SPACING = 14
DELETE_CONFIRM_LABEL_MIN_WIDTH = 360
DELETE_CONFIRM_LABEL_MIN_HEIGHT = 80

# context_menu/actions_bookmark.py: 星ダイアログ寸法（見た目維持）
BOOKMARK_DIALOG_SIZE = (260, 140)
BOOKMARK_DIALOG_MARGINS = (16, 12, 16, 12)
BOOKMARK_DIALOG_SPACING = 10
BOOKMARK_STAR_ROW_SPACING = 6
BOOKMARK_STAR_BTN_SIZE = (32, 32)
BOOKMARK_BTN_WIDTH = 72
BOOKMARK_CANCEL_BTN_WIDTH = 80
BOOKMARK_BTN_RADIUS = 4
BOOKMARK_BTN_PADDING_Y = 4
BOOKMARK_BTN_PADDING_X = 8

# context_menu/book_menu.py: コンテキストメニューQSS寸法（見た目維持）
BOOK_CONTEXT_MENU_MIN_WIDTH = 260
BOOK_CONTEXT_MENU_BORDER_RADIUS = 4
BOOK_CONTEXT_MENU_PADDING_Y = 4          # QMenu padding: 4px 0
BOOK_CONTEXT_MENU_ITEM_PADDING = (6, 24, 6, 16)  # top,right,bottom,left
BOOK_CONTEXT_MENU_ITEM_RADIUS = 3
BOOK_CONTEXT_MENU_SEP_HEIGHT = 1
BOOK_CONTEXT_MENU_SEP_MARGIN = (3, 8)    # top/bottom, left/right

# context_menu/book_menu.py: ショートカット表示行（QWidgetAction）レイアウト
BOOK_CONTEXT_MENU_ROW_MARGINS = (12, 0, 16, 0)  # left, top, right, bottom
BOOK_CONTEXT_MENU_ROW_SPACING = 24
BOOK_CONTEXT_MENU_ROW_LABEL_PADDING_Y = 6

# context_menu/book_menu.py: 削除行の高さ
BOOK_CONTEXT_MENU_DELETE_ROW_HEIGHT = 32

# bookmarklet_window.py: ウィンドウ/サムネ/ネットワーク（見た目維持）
BOOKMARKLET_WINDOW_TITLE = "ブックマークレットキュー"
BOOKMARKLET_WINDOW_SIZE = (800, 500)
BOOKMARKLET_THUMB_SIZE = (180, 180)
BOOKMARKLET_HTTP_TIMEOUT_SEC = 5
BOOKMARKLET_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
BOOKMARKLET_REFERER_DLSITE = "https://www.dlsite.com/"

# statusbar.py: ステータスバーUI（見た目維持）
STATUSBAR_SLIDER_WIDTH = 120
STATUSBAR_LICENSE_MARGIN_X = 12

# thumbnail_crop_dialog.py: ダイアログ/ネットワーク/保存（見た目維持）
THUMB_CROP_DIALOG_MIN_SIZE = (640, 480)
THUMB_CROP_DIALOG_SIZE = (800, 600)
THUMB_CROP_LAYOUT_MARGINS = (12, 12, 12, 12)
THUMB_CROP_LAYOUT_SPACING = 8
THUMB_CROP_FIT_DELAY_MS = 50
THUMB_CROP_DOWNLOAD_TIMEOUT_SEC = 15
# JPEG保存品質（見た目/容量維持）
THUMB_CROP_JPEG_QUALITY = 90

# drop_handler.py: UI寸法・進捗（見た目維持）
DROP_FOLDER_DIALOG_SIZE = (360, 160)
DROP_ARCHIVE_DIALOG_SIZE = (400, 140)
DROP_DIALOG_SPACING = 12
DROP_DIALOG_BTN_HEIGHT = 32
DROP_ZIP_PROGRESS_RANGE = (0, 100)
DROP_ZIP_PROGRESS_MIN_DURATION_MS = 0
# drop_handler.py: PDFカバー生成スケール（見た目維持）
PDF_COVER_SCALE = 1.5

# first_run.py: 初回起動オーバーレイ（見た目維持）
FIRST_RUN_SETUP_BTN_SIZE = (180, 80)
FIRST_RUN_SETUP_BTN_RADIUS = 16
FIRST_RUN_SETUP_BTN_PADDING = (8, 16)  # y, x
FIRST_RUN_SETUP_BTN_PRESSED_OPACITY = 0.9

# debug_tools.py: 初回起動オーバーレイ確認ダイアログ（見た目維持）
DEBUG_FIRST_RUN_DIALOG_TITLE = "初回起動オーバーレイ（デバッグ）"
DEBUG_FIRST_RUN_DIALOG_SIZE = (400, 300)
DEBUG_FIRST_RUN_DIALOG_MARGINS = (16, 16, 16, 16)

# app.py: 最近開いたブックのポップアップ件数
RECENT_BOOKS_MENU_LIMIT = 10

# app.py: スプリッター初期幅（サイドバー）
MAIN_SPLITTER_SIDEBAR_INIT_WIDTH = 200
MAIN_SPLITTER_HANDLE_WIDTH = 1

# app.py: Ctrl+ホイールのカードサイズ変更ステップ
CARD_SIZE_WHEEL_STEP = 10

# app.py: フィルターバッジの寸法（ゴーストバー）
FILTER_BADGE_HEIGHT = 26
FILTER_BADGE_RADIUS = 12
FILTER_BADGE_PADDING_Y = 2
FILTER_BADGE_PADDING_X = 10

# app.py: ソートバーのボタンQSS寸法
SORT_BAR_LABEL_PADDING_LEFT = 4
SORT_BAR_BTN_RADIUS = 6
SORT_BAR_BTN_PADDING_Y = 4
SORT_BAR_BTN_PADDING_X = 10

# app.py: バックアップ復元ダイアログ（見た目維持）
RESTORE_BACKUP_DIALOG_SIZE = (420, 280)

# app.py: コンテキストメニューのスクロール保護タイマー(ms)
CONTEXT_MENU_SCROLL_RESET_DELAY_MS = 600
CONTEXT_MENU_SCROLL_FALLBACK_DELAY_MS = 400

# app.py: 最近開いたブックの表示上限（別用途）
RECENT_BOOKS_LIST_LIMIT = 100

# app.py: 進捗ダイアログ（PDFサムネ修復 / ふりがな一括取得）
PROGRESS_DIALOG_MIN_DURATION_MS = 0

# app.py: 起動直後のライブラリ読み込みをスケジュールする遅延(ms)
APP_STARTUP_LOAD_DELAY_MS = 0

# 共通: 余白/間隔ゼロ指定（Qtレイアウトで頻出）
LAYOUT_MARGINS_ZERO = (0, 0, 0, 0)
LAYOUT_SPACING_ZERO = 0

# app.py: アーカイブ拡張子（cover修復/キャッシュ修復で使用）
ARCHIVE_EXTS = (".zip", ".cbz", ".7z", ".cb7", ".rar", ".cbr")

# updater.py: GitHub API 取得タイムアウト(秒)
UPDATER_GITHUB_API_TIMEOUT_SEC = 5
# updater.py: 更新zipダウンロードタイムアウト(秒)
UPDATER_ZIP_DOWNLOAD_TIMEOUT_SEC = 30
# updater.py: ダウンロードチャンクサイズ(bytes)
UPDATER_DOWNLOAD_CHUNK_SIZE = 8192
# updater.py: アップデート適用後に終了するまでの猶予(ms)
UPDATER_QUIT_DELAY_MS = 500

# main.py: on_startup コールバックを呼ぶまでの遅延(ms)
MAIN_ON_STARTUP_DELAY_MS = 500

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

# properties/store_file_input_dialog.py: レイアウト（見た目維持）
STORE_FILE_INPUT_MARGINS = (16, 16, 16, 16)  # left, top, right, bottom
STORE_FILE_INPUT_SPACING = 10
STORE_FILE_INPUT_ROW_SPACING = 4

# properties/meta_search_dialog.py: ダイアログ寸法/検索行（見た目維持）
META_SEARCH_DIALOG_MIN_SIZE = (560, 420)  # setMinimumSize(w, h)
META_SEARCH_LAYOUT_SPACING = 8
META_SEARCH_ROW_HEIGHT = 28
META_SEARCH_KIND_COMBO_WIDTH = 110
META_SEARCH_BTN_SEARCH_WIDTH = 60
# properties/meta_search_dialog.py: 進捗ダイアログ表示設定（見た目維持）
META_SEARCH_PROGRESS_MIN_DURATION_MS = 0
# properties/meta_search_dialog.py: 検索結果上限（見た目/負荷維持）
META_SEARCH_MAX_RESULTS = 10

# properties/properties_dialog.py: ダイアログ/レイアウト（見た目維持）
PROPERTY_DIALOG_SIZE = (680, 690)            # setFixedSize(w, h)
PROPERTY_DIALOG_MARGINS = (16, 16, 16, 12)   # root layout margins
PROPERTY_DIALOG_SPACING = 10
PROPERTY_DIALOG_TOP_SPACING = 16
PROPERTY_LEFT_COL_WIDTH = 160
PROPERTY_LEFT_COL_SPACING = 8
PROPERTY_RIGHT_COL_SPACING = 6
PROPERTY_ROW_SPACING = 4

# properties/properties_dialog.py: サムネ/フォルダ名/お気に入りUI
PROPERTY_THUMB_SIZE = (160, 220)
PROPERTY_FOLDER_LABEL_MAX_WIDTH = 160
PROPERTY_STAR_ROW_SPACING = 2
PROPERTY_STAR_BTN_SIZE = (28, 28)
PROPERTY_EXCLUDE_BTN_WIDTH = 48
PROPERTY_BOTTOM_ROW_SPACING = 12

# properties/properties_dialog.py: フォルダ名ポップアップ
PROPERTY_RENAME_POPUP_MIN_WIDTH = 500
PROPERTY_RENAME_POPUP_MARGINS = (16, 16, 16, 16)
PROPERTY_RENAME_POPUP_SPACING = 8

# properties/properties_dialog.py: 下部ボタン寸法（見た目維持）
PROPERTY_ACTION_BTN_SIZE = (110, 36)  # width, height

# ── 設定ダイアログ（settings_dialog.py）────────────────────────
# ウィンドウサイズ（見た目維持のため直書き値を定数化）
SETTINGS_DIALOG_MIN_SIZE = (480, 460)       # setMinimumSize(w, h)
SETTINGS_DIALOG_DEFAULT_SIZE = (520, 520)   # resize(w, h)
# レイアウト（ダイアログ全体）
SETTINGS_DIALOG_MARGINS = (16, 16, 16, 16)  # left, top, right, bottom
SETTINGS_DIALOG_SPACING = 12
# 一般タブ：参照ボタン幅
SETTINGS_BROWSE_BTN_WIDTH = 72
# ショートカットタブ：説明テキストのフォントサイズ(px)
SETTINGS_SHORTCUT_HINT_FONT_SIZE_PX = 9
# ショートカットタブ：表示枠/ボタン寸法
SETTINGS_SHORTCUT_DISPLAY_MIN_WIDTH = 140
SETTINGS_SHORTCUT_CAPTURE_BTN_WIDTH = 56
SETTINGS_SHORTCUT_CLEAR_BTN_WIDTH = 28
SETTINGS_SHORTCUT_ROW_SPACING = 6
# 検知完了→終了までの遅延(ms)（キー入力直後の見た目維持）
SETTINGS_SHORTCUT_CAPTURE_END_DELAY_MS = 80
# バックアップタブ
SETTINGS_BACKUP_COUNT_MIN = 1
SETTINGS_BACKUP_COUNT_MAX = 99
SETTINGS_BACKUP_COUNT_DEFAULT = 10
SETTINGS_BACKUP_SPIN_WIDTH = 80
# カード表示タブ：見出し等のフォントサイズ(px)
SETTINGS_SECTION_LABEL_FONT_SIZE_PX = 11
# カード表示タブ：プレビュー外周の余白(px)（左右上下同じ）
SETTINGS_CARD_PREVIEW_OUTER_PAD = 16
# カード表示タブ：左右カラム間などの間隔(px)
SETTINGS_CARD_TAB_ROOT_SPACING = 24
SETTINGS_CARD_TAB_LEFT_SPACING = 16
SETTINGS_CARD_TAB_RIGHT_SPACING = 8

# properties/_utils.py: ボタンQSSの寸法（見た目維持のため直書き値を定数化）
PROP_ACTION_BTN_RADIUS = 4
PROP_ACTION_BTN_PADDING_Y = 6
PROP_ACTION_BTN_PADDING_X = 20
PROP_FETCH_BTN_PADDING_Y = 4
PROP_FETCH_BTN_PADDING_X = 8

# properties/meta_apply_dialog.py: レイアウト/寸法（見た目維持）
META_APPLY_LAYOUT_MARGINS = (16, 16, 16, 12)  # left, top, right, bottom
META_APPLY_LAYOUT_SPACING = 8
META_APPLY_FIELD_COL_WIDTH = 80
META_APPLY_VALUE_COL_WIDTH = 160
META_APPLY_ARROW_COL_WIDTH = 20
META_APPLY_TEXTEDIT_SIZE = (200, 48)  # tags/characters 用
META_APPLY_LINEEDIT_WIDTH = 200
# サムネ選択UI
META_APPLY_THUMB_SIZE = (80, 110)      # QLabel の固定サイズ
META_APPLY_THUMB_PIX_SIZE = (78, 108)  # QPixmap の表示サイズ

# properties/meta_apply_dialog.py: toggle/checkbox の寸法（見た目維持）
META_APPLY_TOGGLE_RADIUS = 3
META_APPLY_TOGGLE_PADDING_Y = 2
META_APPLY_TOGGLE_PADDING_X = 4
META_APPLY_CHECKBOX_INDICATOR_SIZE = 14
META_APPLY_CHECKBOX_INDICATOR_RADIUS = 2

# properties/rename_dialog.py: ウィンドウ寸法/レイアウト（見た目維持）
RENAME_DIALOG_SIZE = (420, 190)             # setFixedSize(w, h)
RENAME_DIALOG_MARGINS = (16, 16, 16, 16)    # left, top, right, bottom
RENAME_DIALOG_SPACING = 8

# ── ビューワー（viewer.py） ─────────────────────────────────
# 初期ウィンドウサイズ（最大化前の基準）
VIEWER_INIT_WIDTH = 900
VIEWER_INIT_HEIGHT = 700
# 上部ツールバー
VIEWER_TOOLBAR_HEIGHT = 36
VIEWER_TOOLBAR_MARGIN = (6, 4, 6, 4)  # left, top, right, bottom
VIEWER_TOOLBAR_SPACING = 4
VIEWER_TOOLBAR_BTN_HEIGHT = 26
VIEWER_TOOLBAR_BTN_PADDING_Y = 2
VIEWER_TOOLBAR_BTN_PADDING_X = 10
# 下部シークバー
VIEWER_SEEKBAR_HEIGHT = 32
VIEWER_SEEKBAR_MARGIN = (10, 4, 10, 4)  # left, top, right, bottom
VIEWER_SEEKBAR_LABEL_WIDTH = 80
# シークバーQSS寸法
VIEWER_SLIDER_GROOVE_H = 4
VIEWER_SLIDER_HANDLE_SIZE = 14  # width/height
VIEWER_SLIDER_HANDLE_RADIUS = 7
VIEWER_SLIDER_HANDLE_MARGIN_Y = -5

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

# filter_popover.py: 表示/フォーカス挙動のタイミング(ms)
FILTER_POPOVER_FOCUS_CHECK_DELAY_MS = 0     # focusOut 後にフォーカス状態を確認する遅延
FILTER_POPOVER_SHOW_SYNC_DELAY_MS = 50      # showEvent 後にボタン高さ同期する遅延
# filter_popover.py: 下部ボタンのQSS padding（上下, 左右）
FILTER_POPOVER_ACTION_BTN_PADDING_Y = 2
FILTER_POPOVER_ACTION_BTN_PADDING_X = 8

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

# ── ブックマークレット連携 ──────────────────────────
BOOKMARKLET_PORT: int = 8765

