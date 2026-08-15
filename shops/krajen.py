import aiohttp
import asyncio
import html as html_mod

SHOP = "krajen"
API_URL = "https://krajen.pl/wp-json/wc/store/v1/products?per_page=100&category=pokemon-tcg&page={page}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "sleeve", "koszulk", "toploader", "album", "binder", "ultra pro", "playmat",
    "pusta puszka", "japan", "japanese", "japenese", "china", "chinese", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "ultra-pro", "portfolio", "segregator", "deck box", "alcove", "lorcana",
    "one piece", "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering",
    "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz", "force of will",
    "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]

async def fetch_page(session, page):
    url = API_URL.format(page=page)
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            return []
        return await resp.json()

async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = [fetch_page(session, pg) for pg in range(1, 3)]
        results = await asyncio.gather(*tasks)
        for data in results:
            for item in data:
                name = html_mod.unescape(item.get("name", ""))
                if not name or len(name) < 5:
                    continue
                if any(ex in name.lower() for ex in EXCLUDE):
                    continue
                pid = item.get("id")
                price_raw = item.get("prices", {}).get("price", "0")
                try:
                    price = f"{int(price_raw) / 100:.2f} zl"
                except (ValueError, TypeError):
                    price = "brak"
                available = item.get("is_in_stock", False)
                permalink = item.get("permalink", "")
                images = item.get("images", [])
                image = images[0].get("src", "") if images else ""
                products.append({"id": f"krajen_{pid}", "name": name, "price": price, "shop": SHOP, "url": permalink, "image": image, "stock": None, "available": available})
    print(f"[KRAJEN] {len(products)} produktow")
    return products
