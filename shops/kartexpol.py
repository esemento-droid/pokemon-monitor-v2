"""
Scraper: kartexpol.pl (Shoper turbo, product-tile)
Kategoria: /pl/c/Pokemon-TCG/38
Dynamic pagination /38/N
"""

import asyncio
import re

import aiohttp
from bs4 import BeautifulSoup

SHOP = "kartexpol"
BASE = "https://www.kartexpol.pl"
CATEGORY_URL = f"{BASE}/pl/c/Pokemon-TCG/38"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader", "holder", "protector",
    "japonsk", "japanese", "chinese", "ultra pro", "one piece", "battle deck", "league battle",
    "rival battle", "v battle", "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "(jp)", "koreański", "koreańsk", "korean", "chiński", "chińsk",
    "(chi)", "ultra-pro", "portfolio", "segregator", "deck box", "alcove", "lorcana",
    "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]


async def get_products() -> list[dict]:
    products = []
    seen_ids = set()

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        # Fetch page 1
        async with session.get(CATEGORY_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            text = await resp.text()

        # Detect pagination /38/N
        page_nums = re.findall(r'/38/(\d+)', text)
        max_page = max([int(x) for x in page_nums]) if page_nums else 1

        all_html = [text]

        # Fetch remaining pages in parallel
        tasks = []
        for page in range(2, max_page + 1):
            tasks.append(session.get(f"{CATEGORY_URL}/{page}", timeout=aiohttp.ClientTimeout(total=30)))

        if tasks:
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for resp in responses:
                if isinstance(resp, Exception):
                    continue
                all_html.append(await resp.text())
                resp.release()

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

                # URL and image from inner HTML
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

                # Availability: "koszyk" in tile text
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
