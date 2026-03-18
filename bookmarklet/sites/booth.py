from __future__ import annotations
from bookmarklet.base import BookmarkletParser


class BoothParser(BookmarkletParser):
    def can_handle(self, url: str) -> bool:
        return "booth.pm" in url

    def parse(self, url: str, html: str) -> dict:
        store_url = url.split("?")[0]
        return {
            "title": "",
            "circle": "",
            "author": "",
            "tags": [],
            "price": None,
            "release_date": "",
            "cover_url": "",
             "store_url": store_url,
            "site": "booth",
        }

