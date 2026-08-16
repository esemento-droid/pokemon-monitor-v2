"""
Scraper: abondegames.pl (WooCommerce Store API)
Endpoint: /wp-json/wc/store/v1/products?search=pokemon&per_page=100
API works without CF bypass. Single request.
"""

import html as html_lib

import aiohttp

SHOP = "abondegames"
API_URL = "https://abondegames.pl/wp-json/wc/store/v1/products"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "battle deck", "league battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)", "figurk", "puzzle", "zeszyt",
]


async def get_products() -> list[dict]:
    products = []

    params = {"search": "pokemon", "per_page": "100"}

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        async with session.get(API_URL, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                print(f"[ABONDEGAMES] HTTP {resp.status}")
                return []
            items = await resp.json()

    for item in items:
        name = html_lib.unescape(item.get("name", ""))
        if not name:
            continue

        # Exclude
        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        # Price
        price_raw = item.get("prices", {}).get("price", "0")
        try:
            price_val = int(price_raw) / 100
        except (ValueError, TypeError):
            price_val = 0
        if 0 < price_val < 10:
            continue
        price = f"{price_val:.2f} zl" if price_val > 0 else "brak"

        # Stock
        available = item.get("is_in_stock", False)

        # Image
        images = item.get("images", [])
        image = images[0].get("src", "") if images else ""

        # URL
        url = item.get("permalink", "")

        # ID
        pid = item.get("id", "")

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

    print(f"[ABONDEGAMES] {len(products)} produktow")
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
