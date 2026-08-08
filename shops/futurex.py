import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

CATEGORIES = [
    "https://futurex.pl/pl/c/POKEMON/809",
    "https://futurex.pl/pl/c/PRZEDSPRZEDAZ/766",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = ["ultra pro", "up -", "portfolio", "deck box", "sleeve", "binder", "toploader", "protector", "koszulk"]


async def fetch_page(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), ssl=False) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None


async def get_products():
    products = []
    seen_ids = set()

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for cat_url in CATEGORIES:
            html1 = await fetch_page(session, cat_url)
            if not html1:
                continue

            soup1 = BeautifulSoup(html1, "lxml")
            tiles = soup1.select("product-tile")
            if not tiles:
                continue

            pages = {1}
            cat_path = cat_url.replace("https://futurex.pl", "")
            for a in soup1.select("a"):
                href = a.get("href", "")
                m = re.search(re.escape(cat_path) + r"/(\d+)", href)
                if m:
                    pages.add(int(m.group(1)))
            max_page = max(pages)

            all_htmls = [html1]
            if max_page > 1:
                tasks = [fetch_page(session, f"{cat_url}/{p}") for p in range(2, max_page + 1)]
                results = await asyncio.gather(*tasks)
                all_htmls += [h for h in results if h]

            for i, html in enumerate(all_htmls):
                soup = BeautifulSoup(html, "lxml") if i > 0 else soup1
                for tile in soup.select("product-tile"):
                    pid = tile.get("product-id")
                    name = tile.get("name", "")
                    if not pid or not name or pid in seen_ids:
                        continue
                    nl = name.lower()
                    if not ("pokemon" in nl or "pokémon" in nl):
                        continue
                    if any(ex in nl for ex in EXCLUDE):
                        continue
                    seen_ids.add(pid)
                    price = tile.get("price", "0") + " PLN"
                    href = tile.select_one("a")
                    href = href.get("href", "") if href else ""
                    purl = f"https://futurex.pl{href}" if href.startswith("/") else href
                    img_el = tile.select_one("img")
                    image = ""
                    if img_el:
                        image = img_el.get("src") or img_el.get("data-src", "")
                        if image and not image.startswith("http"):
                            image = "https://futurex.pl" + image
                    text = tile.get_text(" ", strip=True).lower()
                    available = "koszyk" in text
                    products.append({
                        "id": f"futurex_{pid}",
                        "name": name,
                        "price": price,
                        "shop": "futurex",
                        "url": purl,
                        "image": image,
                        "stock": 1 if available else 0,
                        "available": available,
                    })

    return products
