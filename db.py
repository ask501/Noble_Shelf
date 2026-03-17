"""
db.py - SQLiteデータベース管理・バックアップ処理

担当:
  - DBの初期化・マイグレーション
  - books / bookmarks / recent_books / settings の読み書き
  - 起動時の自動バックアップ（直近10件保持）
  - バックアップ一覧取得・復元
"""
import re
import sqlite3
import os
import shutil
import sys
import unicodedata
from datetime import datetime
from paths import DB_FILE, BACKUP_DIR
MAX_BACKUPS = 10


# ══════════════════════════════════════════════════════
#  接続・初期化
# ══════════════════════════════════════════════════════

def get_conn():
    """DB接続を返す（呼び出し元でclose()すること）"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # 書き込み中でも読み取り可能にする
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """テーブル作成・マイグレーション。起動時に1回呼ぶ。"""
    conn = get_conn()
    try:
        c = conn.cursor()

        # ── books テーブル ──────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS books (
                path        TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                circle      TEXT NOT NULL,
                title       TEXT NOT NULL,
                cover_path  TEXT,
                mtime       REAL,
                updated_at  TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # ── bookmarks テーブル ─────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                path    TEXT PRIMARY KEY,
                rating  INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # ── recent_books テーブル ──────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS recent_books (
                path       TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                opened_at  TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # ── settings テーブル ──────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # ── book_meta テーブル（作者・タイプ・シリーズ・作品ID・除外フラグなど）────
        c.execute("""
            CREATE TABLE IF NOT EXISTS book_meta (
                path         TEXT PRIMARY KEY,
                author       TEXT DEFAULT '',
                type         TEXT DEFAULT '',
                series       TEXT DEFAULT '',
                dlsite_id    TEXT DEFAULT '',
                excluded     INTEGER DEFAULT 0,
                title_kana   TEXT DEFAULT '',
                circle_kana  TEXT DEFAULT '',
                pages        INTEGER,
                release_date TEXT DEFAULT '',
                price        INTEGER,
                memo         TEXT DEFAULT '',
                updated_at   TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        # 既存DBに不足カラムがあれば追加（マイグレーション）
        meta_cols = [r[1] for r in c.execute("PRAGMA table_info(book_meta)").fetchall()]
        if "dlsite_id" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN dlsite_id TEXT DEFAULT ''")
        if "excluded" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN excluded INTEGER DEFAULT 0")
        if "title_kana" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN title_kana TEXT DEFAULT ''")
        if "circle_kana" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN circle_kana TEXT DEFAULT ''")
        if "pages" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN pages INTEGER")
        if "release_date" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN release_date TEXT DEFAULT ''")
        if "price" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN price INTEGER")
        if "memo" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN memo TEXT DEFAULT ''")
        if "meta_source" not in meta_cols:
            c.execute("ALTER TABLE book_meta ADD COLUMN meta_source TEXT DEFAULT ''")

        # ── book_characters テーブル ───────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS book_characters (
                path      TEXT NOT NULL,
                character TEXT NOT NULL,
                PRIMARY KEY (path, character)
            )
        """)

        # ── book_tags テーブル ─────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS book_tags (
                path TEXT NOT NULL,
                tag  TEXT NOT NULL,
                PRIMARY KEY (path, tag)
            )
        """)

        # ── bookmarklet_queue テーブル ─────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS bookmarklet_queue (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                url          TEXT NOT NULL,
                site         TEXT NOT NULL DEFAULT '',
                title        TEXT NOT NULL DEFAULT '',
                circle       TEXT NOT NULL DEFAULT '',
                author       TEXT NOT NULL DEFAULT '',
                dlsite_id    TEXT NOT NULL DEFAULT '',
                tags         TEXT NOT NULL DEFAULT '',
                price        INTEGER,
                release_date TEXT NOT NULL DEFAULT '',
                cover_url    TEXT NOT NULL DEFAULT '',
                status       TEXT NOT NULL DEFAULT 'pending',
                fetched_at   TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # bookmarklet_queue マイグレーション
        bq_cols = [r[1] for r in c.execute("PRAGMA table_info(bookmarklet_queue)").fetchall()]
        if "cover_url" not in bq_cols:
            c.execute("ALTER TABLE bookmarklet_queue ADD COLUMN cover_url TEXT NOT NULL DEFAULT ''")

        # ── booksテーブルにcover_customカラムを追加（なければ）──
        cols = [r[1] for r in c.execute("PRAGMA table_info(books)").fetchall()]
        if 'cover_custom' not in cols:
            c.execute("ALTER TABLE books ADD COLUMN cover_custom TEXT")
        
        # ── booksテーブルにis_dlstカラムを追加（なければ）──
        if 'is_dlst' not in cols:
            c.execute("ALTER TABLE books ADD COLUMN is_dlst INTEGER DEFAULT 0")

        # ── インデックス ───────────────────────────────
        c.execute("CREATE INDEX IF NOT EXISTS idx_books_circle ON books(circle)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_characters_path ON book_characters(path)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tags_path ON book_tags(path)")

        conn.commit()

        # 強制終了で残った「保留ドロップ」設定を起動時に消す（起動時にダイアログが出るバグ防止）
        for key in ("pending_drop_paths", "deferred_drop_paths", "drop_paths"):
            c.execute("DELETE FROM settings WHERE key=?", (key,))
        conn.commit()

        # 追加マイグレーション: release_date のフォーマット統一
        migrate_release_date_format()
    finally:
        conn.close()




def migrate_release_date_format():
    """release_dateを 'yyyy年m月d日' 形式に統一する"""
    import re as _re

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT path, release_date FROM book_meta WHERE release_date != ''"
        ).fetchall()
        for row in rows:
            rd = row["release_date"] or ""
            m = _re.match(r"(\\d{4})[-/\\.](\\d{1,2})[-/\\.](\\d{1,2})", rd)
            if m:
                normalized = f"{m.group(1)}年{int(m.group(2))}月{int(m.group(3))}日"
                conn.execute(
                    "UPDATE book_meta SET release_date = ? WHERE path = ?",
                    (normalized, row["path"]),
                )
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  bookmarklet_queue
# ══════════════════════════════════════════════════════

def add_bookmarklet_queue(
    url: str,
    site: str,
    title: str,
    circle: str,
    author: str,
    dlsite_id: str,
    tags: str,
    price: int | None,
    release_date: str,
    cover_url: str,
    status: str = "pending",
) -> int:
    """キューに1件追加してidを返す"""
    conn = get_conn()
    try:
        c = conn.execute(
            """INSERT INTO bookmarklet_queue
               (url, site, title, circle, author, dlsite_id, tags, price, release_date, cover_url, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, site, title, circle, author, dlsite_id, tags, price, release_date, cover_url, status),
        )
        conn.commit()
        return c.lastrowid
    finally:
        conn.close()


def get_bookmarklet_queue() -> list[dict]:
    """キュー全件を新しい順で返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM bookmarklet_queue ORDER BY fetched_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_bookmarklet_status(id: int, status: str) -> None:
    """ステータスを更新する"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE bookmarklet_queue SET status = ? WHERE id = ?",
            (status, id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_bookmarklet_queue_by_status(status: str) -> None:
    """指定ステータスの件を一括削除する"""
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM bookmarklet_queue WHERE status = ?", (status,)
        )
        conn.commit()
    finally:
        conn.close()


def delete_bookmarklet_queue_all() -> None:
    """キューを全削除する"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM bookmarklet_queue")
        conn.commit()
    finally:
        conn.close()


def delete_bookmarklet_queue_by_id(id: int) -> None:
    """個別削除する"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM bookmarklet_queue WHERE id = ?", (id,))
        conn.commit()
    finally:
        conn.close()


def get_bookmarklet_queue_by_id(row_id: int) -> dict | None:
    conn = get_conn()
    try:
        c = conn.execute(
            "SELECT id, url, site, title, circle, author, dlsite_id, tags, price, release_date, cover_url, status, fetched_at "
            "FROM bookmarklet_queue WHERE id = ?",
            (row_id,),
        )
        row = c.fetchone()
        if not row:
            return None
        keys = [
            "id",
            "url",
            "site",
            "title",
            "circle",
            "author",
            "dlsite_id",
            "tags",
            "price",
            "release_date",
            "cover_url",
            "status",
            "fetched_at",
        ]
        return dict(zip(keys, row))
    finally:
        conn.close()


def update_bookmarklet_queue_status(row_id: int, status: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE bookmarklet_queue SET status = ? WHERE id = ?",
            (status, row_id),
        )
        conn.commit()
    finally:
        conn.close()


def find_book_by_bookmarklet(dlsite_id: str, title: str, url: str = "") -> dict | None:
    """
    ブックマークレットのメタデータからライブラリの作品を探す。
    検索順:
      ① book_meta.dlsite_id 完全一致
      ② books.name にID含む部分一致（URLからも抽出）
      ③ NFKC正規化後のタイトル完全一致
    """
    import unicodedata
    import re

    def normalize(s: str) -> str:
        return unicodedata.normalize("NFKC", (s or "").strip()).lower()

    conn = get_conn()
    try:
        # ① dlsite_id 完全一致
        if dlsite_id:
            row = conn.execute(
                "SELECT b.path, b.name, b.title, b.circle FROM books b "
                "LEFT JOIN book_meta m ON b.path = m.path "
                "WHERE m.dlsite_id = ?",
                (dlsite_id,),
            ).fetchone()
            if row:
                return dict(row)

        # URLからIDを抽出して追加で検索
        ids_to_check: set[str] = set()
        if dlsite_id:
            ids_to_check.add(dlsite_id)
        if url:
            m = re.search(r"(RJ|BJ|VJ|\d{6,})", url, re.IGNORECASE)
            if m:
                ids_to_check.add(m.group(0).upper())

        # ② books.name にID含む部分一致
        for id_str in ids_to_check:
            row = conn.execute(
                "SELECT path, name, title, circle FROM books WHERE name LIKE ?",
                (f"%{id_str}%",),
            ).fetchone()
            if row:
                return dict(row)

        # ③ NFKC正規化タイトル完全一致
        if title:
            norm_title = normalize(title)
            rows = conn.execute("SELECT path, name, title, circle FROM books").fetchall()
            for row in rows:
                if normalize(row["title"]) == norm_title or normalize(row["name"]) == norm_title:
                    return dict(row)

        return None
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  バックアップ
# ══════════════════════════════════════════════════════

def backup_on_startup() -> None:
    """
    起動時に自動バックアップを取る。
    BACKUP_DIR に library_YYYYMMDD_HHMMSS.db を作成し、
    設定の backup_max_count を超えた古いファイルを削除する。
    """
    if not os.path.exists(DB_FILE):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"library_{ts}.db")
    shutil.copy2(DB_FILE, dst)
    _trim_backups_with_setting()


def _trim_backups_with_setting() -> None:
    """バックアップ件数が上限を超えたら古いものから削除する（backup_max_count 設定を優先）。"""
    try:
        max_count = int(get_setting("backup_max_count") or MAX_BACKUPS)
    except (TypeError, ValueError):
        max_count = MAX_BACKUPS
    backups = list_backups()  # 既存の list_backups() は新しい順の dict リストを返す
    for info in backups[max_count:]:
        path = info.get("path")
        if not path:
            continue
        try:
            os.remove(path)
        except OSError:
            pass


# ══════════════════════════════════════════════════════
#  settings 読み書き
# ══════════════════════════════════════════════════════

def get_setting(key, default=None):
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key, value):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value) if value is not None else None)
        )
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  books 読み書き
# ══════════════════════════════════════════════════════

def get_all_books():
    """全booksを (name, circle, title, path, cover_path, is_dlst) のリストで返す
    cover_customが設定されていればそちらを優先"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT name, circle, title, path, 
               COALESCE(NULLIF(cover_custom, ''), cover_path) as cover_path,
               COALESCE(is_dlst, 0) as is_dlst
               FROM books ORDER BY name"""
        ).fetchall()
        return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"], r["is_dlst"]) for r in rows]
    finally:
        conn.close()


def get_all_books_order_by_added_desc():
    """全booksを追加順（updated_at 降順）で返す。get_all_books と同じ形式。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT name, circle, title, path,
               COALESCE(NULLIF(cover_custom, ''), cover_path) as cover_path,
               COALESCE(is_dlst, 0) as is_dlst
               FROM books ORDER BY updated_at DESC, name"""
        ).fetchall()
        return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"], r["is_dlst"]) for r in rows]
    finally:
        conn.close()


def repair_folder_covers():
    """
    フォルダ型書籍で cover_path が未設定または存在しない場合、
    フォルダ内の先頭画像をカバーとして設定する。
    """
    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
    conn = get_conn()
    try:
        rows = conn.execute("SELECT path, cover_path FROM books").fetchall()
        updated = 0
        for r in rows:
            path = r["path"] or ""
            raw_cover = r["cover_path"] or ""
            cover_path = resolve_cover_stored_value(raw_cover) if raw_cover else ""
            if not path or not os.path.isdir(path):
                continue
            if cover_path and os.path.isfile(cover_path):
                continue
            try:
                images = sorted(
                    name
                    for name in os.listdir(path)
                    if os.path.splitext(name)[1].lower() in IMAGE_EXTS
                )
            except Exception:
                continue
            if not images:
                continue
            new_cover = os.path.join(path, images[0])
            if not os.path.isfile(new_cover):
                continue
            store = _normalize_cover_for_save(new_cover)
            conn.execute(
                "UPDATE books SET cover_path=?, updated_at=datetime('now','localtime') WHERE path=?",
                (store, path),
            )
            updated += 1
        if updated:
            conn.commit()
        return updated
    finally:
        conn.close()


def update_book_cover_path(path: str, cover_path: str) -> bool:
    """指定 path の書籍の cover_path を更新する。cover_cache 内は ID のみ保存。戻り値: 更新したら True。"""
    if not path or not str(path).strip():
        return False
    store = _normalize_cover_for_save(cover_path) if cover_path else ""
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE books SET cover_path=?, updated_at=datetime('now','localtime') WHERE path=?",
            (store, path),
        )
        if cur.rowcount:
            conn.commit()
            return True
        return False
    finally:
        conn.close()


def get_known_paths():
    """DB登録済みのpathセットを返す（差分スキャン用）"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT path, mtime FROM books").fetchall()
        return {r["path"]: r["mtime"] for r in rows}
    finally:
        conn.close()


def is_path_registered(path: str) -> bool:
    """指定パスが books に登録済みなら True（二重登録防止用）。パスは正規化して比較する。"""
    if not path or not str(path).strip():
        return False
    norm = os.path.normpath(os.path.abspath(path))
    conn = get_conn()
    try:
        rows = conn.execute("SELECT path FROM books").fetchall()
        for r in rows:
            if os.path.normpath(os.path.abspath(r["path"])) == norm:
                return True
        return False
    finally:
        conn.close()


def upsert_book(name, circle, title, path, cover_path, mtime=None, is_dlst=0, pages=None):
    store_cover = _normalize_cover_for_save(cover_path) if cover_path else ""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO books(name, circle, title, path, cover_path, mtime, is_dlst, updated_at)
               VALUES(?,?,?,?,?,?,?,datetime('now','localtime'))
               ON CONFLICT(path) DO UPDATE SET
                 name=excluded.name, circle=excluded.circle, title=excluded.title,
                 cover_path=excluded.cover_path, mtime=excluded.mtime, is_dlst=excluded.is_dlst,
                 updated_at=excluded.updated_at""",
            (name, circle, title, path, store_cover, mtime, is_dlst)
        )
        conn.commit()
        if pages is not None:
            set_book_meta(path, pages=pages)
    finally:
        conn.close()


def bulk_upsert_books(records):
    """
    books テーブルへの upsert をまとめて1トランザクションで実行する。
    records: [(name, circle, title, path, cover_path, mtime, is_dlst), ...]
    cover_path は保存時に正規化（cover_cache 内は ID のみ）される。
    """
    if not records:
        return
    normalized = [
        (r[0], r[1], r[2], r[3], _normalize_cover_for_save(r[4]) if r[4] else "", r[5], r[6])
        for r in records
    ]
    conn = get_conn()
    try:
        conn.executemany(
            """INSERT INTO books(name, circle, title, path, cover_path, mtime, is_dlst, updated_at)
               VALUES(?,?,?,?,?,?,?,datetime('now','localtime'))
               ON CONFLICT(path) DO UPDATE SET
                 name=excluded.name, circle=excluded.circle, title=excluded.title,
                 cover_path=excluded.cover_path, mtime=excluded.mtime, is_dlst=excluded.is_dlst,
                 updated_at=excluded.updated_at""",
            normalized,
        )
        conn.commit()
    finally:
        conn.close()


def delete_book(path):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM books WHERE path=?", (path,))
        conn.execute("DELETE FROM bookmarks WHERE path=?", (path,))
        conn.commit()
    finally:
        conn.close()


def bulk_delete_books(paths):
    """
    複数 path の books / bookmarks レコードをまとめて削除する。
    """
    if not paths:
        return
    # 重複を排除
    unique_paths = list(set(paths))
    conn = get_conn()
    try:
        conn.executemany("DELETE FROM books WHERE path=?", [(p,) for p in unique_paths])
        conn.executemany("DELETE FROM bookmarks WHERE path=?", [(p,) for p in unique_paths])
        conn.commit()
    finally:
        conn.close()


def rename_book(old_path, new_path, new_name, new_circle, new_title, new_cover_path):
    conn = get_conn()
    try:
        # 新しいパスに既存のエントリがある場合は先に削除（UNIQUE制約エラー回避）
        conn.execute("DELETE FROM books WHERE path=? AND path!=?", (new_path, old_path))
        conn.execute("DELETE FROM book_meta WHERE path=? AND path!=?", (new_path, old_path))
        conn.execute("DELETE FROM book_tags WHERE path=? AND path!=?", (new_path, old_path))
        conn.execute("DELETE FROM book_characters WHERE path=? AND path!=?", (new_path, old_path))
        conn.execute("DELETE FROM bookmarks WHERE path=? AND path!=?", (new_path, old_path))
        conn.execute("DELETE FROM recent_books WHERE path=? AND path!=?", (new_path, old_path))

        # cover_custom が旧パス配下なら新パスに差し替え（参照切れ防止）。ID のみの場合はそのまま。
        row = conn.execute("SELECT cover_custom FROM books WHERE path=?", (old_path,)).fetchone()
        new_cover_custom = None
        if row and row["cover_custom"]:
            cc = row["cover_custom"].strip()
            if os.sep in cc or (len(cc) >= 2 and cc[1] == ":"):
                ob = os.path.normpath(old_path if os.path.isdir(old_path) else os.path.dirname(old_path))
                nb = os.path.normpath(new_path if os.path.isdir(new_path) else os.path.dirname(new_path))
                cc_norm = os.path.normpath(cc)
                if cc_norm == ob or cc_norm.startswith(ob + os.sep):
                    new_cover_custom = nb + cc_norm[len(ob):]
            if new_cover_custom is None:
                new_cover_custom = row["cover_custom"]
        if new_cover_custom is None and row:
            new_cover_custom = row["cover_custom"]

        cover_path_store = _normalize_cover_for_save(new_cover_path) if new_cover_path else ""
        conn.execute(
            """UPDATE books SET path=?, name=?, circle=?, title=?, cover_path=?,
               cover_custom=COALESCE(?, cover_custom), updated_at=datetime('now','localtime') WHERE path=?""",
            (new_path, new_name, new_circle, new_title, cover_path_store, new_cover_custom, old_path)
        )
        # 関連テーブルも path を更新
        conn.execute("UPDATE bookmarks SET path=? WHERE path=?", (new_path, old_path))
        conn.execute("UPDATE recent_books SET path=? WHERE path=?", (new_path, old_path))
        conn.execute("UPDATE book_meta SET path=? WHERE path=?", (new_path, old_path))
        conn.execute("UPDATE book_tags SET path=? WHERE path=?", (new_path, old_path))
        conn.execute("UPDATE book_characters SET path=? WHERE path=?", (new_path, old_path))
        conn.commit()
    finally:
        conn.close()


def repair_wrong_paths(library_folder: str, on_progress=None):
    """
    パスが「フォルダ名だけ」など誤って登録されているブックを修復する。
    path が絶対パスでない、または実在しない場合に、library_folder 配下で
    名前・サークル/タイトルが一致するフォルダ/ファイルを探して path を正す。
    戻り値: (修復数, エラーメッセージ or None, [(old_path, new_path), ...])
    """
    lib = (library_folder or "").strip()
    if not lib or not os.path.isdir(lib):
        return (0, "ライブラリフォルダが設定されていません。", [])

    def _path_is_wrong(p):
        if not p or not str(p).strip():
            return True
        # 実在しないパス（フォルダ名だけなどで登録された場合）は修復対象
        return not (os.path.isdir(p) or os.path.isfile(p))

    def _find_correct_path(name, circle, title, wrong_path):
        """library_folder 配下で name / [circle]title / circle - title に一致する実在パスを返す。"""
        candidates = [
            name,
            format_book_name(circle or "", title or ""),
            f"{circle or ''} - {title or ''}".strip(" -"),
            wrong_path.strip(),
        ]
        try:
            entries = os.listdir(lib)
        except OSError:
            return None
        for entry in entries:
            full = os.path.join(lib, entry)
            if not os.path.isdir(full) and not os.path.isfile(full):
                continue
            # 完全一致
            if entry in candidates or full == os.path.normpath(os.path.abspath(wrong_path)):
                return full
            # サークル・タイトルで一致（フォルダ名をパース）
            c, t = parse_display_name(entry)
            if (c or "", t or "") == (circle or "", title or ""):
                return full
        # 誤った path をフォルダ名としてパースし、作品名が一致するフォルダが1件だけなら採用（例: path="すわショタ - すわショタ" → 実フォルダ"[100円外務省]すわショタ"）
        wrong_c, wrong_t = parse_display_name(wrong_path.strip())
        if wrong_t:
            matches = []
            for entry in entries:
                full = os.path.join(lib, entry)
                if not os.path.isdir(full) and not os.path.isfile(full):
                    continue
                c, t = parse_display_name(entry)
                if (t or "").strip() == wrong_t.strip():
                    matches.append(full)
            if len(matches) == 1:
                return matches[0]
        return None

    rows = get_all_books()
    repaired = []
    for i, r in enumerate(rows):
        name, circle, title, path, cover_path, _ = r[0], r[1], r[2], r[3], r[4], r[5]
        if on_progress:
            on_progress(i + 1, len(rows), path)
        if not _path_is_wrong(path):
            continue
        new_path = _find_correct_path(name, circle, title, path)
        if not new_path:
            continue
        try:
            rename_book(path, new_path, name, circle or "", title or "", cover_path or "")
            repaired.append((path, new_path))
        except Exception as e:
            return (len(repaired), str(e), repaired)
    return (len(repaired), None, repaired)


def resolve_book_path(library_folder: str, name: str, circle: str, title: str, wrong_path: str = ""):
    """
    実在しない path（フォルダ名だけなど）に対して、library_folder 配下で
    名前・サークル/タイトルが一致する実在フォルダ/ファイルのフルパスを返す。
    見つからなければ None。
    """
    lib = (library_folder or "").strip()
    if not lib or not os.path.isdir(lib):
        return None
    candidates = [
        (name or "").strip(),
        format_book_name(circle or "", title or ""),
        f"{circle or ''} - {title or ''}".strip(" -"),
        (wrong_path or "").strip(),
    ]
    try:
        entries = os.listdir(lib)
    except OSError:
        return None
    for entry in entries:
        full = os.path.join(lib, entry)
        if not os.path.isdir(full) and not os.path.isfile(full):
            continue
        if entry in candidates:
            return full
        c, t = parse_display_name(entry)
        if (c or "", t or "") == (circle or "", title or ""):
            return full
    # 誤った path をパースして作品名が一致するフォルダが1件だけなら採用
    _, wrong_t = parse_display_name((wrong_path or "").strip())
    if wrong_t:
        wrong_t = wrong_t.strip()
        matches = []
        for entry in entries:
            full = os.path.join(lib, entry)
            if not os.path.isdir(full) and not os.path.isfile(full):
                continue
            _, t = parse_display_name(entry)
            if (t or "").strip() == wrong_t:
                matches.append(full)
        if len(matches) == 1:
            return matches[0]
    return None


def format_book_name(circle: str, title: str) -> str:
    """
    表示名を組み立て: サークルなし→作品名のみ、あり→[サークル名]作品名。
    """
    c = (circle or "").strip()
    t = (title or "").strip()
    if not c:
        return t
    return f"[{c}]{t}"


def parse_display_name(name: str) -> tuple[str, str]:
    """
    表示名・フォルダ名を (サークル名, 作品名) に分解。
    [サークル名]作品名 または 旧形式の サークル名 - 作品名 に対応。どちらでもなければ ( "", 全体 )。
    """
    if not name or not str(name).strip():
        return ("", "")
    s = str(name).strip()
    m = re.match(r"^\[([^\]]*)\](.*)$", s)
    if m:
        return (m.group(1).strip(), m.group(2).strip())
    parts = s.split(" - ", 1)
    if len(parts) > 1:
        return (parts[0].strip(), parts[1].strip())
    return ("", s)


def bulk_rename_to_current_format(library_folder: str, on_progress=None):
    """
    全書籍のフォルダ/ファイル名を [サークル名]作品名 に一括リネーム。DBの circle/title は保持。
    失敗したものはスキップして続行し、最後に失敗一覧を返す。
    on_progress(current, total, path) を呼ぶ。
    戻り値: (成功数, 初期エラーメッセージ or None, 失敗リスト [(path, 希望した新名, エラー文字列), ...])
    """
    lib = (library_folder or "").strip()
    if not lib or not os.path.isdir(lib):
        return (0, "ライブラリフォルダが設定されていません。", [])

    def _is_lib_root(p):
        if not p:
            return False
        return os.path.normpath(os.path.abspath(p)) == os.path.normpath(os.path.abspath(lib))

    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT path, name, circle, title,
                      COALESCE(NULLIF(cover_custom,''), cover_path) AS cover
               FROM books"""
        ).fetchall()
    finally:
        conn.close()

    renamed = 0
    failed = []
    for i, r in enumerate(rows):
        path = r["path"]
        name = r["name"]
        circle = r["circle"] or ""
        title = r["title"] or ""
        cover = r["cover"] or ""
        if on_progress:
            on_progress(i + 1, len(rows), path)
        new_name = format_book_name(circle, title)
        if new_name == name:
            continue
        if not os.path.exists(path):
            failed.append((path, new_name, "ファイル・フォルダが存在しません"))
            continue
        def _updated_cover(old_base: str, new_base: str, cover_path: str) -> str:
            """リネームに伴い、カバーが旧パス配下なら新パスに差し替える"""
            if not cover_path:
                return cover_path
            ob = os.path.normpath(old_base)
            nb = os.path.normpath(new_base)
            cp = os.path.normpath(cover_path)
            if cp == ob or cp.startswith(ob + os.sep):
                return nb + cp[len(ob):]
            return cover_path

        try:
            if os.path.isdir(path):
                if _is_lib_root(path):
                    continue
                base_dir = os.path.dirname(path)
                new_path = os.path.join(base_dir, new_name)
                if new_path != path:
                    os.rename(path, new_path)
                    new_cover = _updated_cover(path, new_path, cover)
                    rename_book(path, new_path, new_name, circle, title, new_cover)
                    renamed += 1
            else:
                parent_dir = os.path.dirname(path)
                if _is_lib_root(parent_dir):
                    ext = os.path.splitext(path)[1]
                    new_path = os.path.join(parent_dir, new_name + ext)
                    if new_path != path:
                        os.rename(path, new_path)
                        rename_book(path, new_path, new_name, circle, title, cover)
                        renamed += 1
                else:
                    grand = os.path.dirname(parent_dir)
                    new_parent = os.path.join(grand, new_name)
                    if new_parent != parent_dir:
                        os.rename(parent_dir, new_parent)
                    # フォルダ内の元ファイルも新名＋拡張子にリネーム
                    ext = os.path.splitext(path)[1]
                    current_file = os.path.join(new_parent, os.path.basename(path))
                    new_path = os.path.join(new_parent, new_name + ext)
                    if current_file != new_path and os.path.isfile(current_file):
                        os.rename(current_file, new_path)
                    new_cover = _updated_cover(parent_dir, new_parent, cover)
                    rename_book(path, new_path, new_name, circle, title, new_cover)
                    renamed += 1
        except Exception as e:
            failed.append((path, new_name, str(e)))
    return (renamed, None, failed)


def update_book_display(path: str, circle: str | None = None, title: str | None = None, name: str | None = None):
    """books テーブルの表示用フィールドのみ更新（フォルダのリネームは行わない）。一括編集用。"""
    if not path:
        return
    conn = get_conn()
    try:
        row = conn.execute("SELECT name, circle, title FROM books WHERE path=?", (path,)).fetchone()
        if not row:
            return
        cur_name = row["name"] or ""
        cur_circle = row["circle"] or ""
        cur_title = row["title"] or ""
        new_name = name if name is not None else cur_name
        new_circle = circle if circle is not None else cur_circle
        new_title = title if title is not None else cur_title
        if new_name == cur_name and new_circle == cur_circle and new_title == cur_title:
            return
        if name is None and (circle is not None or title is not None):
            new_name = format_book_name(new_circle, new_title)
        conn.execute(
            """UPDATE books SET name=?, circle=?, title=?, updated_at=datetime('now','localtime') WHERE path=?""",
            (new_name, new_circle, new_title, path),
        )
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  bookmarks 読み書き
# ══════════════════════════════════════════════════════

def get_all_bookmarks():
    """{ path: rating } の dict を返す"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT path, rating FROM bookmarks").fetchall()
        return {r["path"]: r["rating"] for r in rows}
    finally:
        conn.close()


def set_bookmark(path, rating):
    conn = get_conn()
    try:
        if rating == 0:
            conn.execute("DELETE FROM bookmarks WHERE path=?", (path,))
        else:
            conn.execute(
                """INSERT INTO bookmarks(path, rating, updated_at)
                   VALUES(?,?,datetime('now','localtime'))
                   ON CONFLICT(path) DO UPDATE SET
                     rating=excluded.rating, updated_at=excluded.updated_at""",
                (path, rating)
            )
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  recent_books 読み書き
# ══════════════════════════════════════════════════════

def get_recent_books(limit=10):
    """[(name, path), ...] を新しい順で返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT name, path FROM recent_books ORDER BY opened_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [(r["name"], r["path"]) for r in rows]
    finally:
        conn.close()


def add_recent_book(name, path):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO recent_books(path, name, opened_at)
               VALUES(?,?,datetime('now','localtime'))
               ON CONFLICT(path) DO UPDATE SET
                 name=excluded.name, opened_at=excluded.opened_at""",
            (path, name)
        )
        # 11件目以降を削除
        conn.execute("""
            DELETE FROM recent_books WHERE path NOT IN (
                SELECT path FROM recent_books ORDER BY opened_at DESC LIMIT 10
            )
        """)
        conn.commit()
    finally:
        conn.close()


def remove_recent_book(path):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM recent_books WHERE path=?", (path,))
        conn.commit()
    finally:
        conn.close()


def get_book_name_by_path(path: str):
    """path に対応する books の name（表示名）を返す。無ければ None。"""
    if not path:
        return None
    conn = get_conn()
    try:
        row = conn.execute("SELECT name FROM books WHERE path=?", (path,)).fetchone()
        return row["name"] if row else None
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  バックアップ
# ══════════════════════════════════════════════════════

def create_backup():
    """
    起動時に呼ぶ。library.dbをバックアップフォルダにコピーし、
    MAX_BACKUPS件を超えた古いものを削除する。
    DBが存在しない場合は何もしない。
    """
    if not os.path.exists(DB_FILE):
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"library_{timestamp}.db")
    shutil.copy2(DB_FILE, backup_path)

    # 古いバックアップを削除
    _cleanup_backups()
    return backup_path


def _cleanup_backups():
    """MAX_BACKUPSを超えた古いバックアップを削除"""
    if not os.path.exists(BACKUP_DIR):
        return
    files = sorted([
        f for f in os.listdir(BACKUP_DIR)
        if f.startswith("library_") and f.endswith(".db")
    ])
    while len(files) > MAX_BACKUPS:
        old = os.path.join(BACKUP_DIR, files.pop(0))
        try:
            os.remove(old)
        except Exception:
            pass


def list_backups():
    """
    バックアップ一覧を新しい順で返す。
    [{"filename": str, "path": str, "datetime": str, "size_kb": int}, ...]
    """
    if not os.path.exists(BACKUP_DIR):
        return []
    result = []
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if f.startswith("library_") and f.endswith(".db"):
            full = os.path.join(BACKUP_DIR, f)
            # ファイル名から日時をパース: library_YYYYMMDD_HHMMSS.db
            try:
                ts = f[len("library_"):-len(".db")]
                dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
                dt_str = dt.strftime("%Y/%m/%d %H:%M:%S")
            except Exception:
                dt_str = f
            size_kb = os.path.getsize(full) // 1024
            result.append({
                "filename": f,
                "path":     full,
                "datetime": dt_str,
                "size_kb":  size_kb,
            })
    return result


def restore_backup(backup_path):
    """
    指定バックアップをlibrary.dbに上書き復元する。
    復元前に現在のDBをbackups/pre_restore_*.dbとして保存する。
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"バックアップが見つかりません: {backup_path}")

    os.makedirs(BACKUP_DIR, exist_ok=True)

    # 復元前の現DBを保存
    if os.path.exists(DB_FILE):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pre = os.path.join(BACKUP_DIR, f"library_pre_restore_{timestamp}.db")
        shutil.copy2(DB_FILE, pre)

    shutil.copy2(backup_path, DB_FILE)
    _cleanup_backups()


# ══════════════════════════════════════════════════════
#  config.pkl からの移行ヘルパー
# ══════════════════════════════════════════════════════

def migrate_from_pickle(pickle_path="config.pkl"):
    """
    config.pklが存在する場合にDBへ移行する。
    移行済みなら何もしない（settings.migrated_from_pickle フラグで判定）。
    """
    if get_setting("migrated_from_pickle") == "1":
        return False  # 移行済み
    if not os.path.exists(pickle_path):
        set_setting("migrated_from_pickle", "1")
        return False

    import pickle
    try:
        with open(pickle_path, "rb") as f:
            config = pickle.load(f)
    except Exception:
        return False

    library_folder = config.get("library_folder")
    bookmarks      = config.get("bookmarks", {})
    recent_books   = config.get("recent_books", [])

    if library_folder:
        set_setting("library_folder", library_folder)

    conn = get_conn()
    try:
        for path, rating in bookmarks.items():
            conn.execute(
                """INSERT INTO bookmarks(path, rating) VALUES(?,?)
                   ON CONFLICT(path) DO UPDATE SET rating=excluded.rating""",
                (path, rating)
            )
        # recent_booksは新しい順に挿入（古いほど早い時刻にする）
        for i, (name, path) in enumerate(reversed(recent_books)):
            conn.execute(
                """INSERT INTO recent_books(path, name, opened_at) VALUES(?,?,datetime('now','localtime',?))
                   ON CONFLICT(path) DO UPDATE SET name=excluded.name, opened_at=excluded.opened_at""",
                (path, name, f"+{i} seconds")
            )
        conn.commit()
    finally:
        conn.close()

    set_setting("migrated_from_pickle", "1")
    return True  # 移行した


# ══════════════════════════════════════════════════════
#  book_meta 読み書き（作者・タイプ・シリーズ）
# ══════════════════════════════════════════════════════

def get_book_meta(path):
    """
    1冊分のメタ情報を dict で返す。
    {
        "author": "", "type": "", "series": "", "dlsite_id": "",
        "title_kana": "", "circle_kana": "",
        "pages": int | None, "release_date": "", "price": int | None, "memo": "",
        "characters": [...], "tags": [...]
    }
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT author, type, series, dlsite_id, title_kana, circle_kana, "
            "pages, release_date, price, memo "
            "FROM book_meta WHERE path=?",
            (path,)
        ).fetchone()
        meta = {
            "author":      row["author"]      if row else "",
            "type":        row["type"]        if row else "",
            "series":      row["series"]      if row else "",
            "dlsite_id":   row["dlsite_id"]   if row and row["dlsite_id"] else "",
            "title_kana":  row["title_kana"]  if row and row["title_kana"] is not None else "",
            "circle_kana": row["circle_kana"] if row and row["circle_kana"] is not None else "",
            "pages":       row["pages"]       if row is not None else None,
            "release_date": row["release_date"] if row and row["release_date"] is not None else "",
            "price":        row["price"]        if row is not None else None,
            "memo":         row["memo"]         if row and row["memo"] is not None else "",
        }
        chars = conn.execute(
            "SELECT character FROM book_characters WHERE path=? ORDER BY character", (path,)
        ).fetchall()
        tags = conn.execute(
            "SELECT tag FROM book_tags WHERE path=? ORDER BY tag", (path,)
        ).fetchall()
        meta["characters"] = [r["character"] for r in chars]
        meta["tags"]        = [r["tag"]       for r in tags]
        return meta
    finally:
        conn.close()


def get_all_book_metas() -> dict[str, dict]:
    """全書籍のメタデータを {path: meta_dict} で返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT path, author, type, series, dlsite_id, title_kana, circle_kana, "
            "pages, release_date, price, memo FROM book_meta"
        ).fetchall()
        chars = conn.execute(
            "SELECT path, character FROM book_characters ORDER BY path, character"
        ).fetchall()
        tags = conn.execute(
            "SELECT path, tag FROM book_tags ORDER BY path, tag"
        ).fetchall()

        meta_map: dict[str, dict] = {}
        for r in rows:
            path = r["path"]
            meta_map[path] = {
                "author":      r["author"]      or "",
                "type":        r["type"]        or "",
                "series":      r["series"]      or "",
                "dlsite_id":   r["dlsite_id"]   or "",
                "title_kana":  r["title_kana"]  or "",
                "circle_kana": r["circle_kana"] or "",
                "pages":       r["pages"],
                "release_date": r["release_date"] or "",
                "price":        r["price"],
                "memo":         r["memo"] or "",
                "characters": [],
                "tags": [],
            }

        for r in chars:
            path = r["path"]
            if path not in meta_map:
                meta_map[path] = {
                    "author": "", "type": "", "series": "", "dlsite_id": "",
                    "title_kana": "", "circle_kana": "",
                    "pages": None, "release_date": "", "price": None, "memo": "",
                    "characters": [], "tags": [],
                }
            meta_map[path]["characters"].append(r["character"])

        for r in tags:
            path = r["path"]
            if path not in meta_map:
                meta_map[path] = {
                    "author": "", "type": "", "series": "", "dlsite_id": "",
                    "title_kana": "", "circle_kana": "",
                    "pages": None, "release_date": "", "price": None, "memo": "",
                    "characters": [], "tags": [],
                }
            meta_map[path]["tags"].append(r["tag"])

        return meta_map
    finally:
        conn.close()


def has_metadata(path):
    """
    メタデータが設定されているか（DLSite IDがあるか）
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT dlsite_id FROM book_meta WHERE path=? AND dlsite_id != ''", (path,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_paths_with_metadata():
    """メタデータが設定されている（作品IDあり・除外でない）book pathのセットを返す（booksテーブルに存在するもののみ）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT m.path FROM book_meta m
               INNER JOIN books b ON m.path = b.path
               WHERE m.dlsite_id != '' AND m.excluded = 0"""
        ).fetchall()
        return {r["path"] for r in rows}
    finally:
        conn.close()


def get_paths_excluded():
    """除外されているbook pathのセットを返す（booksテーブルに存在するもののみ）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT m.path FROM book_meta m
               INNER JOIN books b ON m.path = b.path
               WHERE m.excluded = 1"""
        ).fetchall()
        return {r["path"] for r in rows}
    finally:
        conn.close()


def set_excluded(path, excluded=True):
    """除外フラグを設定"""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO book_meta(path, excluded, updated_at)
               VALUES(?, ?, datetime('now','localtime'))
               ON CONFLICT(path) DO UPDATE SET
                 excluded=excluded.excluded, updated_at=excluded.updated_at""",
            (path, 1 if excluded else 0)
        )
        conn.commit()
    finally:
        conn.close()


def is_excluded(path):
    """除外されているか"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT excluded FROM book_meta WHERE path=?", (path,)).fetchone()
        return row is not None and row["excluded"] == 1
    finally:
        conn.close()


def _effective_meta_source(meta_source: str, dlsite_id: str) -> str:
    """meta_source が空なら dlsite_id から推定。戻り値: dlsite, fanza, とらのあな, 同人DB, other のいずれか。
    - URL に dojindb.net を含む → 同人DB
    - 作品IDが 040/042 始まり → とらのあな（DLSite API とらのあな）
    - RJ/BJ/VJ → dlsite、D_ → fanza
    """
    if (meta_source or "").strip():
        return (meta_source or "").strip()
    raw = (dlsite_id or "").strip()
    if not raw:
        return ""
    # URL 参照: dojindb.net を含む → 同人DB
    if "dojindb.net" in raw:
        return "同人DB"
    did = raw.upper()
    if did.startswith("RJ") or did.startswith("BJ") or did.startswith("VJ"):
        return "dlsite"
    if did.startswith("D_"):
        return "fanza"
    # 作品ID 040/042 始まり → とらのあな（DLSite API）
    if raw.startswith("040") or raw.startswith("042"):
        return "とらのあな"
    return "other"


def get_meta_source_counts():
    """メタデータ取得状況を作品ID（dlsite_id）欄で集計。(source_key, label, count) のリスト。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT m.path, m.dlsite_id, m.excluded
               FROM book_meta m INNER JOIN books b ON m.path = b.path"""
        ).fetchall()
        from collections import Counter
        excluded_count = sum(1 for r in rows if r["excluded"] == 1)
        acquired = [r for r in rows if r["excluded"] != 1]
        source_counts = Counter()
        for r in acquired:
            # 作品ID（dlsite_id）のみで取得元を判定
            dlsite_id = (r["dlsite_id"] or "").strip()
            if not dlsite_id:
                continue  # 未取得は別枠で数える
            src = _effective_meta_source("", dlsite_id)
            if not src:
                src = "other"
            source_counts[src] += 1
        not_acquired_count = conn.execute(
            """SELECT COUNT(*) FROM books b
               LEFT JOIN book_meta m ON b.path = m.path
               WHERE (m.path IS NULL OR ((m.dlsite_id IS NULL OR m.dlsite_id = '') AND COALESCE(m.excluded,0) = 0))"""
        ).fetchone()[0]
        label_map = {
            "not_acquired": "未取得",
            "dlsite": "DLSite",
            "fanza": "FANZA",
            "とらのあな": "とらのあな",
            "同人DB": "同人DB",
            "other": "その他",
            "excluded": "除外",
        }
        result = [("not_acquired", "未取得", not_acquired_count)]
        for key in ("dlsite", "fanza", "とらのあな", "同人DB", "other"):
            result.append((key, label_map[key], source_counts.get(key, 0)))
        result.append(("excluded", "除外", excluded_count))
        return result
    finally:
        conn.close()


def get_books_by_meta_source(source_key: str):
    """メタデータ取得元でフィルタ。(name, circle, title, path, cover_path) のタプルリスト。source_key: not_acquired, dlsite, fanza, とらのあな, 同人DB, other, excluded."""
    conn = get_conn()
    try:
        if source_key == "excluded":
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path,
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                FROM books b INNER JOIN book_meta m ON b.path = m.path
                WHERE m.excluded = 1 ORDER BY b.name
            """).fetchall()
            return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
        if source_key == "not_acquired":
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path,
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                FROM books b LEFT JOIN book_meta m ON b.path = m.path
                WHERE (m.path IS NULL OR (COALESCE(m.dlsite_id,'') = '' AND COALESCE(m.excluded,0) = 0))
                ORDER BY b.name
            """).fetchall()
            return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
        # 取得済みのうち作品ID（dlsite_id）の形式で絞り込み
        if source_key == "とらのあな":
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path,
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                FROM books b INNER JOIN book_meta m ON b.path = m.path
                WHERE m.excluded = 0 AND (m.dlsite_id LIKE '040%%' OR m.dlsite_id LIKE '042%%')
                ORDER BY b.name
            """).fetchall()
            return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
        elif source_key == "同人DB":
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path,
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                FROM books b INNER JOIN book_meta m ON b.path = m.path
                WHERE m.excluded = 0 AND m.dlsite_id LIKE '%%dojindb.net%%'
                ORDER BY b.name
            """).fetchall()
            return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
        else:
            if source_key == "dlsite":
                # RJ / BJ / VJ は DLSite 形式（DLSITE_API 対応）
                rows = conn.execute("""
                    SELECT b.name, b.circle, b.title, b.path,
                           COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                    FROM books b INNER JOIN book_meta m ON b.path = m.path
                    WHERE m.excluded = 0 AND (
                        m.dlsite_id LIKE 'RJ%' OR m.dlsite_id LIKE 'BJ%' OR m.dlsite_id LIKE 'VJ%'
                    )
                    ORDER BY b.name
                """).fetchall()
            elif source_key == "fanza":
                rows = conn.execute("""
                    SELECT b.name, b.circle, b.title, b.path,
                           COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path
                    FROM books b INNER JOIN book_meta m ON b.path = m.path
                    WHERE m.excluded = 0 AND m.dlsite_id LIKE 'D_%'
                    ORDER BY b.name
                """).fetchall()
            else:  # other（作品IDの形式で other になるもの）
                rows = conn.execute("""
                    SELECT b.name, b.circle, b.title, b.path,
                           COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path,
                           m.dlsite_id
                    FROM books b INNER JOIN book_meta m ON b.path = m.path
                    WHERE m.excluded = 0 AND m.dlsite_id != '' AND m.dlsite_id IS NOT NULL
                    ORDER BY b.name
                """).fetchall()
                filtered = []
                for r in rows:
                    if _effective_meta_source("", r["dlsite_id"] or "") == "other":
                        filtered.append((r["name"], r["circle"], r["title"], r["path"], r["cover_path"]))
                return filtered
        return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
    finally:
        conn.close()


def get_books_by_metadata_status(status):
    """
    メタデータ取得状況でブックをフィルタリング
    status: "acquired" (取得済み), "not_acquired" (未取得), "excluded" (除外)
    返り値: (name, circle, title, path, cover_path) のタプルリスト
    """
    conn = get_conn()
    try:
        if status == "acquired":
            # 作品IDあり、除外でない
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path, 
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path 
                FROM books b
                INNER JOIN book_meta m ON b.path = m.path
                WHERE m.dlsite_id != '' AND m.excluded = 0
                ORDER BY b.name
            """).fetchall()
        elif status == "excluded":
            # 除外フラグあり
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path, 
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path 
                FROM books b
                INNER JOIN book_meta m ON b.path = m.path
                WHERE m.excluded = 1
                ORDER BY b.name
            """).fetchall()
        else:  # not_acquired
            # 作品IDなし、除外でない（または book_meta にエントリなし）
            rows = conn.execute("""
                SELECT b.name, b.circle, b.title, b.path, 
                       COALESCE(NULLIF(b.cover_custom, ''), b.cover_path) as cover_path 
                FROM books b
                LEFT JOIN book_meta m ON b.path = m.path
                WHERE (m.path IS NULL OR (m.dlsite_id = '' AND m.excluded = 0))
                ORDER BY b.name
            """).fetchall()
        return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"]) for r in rows]
    finally:
        conn.close()


def set_book_meta(
    path,
    author: str = "",
    type_: str = "",
    series: str = "",
    characters=None,
    tags=None,
    dlsite_id=None,
    title_kana: str | None = None,
    circle_kana: str | None = None,
    pages: int | None = None,
    release_date: str | None = None,
    price: int | None = None,
    memo: str | None = None,
    meta_source: str | None = None,
):
    """
    メタ情報を保存。characters/tagsはリスト。
    dlsite_id / title_kana / circle_kana / pages / release_date / price / memo / meta_source が None の場合は既存値を維持する。
    meta_source は dlsite, fanza, とらのあな, 同人DB, other のいずれか（取得元の振り分け用）。
    同時にbooksテーブルのcover_customも必要なら別途set_cover_custom()を呼ぶ。
    """
    conn = get_conn()
    try:
        # 既存値を取得して、None のフィールドは既存値を維持
        cur = conn.execute(
            "SELECT dlsite_id, title_kana, circle_kana, pages, release_date, price, memo, meta_source "
            "FROM book_meta WHERE path=?",
            (path,),
        ).fetchone()

        cur_dlsite_id   = cur["dlsite_id"]   if cur else ""
        cur_title_kana  = cur["title_kana"]  if cur else ""
        cur_circle_kana = cur["circle_kana"] if cur else ""
        cur_pages       = cur["pages"]       if cur else None
        cur_release     = cur["release_date"] if cur else ""
        cur_price       = cur["price"]        if cur else None
        cur_memo        = cur["memo"]         if cur else ""
        cur_meta_source = (cur["meta_source"] or "") if cur else ""

        new_dlsite_id   = dlsite_id   if dlsite_id   is not None else cur_dlsite_id
        new_title_kana  = title_kana  if title_kana  is not None else cur_title_kana
        new_circle_kana = circle_kana if circle_kana is not None else cur_circle_kana
        new_pages       = pages       if pages       is not None else cur_pages
        new_release     = release_date if release_date is not None else cur_release
        new_price       = price       if price       is not None else cur_price
        new_memo        = memo        if memo        is not None else cur_memo
        new_meta_source = (meta_source.strip() if meta_source is not None and meta_source.strip() else cur_meta_source or "")

        conn.execute(
            """INSERT INTO book_meta(
                   path, author, type, series,
                   dlsite_id, title_kana, circle_kana,
                   pages, release_date, price, memo, meta_source,
                   updated_at
               )
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))
               ON CONFLICT(path) DO UPDATE SET
                 author=excluded.author,
                 type=excluded.type,
                 series=excluded.series,
                 dlsite_id=excluded.dlsite_id,
                 title_kana=excluded.title_kana,
                 circle_kana=excluded.circle_kana,
                 pages=excluded.pages,
                 release_date=excluded.release_date,
                 price=excluded.price,
                 memo=excluded.memo,
                 meta_source=excluded.meta_source,
                 updated_at=excluded.updated_at""",
            (
                path,
                author or "",
                type_ or "",
                series or "",
                new_dlsite_id or "",
                new_title_kana or "",
                new_circle_kana or "",
                new_pages,
                new_release or "",
                new_price,
                new_memo or "",
                new_meta_source or "",
            ),
        )
        # キャラクター・タグは全削除→再挿入
        conn.execute("DELETE FROM book_characters WHERE path=?", (path,))
        for c in (characters or []):
            c = c.strip()
            if c:
                conn.execute(
                    "INSERT OR IGNORE INTO book_characters(path, character) VALUES(?,?)", (path, c)
                )
        conn.execute("DELETE FROM book_tags WHERE path=?", (path,))
        for t in (tags or []):
            t = t.strip()
            if t:
                conn.execute(
                    "INSERT OR IGNORE INTO book_tags(path, tag) VALUES(?,?)", (path, t)
                )
        conn.commit()
    finally:
        conn.close()


def set_cover_custom(path, cover_path):
    """カスタムカバー画像パスをbooksテーブルに保存。cover_cache 内は ID のみ保存する。"""
    store = _normalize_cover_for_save(cover_path) if cover_path else ""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE books SET cover_custom=? WHERE path=?", (store, path)
        )
        conn.commit()
    finally:
        conn.close()


def get_cover_custom(path):
    """カスタムカバーパスを返す（未設定ならNone）"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT cover_custom FROM books WHERE path=?", (path,)
        ).fetchone()
        return row["cover_custom"] if row else None
    finally:
        conn.close()


def cleanup_invalid_cover_custom():
    """存在しないファイルを指すcover_customをクリアする。DB値は ID の場合は resolve してから存在チェック。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT path, cover_custom FROM books WHERE cover_custom != '' AND cover_custom IS NOT NULL"
        ).fetchall()
        cleared_count = 0
        for row in rows:
            if not row["cover_custom"]:
                continue
            resolved = resolve_cover_stored_value(row["cover_custom"])
            if resolved and not os.path.exists(resolved):
                conn.execute("UPDATE books SET cover_custom='' WHERE path=?", (row["path"],))
                cleared_count += 1
        if cleared_count > 0:
            conn.commit()
    finally:
        conn.close()


def clear_all_caches():
    """
    thumb_cache（グリッド用サムネPNG）のみ全削除。
    cover_cache（PDF/dmme/dlst/切り抜き等の元画像）は参照されているものは残し、未使用のみ削除。
    戻り値: (削除したファイル数, エラーメッセージ or None)。
    """
    try:
        import config
    except ImportError:
        return (0, "config の読み込みに失敗しました")
    removed = 0
    # グリッド用サムネキャッシュのみ全削除（カード表示用に再生成される）
    if os.path.isdir(config.CACHE_DIR):
        try:
            for name in os.listdir(config.CACHE_DIR):
                full = os.path.join(config.CACHE_DIR, name)
                if os.path.isfile(full):
                    os.remove(full)
                    removed += 1
        except Exception as e:
            return (removed, str(e))
    # cover_cache は未使用ファイルだけ削除（PDF/dmme/dlst/切り抜き画像は保持）
    cleanup_unused_cover_cache()
    return (removed, None)


def _normalize_cover_for_save(cover_path: str) -> str:
    """
    カバーパスをDB保存用に正規化する。
    cover_cache 配下のパスは ID（ファイル名）のみ保存し、それ以外はそのまま保存する。
    これにより cleanup はフルパスに依存せず、COVER_CACHE_DIR + ID で一意に判定できる。
    """
    if not cover_path or not str(cover_path).strip():
        return ""
    try:
        import config
    except ImportError:
        return cover_path.strip()
    v = str(cover_path).strip()
    # すでに ID のみ（パス区切り・ドライブレターなし）の場合はそのまま
    if os.sep not in v and (len(v) < 2 or v[1] != ":"):
        return v
    full = os.path.normpath(os.path.abspath(v))
    cover_dir_norm = os.path.normpath(os.path.abspath(config.COVER_CACHE_DIR))
    if full.startswith(cover_dir_norm):
        return os.path.basename(full)
    return v


def resolve_cover_stored_value(stored: str) -> str:
    """
    DBに保存された cover_path / cover_custom を表示・参照用のフルパスに解決する。
    - 空 → 空文字
    - ID のみ（パス区切りなし）→ COVER_CACHE_DIR 内のファイルとして結合
    - 絶対パス → そのまま正規化
    - 相対パス → APP_BASE 基準で解決
    """
    if not stored or not str(stored).strip():
        return ""
    try:
        import config
    except ImportError:
        return stored.strip()
    p = str(stored).strip()
    # ID のみ（cover_cache 内のファイル名だけ保存されている場合）
    if os.sep not in p and (len(p) < 2 or p[1] != ":"):
        resolved = os.path.normpath(os.path.join(config.COVER_CACHE_DIR, p))
        return os.path.abspath(resolved)
    if os.path.isabs(p):
        return os.path.normpath(os.path.abspath(p))
    app_base = getattr(config, "APP_BASE", os.path.dirname(config.COVER_CACHE_DIR))
    resolved = os.path.normpath(os.path.join(app_base, p))
    return os.path.abspath(resolved)


def _resolve_cover_path_for_cleanup(p: str) -> str | None:
    """DBに保存されたカバーパスを、cleanup 用の絶対パスに変換。ID の場合は cover_cache と結合。"""
    resolved = resolve_cover_stored_value(p) if p else ""
    return resolved if resolved else None


def cleanup_unused_cover_cache():
    """cover_cache内の、どの書籍からも参照されていない画像を削除する。使用中のサムネは絶対に削除しない。"""
    try:
        import config
    except ImportError:
        return
    cover_dir = config.COVER_CACHE_DIR
    if not os.path.isdir(cover_dir):
        return
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT cover_path, cover_custom FROM books"
        ).fetchall()
    finally:
        conn.close()
    used = set()
    for row in rows:
        for i, key in enumerate(("cover_path", "cover_custom")):
            try:
                p = row[i]
            except (IndexError, TypeError):
                p = None
            resolved = _resolve_cover_path_for_cleanup(p)
            if resolved:
                used.add(resolved)
    try:
        for name in os.listdir(cover_dir):
            full = os.path.join(cover_dir, name)
            if not os.path.isfile(full):
                continue
            try:
                full_norm = os.path.normpath(os.path.abspath(full))
                if full_norm not in used:
                    os.remove(full)
            except Exception:
                pass
    except Exception:
        pass


def cleanup_invalid_paths():
    """存在しないフォルダを指すブックをDBから削除する"""
    import os
    conn = get_conn()
    try:
        rows = conn.execute("SELECT path FROM books").fetchall()
        deleted_count = 0
        for row in rows:
            if row["path"] and not os.path.exists(row["path"]):
                # 関連テーブルからも削除
                conn.execute("DELETE FROM books WHERE path=?", (row["path"],))
                conn.execute("DELETE FROM book_meta WHERE path=?", (row["path"],))
                conn.execute("DELETE FROM book_tags WHERE path=?", (row["path"],))
                conn.execute("DELETE FROM book_characters WHERE path=?", (row["path"],))
                conn.execute("DELETE FROM bookmarks WHERE path=?", (row["path"],))
                conn.execute("DELETE FROM recent_books WHERE path=?", (row["path"],))
                deleted_count += 1
        if deleted_count > 0:
            conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  ショートカット設定 読み書き
# ══════════════════════════════════════════════════════

# デフォルトショートカット定義
DEFAULT_SHORTCUTS = {
    "open":        "o",
    "bookmark":    "f",
    "rename":      "m",
    "properties":  "r",
    "explorer":    "i",
    "go_circle":   "g",
    "go_all":      "ctrl+a",
    "delete":      "d",
}

def get_shortcuts():
    """現在のショートカット設定を dict で返す。未設定はデフォルト値を使用。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE 'shortcut_%'"
        ).fetchall()
        saved = {r["key"].replace("shortcut_", ""): r["value"] for r in rows}
        # デフォルトとマージ（保存済み優先）
        result = dict(DEFAULT_SHORTCUTS)
        result.update(saved)
        return result
    finally:
        conn.close()


def set_shortcuts(shortcuts: dict):
    """ショートカット設定を一括保存。空文字は「未割り当て」として保存。"""
    conn = get_conn()
    try:
        for action, key in shortcuts.items():
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (f"shortcut_{action}", key.lower().strip() if key else "")
            )
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  検索バー用候補取得
# ══════════════════════════════════════════════════════

def get_all_tags():
    """登録済みタグを重複なしで返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT tag FROM book_tags ORDER BY tag"
        ).fetchall()
        return [r["tag"] for r in rows]
    finally:
        conn.close()


def get_all_tags_with_count():
    """(タグ, 作品数) のリストを作品数の多い順で返す（booksテーブルに存在するもののみ）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT t.tag, COUNT(DISTINCT t.path) AS cnt 
               FROM book_tags t
               INNER JOIN books b ON t.path = b.path
               GROUP BY t.tag ORDER BY cnt DESC, t.tag"""
        ).fetchall()
        return [(r["tag"], r["cnt"]) for r in rows]
    finally:
        conn.close()


def get_all_circles_with_count():
    """(サークル名, 作品数) のリストを作品数の多い順で返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT circle, COUNT(*) as cnt FROM books
               WHERE circle IS NOT NULL AND circle != ''
               GROUP BY circle ORDER BY cnt DESC, circle"""
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()


def get_all_characters():
    """登録済みキャラクターを重複なしで返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT character FROM book_characters ORDER BY character"
        ).fetchall()
        return [r["character"] for r in rows]
    finally:
        conn.close()


def get_all_characters_with_count():
    """(キャラクター, 作品数) のリストを作品数の多い順で返す（booksテーブルに存在するもののみ）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT c.character, COUNT(DISTINCT c.path) AS cnt 
               FROM book_characters c
               INNER JOIN books b ON c.path = b.path
               GROUP BY c.character ORDER BY cnt DESC, c.character"""
        ).fetchall()
        return [(r["character"], r["cnt"]) for r in rows]
    finally:
        conn.close()


def get_all_authors():
    """登録済み作者を重複なしで返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT author FROM book_meta WHERE author != '' ORDER BY author"
        ).fetchall()
        return [r["author"] for r in rows]
    finally:
        conn.close()


def get_all_authors_with_count():
    """(作者, 作品数) のリストを作品数の多い順で返す（booksテーブルに存在するもののみ）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT m.author, COUNT(m.path) AS cnt 
               FROM book_meta m
               INNER JOIN books b ON m.path = b.path
               WHERE m.author != '' 
               GROUP BY m.author ORDER BY cnt DESC, m.author"""
        ).fetchall()
        return [(r["author"], r["cnt"]) for r in rows]
    finally:
        conn.close()


def get_paths_with_author():
    """authorが設定されているbookのpathリストを返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT path FROM book_meta WHERE author != ''"
        ).fetchall()
        return [r["path"] for r in rows]
    finally:
        conn.close()


def get_paths_with_tag():
    """タグが1件以上あるbookのpathリストを返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT path FROM book_tags"
        ).fetchall()
        return [r["path"] for r in rows]
    finally:
        conn.close()


def get_paths_with_character():
    """キャラクターが1件以上あるbookのpathリストを返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT path FROM book_characters"
        ).fetchall()
        return [r["path"] for r in rows]
    finally:
        conn.close()


def get_all_series():
    """登録済みシリーズを重複なしで返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT series FROM book_meta WHERE series != '' ORDER BY series"
        ).fetchall()
        return [r["series"] for r in rows]
    finally:
        conn.close()


def get_all_circles():
    """登録済みサークル名を重複なしで返す（検索バー・スマートモード用）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT circle FROM books WHERE circle != '' ORDER BY circle"
        ).fetchall()
        return [r["circle"] for r in rows]
    finally:
        conn.close()


def get_all_series_with_count():
    """(シリーズ, 作品数) のリストを作品数の多い順で返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT series, COUNT(path) AS cnt FROM book_meta WHERE series != '' GROUP BY series ORDER BY cnt DESC, series"
        ).fetchall()
        return [(r["series"], r["cnt"]) for r in rows]
    finally:
        conn.close()


def get_paths_with_series():
    """シリーズが設定されている path のセットを返す"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT path FROM book_meta WHERE series != ''"
        ).fetchall()
        return {r["path"] for r in rows}
    finally:
        conn.close()


def search_books(conditions, operator="AND"):
    """
    conditions: [{"field": "title"|"circle"|"author"|"series"|"character"|"tag", "value": str}, ...]
    operator: "AND" | "OR"
    全booksを (name, circle, title, path, cover_path) のリストで返す
    検索語・DB側とも NFKC 正規化して比較する（全角/半角・異体字などを同一視）
    """
    if not conditions:
        return get_all_books()

    def _nfkc(s):
        return unicodedata.normalize("NFKC", s or "") if s else ""

    conn = get_conn()
    try:
        conn.create_function("nfkc", 1, lambda s: _nfkc(s))
        path_sets = []
        for cond in conditions:
            field = cond["field"]
            val_raw = cond["value"].strip()
            if not val_raw:
                continue
            val = _nfkc(val_raw).lower()
            pattern = f"%{val}%"

            if field == "all":
                all_paths = set()
                rows = conn.execute(
                    "SELECT path FROM books WHERE lower(nfkc(title)) LIKE ?", (pattern,)
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                rows = conn.execute(
                    "SELECT path FROM books WHERE lower(nfkc(circle)) LIKE ?", (pattern,)
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                rows = conn.execute(
                    "SELECT path FROM book_meta WHERE lower(nfkc(author)) LIKE ?", (pattern,)
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                rows = conn.execute(
                    "SELECT path FROM book_meta WHERE lower(nfkc(series)) LIKE ?", (pattern,)
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                rows = conn.execute(
                    "SELECT path FROM book_characters WHERE lower(nfkc(character)) LIKE ?", (pattern,)
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                rows = conn.execute(
                    "SELECT path FROM book_tags WHERE lower(nfkc(tag)) LIKE ?", (pattern,)
                ).fetchall()
                all_paths.update(r["path"] for r in rows)
                path_sets.append(all_paths)
                continue
            elif field == "title":
                rows = conn.execute(
                    "SELECT path FROM books WHERE lower(nfkc(title)) LIKE ?", (pattern,)
                ).fetchall()
            elif field == "circle":
                rows = conn.execute(
                    "SELECT path FROM books WHERE lower(nfkc(circle)) LIKE ?", (pattern,)
                ).fetchall()
            elif field == "author":
                rows = conn.execute(
                    "SELECT path FROM book_meta WHERE lower(nfkc(author)) LIKE ?", (pattern,)
                ).fetchall()
            elif field == "series":
                rows = conn.execute(
                    "SELECT path FROM book_meta WHERE lower(nfkc(series)) LIKE ?", (pattern,)
                ).fetchall()
            elif field == "character":
                rows = conn.execute(
                    "SELECT path FROM book_characters WHERE lower(nfkc(character)) LIKE ?", (pattern,)
                ).fetchall()
            elif field == "tag":
                rows = conn.execute(
                    "SELECT path FROM book_tags WHERE lower(nfkc(tag)) LIKE ?", (pattern,)
                ).fetchall()
            elif field == "metadata":
                if "取得" in val or "済" in val:
                    rows = conn.execute("""
                        SELECT b.path FROM books b
                        INNER JOIN book_meta m ON b.path = m.path
                        WHERE m.dlsite_id != '' AND m.dlsite_id IS NOT NULL AND m.excluded = 0
                    """).fetchall()
                elif "未" in val:
                    acquired = conn.execute("""
                        SELECT path FROM book_meta WHERE dlsite_id != '' AND dlsite_id IS NOT NULL AND excluded = 0
                    """).fetchall()
                    excluded = conn.execute("SELECT path FROM book_meta WHERE excluded = 1").fetchall()
                    all_paths = {r["path"] for r in conn.execute("SELECT path FROM books").fetchall()}
                    path_sets.append(all_paths - {r["path"] for r in acquired} - {r["path"] for r in excluded})
                    continue
                else:
                    continue
                path_sets.append({r["path"] for r in rows})
                continue
            elif field == "added_date":
                rows = conn.execute(
                    "SELECT path FROM books WHERE date(updated_at) = ? OR strftime('%Y-%m-%d', updated_at) LIKE ?",
                    (val, val + "%")
                ).fetchall()
                path_sets.append({r["path"] for r in rows})
                continue
            else:
                continue

            path_sets.append({r["path"] for r in rows})

        if not path_sets:
            return get_all_books()

        if operator == "AND":
            matched_paths = path_sets[0]
            for s in path_sets[1:]:
                matched_paths &= s
        else:  # OR
            matched_paths = set()
            for s in path_sets:
                matched_paths |= s

        if not matched_paths:
            return []

        placeholders = ",".join("?" * len(matched_paths))
        rows = conn.execute(
            f"SELECT name, circle, title, path, "
            f"COALESCE(NULLIF(cover_custom, ''), cover_path) as cover_path, "
            f"COALESCE(is_dlst, 0) as is_dlst FROM books "
            f"WHERE path IN ({placeholders}) ORDER BY name",
            list(matched_paths)
        ).fetchall()
        return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"], r["is_dlst"]) for r in rows]
    finally:
        conn.close()


def get_added_dates_with_count():
    """追加日（updated_atの日付）ごとの件数を返す。[(日付文字列, 件数), ...] 新しい順"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT date(updated_at) as d, COUNT(*) as cnt
               FROM books WHERE updated_at IS NOT NULL AND updated_at != ''
               GROUP BY d ORDER BY d DESC"""
        ).fetchall()
        return [(r["d"], r["cnt"]) for r in rows]
    finally:
        conn.close()


def get_books_by_added_date(date_str):
    """指定した追加日（YYYY-MM-DD）の書籍を追加順（updated_at 降順）で返す。get_all_books と同じ形式"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT name, circle, title, path,
               COALESCE(NULLIF(cover_custom, ''), cover_path) as cover_path,
               COALESCE(is_dlst, 0) as is_dlst
               FROM books WHERE date(updated_at) = ? ORDER BY updated_at DESC""",
            (date_str,)
        ).fetchall()
        return [(r["name"], r["circle"], r["title"], r["path"], r["cover_path"], r["is_dlst"]) for r in rows]
    finally:
        conn.close()
