import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "bastacentershop"
BASE = "https://www.bastacentershop.pl"
START_URL = f"{BASE}/pl/c/Pokemon-TCG/41/1/default/1"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
EXCLUDE = [
    "album", "koszulk", "toploader", "sleeves", "figurk", "pluszak", "klocki", "torb", "plecak",
    "ubrani", "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "pro-binder", "segregator", "deck box",
    "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle", "figure set"
]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS, connector=aiohttp.TCPConnector(ssl=False)) as session:
        # Fetch page 1 to detect max pages
        async with session.get(START_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return products
            html = await resp.text()
        soup = BeautifulSoup(html, "lxml")
        # Detect pagination
        pages = {1}
        for a in soup.select("a"):
            href = a.get("href", "")
            m = re.search(r'/41/1/default/(\d+)', href)
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages)
        # Parse page 1
        for tile in soup.select("product-tile[product-id]"):
            pid = tile.get("product-id", "")
            if pid in seen:
                continue
            seen.add(pid)
            name = tile.get("name", "").strip()
            if any(ex in name.lower() for ex in EXCLUDE):
                continue
            price_raw = tile.get("price", "0")
            try:
                price = f"{int(price_raw):.2f} zl"
            except:
                price = "brak"
            text = tile.get_text(" ", strip=True).lower()
            available = "koszyk" in text
            img = tile.select_one("img")
            image = ""
            if img:
                image = img.get("src") or img.get("data-src") or ""
                if image and not image.startswith("http"):
                    image = BASE + image
            link = tile.select_one("a[href*='/pl/p/']")
            url = BASE + link["href"] if link else ""
            products.append({"id": f"bastacentershop_{pid}", "name": name, "price": price, "shop": SHOP, "url": url, "image": image, "stock": None, "available": available})
        # Fetch remaining pages in parallel
        if max_page > 1:
            async def fetch_page(page_num):
                url = f"{BASE}/pl/c/Pokemon-TCG/41/1/default/{page_num}"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                        if r.status != 200:
                            return []
                        return await r.text()
                except:
                    return ""
            htmls = await asyncio.gather(*[fetch_page(p) for p in range(2, max_page + 1)])
            for h in htmls:
                if not h:
                    continue
                s = BeautifulSoup(h, "lxml")
                for tile in s.select("product-tile[product-id]"):
                    pid = tile.get("product-id", "")
                    if pid in seen:
                        continue
                    seen.add(pid)
                    name = tile.get("name", "").strip()
                    if any(ex in name.lower() for ex in EXCLUDE):
                        continue
                    price_raw = tile.get("price", "0")
                    try:
                        price = f"{int(price_raw):.2f} zl"
                    except:
                        price = "brak"
                    text = tile.get_text(" ", strip=True).lower()
                    available = "koszyk" in text
                    img = tile.select_one("img")
                    image = ""
                    if img:
                        image = img.get("src") or img.get("data-src") or ""
                        if image and not image.startswith("http"):
                            image = BASE + image
                    link = tile.select_one("a[href*='/pl/p/']")
                    url = BASE + link["href"] if link else ""
                    products.append({"id": f"bastacentershop_{pid}", "name": name, "price": price, "shop": SHOP, "url": url, "image": image, "stock": None, "available": available})
    print(f"[BASTACENTERSHOP] {len(products)} produktow")
    return products
