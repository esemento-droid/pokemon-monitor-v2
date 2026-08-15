import aiohttp
import html as html_mod

SHOP = "nearmint"
API_URL = "https://nearmint.pl/wp-json/wc/store/v1/products?per_page=100&category=pokemon"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "pro-binder", "ultra pro", "playmat", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk",
    "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese", "ultra-pro", "portfolio",
    "segregator", "deck box", "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood", "flesh and blood",
    "dragon shield", "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle",
    "figurk", "figure set"
]

async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(API_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                print(f"[NEARMINT] HTTP {resp.status}")
                return []
            data = await resp.json()
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
        products.append({"id": f"nearmint_{pid}", "name": name, "price": price, "shop": SHOP, "url": permalink, "image": image, "stock": None, "available": available})
    print(f"[NEARMINT] {len(products)} produktow")
    return products
