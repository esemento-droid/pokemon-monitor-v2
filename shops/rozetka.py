import aiohttp
import asyncio

SHOP = "rozetka"
SEARCH_URL = "https://search.rozetka.pl/search/api/v6/?text=Pokemon+tcg&lang=pl&page_size=60"
PRODUCT_URL = "https://rozetka.pl/api/product-api/v4/goods/get-main?front-type=xl&country=PL&lang=pl&goodsId={}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
EXCLUDE = [
    "spanish", "espanol", "planszow", "gra planszowa", "board game", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk",
    "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese", "ultra pro", "ultra-pro",
    "playmat", "portfolio", "pro-binder", "sleeves", "toploader", "album", "koszulk", "segregator",
    "deck box", "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]

async def fetch_product(session, pid, sem):
    async with sem:
        for attempt in range(3):
            try:
                url = PRODUCT_URL.format(pid)
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("data")
                    elif resp.status == 429:
                        await asyncio.sleep(2 * (attempt + 1))
                    else:
                        return None
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(1)
        return None

async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        search_data = None
        for attempt in range(3):
            try:
                async with session.get(SEARCH_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        search_data = await resp.json()
                        if search_data.get("data", {}).get("goods"):
                            break
            except Exception:
                pass
            if attempt < 2:
                await asyncio.sleep(3)

        if not search_data:
            return []

        goods = search_data.get("data", {}).get("goods", [])
        ids = [str(g.get("id", "")) for g in goods if g.get("id")]

        sem = asyncio.Semaphore(10)
        results = await asyncio.gather(*[fetch_product(session, pid, sem) for pid in ids])

    for d in results:
        if not d:
            continue
        title = d.get("title", "")
        if any(ex in title.lower() for ex in EXCLUDE):
            continue
        pid = str(d.get("id", ""))
        price_val = d.get("price")
        price = f"{price_val} PLN" if price_val else "brak"
        href = d.get("href", "")
        sell_status = d.get("sell_status", "")
        available = sell_status == "available"
        images = d.get("images", [])
        image = ""
        if images:
            image = images[0].get("original", {}).get("url", "")
        products.append({
            "id": f"rozetka_{pid}",
            "name": title,
            "price": price,
            "shop": SHOP,
            "url": href,
            "image": image,
            "stock": 1 if available else 0,
            "available": available,
        })
    print(f"[ROZETKA] {len(products)} produktow")
    return products
