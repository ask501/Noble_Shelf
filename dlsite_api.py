# dlsite_api.py - DLSite / FANZA / とらのあな からメタデータを取得
import asyncio
import re
import unicodedata
from urllib.parse import quote
from typing import Optional, List, Dict, Any, Tuple


def _normalize_query(q: str) -> str:
    """検索クエリを NFKC 正規化（全角→半角・合成済みかななどに統一）。ヒットしやすくする。"""
    if not q or not isinstance(q, str):
        return (q or "").strip()
    return unicodedata.normalize("NFKC", q.strip())

# 依存パッケージのチェック
HAS_AIOHTTP = False
HAS_BS4 = False
MISSING_PACKAGES = []

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    MISSING_PACKAGES.append("aiohttp")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    MISSING_PACKAGES.append("beautifulsoup4")

try:
    from dlsite_async import DlsiteAPI
    HAS_DLSITE_ASYNC = True
except ImportError:
    HAS_DLSITE_ASYNC = False


# サポートするサイト
SITES = ["DLSite", "FANZA", "とらのあな", "同人DB"]


def is_available() -> bool:
    """API が利用可能か"""
    return HAS_AIOHTTP and HAS_BS4


def get_missing_packages() -> List[str]:
    """不足しているパッケージのリストを返す"""
    return MISSING_PACKAGES


async def search_dlsite(query: str, max_results: int = 10, search_by: str = "title") -> List[Dict[str, str]]:
    """
    DLSite で検索し、候補リストを返す（部分一致検索）。
    search_by: "title" = 作品名, "circle" = サークル名, "author" = 作者名（maker名で検索）
    返り値: [{"id": "RJ123456", "title": "作品名", "circle": "サークル名"}, ...]
    """
    if not HAS_AIOHTTP or not HAS_BS4:
        return []
    query = _normalize_query(query)
    if not query:
        return []
    results = []
    encoded = quote(query, safe="")
    
    # 検索URL（サークル名・作者名検索の場合は maker_name パラメータを使用）
    base = "https://www.dlsite.com/maniax/fsr/=/language/jp/sex_category%5B0%5D/male/work_category%5B0%5D/doujin/work_category%5B1%5D/books/work_category%5B2%5D/pc/work_category%5B3%5D/app/order%5B0%5D/trend/options_and_or/and/ana_flg/all"
    if search_by in ("circle", "author"):
        url = f"{base}/keyword_maker_name/{encoded}/per_page/{max_results}/page/1/from/fs.header"
    else:
        url = f"{base}/keyword/{encoded}/per_page/{max_results}/page/1/from/fs.header"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.9",
        "Cookie": "adultchecked=1; locale=ja-jp",
        "Referer": "https://www.dlsite.com/",
    }
    # 設定でカスタムCookieがあれば上書き
    try:
        import db
        cookie = (db.get_setting("cookie_dlsite") or "").strip()
        if cookie:
            headers["Cookie"] = cookie
    except Exception:
        pass
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
        
        soup = BeautifulSoup(html, "html.parser")
        results = []
        seen_ids = set()

        for a in soup.find_all("a", href=re.compile(r"product_id/(RJ|BJ|VJ)\d+", re.IGNORECASE)):
            href = a.get("href", "")
            match = re.search(r"(RJ|BJ|VJ)\d+", href, re.IGNORECASE)
            if not match:
                continue

            prod_id = match.group(0).upper()
            if prod_id in seen_ids:
                continue
            seen_ids.add(prod_id)

            title = a.get("title") or a.get_text(strip=True) or ""
            if not title or len(title) < 2:
                continue

            # サークル名: 親要素を遡って maker_id リンクを探す
            circle = ""
            for parent in a.parents:
                maker_link = parent.find("a", href=re.compile(r"maker_id"))
                if maker_link:
                    circle = maker_link.get_text(strip=True)
                    break
                if parent.name in ("body", "html"):
                    break

            results.append({
                "id": prod_id,
                "title": title,
                "circle": circle,
            })

            if len(results) >= max_results:
                break

    except Exception:
        pass

    return results


async def get_metadata(product_id: str) -> Optional[Dict[str, Any]]:
    """
    DLSite 作品IDからメタデータを取得。
    作品IDは RJ / BJ / VJ 形式（DLSITE_API 対応）に対応。
    返り値: {
        "title": str,
        "circle": str,
        "author": str,
        "parody": str,  # シリーズ/パロディ
        "characters": List[str],
        "tags": List[str],
        "title_kana": str,   # 作品名フリガナ（取得できる場合）
        "circle_kana": str,  # サークル名フリガナ（取得できる場合）
        "pages": Optional[int],
        "release_date": str,
        "price": Optional[int],
        "source": "DLSITE",
        "id": str,
    }
    """
    if HAS_DLSITE_ASYNC:
        return await _get_metadata_via_lib(product_id)
    elif HAS_AIOHTTP:
        return await _get_metadata_via_scrape(product_id)
    return None


async def _get_metadata_via_lib(product_id: str) -> Optional[Dict[str, Any]]:
    """dlsite-async ライブラリを使用"""
    try:
        async with DlsiteAPI() as api:
            work = await api.get_work(product_id)

            authors = []
            if hasattr(work, "author") and work.author:
                authors = work.author if isinstance(work.author, list) else [work.author]

            tags = []
            if hasattr(work, "genre") and work.genre:
                tags = list(work.genre) if isinstance(work.genre, (list, tuple)) else [work.genre]

            # パロディ/シリーズ（ジャンルから推測、または空）
            parody = ""
            # キャラクター（DLSite APIでは直接取得できない場合が多い）
            characters = []

            # 追加フィールド（ライブラリから取得できる範囲で）
            pages = getattr(work, "pages", None) or getattr(work, "volume", None)
            release_date = getattr(work, "sales_date", None) or ""
            price = getattr(work, "price", None)

            # 画像URL
            image_url = ""
            if hasattr(work, "work_image") and work.work_image:
                image_url = work.work_image

            return {
                "title": work.work_name or "",
                "circle": work.circle or "",
                "author": ", ".join(authors),
                "parody": parody,
                "characters": characters,
                "tags": tags,
                "title_kana": "",
                "circle_kana": "",
                "pages": pages,
                "release_date": release_date,
                "price": price,
                "source": "DLSITE",
                "id": product_id,
                "image_url": image_url,
            }
    except Exception:
        return await _get_metadata_via_scrape(product_id)


async def _get_metadata_via_scrape(product_id: str) -> Optional[Dict[str, Any]]:
    """HTMLスクレイピングでメタデータ取得"""
    if not HAS_AIOHTTP:
        return None
    
    # 作品ページURL（成人向け/全年齢を試す）
    urls = [
        f"https://www.dlsite.com/maniax/work/=/product_id/{product_id}.html",
        f"https://www.dlsite.com/home/work/=/product_id/{product_id}.html",
        f"https://www.dlsite.com/comic/work/=/product_id/{product_id}.html",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ja,en;q=0.9",
        "Cookie": "adultchecked=1",
    }
    # 設定でカスタムCookieがあれば上書き
    try:
        import db
        cookie = (db.get_setting("cookie_dlsite") or "").strip()
        if cookie:
            headers["Cookie"] = cookie
    except Exception:
        pass
    
    html = None
    try:
        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            break
                except Exception:
                    continue
    except Exception:
        return None
    
    if not html:
        return None
    
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
    # テーブル内の「作者」行を探して td を取得
    def _match_author_th(tag):
        return tag.name == "th" and "作者" in tag.get_text()
    author_th = soup.find(_match_author_th)
    author_el = None
    if author_th:
        row = author_th.find_parent("tr")
        if row:
            author_el = row.find("td")
    if not author_el:
        author_el = soup.find("a", href=re.compile("author"))
    if author_el:
        author = author_el.get_text(strip=True)
    
    # シリーズ/パロディ
    parody = ""
    def _match_series_th(tag):
        return tag.name == "th" and "シリーズ" in tag.get_text()
    series_th = soup.find(_match_series_th)
    parody_el = None
    if series_th:
        row = series_th.find_parent("tr")
        if row:
            parody_el = row.find("a")
    if parody_el:
        parody = parody_el.get_text(strip=True)
    
    # ジャンル/タグ
    tags = []
    genre_links = soup.select("div.main_genre a") or soup.select("a[href*='genre']")
    for g in genre_links:
        t = g.get_text(strip=True)
        if t and t not in tags:
            tags.append(t)
    
    # キャラクター（DLSiteでは通常取得不可）
    characters = []

    # ページ数
    pages = None
    def _match_pages_th(tag):
        return tag.name == "th" and "ページ数" in tag.get_text()
    pages_th = soup.find(_match_pages_th)
    pages_el = None
    if pages_th:
        row = pages_th.find_parent("tr")
        if row:
            pages_el = row.find("td")
    if pages_el:
        import re as _re
        m = _re.search(r"(\d+)", pages_el.get_text())
        if m:
            try:
                pages = int(m.group(1))
            except ValueError:
                pages = None

    # 発売日/販売日
    release_date = ""
    def _match_date_th(tag):
        return tag.name == "th" and ("販売日" in tag.get_text() or "発売日" in tag.get_text())
    date_th = soup.find(_match_date_th)
    rel_el = None
    if date_th:
        row = date_th.find_parent("tr")
        if row:
            rel_el = row.find("td")
    if rel_el:
        release_date = rel_el.get_text(strip=True)

    # 金額
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
        import re as _re2
        m = _re2.search(r"(\d[\d,]*)\s*円", price_el.get_text())
        if m:
            try:
                price = int(m.group(1).replace(",", ""))
            except ValueError:
                price = None

    # サムネイル画像URL
    image_url = ""
    img_el = soup.select_one("img[itemprop='image']") or soup.select_one("div.product-slider-data img") or soup.select_one("img.target_type")
    if img_el:
        image_url = img_el.get("src") or img_el.get("data-src") or ""
        if image_url and image_url.startswith("//"):
            image_url = "https:" + image_url

    return {
        "title": title,
        "circle": circle,
        "author": author,
        "parody": parody,
        "characters": characters,
        "tags": tags,
        "title_kana": "",
        "circle_kana": "",
        "pages": pages,
        "release_date": release_date,
        "price": price,
        "source": "DLSITE",
        "id": product_id,
        "image_url": image_url,
    }


def search_dlsite_sync(query: str, max_results: int = 10, search_by: str = "title") -> List[Dict[str, str]]:
    """同期版の検索（UIスレッドから呼ぶ用）"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(search_dlsite(query, max_results, search_by))
    except Exception:
        return []
    finally:
        loop.close()


def get_metadata_sync(product_id: str, source: str = "DLSite") -> Optional[Dict[str, Any]]:
    """同期版のメタデータ取得"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        if source == "FANZA":
            return loop.run_until_complete(get_fanza_metadata(product_id))
        elif source == "とらのあな":
            return loop.run_until_complete(get_toranoana_metadata(product_id))
        else:
            return loop.run_until_complete(get_metadata(product_id))
    except Exception:
        return None
    finally:
        loop.close()


# ============================================================
# FANZA (DMM) 検索・メタデータ取得
# ============================================================

async def search_fanza(query: str, max_results: int = 10, search_by: str = "title") -> List[Dict[str, str]]:
    """FANZAで検索"""
    if not HAS_AIOHTTP or not HAS_BS4:
        return []
    query = _normalize_query(query)
    if not query:
        return []
    results = []
    encoded = quote(query, safe="")
    
    # FANZA同人検索URL
    url = f"https://www.dmm.co.jp/dc/doujin/-/list/narrow/=/word={encoded}/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.9",
        "Cookie": "age_check_done=1",
    }
    # 設定でカスタムCookieがあれば上書き
    try:
        import db
        cookie_val = (db.get_setting("cookie_fanza") or "").strip()
        if cookie_val:
            headers["Cookie"] = cookie_val
    except Exception:
        cookie_val = ""
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
        
        soup = BeautifulSoup(html, "html.parser")
        seen_ids = set()

        # 作品リストを探す
        items = soup.select("li.productList__item, div.d-item, ul.d-item li")
        
        for item in items:
            # 作品リンクを探す
            link = item.find("a", href=re.compile(r"(d\d+|cid=d\d+)", re.IGNORECASE))
            if not link:
                link = item.find("a", href=re.compile(r"/dc/doujin/"))
            if not link:
                continue
            
            href = link.get("href", "")
            # 作品ID抽出 (d_123456 形式)
            match = re.search(r"[=/](d\d+)|cid=(d\d+)", href, re.IGNORECASE)
            if not match:
                continue
            
            prod_id = (match.group(1) or match.group(2)).lower()
            if prod_id in seen_ids:
                continue
            seen_ids.add(prod_id)
            
            # タイトル
            title_el = item.find("span", class_="title") or item.find("p", class_="title") or link
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 2:
                continue
            
            # サークル名
            circle = ""
            circle_el = item.find("span", class_="circle") or item.find("p", class_="maker")
            if circle_el:
                circle = circle_el.get_text(strip=True)
            
            results.append({
                "id": prod_id,
                "title": title[:60],
                "circle": circle,
                "source": "FANZA",
            })
            
            if len(results) >= max_results:
                break
        
        # フォールバック: 全リンクから探す
        if not results:
            for link in soup.find_all("a", href=re.compile(r"/dc/doujin/-/detail/")):
                href = link.get("href", "")
                match = re.search(r"cid=(d\d+)", href, re.IGNORECASE)
                if not match:
                    continue
                
                prod_id = match.group(1).lower()
                if prod_id in seen_ids:
                    continue
                seen_ids.add(prod_id)
                
                title = link.get("title") or link.get_text(strip=True) or ""
                if not title or len(title) < 2:
                    continue
                
                results.append({
                    "id": prod_id,
                    "title": title[:60],
                    "circle": "",
                    "source": "FANZA",
                })
                
                if len(results) >= max_results:
                    break
        
    except Exception:
        pass

    return results


async def get_fanza_metadata(product_id: str) -> Optional[Dict[str, Any]]:
    """FANZAから作品メタデータを取得"""
    if not HAS_AIOHTTP or not HAS_BS4:
        return None
    
    url = f"https://www.dmm.co.jp/dc/doujin/-/detail/=/cid={product_id}/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ja,en;q=0.9",
        "Cookie": "age_check_done=1",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
        
        soup = BeautifulSoup(html, "html.parser")
        
        # タイトル
        title = ""
        title_el = soup.select_one("h1.productTitle__txt") or soup.select_one("h1#title")
        if title_el:
            title = title_el.get_text(strip=True)
        
        # サークル
        circle = ""
        circle_el = soup.select_one("a[href*='article=maker']") or soup.select_one(".circleName__txt")
        if circle_el:
            circle = circle_el.get_text(strip=True)
        
        # 作者
        author = ""
        author_el = soup.select_one("a[href*='article=author']")
        if author_el:
            author = author_el.get_text(strip=True)
        
        # タグ/ジャンル
        tags = []
        genre_els = soup.select("a[href*='article=genre']")
        for g in genre_els:
            t = g.get_text(strip=True)
            if t and t not in tags:
                tags.append(t)
        
        # シリーズ
        parody = ""
        series_el = soup.select_one("a[href*='article=series']")
        if series_el:
            parody = series_el.get_text(strip=True)

        # ページ数（あれば）
        pages = None
        pages_el = soup.find("th", string=re.compile("ページ", re.I))
        if pages_el and pages_el.parent:
            import re as _re3
            m = _re3.search(r"(\d+)", pages_el.parent.get_text())
            if m:
                try:
                    pages = int(m.group(1))
                except ValueError:
                    pages = None

        # 発売日
        release_date = ""
        rel_el = soup.find("th", string=re.compile("配信開始日|販売開始日|発売日"))  # だいたいこのどれか
        if rel_el and rel_el.parent:
            release_date = rel_el.parent.get_text(strip=True)

        # 価格
        price = None
        price_el = soup.select_one("span.price, p.price") or soup.find("th", string=re.compile("価格"))
        if price_el:
            txt = price_el.get_text()
            import re as _re4
            m = _re4.search(r"(\d[\d,]*)\s*円", txt)
            if m:
                try:
                    price = int(m.group(1).replace(",", ""))
                except ValueError:
                    price = None

        # サムネイル画像URL
        image_url = ""
        img_el = soup.select_one("img.productImage__img") or soup.select_one("div.productPreview__item img")
        if img_el:
            image_url = img_el.get("src") or img_el.get("data-src") or ""

        return {
            "title": title,
            "circle": circle,
            "author": author,
            "parody": parody,
            "characters": [],
            "tags": tags,
            "pages": pages,
            "release_date": release_date,
            "price": price,
            "source": "FANZA",
            "id": product_id,
            "image_url": image_url,
        }
        
    except Exception:
        return None


# ============================================================
# とらのあな 検索・メタデータ取得
# ============================================================

async def search_toranoana(query: str, max_results: int = 10, search_by: str = "title") -> List[Dict[str, str]]:
    """とらのあなで検索"""
    if not HAS_AIOHTTP or not HAS_BS4:
        return []
    query = _normalize_query(query)
    if not query:
        return []
    results = []
    encoded = quote(query, safe="")
    
    # とらのあな検索URL
    url = f"https://ec.toranoana.jp/tora_r/ec/app/catalog/list/?searchWord={encoded}&commodity_kind_name=%E5%90%8C%E4%BA%BA%E8%AA%8C"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.9",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
        
        soup = BeautifulSoup(html, "html.parser")
        seen_ids = set()
        
        # 作品アイテムを探す
        items = soup.select("div.product-list-item, li.product-item, div.item-box")
        
        for item in items:
            # 作品リンクを探す
            link = item.find("a", href=re.compile(r"item/\d+"))
            if not link:
                link = item.find("a", href=re.compile(r"/ec/tora_r/ec/item/"))
            if not link:
                continue
            
            href = link.get("href", "")
            match = re.search(r"item/(\d+)", href)
            if not match:
                continue
            
            prod_id = match.group(1)
            if prod_id in seen_ids:
                continue
            seen_ids.add(prod_id)
            
            # タイトル
            title_el = item.find("p", class_="title") or item.find("span", class_="title") or link
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 2:
                continue
            
            # サークル名
            circle = ""
            circle_el = item.find("p", class_="circle") or item.find("span", class_="circle")
            if circle_el:
                circle = circle_el.get_text(strip=True)
            
            results.append({
                "id": prod_id,
                "title": title[:60],
                "circle": circle,
                "source": "とらのあな",
            })
            
            if len(results) >= max_results:
                break
        
        # フォールバック
        if not results:
            for link in soup.find_all("a", href=re.compile(r"/item/\d+")):
                href = link.get("href", "")
                match = re.search(r"item/(\d+)", href)
                if not match:
                    continue
                
                prod_id = match.group(1)
                if prod_id in seen_ids:
                    continue
                seen_ids.add(prod_id)
                
                title = link.get("title") or link.get_text(strip=True) or ""
                if not title or len(title) < 2:
                    continue
                
                results.append({
                    "id": prod_id,
                    "title": title[:60],
                    "circle": "",
                    "source": "とらのあな",
                })
                
                if len(results) >= max_results:
                    break
        
    except Exception:
        pass
    return results


async def get_toranoana_metadata(product_id: str) -> Optional[Dict[str, Any]]:
    """とらのあなから作品メタデータを取得"""
    if not HAS_AIOHTTP or not HAS_BS4:
        return None
    
    url = f"https://ec.toranoana.jp/tora_r/ec/item/{product_id}/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ja,en;q=0.9",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
        
        soup = BeautifulSoup(html, "html.parser")
        
        # タイトル
        title = ""
        title_el = soup.select_one("h1.product-title") or soup.select_one("h1")
        if title_el:
            title = title_el.get_text(strip=True)
        
        # サークル
        circle = ""
        circle_el = soup.select_one("a[href*='circle']") or soup.select_one(".circle-name")
        if circle_el:
            circle = circle_el.get_text(strip=True)
        
        # 作者
        author = ""
        author_el = soup.select_one("a[href*='author']") or soup.select_one(".author-name")
        if author_el:
            author = author_el.get_text(strip=True)
        
        # ジャンル/タグ
        tags = []
        genre_els = soup.select("a[href*='genre']") or soup.select(".genre-tag")
        for g in genre_els:
            t = g.get_text(strip=True)
            if t and t not in tags:
                tags.append(t)
        
        # 原作/パロディ
        parody = ""
        parody_el = soup.select_one("a[href*='original']") or soup.select_one(".original-name")
        if parody_el:
            parody = parody_el.get_text(strip=True)
        
        # キャラクター
        characters = []
        char_els = soup.select("a[href*='character']")
        for c in char_els:
            ch = c.get_text(strip=True)
            if ch and ch not in characters:
                characters.append(ch)
        
        # サムネイル画像URL
        image_url = ""
        img_el = soup.select_one("img.product-image") or soup.select_one("div.product-img img")
        if img_el:
            image_url = img_el.get("src") or img_el.get("data-src") or ""
            if image_url and image_url.startswith("//"):
                image_url = "https:" + image_url
        
        return {
            "title": title,
            "circle": circle,
            "author": author,
            "parody": parody,
            "characters": characters,
            "tags": tags,
            "source": "とらのあな",
            "id": product_id,
            "image_url": image_url,
        }
        
    except Exception:
        return None


# ============================================================
# 同人DB検索
# ============================================================

async def search_dojindb(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """同人DBで作品を検索する"""
    if not HAS_AIOHTTP or not HAS_BS4:
        return []
    query = _normalize_query(query)
    if not query:
        return []
    encoded = quote(query, safe="")
    url = f"https://dojindb.net/s/?s={encoded}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ja,en;q=0.9",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
        from bs4 import BeautifulSoup as _BS4

        soup = _BS4(html, "html.parser")
        results: List[Dict[str, str]] = []
        seen_ids: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"/w/(\d+)", href)
            if not m:
                continue
            wid = m.group(1)
            if wid in seen_ids:
                continue
            title = a.get_text(strip=True)
            if title:
                results.append({
                    "id": wid,
                    "title": title,
                    "circle": "",
                    "source": "同人DB",
                    "url": f"https://dojindb.net/w/{wid}",
                })
                seen_ids.add(wid)
            if len(results) >= max_results:
                break
        return results
    except Exception:
        return []


def search_dojindb_sync(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(search_dojindb(query, max_results))
    except Exception:
        return []
    finally:
        loop.close()


# ============================================================
# 複数サイト同時検索
# ============================================================

async def search_all_sites(query: str, max_results: int = 10, search_by: str = "title") -> Dict[str, List[Dict[str, str]]]:
    """
    全サイトで同時検索を行う
    返り値: {"DLSite": [...], "FANZA": [...], "とらのあな": [...]}
    """
    tasks = [
        search_dlsite(query, max_results, search_by),
        search_fanza(query, max_results, search_by),
        search_toranoana(query, max_results, search_by),
        search_dojindb(query, max_results),
    ]
    
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    site_results = {}
    for site, result in zip(SITES, results_list):
        if isinstance(result, Exception):
            site_results[site] = []
        else:
            # sourceを付加
            for r in result:
                r["source"] = site
            site_results[site] = result
    
    return site_results


def search_all_sites_sync(query: str, max_results: int = 10, search_by: str = "title") -> Dict[str, List[Dict[str, str]]]:
    """同期版の複数サイト同時検索"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(search_all_sites(query, max_results, search_by))
    except Exception:
        return {"DLSite": [], "FANZA": [], "とらのあな": [], "同人DB": []}
    finally:
        loop.close()


def search_fanza_sync(query: str, max_results: int = 10, search_by: str = "title") -> List[Dict[str, str]]:
    """同期版のFANZA検索（.dmme追加時にメタ取得用）"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(search_fanza(query, max_results, search_by))
    except Exception:
        return []
    finally:
        loop.close()


# ============================================================
# 同人DB (dojindb.net) スクレイピング
# ============================================================

def get_dojindb_metadata(url: str) -> Optional[Dict[str, Any]]:
    """
    同人DBのURLからメタデータをスクレイピングして返す。
    返り値: {
        "title": str,
        "circle": str,
        "tags": List[str],
        "id": str,        # DLSite ID (RJxxxxxx)
        "source": "DOJINDB",
    }
    """
    try:
        import urllib.request
        import re as _re

        if not HAS_BS4:
            return None

        from bs4 import BeautifulSoup as _BS4

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            html = res.read().decode("utf-8", errors="replace")

        soup = _BS4(html, "html.parser")

        # タイトル
        title_tag = soup.find("title")
        title = ""
        if title_tag:
            m = _re.match(r"^(.+?)\s*[\[【]", title_tag.get_text())
            title = m.group(1).strip() if m else title_tag.get_text(strip=True)

        # サークル: /c/?s= のリンク
        circle = ""
        c_link = soup.find("a", href=_re.compile(r"/c/\?s="))
        if c_link:
            circle = c_link.get_text(strip=True)

        # タグ: div.tags_box 内の label-tags リンクのみ取得
        tags: list[str] = []
        tags_box = soup.find("div", class_="tags_box")
        if tags_box:
            for a in tags_box.find_all("a", class_="label-tags"):
                t = a.get_text(strip=True)
                if t:
                    tags.append(t)
        else:
            # フォールバック: ページ内の全 label-tags から重複除去して取得
            all_tags = soup.find_all("a", class_="label-tags")
            seen = set()
            tags = [
                t
                for a in all_tags
                if (t := a.get_text(strip=True))
                and not (t in seen or seen.add(t))
            ]

        # DLSite ID（画像URLから抽出）
        m = _re.search(r"/(RJ\d+)_img", html)
        dlsite_id = m.group(1) if m else ""

        return {
            "title": title,
            "circle": circle,
            "author": "",
            "parody": "",
            "characters": [],
            "tags": tags,
            "id": dlsite_id,
            "dojindb_url": url,
            "source": "DOJINDB",
        }
    except Exception:
        return None
