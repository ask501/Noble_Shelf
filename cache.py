"""アプリ全体で使う汎用インメモリキャッシュ。"""
from __future__ import annotations
from typing import Callable, TypeVar

T = TypeVar("T")
_store: dict[str, object] = {}


def get(key: str, fetch_fn: Callable[[], T]) -> T:
    """キャッシュがあれば返し、なければ fetch_fn() を呼んで保存してから返す。"""
    if key not in _store:
        _store[key] = fetch_fn()
    return _store[key]  # type: ignore[return-value]


def invalidate(*keys: str) -> None:
    """指定キーを削除する。キーを省略すると全クリア。"""
    if keys:
        for k in keys:
            _store.pop(k, None)
    else:
        _store.clear()
