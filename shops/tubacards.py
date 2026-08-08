import aiohttp
import asyncio

SHOP = "tubacards"
BASE_URL = "https://tubacards.pl/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "Mozilla/5.0"}
CATEGORIES = ["angielskie-pokemon-2", "mega-evolution-era", "scarlet-violet-era"]
EXCLUDE = ["japonsk", "japanese", "korean", "chinese", "sleeve", "koszulk", "turniej", "liga"]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for cat in CATEGORIES:
            url = f"{BASE_URL}?per_page=100&category={cat}"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
            except:
                continue
            for item in data:
                pid = str(item.get("id", ""))
                if pid in seen:
                    continue
                seen.add(pid)
                name = item.get("name", "").replace("&#8211;", "-").replace("&amp;", "&")
                if any(ex in name.lower() for ex in EXCLUDE):
                    continue
                price_raw = item.get("prices", {}).get("price", "0")
                try:
                    price = f"{int(price_raw) / 100:.2f} zl"
                except:
                    price = "brak"
                in_stock = item.get("is_in_stock", False)
                url = item.get("permalink", "")
                images = item.get("images", [])
                image = images[0].get("src", "") if images else ""
                products.append({"id": f"tubacards_{pid}", "name": name, "price": price, "shop": SHOP, "url": url, "image": image, "stock": None, "available": in_stock})
    print(f"[TUBACARDS] {len(products)} produktow")
    return products
