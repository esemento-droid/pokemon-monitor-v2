import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "epiccard"
BASE = "https://epiccard.pl"
CAT = "/3-pokemon-tcg"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
MAX_PAGES = 5
PROXY = "http://127.0.0.1:8888"

async def fetch_page(session, page):
    url = f"{BASE}{CAT}" if page == 1 else f"{BASE}{CAT}?page={page}"
    try:
        async with session.get(url, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None

async def get_products():
    products = []
    seen_ids = set()

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        pages_html = await asyncio.gather(*[fetch_page(session, p) for p in range(1, MAX_PAGES + 1)])

    for html in pages_html:
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        for art in soup.select("article.product-miniature"):
            pid = art.get("data-id-product", "")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            title_el = art.select_one(".product-title a, h2 a")
            name = title_el.text.strip() if title_el else ""
            if not name:
                continue
            name_lower = name.lower()
            if any(ex in name_lower for ex in ["ultra pro", "sleeve", "album", "binder", "portfolio", "toploader", "deck box", "koszulk"]):
                continue
            href = title_el.get("href", "") if title_el else ""

            price_el = art.select_one("span.price")
            price = "brak"
            if price_el:
                price_txt = price_el.text.strip()
                m = re.search(r"[\d]+[,,][\d]{2}", price_txt.replace("\xa0", ""))
                if m:
                    price = f"{m.group(0)} zl"

            img_el = art.select_one("img")
            image = ""
            if img_el:
                image = img_el.get("data-src") or img_el.get("src") or ""

            txt = art.get_text(" ", strip=True).lower()
            available = "brak" not in txt and "niedost" not in txt

            products.append({
                "id": f"epiccard_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": href,
                "image": image,
                "stock": 1 if available else 0,
                "available": available,
            })

    print(f"[EPICCARD] {len(products)} produktow")
    return products
