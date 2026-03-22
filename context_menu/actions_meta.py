from __future__ import annotations

from PySide6.QtWidgets import QDialog

import db
from ui.dialogs.properties import MetaSearchDialog


def fetch_metadata(book: dict, parent_window) -> None:
    """BookContextMenu._on_fetch_metadata の中身をそのまま移動"""
    path = (book or {}).get("path", "")
    if not path:
        return
    dlg = MetaSearchDialog(parent_window)
    title = (book or {}).get("title", "") or (book or {}).get("name", "")
    if title:
        dlg._e_search.setText(title)
    try:
        cur_meta = db.get_book_meta(path) or {}
    except Exception:
        cur_meta = {}
    dlg._current_book = book
    dlg._current_meta = cur_meta
    if dlg.exec() != QDialog.Accepted:
        return
    on_updated = getattr(parent_window, "on_book_updated", None)
    if callable(on_updated):
        on_updated(path)

