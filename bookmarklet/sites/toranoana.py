from __future__ import annotations
from bookmarklet.base import BookmarkletParser


class ToranoanaParser(BookmarkletParser):
    def can_handle(self, url: str) -> bool:
        return "toranoana.jp" in url

    def parse(self, url: str, html: str) -> dict:
        return {
            "title": "",
            "circle": "",
            "author": "",
            "tags": [],
            "price": None,
            "release_date": "",
            "cover_url": "",
            "site": "toranoana",
        }

