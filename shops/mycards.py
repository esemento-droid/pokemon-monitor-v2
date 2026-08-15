import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

CATEGORIES = [
    "https://mycards.pl/pl/c/Pokemon-Booster-Pack/5",
    "https://mycards.pl/pl/c/Pokemon-zestawy/6",
    "https://mycards.pl/pl/c/Pokemon-zestawy-specjalne/7",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "singl", "karta pokemon", "psa ", "cgc ", "slab ", "losow", "battle deck", "league battle",
    "rival battle", "v battle", "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk", "korean", "chiński",
    "chińsk", "chinese", "(chi)", "s-chinese", "ultra pro", "ultra-pro", "playmat",
    "portfolio", "pro-binder", "sleeves", "toploader", "album", "koszulk", "segregator", "deck box",
    "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]


async def fetch_page(session, url):
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            return ""
        return await resp.text()


async def get_category(session, base_url):
    html = await fetch_page(session, base_url)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    # Detect pagination
    cat_id = base_url.rstrip("/").split("/")[-1]
    pages = {1}
    for a in soup.select("a"):
        href = a.get("href", "")
        m = re.search(rf"/{cat_id}/(\d+)", href)
        if m:
            pages.add(int(m.group(1)))
    max_page = max(pages)
    # Fetch extra pages in parallel
    extra_htmls = []
    if max_page > 1:
        tasks = [fetch_page(session, f"{base_url}/{p}") for p in range(2, max_page + 1)]
        extra_htmls = await asyncio.gather(*tasks)
    all_htmls = [html] + [h for h in extra_htmls if h]
    # Parse all pages
    products = []
    for h in all_htmls:
        s = BeautifulSoup(h, "lxml") if h != html else soup
        for tile in s.select("product-tile"):
            products.append(tile)
    return products


async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = [get_category(session, url) for url in CATEGORIES]
        results = await asyncio.gather(*tasks)
    all_tiles = []
    for r in results:
        all_tiles.extend(r)
    for tile in all_tiles:
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
            image = f"https://mycards.pl{image}"
        link = tile.select_one("a")
        url_prod = ""
        if link:
            url_prod = link.get("href", "")
            if url_prod and not url_prod.startswith("http"):
                url_prod = f"https://mycards.pl{url_prod}"
        products.append({
            "id": f"mycards_{pid}",
            "name": name,
            "price": price_str,
            "shop": "mycards",
            "url": url_prod,
            "image": image,
            "stock": "",
            "available": available,
        })
    return products
