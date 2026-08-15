"""
Scraper: kieszonkowymonster.pl (Shoper turbo, product-tile)
Categories: Angielskie + Booster Boxy + ETB + 30th Celebration
Dynamic pagination
"""

import asyncio
import re

import aiohttp
from bs4 import BeautifulSoup

SHOP = "kieszonkowymonster"
BASE = "https://kieszonkowymonster.pl"
CATEGORIES = [
    (f"{BASE}/pl/c/Angielskie/44", r'/44/(\d+)'),
    (f"{BASE}/pl/c/Angielskie-Booster-Boxy/47", r'/47/(\d+)'),
    (f"{BASE}/pl/c/Angielskie-ETB/50", r'/50/(\d+)'),
    (f"{BASE}/pl/collection/30th-Celebration/4", r'/4/(\d+)'),
]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE = [
    "sleeve", "koszulk", "playmat", "album", "binder", "toploader", "holder", "protector",
    "japonsk", "japanese", "chinese", "ultra pro", "one piece", "pojedyncz", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "(jp)", "koreański", "koreańsk", "korean",
    "chiński", "chińsk", "(chi)", "ultra-pro", "portfolio", "segregator", "deck box", "alcove",
    "lorcana", "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering",
    "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz", "force of will",
    "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]


async def get_products() -> list[dict]:
    products = []
    seen_ids = set()

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        for cat_url, page_re in CATEGORIES:
            async with session.get(cat_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                text = await resp.text()

            page_nums = re.findall(page_re, text)
            max_page = max([int(x) for x in page_nums]) if page_nums else 1

            all_html = [text]

            for page in range(2, max_page + 1):
                purl = f"{cat_url}/{page}"
                try:
                    async with session.get(purl, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        all_html.append(await resp.text())
                except Exception:
                    break

            for html in all_html:
                soup = BeautifulSoup(html, "lxml")
                tiles = soup.select("product-tile")

                for tile in tiles:
                    pid = tile.get("product-id", "")
                    if not pid or pid in seen_ids:
                        continue

                    name = tile.get("name", "").strip()
                    if not name:
                        continue

                    name_lower = name.lower()
                    if any(ex in name_lower for ex in EXCLUDE):
                        continue

                    seen_ids.add(pid)

                    price = tile.get("price", "")
                    if price:
                        price = f"{price} zl"

                    a_tag = tile.select_one("a")
                    url = ""
                    if a_tag and a_tag.get("href"):
                        url = a_tag["href"]
                        if not url.startswith("http"):
                            url = BASE + url

                    img = tile.select_one("img")
                    image = ""
                    if img:
                        image = img.get("data-src", "") or img.get("src", "")
                        if image and not image.startswith("http"):
                            image = BASE + image

                    tile_text = tile.get_text(" ", strip=True).lower()
                    available = "koszyk" in tile_text

                    products.append({
                        "id": f"{SHOP}_{pid}",
                        "name": name,
                        "price": price,
                        "shop": SHOP,
                        "url": url,
                        "image": image,
                        "stock": "",
                        "available": available,
                    })

    return products


if __name__ == "__main__":
    import time
    start = time.time()
    prods = asyncio.run(get_products())
    elapsed = time.time() - start
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}, Time: {elapsed:.1f}s")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:55]} | {p['price']}")
