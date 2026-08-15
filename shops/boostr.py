import asyncio
import re
import aiohttp
from bs4 import BeautifulSoup

SHOP = "boostr"
BASE = "https://boost-r.pl"
CAT_URL = BASE + "/pl/c/Pokemon/38"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "pro-binder", "ultra pro", "playmat", "energia",
    "energy", "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra-pro", "portfolio", "segregator", "deck box", "alcove", "lorcana", "one piece",
    "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]

async def fetch(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return ""
            return await resp.text()
    except Exception:
        return ""

def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    for tile in soup.select("product-tile"):
        pid = tile.get("product-id", "")
        name = tile.get("name", "")
        price = tile.get("price", "")
        if not pid or not name or len(name) < 5:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        text = tile.get_text(" ", strip=True).lower()
        available = "koszyk" in text
        link_el = tile.select_one("a[href]")
        href = ""
        if link_el:
            h = link_el.get("href", "")
            href = BASE + h if h.startswith("/") else h
        img_el = tile.select_one("img")
        image = ""
        if img_el:
            src = img_el.get("data-src") or img_el.get("src", "")
            if src.startswith("//"):
                image = "https:" + src
            elif src.startswith("/"):
                image = BASE + src
            else:
                image = src
        price_str = f"{float(price):.2f} zl" if price else "brak"
        products.append({"id": f"boostr_{pid}", "name": name, "price": price_str, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
    return products

async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html = await fetch(session, CAT_URL)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        pages = set()
        for a in soup.select("a[href]"):
            m = re.search(r"/38/(\d+)", a.get("href", ""))
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages) if pages else 1
        urls = [CAT_URL] + [f"{CAT_URL}/{pg}" for pg in range(2, max_page + 1)]
        tasks = [fetch(session, u) for u in urls]
        results = await asyncio.gather(*tasks)
        for page_html in results:
            if page_html:
                for p in parse_page(page_html):
                    if p["id"] not in seen_ids:
                        seen_ids.add(p["id"])
                        products.append(p)
    print(f"[BOOSTR] {len(products)} produktow")
    return products
