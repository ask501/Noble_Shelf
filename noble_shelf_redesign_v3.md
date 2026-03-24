# Noble Shelf — DB・パス管理 再設計ドキュメント v3

作成日：2026-03-23  
対象バージョン：v0.3.3以降（リビルド前提）  
既存ユーザー：ゼロ（マイグレーション互換性不要）

---

## 1. 背景と問題点

### 1-1. 現状の構造

Noble Shelfは同人誌ライブラリ管理ソフト（PySide6/Qt、Windows向け）。  
DBはSQLite単一ファイル（`%APPDATA%\NobleShelf\library.db`）。

現在の`books`テーブルのPRIMARY KEYは`path`（絶対パス）：

```sql
CREATE TABLE books (
    path        TEXT PRIMARY KEY,  -- 例: C:\Users\User\Documents\NobleShelf\作品A
    name        TEXT NOT NULL,
    circle      TEXT NOT NULL,
    title       TEXT NOT NULL,
    cover_path  TEXT,
    mtime       REAL,
    updated_at  TEXT DEFAULT (datetime('now','localtime')),
    cover_custom TEXT,
    is_dlst     INTEGER DEFAULT 0,
    media_type  TEXT NOT NULL DEFAULT 'book'
)
```

`book_meta`テーブルも同じく`path`をPKとして`books`と論理参照（FK制約なし）。

### 1-2. 問題点

| 問題 | 原因 | 症状 |
|------|------|------|
| フォルダ移動でメタ消滅 | 絶対パスがPK | スキャン時に別レコードとして新規登録される |
| フォルダリネームでメタ消滅 | 同上 | 同上 |
| ライブラリ移動で全滅 | 同上 | 全作品が新規登録扱いになる |

根本原因：**フォルダのアイデンティティを絶対パスで管理している**こと。

---

## 2. 新設計の方針

### 2-1. UUIDファイル方式

各作品フォルダ内に`.noble-shelf-id`という隠しファイルを置き、UUID v4を1行書き込む。  
DBのPKをこのUUIDに変更する。

```
ライブラリフォルダ/
    作品A/
        .noble-shelf-id   ← "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
        001.jpg
    作品B/
        .noble-shelf-id   ← "7c9e6679-7425-40de-944b-e07fc1f90ae7"
        001.jpg
```

#### スキャン時のフロー

```
作品フォルダを走査
│
├─ .noble-shelf-id あり
│    └─ ファイル読み取り試行
│         └─ IOエラー（ロック等）
│              → 指数バックオフで3回リトライ（100ms→300ms→1s）
│              → 3回失敗 → スキップ＋ログ記録（破損扱いにしない）
│         └─ 読み取り成功
│              └─ UUID正規表現チェック
│                   └─ 不正（空・BOM・ゴミ）→ 破損扱い → 修復ダイアログ表示
│                   └─ 正常
│                        └─ DBに該当UUIDのレコードあり
│                             └─ DB上のpathと現在のpathが一致 → 通常更新
│                             └─ DB上のpathと現在のpathが不一致
│                                  └─ 別フォルダに同一UUIDが存在するか確認
│                                       └─ 存在する（UUID重複・コピー等）
│                                            → 後から来た方に新UUID振り直し＋新規登録
│                                            → トースト通知＋ログ記録
│                                       └─ 存在しない（移動/リネーム）
│                                            → pathを現在のパスに更新、メタ保持
│                        └─ DBに該当UUIDのレコードなし → 新規登録
│
└─ .noble-shelf-id なし
     └─ uuid4()で新規生成 → 原子書き込み（tmp→rename） → 新規登録
```

#### UUID重複ポリシー（確定）

**先勝ち**。同一UUIDを持つフォルダが複数存在した場合、DBに先に登録されている方を正とし、後からスキャンされた方に新しいUUIDを振り直して新規登録する。  
ユーザーへの通知：トースト1件＋ログ記録（サイレントに壊れない）。

#### IDファイルの読み取り仕様

- UUID正規表現チェック必須：`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`
- **IOエラー**（ロック・権限・一時的エラー）：指数バックオフ3回リトライ後スキップ＋ログ。破損扱いにしない。
- **フォーマット破損**（空ファイル・BOM付き・ゴミデータ）：修復ダイアログを表示。自動生成は最後の手段。

#### IDファイルの書き込み仕様（原子書き込み）

```python
import uuid, os

def write_id_file(folder_path: str) -> str:
    uid = str(uuid.uuid4())
    id_file = os.path.join(folder_path, ".noble-shelf-id")
    tmp_file = id_file + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        f.write(uid)
    os.replace(tmp_file, id_file)  # 原子的にリネーム（強制終了時の空ファイル化を防ぐ）
    return uid
```

### 2-2. 相対パス化

DBの`path`カラムはライブラリルート基準の相対パスで保存する。  
ライブラリルートは`settings`テーブルの`library_folder`キーで管理。

```python
# db.py内に実装する変換関数

def _get_library_root() -> str:
    return get_setting("library_folder") or ""

def _to_db_path(abs_path: str) -> str:
    """絶対パス → 相対パス（DB保存用）"""
    root = _get_library_root()
    if not root:
        raise ValueError("ライブラリルートが未設定です")
    return os.path.normpath(os.path.relpath(abs_path, root))

def _from_db_path(rel_path: str) -> str:
    """相対パス → 絶対パス（UI/ファイルアクセス用）"""
    root = _get_library_root()
    if not root:
        raise ValueError("ライブラリルートが未設定です")
    return os.path.normpath(os.path.join(root, rel_path))
```

**注意：ルート未設定時はサイレントに空文字を返さず、必ず例外をスローする。**

#### `library_folder`変更時の挙動

- 変更後の初回スキャン完了までグリッド表示をブロック
- スキャン完了後にUUID照合でpathが自動更新される
- スキャン前のパス参照は行わない

#### パス正規化ルール

- DB保存時・読み出し時ともに`os.path.normpath`で`\`/`/`混在を吸収
- パス比較は必ず`normpath`後に行う

### 2-3. UNIQUE違反時の挙動

`books.path`にUNIQUE制約を設けるため、スキャン時に同一相対パスが重複した場合：

- 後から来た方をスキップ
- スキャン完了後に件数をまとめてトースト表示（例：「3件の重複をスキップしました」）
- ログに詳細を記録

### 2-4. スキャン失敗時の挙動

スキャンが途中で失敗した場合：

- 前回のグリッド表示状態を維持する
- グリッド上部に「古いデータを表示中」フラグを小さく表示
- エラー内容をトーストで通知
- ユーザーが「古いデータです」フラグを見て再スキャンを判断できる状態にする

---

## 3. 新しいDBスキーマ

### 3-1. `books`テーブル

```sql
CREATE TABLE books (
    uuid         TEXT PRIMARY KEY,
    path         TEXT NOT NULL UNIQUE,          -- ライブラリルートからの相対パス（重複禁止）
    name         TEXT NOT NULL,
    circle       TEXT NOT NULL,
    title        TEXT NOT NULL,
    cover_path   TEXT,                          -- 相対パス or NULL
    mtime        REAL,                          -- 将来的に整合性検証に使用する可能性あり
    updated_at   TEXT DEFAULT (datetime('now','localtime')),
    cover_custom TEXT,
    is_dlst      INTEGER DEFAULT 0,
    media_type   TEXT NOT NULL DEFAULT 'book'
)
```

### 3-2. `book_meta`テーブル

```sql
CREATE TABLE book_meta (
    uuid         TEXT PRIMARY KEY,
    author       TEXT DEFAULT '',
    type         TEXT DEFAULT '',
    series       TEXT DEFAULT '',
    dlsite_id    TEXT DEFAULT '',
    excluded     INTEGER DEFAULT 0,
    updated_at   TEXT DEFAULT (datetime('now','localtime')),
    title_kana   TEXT DEFAULT '',
    circle_kana  TEXT DEFAULT '',
    pages        INTEGER,
    release_date TEXT DEFAULT '',
    price        INTEGER,
    memo         TEXT DEFAULT '',
    meta_source  TEXT DEFAULT '',
    store_url    TEXT DEFAULT '',
    FOREIGN KEY (uuid) REFERENCES books(uuid) ON DELETE CASCADE
)
```

- PKを`path`から`uuid`に変更
- FK制約 + ON DELETE CASCADEで孤児レコードを自動削除
- 孤児レコードの手動削除ロジックは不要（FK CASCADEに任せる。余計な削除ロジックはバグ源）

### 3-3. その他テーブル

`book_tags`・`book_characters`も同様に`path` → `uuid`に変更し、FK制約を追加する。

### 3-4. FK制約の有効化

SQLiteはデフォルトでFK制約が無効。接続時に必ず有効化する：

```python
conn.execute("PRAGMA foreign_keys = ON")
```

### 3-5. JOINの例

```sql
-- メタ付きで一覧（メタが無い作品も出す）
SELECT b.*, m.author, m.store_url
FROM books b
LEFT JOIN book_meta m ON b.uuid = m.uuid;
```

---

## 4. マイグレーション方針

**既存データは捨てる。**（既存ユーザーゼロのため互換性不要）

#### 初回起動時の処理

1. 旧DBが存在する場合、`%APPDATA%\NobleShelf\backups\`にタイムスタンプ付きでバックアップ保存
2. 確認ダイアログを表示：
   ```
   ライブラリデータベースを初期化します。

   ・登録済みの作品情報（タイトル・サークル・メモ等）はすべて削除されます
   ・作品ファイル自体は削除されません
   ・バックアップ保存先: %APPDATA%\NobleShelf\backups\library_YYYYMMDD_HHMMSS.db

   初期化してもよいですか？
   ```
3. 新スキーマでDBを再作成
4. ライブラリフォルダをスキャンして全作品を再登録
5. 各作品フォルダに`.noble-shelf-id`を生成（原子書き込み）

---

## 5. 実装順序

| ステップ | 対象ファイル | 内容 |
|---------|-------------|------|
| 1 | `db.py` | 新スキーマ定義・FK有効化・`_to_db_path`/`_from_db_path`（例外付き）・UUID検索/更新API |
| 2 | `scanners/book_scanner.py` | 原子書き込み・UUID読み取り（正規表現チェック）・IOエラーと破損の分離・リトライ（指数バックオフ）・重複検出（先勝ち）・トースト通知 |
| 3 | `app.py` | スキャン失敗時の前回グリッド維持・「古いデータです」フラグ・`_from_db_path`例外ハンドリング |
| 4 | `grid/`・`properties/`等 | pathを直接使っている箇所を`_from_db_path`経由に修正 |
| 5 | 動作確認 | フォルダ移動・リネーム後スキャンでメタ保持確認・UUID重複（コピー）時の先勝ち動作確認・スキャン失敗時の前回維持確認 |

---

## 6. 設計上の制約・非サポート事項

- 複数PC間の同期：非サポート（シングルPC前提）
- Zipファイル直読み（フォルダなし）：非サポート（将来検討）
- マルチライブラリ：現バージョンでは非実装

---

## 7. Cursor向け実装注意事項

① 各ステップは番号順に実装し、前のステップが完了してから次に進む  
② `_from_db_path` / `_to_db_path` はルート未設定時に必ず例外をスローする。サイレントに空文字・Noneを返してはいけない  
③ マジックナンバーは使用せず、`config.py` / `theme.py` に定数を定義する  
④ `theme.py` は `config.py` をインポートしてはいけない  
⑤ 他のカラム・処理には一切触れない  
⑥ テスト前に `__pycache__` を削除する
