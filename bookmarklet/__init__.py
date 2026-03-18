from __future__ import annotations
from bookmarklet.sites.dlsite import DLsiteParser
from bookmarklet.sites.fanza import FanzaParser
from bookmarklet.sites.booth import BoothParser
from bookmarklet.sites.doujindb import DoujindbParser

_PARSERS = [
    DLsiteParser(),
    FanzaParser(),
    BoothParser(),
    DoujindbParser(),
]


def fetch_meta(url: str, html: str) -> dict:
    """
    URLとHTMLからメタデータを抽出して返す。
    対応サイトが見つからない場合は {"site": "unknown"} を返す。
    """
    for parser in _PARSERS:
        if parser.can_handle(url):
            return parser.parse(url, html)
    return {"site": "unknown"}
