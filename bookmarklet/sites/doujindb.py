from __future__ import annotations
import re
from bs4 import BeautifulSoup
from bookmarklet.base import BookmarkletParser


class DoujindbParser(BookmarkletParser):
    def can_handle(self, url: str) -> bool:
        return "dojindb.net" in url

    def parse(self, url: str, html: str) -> dict:
        title = ""
        circle = ""
        author = ""
        dlsite_id = ""
        tags: list[str] = []
        price: int | None = None
        release_date = ""
        cover_url = ""

        try:
            soup = BeautifulSoup(html or "", "html.parser")

            # title: span.work_title 直下のテキストノードのみ結合、なければ <title> から抽出
            title_el = soup.select_one("span.work_title")
            if title_el:
                title = "".join(t for t in title_el.strings if getattr(t, "parent", None) == title_el).strip()
            else:
                raw_title = (soup.title.get_text(strip=True) if soup.title else "").strip()
                m = re.match(r"^(.+?)\s*[\[【]", raw_title)
                title = (m.group(1).strip() if m else raw_title)

            # circle: a.link_circle
            circle_a = soup.find("a", class_="link_circle")
            circle = circle_a.get_text(strip=True) if circle_a else ""

            # release_date: table.mb0 内で「配信開始日」の次の td
            table = soup.select_one("table.mb0")
            if table:
                tds = table.find_all("td")
                for i, td in enumerate(tds):
                    if "配信開始日" in td.get_text(strip=True):
                        if i + 1 < len(tds):
                            release_date = tds[i + 1].get_text(strip=True)
                        break

            # tags: div.tags_box 内の label-tags。なければ全体から拾う
            box = soup.select_one("div.tags_box")
            tag_links = (box.select("a.label-tags") if box else []) or soup.select("a.label-tags")
            for a in tag_links:
                t = a.get_text(strip=True)
                if t and t not in tags:
                    tags.append(t)

            # cover_url: img.img-main の src
            img = soup.select_one("img.img-main")
            if img and img.get("src"):
                cover_url = str(img.get("src") or "").strip()
        except Exception:
            pass

        return {
            "title": title,
            "circle": circle,
            "author": author,
            "dlsite_id": dlsite_id,
            "tags": tags,
            "price": price,
            "release_date": release_date,
            "cover_url": cover_url,
            "store_url": url.split("?")[0],
            "site": "doujindb",
        }

