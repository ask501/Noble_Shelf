from __future__ import annotations
from abc import ABC, abstractmethod


class BookmarkletParser(ABC):
    """サイト別パーサーの基底クラス"""

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """このパーサーが対象URLを処理できるか判定する"""
        ...

    @abstractmethod
    def parse(self, url: str, html: str) -> dict:
        """
        URLとHTMLからメタデータを抽出して返す。
        戻り値のキー:
            title        : str
            circle       : str
            author       : str
            dlsite_id    : str
            tags         : list[str]
            price        : int | None
            release_date : str
            cover_url    : str
            site         : str  # サイト識別子 例: "dlsite"
        """
        ...

