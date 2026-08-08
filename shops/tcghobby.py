import aiohttp
import json
import html as html_mod

SHOP = "tcghobby"
BASE = "https://tcghobby.pl"
API_URL = f"{BASE}/wp-json/wc/store/v1/products?per_page=100&category=pokemon"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}

EXCLUDE = ["sleeve", "koszulk", "toploader", "playmat", "album", "portfolio", "binder", "ultra pro", "single"]

async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        page = 1
        while True:
            url = f"{API_URL}&page={page}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = await r.json()
            if not isinstance(data, list) or not data:
                break
            for p in data:
                pid = p.get("id", "")
                name = html_mod.unescape(p.get("name", ""))
                if not name:
                    continue
                name_low = name.lower()
                if any(ex in name_low for ex in EXCLUDE):
                    continue
                prices = p.get("prices", {})
                price_raw = prices.get("price", "0")
                price = f"{int(price_raw)/100:.2f} zl" if price_raw else ""
                available = p.get("is_in_stock", False)
                url_prod = p.get("permalink", "")
                images = p.get("images", [])
                image = images[0].get("src", "") if images else ""
                products.append({
                    "id": f"{SHOP}_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": url_prod,
                    "image": image,
                    "stock": None,
                    "available": available,
                })
            if len(data) < 100:
                break
            page += 1
    return products

if __name__ == "__main__":
    import asyncio
    async def test():
        prods = await get_products()
        avail = [p for p in prods if p["available"]]
        print(f"Total: {len(prods)}, available: {len(avail)}")
        for p in prods[:5]:
            print(f"  {p['id']} | {p['name'][:50]} | {p['price']} | avail={p['available']}")
    asyncio.run(test())
