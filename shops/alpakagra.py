import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

BASE_URL = "https://alpakagra.pl/pl/c/Pokemon/69/{}/full"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "singl", "karta pokemon", "psa ", "cgc ", "slab ", "losow", "china", "chinese", "chiński",
    "japonsk", "japanese", "korean", "koreańsk", "portfolio", "piórnik", "piornik",
    "riftbound", "tying", "marvel", "fairy tail", "origin", "japan", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "(jp)", "(chi)", "ultra pro", "ultra-pro",
    "playmat", "pro-binder", "sleeves", "toploader", "album", "koszulk", "segregator", "deck box",
    "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "zeszyt", "puzzle", "figurk", "figure set"
]


async def fetch_page(session, url):
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            return ""
        return await resp.text()


async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html1 = await fetch_page(session, BASE_URL.format(1))
        if not html1:
            return []
        soup1 = BeautifulSoup(html1, "lxml")
        pages = {1}
        for a in soup1.select("a"):
            href = a.get("href", "")
            m = re.search(r"Pokemon/69/(\d+)/full", href)
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages)
        if max_page > 1:
            tasks = [fetch_page(session, BASE_URL.format(p)) for p in range(2, max_page + 1)]
            extra = await asyncio.gather(*tasks)
        else:
            extra = []
    all_htmls = [html1] + [h for h in extra if h]
    for i, html in enumerate(all_htmls):
        soup = BeautifulSoup(html, "lxml") if i > 0 else soup1
        for tile in soup.select("product-tile"):
            pid = tile.get("product-id", "")
            name = tile.get("name", "").strip()
            price = tile.get("price", "")
            if not pid or not name:
                continue
            if pid in seen:
                continue
            seen.add(pid)
            name_lower = name.lower()
            if any(ex in name_lower for ex in EXCLUDE):
                continue
            text = tile.get_text(" ", strip=True).lower()
            available = "koszyk" in text
            price_str = f"{price} PLN" if price else "brak"
            img = tile.select_one("img")
            image = img.get("data-src", "") or img.get("src", "") if img else ""
            if image and not image.startswith("http"):
                image = f"https://alpakagra.pl{image}"
            link = tile.select_one("a")
            url_prod = ""
            if link:
                url_prod = link.get("href", "")
                if url_prod and not url_prod.startswith("http"):
                    url_prod = f"https://alpakagra.pl{url_prod}"
            products.append({
                "id": f"alpakagra_{pid}",
                "name": name,
                "price": price_str,
                "shop": "alpakagra",
                "url": url_prod,
                "image": image,
                "stock": "",
                "available": available,
            })
    return products
