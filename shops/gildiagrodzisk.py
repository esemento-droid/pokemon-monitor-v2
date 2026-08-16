"""
Scraper: gildiagrodzisk.pl
Kategoria: /category/pokemon-tcg
Pagination: ?page=N (2 pages)
Static HTML, no JS needed.
"""

import asyncio

import aiohttp
from bs4 import BeautifulSoup

SHOP = "gildiagrodzisk"
BASE = "https://gildiagrodzisk.pl"
CATEGORY_URL = f"{BASE}/category/pokemon-tcg"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader", "holder", "protector",
    "ultra pro", "portfolio", "segregator", "deck box", "alcove",
    "one piece", "lorcana", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "dragon shield", "weiss schwarz",
]

MAX_PAGES = 5


async def _fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        if resp.status != 200:
            return ""
        return await resp.text()


def _parse_page(html: str, seen_urls: set) -> list[dict]:
    products = []
    soup = BeautifulSoup(html, "lxml")
    articles = soup.select("article.front-product-card")

    for art in articles:
        # URL
        overlay = art.select_one("a.front-product-card__overlay")
        if not overlay:
            continue
        url = overlay.get("href", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        # Name
        name_el = art.select_one(".front-product-card__title")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            # fallback from aria-label
            label = overlay.get("aria-label", "")
            name = label.replace("Zobacz produkt: ", "").strip()
        if not name:
            continue

        # Exclude filter
        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        # Price
        price_el = art.select_one(".front-product-card__price")
        price = price_el.get_text(strip=True) if price_el else ""

        # Image
        img = art.select_one("img")
        image = ""
        if img:
            image = img.get("src", "") or img.get("data-src", "")

        # Availability
        avail_el = art.select_one(".front-product-card__badge--availability")
        avail_text = avail_el.get_text(strip=True).lower() if avail_el else ""
        available = avail_text in ("dostępny", "dostepny", "przedsprzedaż", "przedsprzedaz")

        products.append({
            "id": url,
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
    seen_urls: set = set()

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        # Page 1
        html = await _fetch_page(session, CATEGORY_URL)
        if not html:
            print(f"[GILDIAGRODZISK] blad pobierania strony")
            return []

        products.extend(_parse_page(html, seen_urls))

        # Check for more pages
        soup = BeautifulSoup(html, "lxml")
        page_links = soup.select("a[href*='page=']")
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

        # Fetch remaining pages
        tasks = []
        for page in range(2, max_page + 1):
            tasks.append(_fetch_page(session, f"{CATEGORY_URL}?page={page}"))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception) or not result:
                    continue
                products.extend(_parse_page(result, seen_urls))

    print(f"[GILDIAGRODZISK] {len(products)} produktow")
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
