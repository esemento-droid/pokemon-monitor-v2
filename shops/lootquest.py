import aiohttp

SHOP = "lootquest"
MARK_MISSING_AS_OOS = True  # Site hides OOS from listing — mark missing products as unavailable for RESTOCK detection
BASE = "https://lootquest.pl/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "Mozilla/5.0"}
EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "pro-binder", "ultra pro", "playmat", "one piece",
    "lorcana", "yu-gi-oh", "digimon", "magic the", "japonsk", "japońsk", "japanese", "japan",
    "korean", "koreańsk", "korea", "chiński", "chinese", "china", "portfolio", "mata do gry",
    "pudełko", "deck box", "alcove", "kubek", "ultra rare", "battle deck", "league battle",
    "rival battle", "v battle", "world championship", "wcs deck", "wcs ", "battle academy",
    "(jp)", "(chi)", "ultra-pro", "segregator", "naruto", "star wars", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        page = 1
        while True:
            url = f"{BASE}?per_page=100&category=pokemon-tcg&page={page}"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json()
            except:
                break
            if not data:
                break
            for item in data:
                pid = str(item.get("id", ""))
                if pid in seen:
                    continue
                seen.add(pid)
                name = item.get("name", "").replace("&#8211;", "-").replace("&amp;", "&").replace("&#8217;", "'").replace("&#8222;", "\"").replace("&#8221;", "\"")
                name_low = name.lower()
                if "pokemon" not in name_low and "pokémon" not in name_low:
                    continue
                if any(ex in name_low for ex in EXCLUDE):
                    continue
                price_raw = item.get("prices", {}).get("price", "0")
                try:
                    price = f"{int(price_raw) / 100:.2f} zl"
                except:
                    price = "brak"
                in_stock = item.get("is_in_stock", False)
                url_prod = item.get("permalink", "")
                images = item.get("images", [])
                image = images[0].get("src", "") if images else ""
                products.append({
                    "id": f"lootquest_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": url_prod,
                    "image": image,
                    "stock": None,
                    "available": in_stock,
                })
            if len(data) < 100:
                break
            page += 1
    print(f"[LOOTQUEST] {len(products)} produktow")
    return products
