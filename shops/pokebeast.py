import aiohttp
from bs4 import BeautifulSoup
BASE_URL = "https://pokebeast.pl/pl/c/Pokemon-ENG/48"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for page in range(1, 10):
            url = BASE_URL if page == 1 else f"{BASE_URL}?page={page}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=45), ssl=False) as resp:
                if resp.status != 200:
                    break
                html = await resp.text()
            soup = BeautifulSoup(html, "lxml")
            tiles = soup.select("product-tile")
            if not tiles:
                break
            for tile in tiles:
                pid = tile.get("product-id")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                name = tile.get("name", "")
                if not name:
                    continue
                price_val = tile.get("price", "0")
                price = f"{price_val} PLN"
                href = tile.select_one("a")
                href = href.get("href", "") if href else ""
                product_url = f"https://pokebeast.pl{href}" if href.startswith("/") else href
                img_el = tile.select_one("img")
                image = ""
                if img_el:
                    image = img_el.get("src") or img_el.get("data-src", "")
                    if image and not image.startswith("http"):
                        image = "https://pokebeast.pl" + image
                txt = tile.get_text(" ", strip=True).lower()
                available = "brak" not in txt and "niedost" not in txt
                products.append({"id": f"pokebeast_{pid}", "name": name, "price": price, "shop": "pokebeast", "url": product_url, "image": image, "stock": 1 if available else 0, "available": available})
            nxt = soup.select_one("link[rel=" + chr(39) + "next" + chr(39) + "]")
            if not nxt:
                break
    return products
