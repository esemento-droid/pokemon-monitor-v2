import aiohttp
from bs4 import BeautifulSoup

SHOP = "stapis"
MARK_MISSING_AS_OOS = True  # Site hides OOS from listing — mark missing products as unavailable for RESTOCK detection
URL = "https://stapis.com.pl/?product_cat=pokemon-tcg"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

async def get_products():
    products = []
    async with aiohttp.ClientSession() as session:
        async with session.get(URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()

    soup = BeautifulSoup(html, "lxml")
    items = soup.select("li.type-product")

    for item in items:
        classes = item.get("class", [])
        available = "outofstock" not in classes

        a = item.find("a")
        if not a:
            continue
        product_url = a.get("href", "")

        img = item.find("img")
        image = ""
        if img:
            image = img.get("data-src") or img.get("src") or ""
            if "woocommerce-placeholder" in image:
                image = ""

        title = item.select_one("h2, h3, .woocommerce-loop-product__title")
        name = title.get_text(" ", strip=True) if title else ""
        if not name:
            continue

        p = item.select_one(".woocommerce-Price-amount")
        price = p.get_text(" ", strip=True) if p else ""

        products.append({
            "id": product_url,
            "name": name,
            "shop": "stapis",
            "price": price,
            "url": product_url,
            "image": image,
            "available": available,
            "stock": 1 if available else 0,
        })

    print(f"[STAPIS] {len(products)} produktow")
    return products
