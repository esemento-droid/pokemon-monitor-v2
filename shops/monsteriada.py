"""
Scraper: monsteriada.pl (PrestaShop + Cloudflare)
Kategoria: /93-pokemon-tcg-karty-kolekjonerskie
Pagination: ?page=N (4 pages). FlareSolverr.
Category: SLOW (FlareSolverr)
"""

import asyncio

import aiohttp
from bs4 import BeautifulSoup

SHOP = "monsteriada"
BASE = "https://monsteriada.pl"
CATEGORY_URL = f"{BASE}/93-pokemon-tcg-karty-kolekjonerskie"
FLARESOLVERR_URL = "http://localhost:8191/v1"
MAX_PAGES = 8

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "battle deck", "league battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)", "figurk", "puzzle", "zeszyt",
    "pluszak", "brelok", "kubek", "szklank", "maskotk",
    "władca pierścieni", "lord of the ring", "tales of middle",
]


async def _fetch_flare(session: aiohttp.ClientSession, url: str) -> str:
    payload = {"cmd": "request.get", "url": url, "maxTimeout": 30000}
    try:
        async with session.post(FLARESOLVERR_URL, json=payload, timeout=aiohttp.ClientTimeout(total=45)) as resp:
            data = await resp.json()
        if data.get("status") == "ok":
            return data.get("solution", {}).get("response", "")
    except Exception:
        pass
    return ""


def _parse_page(html: str, seen: set) -> list[dict]:
    products = []
    soup = BeautifulSoup(html, "lxml")
    items = soup.select(".product-miniature, article.product-miniature")

    for item in items:
        name_el = item.select_one(".product-title a, h2 a, h3 a, .product-name a")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        url = name_el.get("href", "")
        if not name or not url or url in seen:
            continue
        seen.add(url)

        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        price_el = item.select_one(".product-price, .price, [itemprop=price]")
        price = price_el.get_text(strip=True) if price_el else "brak"

        try:
            import re
            pv = float(re.search(r"(\d+[\s\xa0]?\d*[.,]\d+)", price.replace("\xa0", "")).group(1).replace(",", ".").replace(" ", ""))
            if pv < 10:
                continue
        except (AttributeError, ValueError):
            pass

        img = item.select_one("img")
        image = ""
        if img:
            image = img.get("data-full-size-image-url") or img.get("data-src") or img.get("src") or ""

        avail_el = item.select_one(".product-availability, .availability")
        avail_text = avail_el.get_text(strip=True).lower() if avail_el else ""
        available = avail_text in ("dostępny", "dostepny", "przedsprzedaż", "przedsprzedaz", "w magazynie")

        pid = url.rstrip("/").split("/")[-1].split(".html")[0]

        products.append({
            "id": f"{SHOP}_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": 1 if available else 0,
            "available": available,
        })

    return products


async def get_products() -> list[dict]:
    products = []
    seen: set = set()

    async with aiohttp.ClientSession() as session:
        # Page 1
        html1 = await _fetch_flare(session, CATEGORY_URL)
        if not html1:
            print(f"[MONSTERIADA] blad pobierania")
            return []

        products.extend(_parse_page(html1, seen))

        # Detect pagination
        soup = BeautifulSoup(html1, "lxml")
        page_links = soup.select(".pagination a, a[rel=next]")
        page_nums = set()
        for link in page_links:
            href = link.get("href", "")
            if "page=" in href:
                try:
                    num = int(href.split("page=")[-1].split("&")[0])
                    page_nums.add(num)
                except ValueError:
                    pass

        max_page = max(page_nums) if page_nums else 1
        max_page = min(max_page, MAX_PAGES)

        # Fetch remaining pages sequentially (FlareSolverr = 1 req at a time)
        for page in range(2, max_page + 1):
            html = await _fetch_flare(session, f"{CATEGORY_URL}?page={page}")
            if html:
                new = _parse_page(html, seen)
                if new:
                    products.extend(new)

    print(f"[MONSTERIADA] {len(products)} produktow")
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
        print(f"  {status} {p['name'][:60]:60} | {p['price']}")
