import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "time4magic"
BASE = "https://time4magic.pl"
URL = BASE + "/pokemon-trading-card-game"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126"}

async def fetch_page(session, page):
    url = URL if page == 1 else f"{URL}/{page}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None

def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    for tile in soup.select("product-tile"):
        pid = tile.get("product-id", "")
        if not pid:
            continue
        name = (tile.get("name") or "").strip()
        if not name:
            continue
        price_val = tile.get("price", "0")
        price = f"{price_val} PLN"
        text = tile.get_text(" ", strip=True).lower()
        available = "koszyk" in text and "brak" not in text
        link = tile.select_one("a[href]")
        href = ""
        if link:
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = BASE + href
        img = tile.select_one("img")
        image = ""
        if img:
            image = img.get("data-src") or img.get("src", "")
            if image and not image.startswith("http"):
                image = BASE + image
        products.append({"id": f"time4magic_{pid}", "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
    return products

async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html1 = await fetch_page(session, 1)
        if not html1:
            return []
        soup1 = BeautifulSoup(html1, "lxml")
        pages = set()
        for a in soup1.select("a[href]"):
            m = re.search(r"/pokemon-trading-card-game/(\d+)", a.get("href", ""))
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages) if pages else 1
        all_html = [html1]
        if max_page > 1:
            rest = await asyncio.gather(*[fetch_page(session, p) for p in range(2, max_page + 1)])
            all_html.extend(rest)
    for html in all_html:
        if not html:
            continue
        for prod in parse_page(html):
            if prod["id"] not in seen_ids:
                seen_ids.add(prod["id"])
                products.append(prod)
    print(f"[TIME4MAGIC] {len(products)} produktow")
    return products
