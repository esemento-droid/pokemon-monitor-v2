"""
Scraper: senpaistore.pl
Platform: Shopify (JSON API)
Method: aiohttp /products.json
Products: Pokemon TCG sealed (English only)
"""
import aiohttp
import re

SHOP = "senpaistore"
API_URL = "https://senpaistore.pl/products.json?limit=250"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

EXCLUDE = [
    "figurk", "figure", "plush", "pluszak", "maskotk", "manga", "one piece", "jujutsu",
    "chainsaw", "dragon ball", "naruto", "attack on titan", "demon slayer",
    "my hero", "dress-up darling", "gachiakuta", "spy x family",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk", "korean",
    "chiński", "chińsk", "chinese", "(chi)", "s-chinese", "simplified chinese",
    "china", "gem pack",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "pro-binder", "sleeves",
    "toploader", "album", "koszulk", "segregator", "deck box", "alcove",
    "lorcana", "yu-gi-oh", "digimon", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set",
    "singl", "psa ", "cgc ", "slab ",
]


async def get_products():
    products = []
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(API_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    print(f"[senpaistore] HTTP {resp.status}")
                    return []
                data = await resp.json()
    except Exception as e:
        print(f"[senpaistore] Error: {e}")
        return []

    for item in data.get("products", []):
        name = item.get("title", "")
        if not name:
            continue

        name_low = name.lower()

        # Must be Pokemon-related
        if "pokemon" not in name_low and "pokémon" not in name_low:
            continue

        # Exclude unwanted
        if any(ex in name_low for ex in EXCLUDE):
            continue

        pid = str(item.get("id", ""))
        handle = item.get("handle", "")
        url = f"https://senpaistore.pl/products/{handle}" if handle else ""

        # Price from first variant
        variants = item.get("variants", [])
        price = "brak"
        available = False
        if variants:
            v = variants[0]
            p = v.get("price", "")
            if p:
                price = f"{p} zl"
            available = v.get("available", False)

        # Image
        images = item.get("images", [])
        image = images[0].get("src", "") if images else ""

        products.append({
            "id": f"senpaistore_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": None,
            "available": available,
        })

    print(f"[SENPAISTORE] {len(products)} produktow")
    return products
