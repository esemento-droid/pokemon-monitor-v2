"""
Scraper: maginarium.pl (WooCommerce)
Search URL: /?s=Pokemon+tcg+&post_type=product
15 pages, ~164 products. Parallel fetch.
"""

import asyncio

import aiohttp
from bs4 import BeautifulSoup

SHOP = "maginarium"
BASE = "https://maginarium.pl"
SEARCH_URL = f"{BASE}/?s=Pokemon+tcg+&post_type=product"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
MAX_PAGES = 20

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "battle deck", "league battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "battle arena", "theme deck",
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)", "figurk", "puzzle", "zeszyt",
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
    items = soup.select("li.product, li.type-product")

    for item in items:
        classes = item.get("class", [])
        available = "outofstock" not in classes

        a = item.find("a")
        if not a:
            continue
        url = a.get("href", "")
        if not url or url in seen:
            continue
        seen.add(url)

        # Name
        title = item.select_one("h2, h3, .woocommerce-loop-product__title")
        name = title.get_text(" ", strip=True) if title else ""
        if not name:
            continue

        # Exclude
        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        # Price
        price_el = item.select_one(".woocommerce-Price-amount")
        price = price_el.get_text(strip=True) if price_el else "brak"

        # Price filter <10
        try:
            pv = float(price.replace("zł", "").replace("\xa0", "").replace(",", ".").replace(" ", ""))
            if pv < 10:
                continue
        except (ValueError, AttributeError):
            pass

        # Image
        img = item.find("img")
        image = ""
        if img:
            image = img.get("data-src") or img.get("src") or ""
            if "woocommerce-placeholder" in image:
                image = ""

        # ID from URL
        pid = url.rstrip("/").split("/")[-1]

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
        # Fetch all pages in parallel (pagination not visible on page 1)
        search_params = "?s=Pokemon+tcg+&post_type=product"
        tasks = []
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE}/page/{page}/{search_params}" if page > 1 else f"{BASE}/{search_params}"
            tasks.append(_fetch(session, url))

        results = await asyncio.gather(*tasks)

        for html in results:
            if not html:
                continue
            new_products = _parse_page(html, seen)
            if not new_products:
                break  # empty page = end of results
            products.extend(new_products)

    print(f"[MAGINARIUM] {len(products)} produktow")
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
