import aiohttp
from bs4 import BeautifulSoup

CATEGORIES = ["https://futurex.pl/pl/c/POKEMON/809", "https://futurex.pl/pl/c/PRZEDSPRZEDAZ/766"]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
EXCLUDE = ["ultra pro", "up -", "portfolio", "deck box", "sleeve", "binder", "toploader", "protector", "koszulk"]

async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for cat_url in CATEGORIES:
            for page in range(1, 10):
                url = cat_url if page == 1 else f"{cat_url}/{page}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=45), ssl=False) as resp:
                    if resp.status != 200: break
                    html = await resp.text()
                soup = BeautifulSoup(html, "lxml")
                tiles = soup.select("product-tile")
                if not tiles: break
                for tile in tiles:
                    pid = tile.get("product-id")
                    name = tile.get("name", "")
                    if not pid or not name or pid in seen_ids: continue
                    nl = name.lower()
                    if not ("pokemon" in nl or "pokémon" in nl): continue
                    if any(ex in nl for ex in EXCLUDE): continue
                    seen_ids.add(pid)
                    price = tile.get("price", "0") + " PLN"
                    href = tile.select_one("a")
                    href = href.get("href", "") if href else ""
                    purl = f"https://futurex.pl{href}" if href.startswith("/") else href
                    img_el = tile.select_one("img")
                    image = ""
                    if img_el:
                        image = img_el.get("src") or img_el.get("data-src", "")
                        if image and not image.startswith("http"): image = "https://futurex.pl" + image
                    products.append({"id":f"futurex_{pid}","name":name,"price":price,"shop":"futurex","url":purl,"image":image,"stock":1 if "koszyk" in tile.get_text(" ", strip=True).lower() else 0,"available":"koszyk" in tile.get_text(" ", strip=True).lower()})
                nxt = soup.select_one("link[rel=" + chr(39) + "next" + chr(39) + "]")
                if not nxt: break
    return products
