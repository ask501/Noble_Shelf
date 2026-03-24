"""
scanners/base_scanner.py - スキャナ共通の抽象基底
"""
from __future__ import annotations


class BaseScanner:
    """全スキャナ共通の抽象基底クラス。
    各スキャナは media_type / folder_name を定義し scan() を実装する。"""

    media_type: str = ""
    folder_name: str = ""
    target_exts: set[str] = set()
    display_name_ja: str = ""

    def scan(
        self,
        folder: str,
        on_finished,
        on_progress=None,
        on_error=None,
        on_store_files_pending=None,
    ) -> None:
        raise NotImplementedError
