import asyncio
import aiohttp
from bs4 import BeautifulSoup

SHOP = "pikatube"
BASE = "https://pikatube.pl"
CAT_URL = BASE + "/pl/c/Pokemon-TCG-ENG/38"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = ["sleeve", "koszulk", "toploader", "album", "binder", "ultra pro", "ultra-pro", "playmat", "portfolio"]

async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(CAT_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
    soup = BeautifulSoup(html, "lxml")
    for tile in soup.select("product-tile"):
        pid = tile.get("product-id", "")
        name = tile.get("name", "")
        price = tile.get("price", "")
        if not pid or not name or len(name) < 5:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        text = tile.get_text(" ", strip=True).lower()
        available = "koszyk" in text
        link_el = tile.select_one("a[href]")
        href = ""
        if link_el:
            h = link_el.get("href", "")
            href = BASE + h if h.startswith("/") else h
        img_el = tile.select_one("img")
        image = ""
        if img_el:
            src = img_el.get("data-src") or img_el.get("src", "")
            if src.startswith("//"):
                image = "https:" + src
            elif src.startswith("/"):
                image = BASE + src
            else:
                image = src
        price_str = f"{float(price):.2f} zl" if price else "brak"
        products.append({"id": f"pikatube_{pid}", "name": name, "price": price_str, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
    print(f"[PIKATUBE] {len(products)} produktow")
    return products
