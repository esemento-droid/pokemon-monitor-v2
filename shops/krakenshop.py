"""
Scraper: krakenshop.pl (Sky-Shop, Angular SPA)
Kategoria: /karty-pokemon
Products from HTML figure.product-tile + dataLayer (quantity/availability).
Single page, 10 products.
"""

import re
import json

import aiohttp
from bs4 import BeautifulSoup

SHOP = "krakenshop"
MARK_MISSING_AS_OOS = True  # Site hides OOS from listing — mark missing products as unavailable for RESTOCK detection
BASE = "https://krakenshop.pl"
CATEGORY_URL = f"{BASE}/karty-pokemon"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "battle deck", "league battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)", "figurk", "puzzle", "zeszyt",
]


async def get_products() -> list[dict]:
    products = []

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        async with session.get(CATEGORY_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                print(f"[KRAKENSHOP] HTTP {resp.status}")
                return []
            html = await resp.text()

    # Extract quantity map from GA4 dataLayer
    qty_map = {}
    match = re.search(r'view_item_list.*?(\{"currency.*?\})\s*\)', html, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1).replace("&amp;", "&"))
            for item in data.get("items", []):
                name = item.get("item_name", "").replace("&amp;", "&")
                qty_map[name] = item.get("quantity", 0)
        except (json.JSONDecodeError, KeyError):
            pass

    # Parse product tiles from HTML
    soup = BeautifulSoup(html, "lxml")
    tiles = soup.select("figure.product-tile")

    for tile in tiles:
        name_el = tile.select_one("a.product-name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name:
            continue

        # Exclude
        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        # URL
        href = name_el.get("href", "")
        url = f"{BASE}{href}" if href.startswith("/") else href
        if not url:
            continue

        # Price
        price_el = tile.select_one("[class*=price]")
        price_text = price_el.get_text(strip=True) if price_el else ""
        price_match = re.search(r"(\d+[.,]\d+)", price_text)
        price = price_match.group(1).replace(",", ".") + " zl" if price_match else "brak"

        # Price filter <10 PLN
        try:
            pv = float(price.replace(" zl", ""))
            if pv < 10:
                continue
        except (ValueError, AttributeError):
            pass

        # Image
        img = tile.select_one("img")
        image = ""
        if img:
            src = img.get("src", "") or img.get("srcset", "").split(" ")[0]
            image = f"{BASE}{src}" if src.startswith("/") else src

        # Availability: quantity from dataLayer, fallback to button text
        qty = qty_map.get(name, -1)
        if qty >= 0:
            available = qty > 0
        else:
            btn = tile.select_one("button")
            btn_text = btn.get_text(strip=True).lower() if btn else ""
            available = "dodaj" in btn_text or "koszyk" in btn_text

        # ID from URL slug
        pid = href.strip("/").split("/")[-1] if href else name

        products.append({
            "id": f"{SHOP}_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": qty if qty >= 0 else (1 if available else 0),
            "available": available,
        })

    print(f"[KRAKENSHOP] {len(products)} produktow")
    return products


if __name__ == "__main__":
    import asyncio
    import time
    start = time.time()
    prods = asyncio.run(get_products())
    elapsed = time.time() - start
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}, Time: {elapsed:.1f}s")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:60]:60} | {p['price']:12} | stock:{p['stock']}")
