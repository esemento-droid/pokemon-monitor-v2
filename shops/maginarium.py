"""
Scraper: maginarium.pl (WooCommerce + Cloudflare)
Search URL: /?s=Pokemon+tcg+&post_type=product
15+ pages, parallel fetch via FlareSolverr.
Category: SLOW (FlareSolverr)
"""

import asyncio

import aiohttp
from bs4 import BeautifulSoup

SHOP = "maginarium"
BASE = "https://maginarium.pl"
SEARCH_PARAMS = "?s=Pokemon+tcg+&post_type=product"
FLARESOLVERR_URL = "http://localhost:8191/v1"
MAX_PAGES = 30

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

        title = item.select_one("h2, h3, .woocommerce-loop-product__title")
        name = title.get_text(" ", strip=True) if title else ""
        if not name:
            continue

        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        price_el = item.select_one(".woocommerce-Price-amount")
        price = price_el.get_text(strip=True) if price_el else "brak"

        try:
            pv = float(price.replace("zł", "").replace("\xa0", "").replace(",", ".").replace(" ", ""))
            if pv < 10:
                continue
        except (ValueError, AttributeError):
            pass

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

    return products


async def get_products() -> list[dict]:
    products = []
    seen: set = set()

    async with aiohttp.ClientSession() as session:
        # Fetch pages in batches of 5 until empty
        page = 1
        while page <= MAX_PAGES:
            batch_end = min(page + 4, MAX_PAGES + 1)
            tasks = []
            for p in range(page, batch_end):
                url = f"{BASE}/page/{p}/{SEARCH_PARAMS}" if p > 1 else f"{BASE}/{SEARCH_PARAMS}"
                tasks.append(_fetch_flare(session, url))

            results = await asyncio.gather(*tasks)

            found_empty = False
            for html in results:
                if not html:
                    found_empty = True
                    break
                new_products = _parse_page(html, seen)
                if not new_products:
                    found_empty = True
                    break
                products.extend(new_products)

            if found_empty:
                break
            page = batch_end

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
