import aiohttp
from bs4 import BeautifulSoup

SHOP = "lukillo.pl"
BASE_URL = "https://lukillo.pl"
CATEGORY_URL = "/pl/c/Pokemon-TCG/46"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(BASE_URL + CATEGORY_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()

    soup = BeautifulSoup(html, "lxml")
    for tile in soup.select("product-tile"):
        pid = tile.get("product-id")
        if not pid or pid in seen:
            continue
        seen.add(pid)

        name = (tile.get("name") or "").strip()
        if not name:
            continue

        price_val = tile.get("price", "0")
        price = f"{price_val} PLN" if price_val else "brak"

        link = tile.select_one("a[href*='/pl/p/']")
        href = link.get("href", "") if link else ""
        url = BASE_URL + href if href.startswith("/") else href

        img_el = tile.select_one("img")
        image = ""
        if img_el:
            image = img_el.get("src") or img_el.get("data-src", "")
            if image and image.startswith("/"):
                image = BASE_URL + image

        txt = tile.get_text(" ", strip=True).lower()
        available = ("koszyk" in txt or "dodaj" in txt) and "niedost" not in txt

        products.append({
            "id": f"lukillo_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": 1 if available else 0,
            "available": available,
        })

    print(f"[lukillo] {len(products)} produktow")
    return products
