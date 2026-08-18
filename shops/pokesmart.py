"""
DISABLED 2026-08-18: Domain SSL dead (Cannot connect to host pokesmart.pl:443 ssl:Fail)
Re-enable when domain comes back.
"""

SHOP_DISABLED = True

"""
Scraper: KupTeraz.com.pl
Platform: Custom (product-tile web component)
Method: aiohttp + BeautifulSoup
Category: /pokemon (multi-page)
Availability: data-basestock > 0
"""

import aiohttp
from bs4 import BeautifulSoup

BASE_URL = "https://pokesmart.pl/pl/c/Produkty/232"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for page in range(1, 20):
            url = BASE_URL if page == 1 else f"{BASE_URL}/{page}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=45), ssl=False) as resp:
                if resp.status != 200:
                    break
                html = await resp.text()
            soup = BeautifulSoup(html, "lxml")
            tiles = soup.select("product-tile")
            if not tiles:
                break
            for tile in tiles:
                pid = tile.get("product-id")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                name = tile.get("name", "")
                if not name:
                    continue
                price_val = tile.get("price", "0")
                price = f"{price_val} PLN"
                href = tile.select_one("a")
                href = href.get("href", "") if href else ""
                product_url = f"https://pokesmart.pl{href}" if href.startswith("/") else href
                img_el = tile.select_one("img")
                image = ""
                if img_el:
                    image = img_el.get("src") or img_el.get("data-src", "")
                    if image and not image.startswith("http"):
                        image = "https://pokesmart.pl" + image
                tile_text = tile.get_text(" ", strip=True).lower()
                available = "koszyk" in tile_text or "dodaj" in tile_text




                products.append({
                    "id": f"pokesmart_{pid}",
                    "name": name,
                    "price": price,
                    "shop": "pokesmart",
                    "url": product_url,
                    "image": image,
                    "stock": 1 if available else 0,
                    "available": available,
                })
            next_link = soup.select_one('link[rel="next"]')
            if not next_link:
                break
    return products
