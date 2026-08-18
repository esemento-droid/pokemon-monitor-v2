"""
DISABLED 2026-08-18: Domain SSL dead (Cannot connect to host www.tcglove.pl:443 ssl:Fail)
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

BASE_URL = "https://www.tcglove.pl/pokemon-tcg"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


EXCLUDE = ["battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean",
    "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "pro-binder",
    "sleeves", "toploader", "album", "koszulk", "segregator",
    "deck box", "alcove",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto",
    "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz",
    "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"]


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
                product_url = f"https://www.tcglove.pl{href}" if href.startswith("/") else href
                img_el = tile.select_one("img")
                image = ""
                if img_el:
                    image = img_el.get("src") or img_el.get("data-src", "")
                    if image and not image.startswith("http"):
                        image = "https://www.tcglove.pl" + image
                tile_text = tile.get_text(" ", strip=True).lower()
                available = "powiadom" not in tile_text




                if any(ex in name.lower() for ex in EXCLUDE): continue





                products.append({
                    "id": f"tcglove_{pid}",
                    "name": name,
                    "price": price,
                    "shop": "tcglove",
                    "url": product_url,
                    "image": image,
                    "stock": 1 if available else 0,
                    "available": available,
                })
            next_link = soup.select_one('link[rel="next"]')
            if not next_link:
                break
    return products
