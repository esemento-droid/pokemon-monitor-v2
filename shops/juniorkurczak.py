import aiohttp

SHOP = "juniorkurczak"
API_URL = "https://app.ecwid.com/api/v3/111352604/products"
TOKEN = "public_nt3ritVaCxYq4mZtH1cFzQpcjFzSqBy7"
CATEGORY = 175912935
EXCLUDE = ["album", "koszulk", "sleeve", "deck box", "zawieszk", "lego", "planszow", "książk", "ksiazk", "korea", "chiński", "chińsk", "chinese", "korean", "koreański", "koreansk", "japoński", "japońsk", "japanese", "japonsk"]

async def get_products():
    products = []
    params = {
        "category": CATEGORY,
        "limit": 100,
        "token": TOKEN,
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, params=params,
                               timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                print(f"[JUNIORKURCZAK] HTTP {resp.status}")
                return []
            data = await resp.json()
    for item in data.get("items", []):
        name = item.get("name", "")
        name_low = name.lower()
        if any(ex in name_low for ex in EXCLUDE):
            continue
        price = item.get("price", 0)
        in_stock = item.get("inStock", False)
        quantity = item.get("quantity", 0)
        enabled = item.get("enabled", True)
        url = item.get("url", "")
        image = ""
        if item.get("imageUrl"):
            image = item["imageUrl"]
        elif item.get("thumbnailUrl"):
            image = item["thumbnailUrl"]
        products.append({
            "id": f"juniorkurczak_{item['id']}",
            "name": name,
            "price": f"{price} zl",
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": quantity if quantity else None,
            "available": in_stock and enabled,
        })
    print(f"[JUNIORKURCZAK] {len(products)} produktow")
    return products
