# 技術負債リスト

意図的に先送りした設計上の問題を記録する。
着手前に必ずこのファイルを確認し、完了したら該当項目を削除する。

---

## 🔴 高優先

### [DB-001] パス変換の二重系統の統一
**問題**
`to_rel()`（paths.py）と `to_db_path_from_any()`（db.py）が同じ目的で並存している。
動作上の欠陥ではないが、新規実装時にどちらを使うか迷いやすく、
誤用によるバグを将来的に招きやすい。

**挙動の差異（統一前に必ず確認）**

| 項目 | to_rel() | to_db_path_from_any() |
|------|----------|----------------------|
| ルート取得 | 引数で受け取る | DBから取得 |
| ライブラリ外パス | そのまま返す | ValueError |
| None入力 | Noneを返す | 空文字チェックのみ |
| 現在の使用箇所 | set_bookmark等4関数 | upsert_book等5関数 |

**対応方針**
① 各呼び出し元がライブラリ外パスを渡しうるか個別確認する
② 問題なければ db.py 内は `to_db_path_from_any()` に統一する
③ path_utils.py への分離（DB非依存・引数渡し設計）は別途検討

**分類**
負債（欠陥ではない。動作は正しい）

---

### [DB-002] 返り値型の統一（TypedDict導入）
- **状態**: ✅ 完了

**完了内容**
types_ns.py に BookRow TypedDict を定義。
全取得系関数（get_all_books 系4関数）の返り値を BookRow に統一。
呼び出し側（app.py 等6ファイル）の row[N] 参照を全てキー参照に変更。
APP-001 / APP-002 として実施済み。

---

## 🟡 中優先

### [DB-003] God function分割（set_book_meta）
**問題**
`set_book_meta()` が引数12個+UNSETセンチネル。
フィールド追加のたびに全呼び出し箇所に影響する。

**本来あるべき姿**
set_book_meta_core() / set_book_tags() / set_book_characters() に分割。

---

### [DB-004] ビジネスロジックのdb.pyからの移動
**問題**
以下がDB操作と無関係な処理をdb.pyに持っている:
- `format_book_name()` / `parse_display_name()` → book_utils.py（新規）へ
- `_effective_meta_source()` → book_utils.py（新規）へ
- `bulk_rename_to_current_format()` → book_updater.pyへ

**影響範囲**
- 移動前に全呼び出し元をgrepで洗い出すこと

---

## 🟢 低優先

### [DB-005] キャッシュ設計の改善
**問題**
`cache.invalidate()` が書き込み関数20箇所以上に散在し全破棄のみ。
テーブル単位の粒度での無効化に変更すべき。

---

### [DB-006] get_conn() のcontextmanager化
**問題**
READ関数のclose漏れが構造的に防げていない。人間に委ねている設計。

**本来あるべき姿**
read_conn() contextmanagerを新設し、全READ関数をwithブロックに統一する。
約70関数の一括変更になるため専用スプリントで対応。

---

### [ARCH-001] ディレクトリ構造の整理
**問題**
ルートディレクトリにモジュールが平置きされており、責務の境界が不明瞭。
現状約20ファイルがフラットに並んでいる。

**本来あるべき姿**
責務単位でパッケージに整理する。例:
- `core/` — db.py、db_migrations.py、paths.py、config.py、cache.py
- `services/` — book_updater.py、store_file_resolver.py、cover_paths.py
- `utils/` — path_utils.py（DB-001完了後）、book_utils.py（DB-004完了後）

**影響範囲**
- 全ファイルのimportパスが変わる
- app.py、main.py、launcher.pyを含む全モジュールへの影響
- DB-001〜DB-004完了後に着手すること（整理先が確定してから移動する）

**着手条件**
- 負債DB-001〜004が完了し、モジュールの責務が確定してから
- 一括移動はCursorでも見落としが出やすいため、パッケージ単位で段階的に実施

---

## 進行中（調査フェーズ）

### [APP-001] app.py の row[] インデックス参照除去（TypedDict化）

**作業順序**
① app.py で `db.get_all_books()` 等の返り値を `row[N]` で参照している箇所を全て洗い出す
② 各箇所が何のフィールドを参照しているか確認し、TypedDict化で安全に置き換え可能か判断する
③ 判断後、db.py に `BookRow` TypedDict を定義し、取得系関数の返り値を変更する
④ app.py の全インデックス参照をキー参照に書き換える

**現状**
調査未着手。①から開始する。

**対象関数（db.py側）**
- `get_all_books()` → tuple8要素
- `get_all_books_order_by_added_desc()` → tuple8要素
- `search_books()` → tuple8要素
- `get_books_by_added_date()` → tuple6要素（uuidとmissing_since_dateなし）
- その他取得系関数

**注意**
- app.py以外（grid/、scanners/等）にも呼び出し元がある可能性がある
- 調査完了前にdb.py側を変更しない

---

## app.py 負債

## APP-002: BookRowCompat 削除
- **状態**: ✅ 完了

---

### [APP-003] _on_receive_bookmarklet の分割
**問題**
約200行の単一メソッドにfetch_meta・DB検索・FS操作・リネーム・DB更新が直列している。
内部にネスト関数が3つあり読みにくい。

**本来あるべき姿**
以下に分割する:
- `_fetch_and_normalize_meta(url, html)` — メタ取得・正規化
- `_apply_bookmarklet_meta(found_path, meta)` — DB更新
- `_rename_book_from_bookmarklet(found_path, meta)` — リネーム処理

**着手条件**
- APP-002（Controller分離）と同時に対応する

---

### [APP-004] on_book_updated の責務整理
**問題**
約80行。DB再取得・キャッシュ更新・フィルタ適用・スクロール復元を1メソッドで実行。
rangeChangedシグナルのネスト関数定義が読みにくい。

**改善案**
スクロール復元ロジックを `_restore_scroll_position()` として分離する。

**着手条件**
- APP-002と同時に対応する

---

### [APP-005] _apply_filters の構造整理
**問題**
約80行。サイドバー・ストア・カバー・missing・検索・パネルフィルタを順次適用するが
各フィルタが独立していない。フィルタ追加時に全体を読む必要がある。

**改善案**
各フィルタを独立した関数として定義し、パイプラインとして明示的に繋ぐ。
現状の `_apply_sidebar_filter` / `_apply_store_filter` 等は既に分離されているので
`_apply_filters` 本体の整理だけで済む。

**着手条件**
- APP-001完了後に対応可能（単独で着手できる）

---

### [APP-006] _collect_folder_thumb_repair_targets の DB直接呼び出し
**問題**
`db.get_conn()` を app.py から直接呼んでいる。
db.pyのREAD関数を使うべき箇所。

**改善案**
db.py に `get_books_with_cover_info()` 等の関数を追加して間接化する。

**着手条件**
- 低優先。動作上の問題なし。リファクタスプリントで対応

---

### [APP-007] パフォーマンス計測コードの分離
**問題**
`_property_save_perf_*` 系メソッド4本が本番コードに混在している。

**改善案**
デバッグフラグで無効化できる形に整理するか、削除する。

**着手条件**
- 低優先。v1.0リリース前に削除候補として確認する

---

## 完了済み

- [DB-✅] マイグレーション管理の導入（db_migrations.py）
- [DB-✅] 接続管理の統一（transaction()全書き込み関数への展開）
