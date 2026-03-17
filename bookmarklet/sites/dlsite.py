from __future__ import annotations
import re
from bs4 import BeautifulSoup
from bookmarklet.base import BookmarkletParser


class DLsiteParser(BookmarkletParser):

    def can_handle(self, url: str) -> bool:
        return "dlsite.com" in url

    def parse(self, url: str, html: str) -> dict:
        # product_id を URLから抽出
        m = re.search(r"(RJ|BJ|VJ)\d+", url, re.IGNORECASE)
        dlsite_id = m.group(0).upper() if m else ""

        soup = BeautifulSoup(html, "html.parser")

        # 作品名
        title = ""
        title_el = soup.select_one("#work_name") or soup.select_one("h1[itemprop='name']")
        if title_el:
            title = title_el.get_text(strip=True)

        # サークル
        circle = ""
        circle_el = soup.select_one("span.maker_name a") or soup.select_one("a[href*='maker_id']")
        if circle_el:
            circle = circle_el.get_text(strip=True)

        # 作者
        author = ""

        def _match_author_th(tag):
            return tag.name == "th" and "作者" in tag.get_text()

        author_th = soup.find(_match_author_th)
        if author_th:
            row = author_th.find_parent("tr")
            if row:
                td = row.find("td")
                if td:
                    author = td.get_text(strip=True)

        # ジャンル/タグ
        tags = []
        genre_links = soup.select("div.main_genre a") or soup.select("a[href*='genre']")
        for g in genre_links:
            t = g.get_text(strip=True)
            if t and t not in tags:
                tags.append(t)

        # 発売日
        release_date = ""

        def _match_date_th(tag):
            return tag.name == "th" and ("販売日" in tag.get_text() or "発売日" in tag.get_text())

        date_th = soup.find(_match_date_th)
        if date_th:
            row = date_th.find_parent("tr")
            if row:
                td = row.find("td")
                if td:
                    release_date = td.get_text(strip=True)

        # 価格
        price = None

        def _match_price_th(tag):
            return tag.name == "th" and "価格" in tag.get_text()

        price_th = soup.find(_match_price_th)
        price_el = None
        if price_th:
            row = price_th.find_parent("tr")
            if row:
                price_el = row.find("td")
        if not price_el:
            price_el = soup.find("span", id="work_price") or soup.find(class_="price")
        if price_el:
            pm = re.search(r"(\d[\d,]*)\s*円", price_el.get_text())
            if pm:
                try:
                    price = int(pm.group(1).replace(",", ""))
                except ValueError:
                    price = None

        # サムネイルURL
        cover_url = ""
        img_el = (
            soup.select_one("div.product-slider img")
            or soup.select_one("li.slider_item.active img")
            or soup.select_one("li.slider_item img")
            or soup.select_one("picture img")
            or soup.select_one("img[itemprop='image']")
        )
        if img_el:
            cover_url = img_el.get("src") or img_el.get("data-src") or ""
            if cover_url.startswith("//"):
                cover_url = "https:" + cover_url

        return {
            "title": title,
            "circle": circle,
            "author": author,
            "dlsite_id": dlsite_id,
            "tags": tags,
            "price": price,
            "release_date": release_date,
            "cover_url": cover_url,
            "site": "dlsite",
        }

