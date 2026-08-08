import aiohttp
import asyncio

BASE_URL = "https://pokeverse.pl/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
EXCLUDE = ["singl", "psa ", "cgc ", "slab ", "sleeve", "koszulk", "toploader", "binder", "portfolio", "ultra pro", "playmat"]


async def get_products():
    products = []
    seen = set()
    page = 1
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        while True:
            url = f"{BASE_URL}?per_page=100&category=karty-pokemon-tcg&page={page}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    break
                data = await resp.json()
            if not data:
                break
            for item in data:
                pid = str(item.get("id", ""))
                name = item.get("name", "").replace("&#8211;", "-").replace("&ndash;", "-")
                if not pid or not name:
                    continue
                if pid in seen:
                    continue
                seen.add(pid)
                name_lower = name.lower()
                if any(ex in name_lower for ex in EXCLUDE):
                    continue
                prices = item.get("prices", {})
                raw_price = prices.get("price", "0")
                price_val = int(raw_price) / 100 if raw_price else 0
                price_str = f"{price_val:.2f} PLN" if price_val else "brak"
                available = item.get("is_in_stock", False)
                url_prod = item.get("permalink", "")
                images = item.get("images", [])
                image = images[0].get("src", "") if images else ""
                stock_text = item.get("stock_availability", {}).get("text", "")
                products.append({
                    "id": f"pokeverse_{pid}",
                    "name": name,
                    "price": price_str,
                    "shop": "pokeverse",
                    "url": url_prod,
                    "image": image,
                    "stock": stock_text,
                    "available": available,
                })
            if len(data) < 100:
                break
            page += 1
    return products
