# config.py - アプリ全体で共有する定数・設定の一元管理
# 全モジュールはここを参照し、マジックナンバーを排除する。
import os

from paths import APP_BASE, APP_DATA_DIR, CACHE_DIR, COVER_CACHE_DIR

# ── UIスタイル共通定数 ────────────────────────────────────
BORDER_RADIUS = 6        # ウィジェット共通の角丸半径(px)
BORDER_WIDTH  = 1       # ボーダー幅(px)

# ── アプリ名（全ウィンドウのタイトルに使用）─────────────────
APP_TITLE = "Noble Shelf"
STORE_FILE_NAMESPACE = "9f4a5f5f-52f1-4b13-9db0-9ad7b4df7f1a"

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
# ui/dialogs/bookmarklet_help_dialog.py（本文・ページ番号は同サイズ）
FONT_SIZE_BOOKMARKLET_HELP_TITLE = FONT_SIZE_XL   # ページ見出し（QFont）
FONT_SIZE_BOOKMARKLET_HELP_BODY  = FONT_SIZE_LG    # 本文・フッタ（QSS。旧: CONTEXT_MENU と同値）
FONT_SIZE_BTN_DEFAULT     = FONT_SIZE_DEFAULT   # 通常ボタン
FONT_SIZE_BTN_ACTION      = FONT_SIZE_MD        # 保存・キャンセル・取得等のアクションボタン（QSS）
FONT_SIZE_BTN_LARGE       = FONT_SIZE_LG        # 主要ボタン（より大きくしたい場合）
FONT_SIZE_BTN_STAR        = FONT_SIZE_XL        # 星評価ボタン（コンテキストメニュー等）
FONT_SIZE_RATING_UI       = FONT_SIZE_XL        # プロパティパネル内の星評価ボタン（QSS）
FONT_SIZE_SORT_LABEL      = FONT_SIZE_GHOSTBAR  # ゴーストバーのソートラベル
FONT_SIZE_SORT_BTN        = FONT_SIZE_DEFAULT   # ゴーストバーの昇順/降順ボタン
FONT_SIZE_SEARCH_INPUT    = FONT_SIZE_LG   # 検索バー入力欄（setFont用）
FONT_SIZE_SEARCHBAR       = FONT_SIZE_MD        # 検索バー入力欄（QSS font-size）
FONT_SIZE_SEARCHBAR_BTN   = FONT_SIZE_LG        # 検索バー検索ボタン用（現状はアイコンのみ・QSS 未使用）
FONT_SIZE_STATUS_BAR      = FONT_SIZE_DEFAULT   # ステータスバー
FONT_SIZE_VIEWER_UI       = FONT_SIZE_XS        # ビューワー：ツールバーボタン・ページラベル（QSS）
FONT_SIZE_VIEWER_SEEK     = FONT_SIZE_DEFAULT   # ビューワー：シークバーラベル（QSS）
FONT_SIZE_PROP_HINT       = FONT_SIZE_XS        # プロパティ・ダイアログの補助テキスト（QSS）
FONT_SIZE_CONTEXT_MENU    = FONT_SIZE_MD        # コンテキストメニュー（QSS）
FONT_SIZE_CONTEXT_MENU_SHORTCUT = FONT_SIZE_XS  # コンテキストメニュー右側ショートカット表示（QSS）
FONT_SIZE_STAR_UI         = FONT_SIZE_XL        # 星評価ボタン等（QSS）
FONT_SIZE_APP_GLOBAL      = FONT_SIZE_MD        # アプリ全体QSSのデフォルト（QWidget等）
FONT_SIZE_TOAST           = 13
# theme.py: APP_QSS 内 QComboBox::down-arrow（SVG）の幅・高さ(px)
APP_QSS_COMBO_DOWN_ARROW_SIZE_PX = 10



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
# sidebar.py: 履歴モードで表示する recent_books の最大件数
SIDEBAR_HISTORY_RECENT_LIMIT = 50
SEARCHBAR_HEIGHT       = 44
SEARCHBAR_MAX_WIDTH    = 600   # searchbar.py: 角丸カプセルの最大幅(px)
# searchbar.py: 角丸カプセルの最小幅(px)。未設定だと QLineEdit の min が小さく全体が極端に細くなる
SEARCHBAR_CAPSULE_MIN_WIDTH = 600
SEARCH_INPUT_MAX_WIDTH = 800   # 検索入力欄の最大幅(px)。検索バー幅はそのまま

# searchbar.py（検索バー）: レイアウト/寸法（見た目維持のため直書き値を定数化）
SEARCHBAR_OUTER_MARGINS = (8, 4, 8, 4)   # left, top, right, bottom
SEARCHBAR_CAPSULE_HEIGHT_INSET = 8       # SEARCHBAR_HEIGHT から引く値（上下余白合計）
SEARCHBAR_CAPSULE_RADIUS = 14            # 角丸半径(px)
SEARCHBAR_CAPSULE_BTN_WIDTH = 44         # 右側の検索ボタン幅(px)
# searchbar.py: 入力欄と検索ボタン間の縦区切り線の幅(px)。直線の「｜」に見せる
SEARCHBAR_BTN_DIVIDER_WIDTH = 1
# searchbar.py: 検索実行ボタンの QIcon 一辺(px)。ボタン高さより小さくして見切れを防ぐ
SEARCHBAR_SEARCH_BTN_ICON_SIZE = 20
SEARCHBAR_INPUT_PADDING_Y = 6
SEARCHBAR_INPUT_PADDING_X = 12
# searchbar.py: 入力→検索発火までの遅延(ms)（見た目/体感維持）
SEARCHBAR_DEBOUNCE_MS = 50

# app.py: メニューバー直下のメインツールバー（ハンバーガー・検索・グリッド）
MAIN_TOOLBAR_HEIGHT = SEARCHBAR_HEIGHT
# toolbar.py: 行の上下に空ける余白(px)。ボタン一辺 = 行高 - 2*この値（大きいとアイコン・ホバーが見切れにくい）
MAIN_TOOLBAR_BTN_VERTICAL_INSET = 4
# toolbar.py: ハンバーガー/グリッド QPushButton の正方形一辺(px)
MAIN_TOOLBAR_BTN_SIZE = MAIN_TOOLBAR_HEIGHT - 2 * MAIN_TOOLBAR_BTN_VERTICAL_INSET
MAIN_TOOLBAR_MARGINS = SEARCHBAR_OUTER_MARGINS
MAIN_TOOLBAR_SPACING = 4
# toolbar.py: setIconSize 用。MAIN_TOOLBAR_BTN_SIZE 以下を推奨（はみ出し・クリップ対策）
MAIN_TOOLBAR_ICON_SIZE = 26
# toolbar.py: ランダムボタン押下時の accent フラッシュ表示時間(ms)
MAIN_TOOLBAR_RANDOM_BTN_FLASH_MS = 200
# toolbar.py: 設定アイコンボタン（処理未接続時のツールチップ文言）
MAIN_TOOLBAR_SETTINGS_TOOLTIP = "設定（未接続）"
# menubar.py: 表示メニュー（グリッド上のソート帯の表示トグル）
VIEW_MENU_TITLE_BAR_LABEL = "タイトルバー"
# toolbar.py: title.png トグル（上記ソート帯）
MAIN_TOOLBAR_TITLE_BAR_TOGGLE_TOOLTIP = "タイトルバーを表示/非表示"

TOAST_DURATION_MS = 4000
TOAST_MARGIN_RIGHT = 16
TOAST_MARGIN_BOTTOM = 48
TOAST_BORDER_RADIUS = 6
TOAST_PADDING_X = 16
TOAST_PADDING_Y = 8

# メインウィンドウ・タイトルバー（app.py）
TITLE_BAR_DBLCLICK_HEIGHT = 50  # この高さ未満のダブルクリックで最大化

# ゴーストバー（ソートバー）（app.py）
SORT_BAR_BUTTON_HEIGHT = 32
SORT_BAR_MARGIN_LEFT = 16
SORT_BAR_MARGIN_RIGHT = 8
SORT_BAR_SPACING = 12

# ── カード・サムネイル（グリッド）────────────────────────────
# スライダー用の幅範囲（情報バーのカードサイズスライダーで使用）
SLIDER_MIN_WIDTH = 100
SLIDER_MAX_WIDTH = 800
DEFAULT_CARD_WIDTH = 220

CARD_SIZE_MIN = SLIDER_MIN_WIDTH
CARD_SIZE_MAX = SLIDER_MAX_WIDTH
CARD_SIZE_DEFAULT = DEFAULT_CARD_WIDTH

THUMB_WIDTH_BASE = 120
THUMB_HEIGHT_BASE = 170
# グリッド用サムネ PNG（thumb_cache）の外接ボックス。幅を基準にカードと同じ縦横比（grid/thumb.py）
THUMB_CACHE_WIDTH = 300
THUMB_CACHE_HEIGHT = int(THUMB_CACHE_WIDTH * THUMB_HEIGHT_BASE // THUMB_WIDTH_BASE)
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

# scanners/book_scanner.py: books.media_type 既定・スキャン時の誤削除抑止（分数閾値）
BOOKS_MEDIA_TYPE_DEFAULT = "book"
SCAN_STALE_DELETE_SKIP_FRACTION_NUMERATOR = 1
SCAN_STALE_DELETE_SKIP_FRACTION_DENOMINATOR = 2
# db.py: SQLiteロック競合時の待機時間（ms）
DB_BUSY_TIMEOUT_MS = 3000
# scanners/book_scanner.py: 進捗シグナル発火間隔（件）
SCAN_PROGRESS_EMIT_INTERVAL = 10
# scanners/book_scanner.py: 診断ログで path 一覧を省略する際の最大件数
SCAN_LOG_PATH_LIST_MAX = 40
# scanners/book_scanner.py: mtime比較の許容誤差（秒）
MTIME_TOLERANCE = 2.0
# scanners/book_scanner.py: Phase2 missing_map で content_hash が NULL の行を束ねるキー
SCAN_MISSING_HASH_MAP_KEY = "__NULL__"
# scanners/book_scanner.py: missing本を自動削除するまでの日数
MISSING_BOOK_TTL_DAYS = 30
# ui/widgets/menubar.py: 「見つからない本を表示...」OFF=通常グリッドでは非表示、ON=missing のみ表示
VIEW_MENU_MISSING_BOOKS_ACTION_LABEL = "見つからない本を表示..."
# ui/dialogs/missing_books_dialog.py: 行クリック／今すぐ削除の確認（{title}=作品タイトル）
MISSING_BOOKS_DIALOG_ROW_DELETE_TEXT_TEMPLATE = '"{title}" をライブラリから削除しますか？'
MISSING_BOOKS_DIALOG_ROW_DELETE_INFO = "この操作は取り消せません。"
MISSING_BOOKS_DIALOG_BTN_DELETE = "削除"
MISSING_BOOKS_DIALOG_BTN_CANCEL = "キャンセル"

# scanners/book_scanner.py: 作品フォルダ内の永続UUID（.noble-shelf-id）
NOBLE_SHELF_ID_FILENAME = ".noble-shelf-id"
NOBLE_SHELF_ID_TMP_SUFFIX = ".tmp"
# UUID v4 1行の検証用（小文字・ハイフン区切り）
NOBLE_SHELF_UUID_V4_REGEX = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
# 読み取りリトライ間隔（ms）: 指数バックオフ 100 → 300 → 1000
NOBLE_SHELF_ID_READ_BACKOFF_MS = (100, 300, 1000)
# 書き込みリトライ間隔（ms）: PermissionError 対策
NOBLE_SHELF_ID_WRITE_RETRY_DELAY_MS = [100, 100, 100]
# UUID重複（先勝ちで後から来たフォルダを振り直した）ときのトースト文面（{name}=フォルダ名）
SCAN_UUID_DUPLICATE_TOAST_TEMPLATE = "同一作品IDが重複したため、新しいIDに振り直しました: {name}"

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


def grid_card_total_height_for_width(card_width: int) -> int:
    """グリッドカード総高：正方形サムネ（一辺＝カード幅）＋ CARD_TEXT_HEIGHT_FIXED。"""
    return card_width + CARD_TEXT_HEIGHT_FIXED


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
BOOKMARKLET_THUMB_SIZE = (120, 180)
BOOKMARKLET_SCROLL_DELAY_MS = 100
BOOKMARKLET_SCROLL_RETRY_COUNT = 5
BOOKMARKLET_HTTP_TIMEOUT_SEC = 5
BOOKMARKLET_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
BOOKMARKLET_REFERER_DLSITE = "https://www.dlsite.com/"
# ui/bookmarklet_help_dialog.py: ブックマークレットヘルプ（ページ送り）
# フォントサイズは FONT_SIZE_BOOKMARKLET_HELP_*（セマンティック層）を参照
# ブラウザ登録ページのスクリーンショットが横長のため幅を確保
BOOKMARKLET_HELP_DIALOG_MIN_SIZE = (560, 380)
BOOKMARKLET_HELP_DIALOG_SIZE = (680, 560)
BOOKMARKLET_HELP_PAGE_TITLE_FONT_SIZE = FONT_SIZE_BOOKMARKLET_HELP_TITLE
BOOKMARKLET_HELP_FOOTER_SPACING = 8
# ヘルプ内スクリーンショットの最大表示幅（ダイアログ幅に合わせ縮小）
# ヘルプ内スクリーンショットの最大幅（大きすぎるとはみ出しやすいため 620 の約7割）
BOOKMARKLET_HELP_SCREENSHOT_MAX_WIDTH = 434

# statusbar.py: ステータスバーUI（見た目維持）
STATUSBAR_SLIDER_WIDTH = 120
STATUSBAR_LICENSE_MARGIN_X = 12
# app.py: スキャン進捗（QProgressBar + ラベル）
STATUSBAR_SCAN_PROGRESS_WIDTH = 140
STATUSBAR_SCAN_PROGRESS_HEIGHT = 16
STATUSBAR_SCAN_PROGRESS_SPACING = 8
STATUSBAR_SCAN_PROGRESS_BORDER_RADIUS = 2
# 表示例: 「スキャン中... 123/526」
SCAN_PROGRESS_LABEL_TEMPLATE = "スキャン中... {scanned}/{total}"

# thumbnail_crop_dialog.py: ダイアログ/ネットワーク/保存（見た目維持）
THUMB_CROP_DIALOG_MIN_SIZE = (640, 480)
THUMB_CROP_DIALOG_SIZE = (800, 600)
THUMB_CROP_LAYOUT_MARGINS = (12, 12, 12, 12)
THUMB_CROP_LAYOUT_SPACING = 8
THUMB_CROP_FIT_DELAY_MS = 50
THUMB_CROP_DOWNLOAD_TIMEOUT_SEC = 15
# library_check_dialog.py: ライブラリ整合性チェックダイアログ（見た目維持）
LIBRARY_CHECK_DIALOG_MIN_SIZE = (500, 280)
LIBRARY_CHECK_DIALOG_SIZE = (700, 520)
# JPEG保存品質（見た目/容量維持）
THUMB_CROP_JPEG_QUALITY = 90
# 切り抜きビュー：フィット時のスケール下限・上限（ホイールズームと整合）
THUMB_CROP_ZOOM_MIN = 0.05
THUMB_CROP_ZOOM_MAX = 0.50
# 切り抜きビュー：ホイール1ノッチあたりの拡大縮小倍率
THUMB_CROP_WHEEL_ZOOM_FACTOR = 1.05

# drop_handler.py: UI寸法・進捗（見た目維持）
DROP_FOLDER_DIALOG_SIZE = (360, 160)
DROP_ARCHIVE_DIALOG_SIZE = (400, 140)
DROP_DIALOG_SPACING = 12
DROP_DIALOG_BTN_HEIGHT = 32
DROP_ZIP_PROGRESS_RANGE = (0, 100)
DROP_ZIP_PROGRESS_MIN_DURATION_MS = 0
# app.py: スキャン中は D&D / 貼り付けを拒否するときのダイアログ文言
DROP_SCAN_BLOCKED_DIALOG_TITLE = "スキャン中"
DROP_SCAN_BLOCKED_DROP_MESSAGE = "スキャン完了後にもう一度ドロップしてください。"
DROP_SCAN_BLOCKED_PASTE_MESSAGE = "スキャン完了後にもう一度お試しください。"
# drop_handler.py: 解凍失敗ダイアログタイトル
DROP_EXTRACT_ERROR_DIALOG_TITLE = "解凍エラー"
# drop_handler.py: PDFカバー生成スケール（見た目維持）
PDF_COVER_SCALE = 1.5

# first_run.py: 初回起動オーバーレイ（見た目維持）
FIRST_RUN_SETUP_BTN_SIZE = (280, 80)
FIRST_RUN_SETUP_BTN_RADIUS = 16
FIRST_RUN_SETUP_BTN_PADDING = (8, 16)  # y, x
FIRST_RUN_SETUP_BTN_PRESSED_OPACITY = 0.9

# debug_tools.py: 初回起動オーバーレイ確認ダイアログ（見た目維持）
DEBUG_FIRST_RUN_DIALOG_TITLE = "初回起動オーバーレイ（デバッグ）"
DEBUG_FIRST_RUN_DIALOG_SIZE = (500, 300)
DEBUG_FIRST_RUN_DIALOG_MARGINS = (16, 16, 16, 16)

# library_folder_dialog.py: ライブラリフォルダ設定ダイアログ
LIBRARY_FOLDER_DIALOG_TITLE = "ライブラリフォルダを設定"
LIBRARY_FOLDER_DIALOG_SIZE = (500, 120)

# app.py: 最近開いたブックのポップアップ件数
RECENT_BOOKS_MENU_LIMIT = 10

# app.py: スプリッター初期幅（サイドバー）
MAIN_SPLITTER_SIDEBAR_INIT_WIDTH = 200
MAIN_SPLITTER_HANDLE_WIDTH = 1

# app.py: Ctrl+ホイールのカードサイズ変更ステップ
CARD_SIZE_WHEEL_STEP = 10

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

# app.py / PropertyDialog: プロパティ保存〜グリッド反映までの計測ログのプレフィックス
PROPERTY_SAVE_PERF_LOG_PREFIX = "[PERF] property_save"

# app.py: 最近開いたブックの表示上限（別用途）
RECENT_BOOKS_LIST_LIMIT = 100

# app.py: 進捗ダイアログ（PDFサムネ修復 / ふりがな一括取得）
PROGRESS_DIALOG_MIN_DURATION_MS = 0

# app.py: フォルダ型サムネイル修復（ツールメニュー・確認/完了ダイアログ）
THUMB_REPAIR_MENU_LABEL = "サムネイルを修復"
THUMB_REPAIR_DIALOG_TITLE = "サムネイルを修復"
THUMB_REPAIR_CONFIRM_DIALOG_SIZE = (560, 440)
THUMB_REPAIR_CONFIRM_LIST_MIN_HEIGHT_PX = 200
THUMB_REPAIR_CONFIRM_PROMPT_TEMPLATE = "{count}件のサムネイルを修復しますか？"
THUMB_REPAIR_NONE_MESSAGE = "修復が必要なフォルダ型の作品はありません。"
THUMB_REPAIR_PROGRESS_WINDOW_TITLE = "サムネイルを修復"
THUMB_REPAIR_PROGRESS_LABEL_PREFIX = "サムネイルを修復しています..."
THUMB_REPAIR_DONE_TEMPLATE = "{count}件修復しました。"
THUMB_REPAIR_RUN_BUTTON_LABEL = "実行"
THUMB_REPAIR_ERROR_FETCH_MESSAGE = "書籍情報の取得に失敗しました:\n{error}"

# app.py: 起動直後のライブラリ読み込みをスケジュールする遅延(ms)
APP_STARTUP_LOAD_DELAY_MS = 0

# 共通: 余白/間隔ゼロ指定（Qtレイアウトで頻出）
LAYOUT_MARGINS_ZERO = (0, 0, 0, 0)
LAYOUT_SPACING_ZERO = 0

# app.py: メイン中央レイアウトの水平セパレーター線の高さ(px)
SEPARATOR_LINE_HEIGHT = 1

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
SETTINGS_DIALOG_MIN_SIZE = (720, 560)       # setMinimumSize(w, h)
SETTINGS_DIALOG_DEFAULT_SIZE = (780, 650)   # resize(w, h)
# レイアウト（ダイアログ全体）
SETTINGS_DIALOG_MARGINS = (16, 16, 16, 16)  # left, top, right, bottom
SETTINGS_DIALOG_SPACING = 12
# 一般タブ：ビュアーパス入力（QLineEdit）の最低高さ(px)
SETTINGS_INPUT_MIN_HEIGHT = 28
# 下部の QDialogButtonBox（保存・キャンセル）ラベル
SETTINGS_DIALOG_BTN_SAVE_TEXT = "保存"
SETTINGS_DIALOG_BTN_CANCEL_TEXT = "キャンセル"
# 起動時ソート（settings_dialog.py / app.py、DB キーは定数のみ参照）
STARTUP_SORT_RESTORE_CHECKBOX_LABEL = "前回のソート状態を復元する"
STARTUP_SORT_COMBO_ROW_LABEL = "起動時ソート順:"
STARTUP_SORT_RESTORE_LAST_SETTING_KEY = "startup_sort_restore_last"
STARTUP_SORT_DEFAULT_KEY_SETTING_KEY = "startup_sort_default_key"
STARTUP_SORT_DEFAULT_KEY_FALLBACK = "added_date"
# 起動時「前回復元OFF」で DB に降順指定がないとき、これらのキーは既定で降順
SORT_KEYS_DEFAULT_DESC = {"added_date"}
SORT_LAST_KEY_SETTING_KEY = "sort_last_key"
SORT_LAST_DESC_SETTING_KEY = "sort_last_desc"
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
BACKUP_INTERVAL_SEC = 60 * 60 * 24  # 24時間
# バックアップファイル名・理由（db.py の命名・一覧と整合）
BACKUP_REASON_MANUAL = "manual"
BACKUP_REASON_LIB_CHANGE_BEFORE = "libchange_before"
BACKUP_REASON_LIB_CHANGE_AFTER = "libchange_after"
BACKUP_REASON_PRE_RESTORE = "pre_restore"
BACKUP_REASONS = frozenset(
    {
        BACKUP_REASON_MANUAL,
        BACKUP_REASON_LIB_CHANGE_BEFORE,
        BACKUP_REASON_LIB_CHANGE_AFTER,
        BACKUP_REASON_PRE_RESTORE,
    }
)
BACKUP_FILENAME_PATTERN = r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}-\d{3}_.+\.db$"
BACKUP_FILENAME_CAPTURE_PATTERN = (
    r"^(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}-\d{3})_(?P<reason>.+)\.db$"
)
BACKUP_DB_FILENAME_SUFFIX = ".db"
BACKUP_TIMESTAMP_FILENAME_DATE_TIME_FORMAT = "%Y-%m-%d_%H-%M-%S-"
BACKUP_MICROSECONDS_PER_MILLISECOND = 1000
BACKUP_TIMESTAMP_MILLISECOND_DIGITS = 3
BACKUP_SIZE_KIBIBYTES = 1024
# 一覧表示用（ファイル名 ts 部を人間向けに整形）
BACKUP_LIST_TS_DATE_TIME_SEPARATOR = "_"
BACKUP_LIST_TS_DATE_COMPONENT_SEP = "-"
BACKUP_LIST_DISPLAY_DATE_SEP = "/"
BACKUP_LIST_DISPLAY_DATE_TIME_GAP = " "
BACKUP_LIST_DISPLAY_TIME_COMPONENT_SEP = ":"
BACKUP_LIST_DISPLAY_MS_SEP = "."
BACKUP_LIST_EXPECTED_TIME_PARTS = 4  # HH, MM, SS, fff
# 復元ダイアログ: 日時と理由の区切り
BACKUP_RESTORE_DIALOG_REASON_OPEN = " ("
BACKUP_RESTORE_DIALOG_REASON_CLOSE = ")"
DB_BACKUP_DAILY_PATH = os.path.join(APP_DATA_DIR, "library_daily.db")
APP_LOCK_FILE_PATH = os.path.join(APP_DATA_DIR, "app.lock")
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

# duplicate_cover_dialog.py: サムネ比較表示
DUPLICATE_COVER_THUMB_SIZE = (160, 220)  # サムネ表示サイズ (w, h)
DUPLICATE_COVER_THUMB_SPACING = 24  # サムネ間のスペーシング
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
# DBキー・綴じ方向（settings_dialog と viewer で共有。未設定時は右綴じ＝右→左）
VIEWER_DIRECTION_SETTING_KEY = "viewer_direction"
VIEWER_DIRECTION_DEFAULT = "rtl"
VIEWER_DIRECTION_DATA_RTL = "rtl"
VIEWER_DIRECTION_DATA_LTR = "ltr"
# 初期ウィンドウサイズ（最大化前の基準）
VIEWER_INIT_WIDTH = 900
VIEWER_INIT_HEIGHT = 700
# PageCanvas: この倍率を超えたらフル解像度 pixmap で描画（以下は縮小済み pixmap）
VIEWER_CANVAS_ZOOM_BASE = 1.0
# PageCanvas: ウィジェット中心座標（幅・高さをこの値で割る）
VIEWER_CANVAS_WIDGET_CENTER_DIVISOR = 2
# 1P 時フル解像度先読み: 現在ページから ± このページ数（2P は original 未使用のため _schedule_original_loads は no-op）
VIEWER_ORIGINAL_PRELOAD_RADIUS_1P = 1
# 上部ツールバー
VIEWER_TOOLBAR_HEIGHT = 36
VIEWER_TOOLBAR_MARGIN = (6, 4, 6, 4)  # left, top, right, bottom
VIEWER_TOOLBAR_SPACING = 4
VIEWER_TOOLBAR_BTN_HEIGHT = 26
VIEWER_TOOLBAR_BTN_BORDER_RADIUS = 4
VIEWER_TOOLBAR_ICON_SIZE = 22
VIEWER_TOOLBAR_BTN_PADDING_Y = 2
VIEWER_TOOLBAR_BTN_PADDING_X = 10
VIEWER_TOOLTIP_2P_MODE = "2ページ表示"
VIEWER_TOOLTIP_PAGE_OFFSET = "ページをずらす"
# 2P時「1ページ送り」ボタンで進めるインデックス量
VIEWER_SINGLE_PAGE_STEP = 1
# 下部シークバー
VIEWER_SEEKBAR_HEIGHT = 32
VIEWER_SEEKBAR_MARGIN = (10, 4, 10, 4)  # left, top, right, bottom
VIEWER_SEEKBAR_LABEL_WIDTH = 80
# シークバーQSS寸法
VIEWER_SLIDER_GROOVE_H = 4
VIEWER_SLIDER_HANDLE_SIZE = 14  # width/height
VIEWER_SLIDER_HANDLE_RADIUS = 7
VIEWER_SLIDER_HANDLE_MARGIN_Y = -5
# サムネイルストリップ（viewer.py）
VIEWER_THUMB_STRIP_SIZE = (80, 80)
VIEWER_THUMB_STRIP_HEIGHT = 116
VIEWER_THUMB_STRIP_PAGE_LABEL_HEIGHT = 16
VIEWER_THUMB_STRIP_PAGE_LABEL_FONT_SIZE = 10
VIEWER_THUMB_STRIP_SETTING_KEY = "viewer_thumb_strip_visible"
VIEWER_THUMB_STRIP_CELL_SPACING = 4
VIEWER_THUMB_STRIP_BORDER_WIDTH = 3
VIEWER_THUMB_STRIP_INNER_MARGIN = 2
VIEWER_THUMB_STRIP_TOOLBAR_ICON_SIZE = 22
VIEWER_THUMB_STRIP_SCROLL_ENSURE_MARGIN = 24
VIEWER_THUMB_STRIP_BORDER_RADIUS = 4
VIEWER_THUMB_STRIP_PLACEHOLDER_BORDER_RADIUS = 2
VIEWER_THUMB_STRIP_ENSURE_PAGE_RADIUS = 5
# ストリップ上ホイール: angleDelta.y の刻み（通常 120＝1ノッチ）
VIEWER_THUMB_STRIP_WHEEL_ANGLE_PER_NOTCH = 120
# ストリップ上ホイール1ノッチあたりの横スクロール量（px）
VIEWER_THUMB_STRIP_WHEEL_HSCROLL_STEP = 64
# 全画面サムネイルオーバーレイ（viewer.py ThumbnailOverlay）
VIEWER_OVERLAY_THUMB_SIZE = (160, 160)
VIEWER_OVERLAY_THUMB_LOW_SIZE = (80, 80)
VIEWER_OVERLAY_THUMB_GAP = 8
VIEWER_OVERLAY_BG_ALPHA = 192
VIEWER_OVERLAY_PREVIEW_DEBOUNCE_MS = 80
VIEWER_OVERLAY_SCROLL_THROTTLE_MS = 32
VIEWER_OVERLAY_PRELOAD_ROWS = 2
VIEWER_OVERLAY_WHEEL_DIVISOR = 2
VIEWER_OVERLAY_FADE_IN_MS = 150
VIEWER_OVERLAY_FADE_OUT_MS = 100
VIEWER_OVERLAY_BORDER_WIDTH = 2
VIEWER_OVERLAY_PAGE_NUM_FONT_SIZE = 11
VIEWER_OVERLAY_SCHEDULE_BATCH = 12
# ThumbnailOverlay 用 QThreadPool の同時ワーカー上限
VIEWER_OVERLAY_POOL_MAX_THREADS = 4
DRAG_THRESHOLD_PX = 6

# （旧）起動直後スキャンでストアダイアログを抑止する時間(秒)。app.py は _is_startup_scan で管理。
INITIAL_SCAN_SUPPRESS_DIALOG_SEC = 30.0
# app.py: スキャン失敗時にグリッド上部へ表示する小ラベル
SCAN_STALE_FLAG_TEXT = "古いデータを表示中"
# app.py: ステータスバー簡易トースト表示時間(ms)
SCAN_TOAST_DURATION_MS = 4000

# ── フィルターポップオーバー（ツールバーから開く右パネル）──────────────
# filter_popover.py: 即時反映パネルのヘッダー・コンボ先頭項目
FILTER_PANEL_TITLE = "フィルター"
FILTER_PANEL_NONE_LABEL = "指定なし"
# 条件行コンボ横の「×」ラベル（ヘッダ閉じるボタン廃止後も行削除で使用）
FILTER_PANEL_CLOSE_SYMBOL = "×"
# filter_popover.py: 条件行コンボ横の「×」（1件だけ削除）ツールチップ
FILTER_POPOVER_COMBO_CLEAR_TOOLTIP = "この条件を削除"
# filter_popover.py: 条件の結合（項目間 AND / OR）トグルラベル
FILTER_POPOVER_LOGIC_AND_LABEL = "すべて一致"
FILTER_POPOVER_LOGIC_OR_LABEL = "どれか一致"
# filter_popover.py: パネル下部の条件一括クリアボタンラベル
FILTER_POPOVER_CLEAR_LABEL = "クリア"

FILTER_POPOVER_WIDTH = 320        # ポップオーバー幅(px)
BOOKMARKLET_PANEL_WIDTH = FILTER_POPOVER_WIDTH
BOOKMARKLET_DETAIL_HEIGHT = 220
FILTER_POPOVER_ROW_HEIGHT = 26    # 1行の高さ(px)。コンボ・入力欄・追加/クリアボタンの基準（表示時は左コンボに同期）
FILTER_POPOVER_LIST_HEIGHT = 120   # 条件リストの高さ(px)
FILTER_POPOVER_MARGINS = 8         # レイアウト余白(px)
FILTER_POPOVER_SPACING = 6        # レイアウト間隔(px)
# filter_popover.py: 作者/サークル等のセクション（見出し〜コンボ群）同士の余白(px)
FILTER_POPOVER_SECTION_SPACING = 12
# filter_popover.py: QComboBox QSS の上下 padding（文字・枠の見切れ防止）
FILTER_POPOVER_COMBO_PADDING_Y = 3
# filter_popover.py: QComboBox 外観の高さ(px)。QSS min-height・setMinimumHeight・行の×ボタンと一致
FILTER_POPOVER_COMBO_OUTER_HEIGHT = (
    FILTER_POPOVER_ROW_HEIGHT + 2 * FILTER_POPOVER_COMBO_PADDING_Y
)
# filter_popover.py: QComboBox テキスト左右余白(px)。狭い FILTER_POPOVER_WIDTH 向け
FILTER_POPOVER_COMBO_PADDING_LEFT = 6
FILTER_POPOVER_COMBO_PADDING_RIGHT = 4
# filter_popover.py: QComboBox 右端▼領域の幅(px)（高さと同じにするとテキストが狭く途切れやすい）
FILTER_POPOVER_COMBO_DROPDOWN_WIDTH = 22
# filter_popover.py: QComboBox 最小幅の目安文字数（候補が長くても横に暴れない）
FILTER_POPOVER_COMBO_MIN_VISIBLE_CHARS = 12
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
# filter_popover.py: 下部 AND/OR トグルボタンの高さ(px)
FILTER_POPOVER_LOGIC_TOGGLE_HEIGHT = 32

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

