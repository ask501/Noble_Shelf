"""
properties/_utils.py - properties パッケージ内の共通ユーティリティ
（旧 properties.py から移動。動作変更なし）
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Optional

from PySide6.QtWidgets import QWidget

import config
import db
from theme import (
    COLOR_BTN_CANCEL,
    COLOR_BTN_CANCEL_BORDER,
    COLOR_BTN_FETCH,
    COLOR_BTN_FETCH_BORDER,
    COLOR_BTN_SAVE,
    COLOR_BTN_SAVE_BORDER,
    COLOR_WHITE,
)

# 一括編集で値が異なる項目のプレースホルダー（書き換えれば一括上書き、そのままだと元の値を保持）
MULTI_PLACEHOLDER = "（複数選択）"


def _is_library_root(path: str) -> bool:
    """指定パスがライブラリフォルダそのものであればTrue（リネーム禁止のガード用）"""
    if not path or not path.strip():
        return False
    lib = (db.get_setting("library_folder") or "").strip()
    if not lib:
        return False
    return os.path.normpath(os.path.abspath(path)) == os.path.normpath(os.path.abspath(lib))


def _meta_source_for_apply(meta: dict, applied: dict) -> str | None:
    """メタ適用時の取得元キー。URL・DLSite API に基づく。dlsite, fanza, とらのあな, 同人DB, other のいずれかまたは None。"""
    did = (applied.get("dlsite_id") or "").strip()
    if meta.get("dojindb_url") or "dojindb.net" in did:
        return "同人DB"
    src = meta.get("source")
    if src == "とらのあな":
        return "とらのあな"
    if src == "FANZA":
        return "fanza"
    if src == "DLSite":
        return "dlsite"
    if src == "同人DB":
        return "同人DB"
    return db._effective_meta_source("", did) or None


# pykakasi（新API）によるフリガナ自動生成
try:
    import pykakasi

    _KKS = pykakasi.kakasi()
except Exception:  # pykakasi 未インストールなど
    _KKS = None


# ボタン用スタイル（theme の定数を使用）
BTN_SAVE_STYLE = f"""
    QPushButton {{
        background: {COLOR_BTN_SAVE}; color: {COLOR_WHITE};
        border: 1px solid {COLOR_BTN_SAVE_BORDER}; border-radius: {config.PROP_ACTION_BTN_RADIUS}px;
        padding: {config.PROP_ACTION_BTN_PADDING_Y}px {config.PROP_ACTION_BTN_PADDING_X}px; font-size: {config.FONT_SIZE_BTN_ACTION}px;
    }}
    QPushButton:hover {{ background: {COLOR_BTN_SAVE_BORDER}; }}
"""
BTN_CANCEL_STYLE = f"""
    QPushButton {{
        background: {COLOR_BTN_CANCEL}; color: {COLOR_WHITE};
        border: 1px solid {COLOR_BTN_CANCEL_BORDER}; border-radius: {config.PROP_ACTION_BTN_RADIUS}px;
        padding: {config.PROP_ACTION_BTN_PADDING_Y}px {config.PROP_ACTION_BTN_PADDING_X}px; font-size: {config.FONT_SIZE_BTN_ACTION}px;
    }}
    QPushButton:hover {{ background: {COLOR_BTN_CANCEL_BORDER}; }}
"""
BTN_FETCH_STYLE = f"""
    QPushButton {{
        background: {COLOR_BTN_FETCH}; color: {COLOR_WHITE};
        border: 1px solid {COLOR_BTN_FETCH_BORDER}; border-radius: {config.PROP_ACTION_BTN_RADIUS}px;
        padding: {config.PROP_FETCH_BTN_PADDING_Y}px {config.PROP_FETCH_BTN_PADDING_X}px; font-size: {config.FONT_SIZE_CONTEXT_MENU}px;
    }}
    QPushButton:hover {{ background: {COLOR_BTN_FETCH_BORDER}; }}
"""


def _parse_multi(text: str) -> list[str]:
    """カンマ・空白区切りの文字列をリストに変換"""
    if not text.strip():
        return []
    return [v.strip() for v in re.split(r"[,\s]+", text.strip()) if v.strip()]


def _auto_kana(text: str) -> str:
    if not text:
        return ""
    if _KKS is None:
        return text
    try:
        result = _KKS.convert(text)
        kana = "".join(item["hira"] if item["hira"] else item["orig"] for item in result)
        return kana
    except Exception:
        return text


def _needs_kana_conversion(text: str) -> bool:
    """漢字が含まれていたら再変換が必要と判定"""
    for ch in text:
        if unicodedata.category(ch) in ("Lo",) and "\u4e00" <= ch <= "\u9fff":
            return True
    return False


class PropertyFormContext:
    """プロパティフォーム用のコンテキスト。プラグインが get_property_buttons(context) で受け取り、ボタンから fetch_by_id / open_meta_search を呼ぶために使う。"""

    def __init__(self, form: QWidget):
        self._form = form

    def fetch_by_id(self) -> None:
        """作品ID欄の値でメタ取得してフォームに反映する。"""
        if hasattr(self._form, "_on_fetch_meta"):
            self._form._on_fetch_meta()

    def open_meta_search(self) -> None:
        """メタデータ検索ダイアログを開き、適用結果をフォームに反映する。"""
        if hasattr(self._form, "_on_meta_search"):
            self._form._on_meta_search()

    def get_parent(self) -> QWidget:
        """ボタンなどの親ウィジェット（ダイアログ／パネル）。"""
        return self._form

