"""
Scraper: Mugiwara.pl
Platform: Ecwid (Lightspeed)
Method: aiohttp (public API token)
Products: ~6
Availability: inStock field
"""

import aiohttp

API_URL = "https://app.ecwid.com/api/v3/120153270/products?category=184207770&limit=100"
HEADERS = {
    "Authorization": "Bearer public_knPMbJqLcYPiVASX1upCAiM8nHymqpNA",
    "User-Agent": "Mozilla/5.0",
}

async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(API_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return products
            data = await resp.json()
    for item in data.get("items", []):
        if "name" not in item:
            continue
        pid = item["id"]
        name = item["name"]
        price_val = item.get("price", 0)
        price = f"{price_val:.2f} PLN" if price_val else "brak"
        url = item.get("url", "")
        image = item.get("thumbnailUrl", "")
        in_stock = item.get("inStock", False)
        products.append({
            "id": f"mugiwara_{pid}",
            "name": name,
            "price": price,
            "shop": "mugiwara",
            "url": url,
            "image": image,
            "stock": 1 if in_stock else 0,
            "available": in_stock,
        })
    return products
