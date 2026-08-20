"""
gryujanusza.pl — Shopify JSON API scraper
Pokemon TCG sealed products (booster boxes, ETBs, tins, collections, blisters, packs)

Platform: Shopify
Method: /collections/tcg-pokemon/products.json (single request, ~250 products max)
Speed: ~0.5-2s (one HTTP call, no pagination needed for 34 products)
"""

import aiohttp

SHOP = "gryujanusza"
MARK_MISSING_AS_OOS = True  # Site hides OOS from listing — mark missing products as unavailable for RESTOCK detection
URL = "https://gryujanusza.pl/collections/tcg-pokemon/products.json?limit=250"

EXCLUDE_KEYWORDS = [
    "deck", "league battle", "rival battle", "v battle", "world championship", "wcs ",
    "battle academy", "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk",
    "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese", "ultra pro", "ultra-pro",
    "playmat", "portfolio", "pro-binder", "sleeves", "toploader", "album", "koszulk", "segregator",
    "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def _is_excluded(name: str) -> bool:
    low = name.lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw in low:
            return True
    return False


async def get_products():
    products = []

    async with aiohttp.ClientSession() as session:
        async with session.get(URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

    for product in data.get("products", []):
        title = product.get("title", "")

        if _is_excluded(title):
            continue

        handle = product.get("handle", "")
        product_url = f"https://gryujanusza.pl/products/{handle}"
        product_id = str(product.get("id", ""))

        # Image
        images = product.get("images", [])
        image = images[0]["src"] if images else ""

        # Variants — get lowest price and check availability
        variants = product.get("variants", [])
        if not variants:
            continue

        any_available = any(v.get("available", False) for v in variants)

        # Lowest price among variants
        prices = []
        for v in variants:
            try:
                prices.append(float(v["price"]))
            except (ValueError, KeyError):
                pass

        price = str(min(prices)) if prices else "0"

        # Stock info from variant count available
        stock_count = sum(1 for v in variants if v.get("available", False))

        products.append({
            "id": product_id,
            "name": title,
            "price": price,
            "url": product_url,
            "image": image,
            "shop": SHOP,
            "available": any_available,
            "stock": str(stock_count) if stock_count > 0 else "0",
        })

    return products
