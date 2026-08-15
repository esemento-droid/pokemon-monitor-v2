import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

SHOP = "pokemaniak"
BASE = "https://pokemaniak.pl"
CATS = [
    f"{BASE}/pl/c/Pokemon-TCG-Angielskie-Produkty/21",
    f"{BASE}/pl/c/Preorder/35",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}

EXCLUDE = [
    "sleeves", "koszulk", "toploader", "playmat", "album", "portfolio", "pro-binder", "ultra pro",
    "single", "one piece", "japońsk", "japanese", "japonsk", "battle deck", "league battle",
    "rival battle", "v battle", "world championship", "wcs deck", "wcs ", "battle academy",
    "(jp)", "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)",
    "s-chinese", "ultra-pro", "segregator", "deck box", "alcove", "lorcana", "yu-gi-oh",
    "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]


async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for cat_url in CATS:
            page = 1
            prev_ids = set()
            while True:
                url = cat_url if page == 1 else f"{cat_url}/{page}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    html = await r.text()
                soup = BeautifulSoup(html, "lxml")
                tiles = soup.select("product-tile")
                if not tiles:
                    break
                current_ids = set(t.get("product-id", "") for t in tiles)
                if current_ids == prev_ids:
                    break
                prev_ids = current_ids
                for t in tiles:
                    pid = t.get("product-id", "")
                    if not pid or pid in seen:
                        continue
                    seen.add(pid)
                    name = t.get("name", "")
                    if not name:
                        continue
                    name_low = name.lower()
                    if any(ex in name_low for ex
 in EXCLUDE):
                        continue
                    if "pokemon" not in name_low and "pokémon" not in name_low:
                        continue
                    price = t.get("price", "")
                    if price:
                        price = f"{price} zl"
                    text = t.get_text(" ", strip=True).lower()
                    available = "koszyk" in text
                    link = t.select_one("a[href]")
                    url = ""
                    if link and link.get("href"):
                        href = link["href"]
                        url = BASE + href if href.startswith("/") else href
                    img = t.select_one("img[data-src]") or t.select_one("img[src]")
                    image = ""
                    if img:
                        image = img.get("data-src") or img.get("src") or ""
                        if image and not image.startswith("http"):
                            image = BASE + image
                    products.append({
                        "id": f"{SHOP}_{pid}",
                        "name": name,
                        "price": price,
                        "shop": SHOP,
                        "url": url,
                        "image": image,
                        "stock": None,
                        "available": available,
                    })
                page += 1
    return products


if __name__ == "__main__":
    async def test():
        prods = await get_products()
        avail = [p for p in prods if p["available"]]
        print(f"Total: {len(prods)}, available: {len(avail)}")
        for p in prods[:5]:
            print(f"  {p['id']} | {p['name'][:50]} | {p['price']} | avail={p['available']}")
    asyncio.run(test())
