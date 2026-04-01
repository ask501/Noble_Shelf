from __future__ import annotations

from typing import TypedDict


class BookRow(TypedDict):
    name: str
    circle: str
    title: str
    path: str
    cover_path: str
    is_dlst: int
    uuid: str
    missing_since_date: str
