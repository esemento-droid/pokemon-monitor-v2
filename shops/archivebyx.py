"""
Scraper: archivebyx.com (WooCommerce — buty/odzież + Pokemon TCG)
Search URL: /?s=pokemon+tcg&post_type=product
Static HTML (no CF on product pages).
Uses proxy with direct fallback (VPS IP may be blocked).
"""

import aiohttp
from bs4 import BeautifulSoup

SHOP = "archivebyx"
BASE = "https://www.archivebyx.com"
SEARCH_URL = f"{BASE}/?s=pokemon+tcg&post_type=product"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
PROXY = "http://127.0.0.1:8888"

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "battle deck", "league battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)", "figurk", "puzzle", "zeszyt",
    "buty", "shoes", "sneaker", "t-shirt", "hoodie", "bluza", "koszulka",
]


async def _fetch_html(session, url, proxy=None):
    """Fetch HTML with optional proxy."""
    try:
        async with session.get(url, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None


async def get_products() -> list[dict]:
    products = []

    html = None
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        # Try with proxy first (VPS IP may be blocked)
        html = await _fetch_html(session, SEARCH_URL, proxy=PROXY)
        if not html:
            # Fallback: direct (no proxy)
            html = await _fetch_html(session, SEARCH_URL, proxy=None)

    if not html:
        print("[ARCHIVEBYX] Both proxy and direct failed")
        return []

    soup = BeautifulSoup(html, "lxml")
    items = soup.select("li.product, li.type-product")
    seen = set()

    for item in items:
        classes = item.get("class", [])
        available = "outofstock" not in classes

        a = item.find("a", href=True)
        if not a:
            continue
        url = a.get("href", "")
        if not url or url in seen:
            continue
        seen.add(url)

        title = item.select_one("h2, h3, .woocommerce-loop-product__title")
        name = title.get_text(" ", strip=True) if title else ""
        if not name:
            continue

        # Only pokemon tcg products
        name_lower = name.lower()
        if "pokemon" not in name_lower and "pokémon" not in name_lower:
            continue

        if any(ex in name_lower for ex in EXCLUDE):
            continue

        price_el = item.select_one(".woocommerce-Price-amount")
        price = price_el.get_text(strip=True) if price_el else "brak"

        img = item.find("img")
        image = ""
        if img:
            image = img.get("data-src") or img.get("src") or ""
            if "woocommerce-placeholder" in image:
                image = ""

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

    print(f"[ARCHIVEBYX] {len(products)} produktow")
    return products


if __name__ == "__main__":
    import asyncio
    import time
    start = time.time()
    prods = asyncio.run(get_products())
    elapsed = time.time() - start
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}, Time: {elapsed:.1f}s")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:60]:60} | {p['price']}")
