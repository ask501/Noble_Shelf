from __future__ import annotations
import json
import re
from bs4 import BeautifulSoup
from bookmarklet.base import BookmarkletParser


class FanzaParser(BookmarkletParser):

    def can_handle(self, url: str) -> bool:
        return "dmm.co.jp" in url or "fanza.com" in url

    def parse(self, url: str, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        # JSON-LDからメタデータ取得
        ld: dict = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = data[0]
                if isinstance(data, dict) and data.get("@type") == "Product":
                    ld = data
                    break
            except Exception:
                continue

        title = ld.get("name", "") if isinstance(ld, dict) else ""
        brand = ld.get("brand", "") if isinstance(ld, dict) else ""
        if isinstance(brand, dict):
            circle = brand.get("name", "")
        elif isinstance(brand, str):
            circle = brand
        else:
            circle = ""

        # subjectOf から詳細情報を取得
        subject = ld.get("subjectOf", {}) if isinstance(ld, dict) else {}

        # 作者
        author = ""
        author_data = subject.get("author", {}) if isinstance(subject, dict) else {}
        if isinstance(author_data, dict):
            names = author_data.get("name", "")
            if isinstance(names, list):
                author = ", ".join(names)
            else:
                author = names
        elif isinstance(author_data, list):
            author = ", ".join(a.get("name", "") for a in author_data if isinstance(a, dict))

        # 発売日
        release_date = subject.get("dateCreated", "") if isinstance(subject, dict) else ""

        # タグ
        tags: list[str] = []
        if isinstance(subject, dict):
            genre = subject.get("genre", [])
            if isinstance(genre, list):
                tags = [g for g in genre if g]
            elif isinstance(genre, str):
                tags = [genre] if genre else []

        cover_url = ld.get("image", "") if isinstance(ld, dict) else ""
        if cover_url and isinstance(cover_url, str) and cover_url.startswith("//"):
            cover_url = "https:" + cover_url

        # 価格（offers から）
        price = None
        offers = ld.get("offers", {}) if isinstance(ld, dict) else {}
        if isinstance(offers, dict):
            try:
                price = int(float(offers.get("price", 0))) or None
            except (ValueError, TypeError):
                price = None

        # FANZA ID（URLから抽出）
        fanza_id = ""
        m = re.search(r"/product/\d+/([a-z0-9]+)/?", url)
        if m:
            fanza_id = m.group(1)

        # ストアURL: クエリパラメータを除いたURL
        store_url = url.split("?")[0].rstrip("/") + "/"

        return {
            "title":        title,
            "circle":       circle,
            "author":       author,
            "dlsite_id":    fanza_id,
            "tags":         tags,
            "price":        price,
            "release_date": release_date,
            "cover_url":    cover_url,
            "store_url":    store_url,
            "site":         "fanza",
        }

