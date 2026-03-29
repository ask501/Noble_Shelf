**公式サイト（紹介・更新履歴など）:** [Noble Shelf - ローカル同人誌ライブラリ管理ツール](https://ask501.github.io/Noble_Shelf/)

# Noble Shelf

**ローカルの同人誌・電子書籍を、フォルダのまま整理・閲覧・管理できる Windows 向けデスクトップライブラリです。**

**想定している人:** 作品をフォルダや ZIP / PDF で持っていて、**専用の整理用 DB に取り込みたくない**／**DMM・DLSite などのストアファイルも同じ棚で管理したい**／**ブラウザで見た情報を作品に反映したい**、というローカル中心の読者・コレクター向けです。

### ひとことで言うと（価値の芯）

- **フォルダをそのままライブラリの根にできる**（無理な再配置や独自形式への囲い込みをしない）
- **ZIP / PDF・画像フォルダを内置ビューワーで読める**（一覧からそのまま開く）
- **ブックマークレットやプラグイン経由でメタデータを取り込み、作品に適用できる**（ストア併用の「情報の橋」）

この三つを **ひとつの UI と DB** にまとめているのが、このアプリの強みです。

### スクリーンショット

この手のツールは **見た目で伝わる部分が大きい**です。

**ダミーモード（デバッグメニュー）** … 作品名・サムネ・タグ行・サイドバー（タグ／サークル）などをプレースホルダーに差し替え、**スクショ公開時に実データを隠す**ための表示です（DB やファイルは変更しません）。

![ダミーモード有効時のメイン画面（プレースホルダー表示）](docs/screenshots/dummy_mode.png)

その他の画面例は [公式サイト](https://ask501.github.io/Noble_Shelf/) の掲載も参照してください。

### Quick Start（とりあえず使う）

1. **入手** … リポジトリを clone するか、[Releases](https://github.com/ask501/Noble_Shelf/releases) の配布物を展開する（配布がある場合）。
2. **起動** … 開発時は `python launcher.py`（更新確認あり）または `python main.py`。
3. **ライブラリフォルダ** … メニュー **「ファイル」→「ライブラリフォルダを設定」** で、同人・電子書籍を置いているフォルダを指定する。
4. **待つ** … スキャン後、グリッドに並ぶ。作品を選んで内置ビューワーやプロパティを開く。

依存パッケージ・exe 化・トラブル時は下の **[使い方](#使い方)** を参照。

---

**技術メモ:** Python 3.14 想定、GUI は PySide6。ライブラリフォルダ配下をスキャンし、サムネ付きグリッド・検索・フィルター・評価・プロパティ編集・内置ビューワー・ストアファイル連携・DB バックアップなどを一体で提供します。

---

## 主な機能

- **ライブラリ管理** … 1 フォルダをライブラリとして登録し、サブフォルダ・アーカイブ・PDF・ストアファイルをスキャンして SQLite（`library.db`）に登録
- **グリッド表示** … サムネイル・作品名・サークル名・ページ数（または DMM / DLSite バッジ）をカード表示（`grid/`：モデル・ビュー・デリゲート・非同期サムネ）
- **検索 / ソート / フィルター** … テキスト検索、複合条件のフィルター（`filter_popover.py`）、ソート
- **内置ビューワー**（`ui/dialogs/viewer/` パッケージ）  
  - **1P / 2P**：2 ページ表示はツールバーのトグル＋アイコン（`2_page.svg`）。左綴じ / 右綴じ（設定）に応じた見開きの左右割り当て  
  - **1 ページ送り**：ツールバーボタン（`next_page.svg`）で現在インデックスを 1 ページ進める（1P / 2P 共通で表示）  
  - **サムネイルストリップ**：表示 ON/OFF を DB に保存。セルにページ番号と読み込み前プレースホルダー、横スクロール・ホイール操作  
  - **全画面サムネイルオーバーレイ**：グリッド表示のトグル（`overlay_grid.svg`）  
  - シークバー（綴じ方向に応じた見た目）、全画面、キャンバスクリック・キーボードでのページ送り、PDF / アーカイブ / 画像フォルダの読み込み（`BookReader` 系）
- **ストアファイル** … DMM（`.dmmb`, `.dmme`, `.dmmr`）・DLSite（`.dlst`）は専用ビュアー起動（`context_menu/_utils.py` 等で解決）
- **カバー画像** … `cover_paths.py` とキャッシュ連携で表紙パスを扱う
- **プロパティ編集** … `ui/dialogs/properties/`（タイトル / サークル、カバー、名前変更、メタ検索・適用 等）
- **コンテキストメニュー** … `context_menu/`（開く・プロパティ・削除・除外・ブックマーク 等）
- **プラグイン** … `plugin_loader.py` で有効 / 無効。メタデータ取得系 UI は有効時のみ
- **ドラッグ＆ドロップ** … `drop_handler.py` でフォルダ・アーカイブ・PDF 等の取り込み
- **DB バックアップ / 復元** … `db.py`・設定タブ（`ui/dialogs/settings/tab_backup.py`）
- **自動アップデート** … `launcher.py` → `updater.py`（GitHub Releases）
- **ブックマークレット** … `local_server.py`・`bookmarklet/`・`bookmarklet_window.py` でブラウザからメタ送信
- **補助ダイアログ** … 初回起動（`first_run.py`）、ライブラリフォルダ、重複カバー、欠損作品、ライブラリ整理・確認 等（`library_*_dialog.py`, `missing_books_dialog.py`, `duplicate_cover_dialog.py`, `library_checker.py` 等）

---

## 対応形式（概要）

| 種別 | 拡張子 | 備考 |
|------|--------|------|
| **アーカイブ（内置ビューワー・ページ数）** | `.zip`, `.cbz`, `.7z`, `.cb7`, `.rar`, `.cbr` | 内包画像でページ数カウント。画像拡張子は `config` 定義に準拠 |
| **PDF** | `.pdf` | 内置ビューワー。表紙は `cover_cache` にキャッシュ |
| **フォルダ** | （フォルダ単位） | 画像フォルダまたは PDF 1 本入りフォルダとして登録 |
| **DMM ストア** | `.dmmb`, `.dmme`, `.dmmr` | 専用ビュアー起動 |
| **DLSite ストア** | `.dlst` | 専用ビュアー起動 |

詳細な拡張子・解像度・UI 定数は `config.py` を参照してください。

---

## プロジェクト構成（主要ファイル）

```
（リポジトリルート）/
├── launcher.py              # 起動：クリーンアップ → 更新確認 → main.main()
├── main.py                  # QApplication・フォント・テーマ・MainWindow 表示のみ
├── app.py                   # メインウィンドウ。レイアウト・スキャン・D&D・シグナル統合
├── version.py               # アプリバージョン
├── config.py                # 定数（フォント、ビューア UI、グリッド、拡張子 等）
├── paths.py                 # APP_BASE、DB、キャッシュ、プラグイン、アイコン SVG パス
├── theme.py                 # QSS・カラー定数・ダークタイトルバー補助
├── db.py                    # SQLite・マイグレーション・バックアップ
├── cover_paths.py           # カバー画像パス解決
├── book_updater.py          # 作品名・メタ更新の共通処理
├── store_file_resolver.py   # ストアファイルの重複・リネーム判定
├── drop_handler.py          # D&D 登録
├── cache.py                 # キャッシュ補助
├── debug_tools.py           # 開発用
├── updater.py               # GitHub Releases 更新
├── local_server.py          # ブックマークレット用 HTTP（127.0.0.1）
├── plugin_loader.py         # プラグイン読み込み・有効フラグ
├── scanners/                # scan_library()、book スキャン（`book_scanner.py` 等）
├── grid/                    # グリッド（view / model / delegate / thumb / roles）
├── context_menu/            # 右クリックメニュー・アクション分割
├── bookmarklet/             # JS・サイト別パーサ（DLsite / FANZA / BOOTH / 同人DB）
├── ui/
│   ├── widgets/             # メニューバー、ツールバー、サイドバー、検索バー、ステータスバー、トースト
│   ├── dialogs/
│   │   ├── viewer/          # 内置ビューワー（Viewer・キャンバス・オーバーレイ・ストリップ・Reader）
│   │   ├── properties/      # プロパティ・リネーム・メタ検索 / 適用
│   │   ├── settings/        # 設定タブ（一般・ショートカット・バックアップ・カード）
│   │   ├── filter_popover.py
│   │   ├── bookmarklet_window.py / bookmarklet_help_dialog.py
│   │   ├── library_folder_dialog.py / first_run.py
│   │   ├── duplicate_cover_dialog.py / missing_books_dialog.py
│   │   ├── library_organize_dialog.py / library_init_confirm_dialog.py
│   │   ├── library_check_dialog.py / library_checker.py
│   │   └── thumbnail_crop_dialog.py
│   └── utils/               # 自動スクロール等
├── tests/                   # スキャナ・リゾルバ等のテスト
├── scripts/                 # 例: fix_uuid_mismatch.py
├── assets/                  # アイコン・バッジ・ビューア用 SVG（paths.py の定数と対応）
└── docs/                    # ドキュメント用静的ファイル

ユーザーデータ（既定）: %APPDATA%\NobleShelf\
├── library.db
├── backups/
├── thumb_cache/ / cover_cache/
└── plugins/
```

※ 旧単体 `viewer.py` は `viewer_old.py` / `viewer.py.bak` として参照用に残っている場合があります。実行時は `from ui.dialogs.viewer import Viewer`（パッケージ）を使用します。

---

## プラグイン

- **配置先**: **`%APPDATA%\NobleShelf\plugins\`** 直下の各サブフォルダ（`__init__.py` を持つものが 1 プラグイン）。メニュー「プラグイン → プラグインフォルダを開く」から開けます。配布 Zip にプラグインは同梱しません。
- **契約**（`__init__.py` で export）: モジュール直下または `get_plugin()` の戻り値に  
  `PLUGIN_NAME`, `PLUGIN_SOURCE_KEY`, `search_sync`, `get_metadata_sync` を定義。  
  任意: `can_handle(...)`, `get_property_buttons(context)` 等。
- **有効 / 無効**: 設定キー `plugin_enabled_<PLUGIN_SOURCE_KEY>` を DB の `settings` に `"1"` / `"0"` で保存。未設定は有効扱い。
- **API**:  
  - **`get_plugins()`** … 有効なプラグインのみ。検索・メタ取得・コンテキスト・プロパティの取得系 UI はここ経由。  
  - **`get_all_plugins()`** … 有効無効を問わず一覧。メニュー「プラグイン」の ON/OFF 表示用。

---

## 使い方

### 要件

- **OS**: Windows（ダークタイトルバー等）
- **Python**: 3.14 想定で開発
- **依存**: `PySide6`, `PyMuPDF`（`fitz`）, `Pillow`, `py7zr`, `rarfile`, `beautifulsoup4`, `Send2Trash` 等（`requirements.txt` が無い場合は個別 `pip install`）

### 起動

- **`python launcher.py`（推奨）** … クリーンアップと更新確認あり。
- **`python main.py`** … メインウィンドウのみ。

初回はライブラリフォルダ未設定の場合、オーバーレイやダイアログからフォルダを指定してスキャンします。

### メンテナンス

- `python scripts/fix_uuid_mismatch.py` … `.noble-shelf-id` と DB の UUID 不整合の修復（対話確認）。

### exe 化

- `BUILD.bat` は PyInstaller で `launcher.py` をエントリにする例。`assets` は `--add-data` で同梱想定。

---

## ブックマークレット連携

ブラウザの作品ページから、ローカルサーバー（既定 `http://127.0.0.1:8765`）経由でメタデータを送信し、ライブラリの既存作品に適用できます。

> 表示中の HTML をローカルで解析する用途です。各サイトの利用規約に従ってください。

### 対応サイト（パーサ実装）

- DLsite、FANZA（DMM ブックス）、BOOTH、同人 DB（doujinshi.org）

### 手順の概要

1. アプリ起動後、**「ツール」→「ブックマークレットキュー」** を開く。  
2. **「ブックマークレットをコピー」** で JS をクリップボードにコピーし、ブラウザのブックマーク URL に貼り付け。  
3. 対応サイトでブックマークレット実行 → キューに追加 → 「ライブラリで探す」「メタデータを適用」等。

### ライブラリフォルダ

**「ファイル」→「ライブラリフォルダを設定」** でフォルダを選ぶとスキャンが走ります。**「ライブラリを開く」** でエクスプローラーから開けます。

---

## サードパーティ / 依存ライブラリ

| 名前 | 用途 | ライセンス |
|------|------|------------|
| [PySide6](https://doc.qt.io/qtforpython/) | GUI | LGPL 等 |
| Python | 実行環境 | PSF License |

その他 PyMuPDF、Pillow、py7zr、rarfile、Beautiful Soup、Send2Trash 等。各パッケージの表記に従います。

---

## ライセンス

本リポジトリのコードは **MIT License** です。Copyright (c) 2026 ask501。  
全文は [LICENSE](LICENSE) を参照してください。
