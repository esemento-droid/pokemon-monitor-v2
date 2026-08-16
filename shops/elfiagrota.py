"""
Scraper: elfiagrota.pl (osCommerce, schema.org structured data)
Kategoria: /pokmon-c-43.html/s=N (9 stron, 20 per page)
Parallel fetch, static HTML.
"""

import asyncio

import aiohttp
from bs4 import BeautifulSoup

SHOP = "elfiagrota"
BASE = "https://elfiagrota.pl"
CATEGORY_URL = f"{BASE}/pokmon-c-43.html/s="
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
MAX_PAGES = 12

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "battle deck", "league battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)", "figurk", "puzzle", "zeszyt",
    "pencil case", "piórnik", "pluszak", "brelok", "clip on", "plush",
    "my first battle",
]


async def _fetch(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return ""
            return await resp.text()
    except Exception:
        return ""


def _parse_page(html: str, seen: set) -> list[dict]:
    products = []
    soup = BeautifulSoup(html, "lxml")
    items = soup.select('[itemtype="https://schema.org/Product"]')

    for item in items:
        # Name
        name_meta = item.select_one('meta[itemprop="name"]')
        name = name_meta.get("content", "") if name_meta else ""
        if not name:
            continue

        # URL
        url_link = item.select_one('link[itemprop="url"]')
        url = url_link.get("href", "") if url_link else ""
        if not url or url in seen:
            continue
        seen.add(url)

        # Exclude filter
        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        # Offer data
        offer = item.select_one('[itemtype="https://schema.org/Offer"]')
        price_meta = offer.select_one('meta[itemprop="price"]') if offer else None
        price_val = float(price_meta.get("content", "0")) if price_meta else 0.0

        avail_link = offer.select_one('link[itemprop="availability"]') if offer else None
        avail_href = avail_link.get("href", "") if avail_link else ""
        available = "InStock" in avail_href

        # Price string
        if price_val > 0:
            price = f"{price_val:.2f} zl"
        else:
            price = "brak"

        # Skip singles (<10 PLN)
        if 0 < price_val < 10:
            continue

        # Image
        img_link = item.select_one('link[itemprop="image"]')
        image = img_link.get("href", "") if img_link else ""

        # ID from URL (-p-XXX)
        pid = ""
        if "-p-" in url:
            pid = url.split("-p-")[-1].replace(".html", "")
        if not pid:
            pid = url

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

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        # Fetch page 1 first to detect max pages
        html1 = await _fetch(session, f"{CATEGORY_URL}1")
        if not html1:
            print(f"[ELFIAGROTA] blad pobierania")
            return []

        products.extend(_parse_page(html1, seen))

        # Detect pagination
        soup = BeautifulSoup(html1, "lxml")
        page_links = soup.select('a[href*="/s="]')
        page_nums = set()
        for link in page_links:
            href = link.get("href", "")
            if "/s=" in href:
                try:
                    num = int(href.split("/s=")[-1])
                    page_nums.add(num)
                except ValueError:
                    pass

        max_page = max(page_nums) if page_nums else 1
        max_page = min(max_page, MAX_PAGES)

        # Fetch remaining pages in parallel
        if max_page > 1:
            tasks = [_fetch(session, f"{CATEGORY_URL}{p}") for p in range(2, max_page + 1)]
            results = await asyncio.gather(*tasks)
            for html in results:
                if html:
                    products.extend(_parse_page(html, seen))

    print(f"[ELFIAGROTA] {len(products)} produktow")
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
