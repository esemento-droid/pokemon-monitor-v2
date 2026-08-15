"""
Scraper: pkmnshop.pl (Shoper rwd_shoper_4)
Kategoria: /Pokemon-TCG
"""

import asyncio
import re

import aiohttp
from bs4 import BeautifulSoup

SHOP = "pkmnshop"
BASE = "https://pkmnshop.pl"
CATEGORY_URL = f"{BASE}/Pokemon-TCG"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE = [
    "japonsk", "japanese", "chinese", "sleeve", "koszulk", "playmat", "album", "binder",
    "toploader", "akcesori", "skup kart", "battle deck", "league battle", "rival battle",
    "v battle", "world championship", "wcs deck", "wcs ", "battle academy", "japoński",
    "japońsk", "(jp)", "koreański", "koreańsk", "korean", "chiński", "chińsk", "(chi)",
    "ultra pro", "ultra-pro", "portfolio", "segregator", "deck box", "alcove", "lorcana",
    "one piece", "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering",
    "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz", "force of will",
    "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]


async def get_products() -> list[dict]:
    products = []

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        # Fetch first page
        async with session.get(CATEGORY_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            text = await resp.text()

        # Detect pagination
        page_nums = re.findall(r'/Pokemon-TCG/(\d+)', text)
        pages_to_fetch = []
        if page_nums:
            max_page = max(int(p) for p in page_nums)
            for i in range(2, max_page + 1):
                pages_to_fetch.append(f"{CATEGORY_URL}/{i}")

        all_html = [text]

        for page_url in pages_to_fetch:
            async with session.get(page_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                all_html.append(await resp.text())

        seen_ids = set()

        for html in all_html:
            soup = BeautifulSoup(html, "lxml")
            boxes = soup.select("[data-product-id]")

            for box in boxes:
                pid = box.get("data-product-id", "")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)

                # Name
                name_el = box.select_one("span.productname")
                name = name_el.get_text(strip=True) if name_el else ""

                if not name:
                    continue

                name_lower = name.lower()
                if any(ex in name_lower for ex in EXCLUDE):
                    continue

                # URL
                a_tag = box.select_one("a.prodname")
                url = ""
                if a_tag and a_tag.get("href"):
                    url = a_tag["href"]
                    if not url.startswith("http"):
                        url = BASE + url

                # Image
                img = box.select_one("img[data-src]")
                image = ""
                if img and img.get("data-src"):
                    image = img["data-src"]
                    if not image.startswith("http"):
                        image = BASE + image

                # Price
                price_el = box.select_one(".price em")
                price = ""
                if price_el:
                    price_text = price_el.get_text(strip=True)
                    price_text = re.sub(r'[\s\xa0]', '', price_text)
                    price_text = price_text.replace(',', '.').replace('zł', '').replace('PLN', '').strip()
                    if price_text:
                        price = f"{price_text} zl"

                # Availability: wyprzedane in text = unavailable
                box_text = box.get_text(" ", strip=True).lower()
                available = "koszyk" in box_text

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
