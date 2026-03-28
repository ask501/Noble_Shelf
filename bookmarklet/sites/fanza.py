from __future__ import annotations
import json
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bookmarklet.base import BookmarkletParser


class FanzaParser(BookmarkletParser):

    def can_handle(self, url: str) -> bool:
        return "dmm.co.jp" in url or "fanza.com" in url

    def parse(self, url: str, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        # JSON-LDからname/brand/sku/offers/imageを取得
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

        fanza_id = ld.get("sku", "") if isinstance(ld, dict) else ""

        if not fanza_id:
            # URL パスの末尾セグメントから ID を抽出
            # 例: https://book.dmm.co.jp/product/4032985/b158aakn01146/
            # → b158aakn01146
            try:
                path_parts = [p for p in urlparse(url).path.split("/") if p]
                if path_parts:
                    fanza_id = path_parts[-1]
            except Exception:
                pass

        offers = ld.get("offers", {}) if isinstance(ld, dict) else {}
        try:
            price = int(float(offers.get("price", 0))) if isinstance(offers, dict) else None
            price = price or None
        except (ValueError, TypeError):
            price = None

        cover_url = ld.get("image", "") if isinstance(ld, dict) else ""
        if isinstance(cover_url, list):
            cover_url = cover_url[0] if cover_url else ""
        if isinstance(cover_url, str) and cover_url.startswith("//"):
            cover_url = "https:" + cover_url

        store_url = url

        # HTMLのinformationListから作者・発売日を取得
        author = ""
        release_date = ""
        for dl in soup.find_all("dl", class_=lambda c: c and "informationList" in c):
            dt = dl.find("dt")
            dd = dl.find("dd")
            if not dt or not dd:
                continue
            label = dt.get_text(strip=True)
            value = dd.get_text(strip=True)
            if label == "作者" and not author:
                author = value
            elif label == "配信開始日" and not release_date:
                # "2021/08/13 00:00" -> "2021-08-13"
                release_date = value.split()[0].replace("/", "-")

        # タグはgenreTagListから取得
        tags: list[str] = []
        ul = soup.find("ul", class_="genreTagList")
        if ul:
            tags = [
                a.get_text(strip=True)
                for a in ul.find_all("a", class_="genreTag__txt")
                if a.get_text(strip=True)
            ]

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

