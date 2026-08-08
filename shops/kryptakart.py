import aiohttp

API_URL = "https://kryptakart.pl/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}


async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        page = 1
        while True:
            url = f"{API_URL}?per_page=100&page={page}&category=angielskie-karty-pokemon"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    break
                data = await resp.json()
            if not data:
                break
            for p in data:
                pid = str(p.get("id", ""))
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                name = p.get("name", "").replace("&#8211;", "-").replace("&#8217;", "'").replace("&amp;", "&")
                price_raw = p.get("prices", {}).get("price", "0")
                price = f"{int(price_raw) / 100:.2f} PLN" if price_raw else "brak"
                images = p.get("images", [])
                image = images[0].get("src", "") if images else ""
                url_prod = p.get("permalink", "")
                available = p.get("is_in_stock", False)
                products.append({
                    "id": f"kryptakart_{pid}",
                    "name": name,
                    "price": price,
                    "shop": "kryptakart",
                    "url": url_prod,
                    "image": image,
                    "stock": 1 if available else 0,
                    "available": available,
                })
            if len(data) < 100:
                break
            page += 1
    return products
