import aiohttp
import asyncio

API_URL = "https://pokenest.pl/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
EXCLUDE = ["japońska karta", "karta pokémon", "karta pokemon", "ultra pro", "album",
           "segregator", "battle deck", "league battle", "psa ", "x psa",
           "koszulki", "toploader", "sleeve", "zestaw"]

async def fetch_page(session, page):
    url = f"{API_URL}?per_page=100&page={page}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200: return []
            return await resp.json()
    except: return []

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        pages = await asyncio.gather(*[fetch_page(session, p) for p in range(1, 4)])
        for data in pages:
            for p in data:
                cats = [c.get("slug", "") for c in p.get("categories", [])]
                if not any("pokemon" in c for c in cats): continue
                pid = str(p.get("id", ""))
                if not pid or pid in seen: continue
                seen.add(pid)
                name = p.get("name", "").replace("&#8211;", "-").replace("&#8217;", "'").replace("&amp;", "&").replace("&#038;", "&")
                name_low = name.lower()
                if any(ex in name_low for ex in EXCLUDE): continue
                pr = p.get("prices", {}).get("price", "0")
                price = f"{int(pr)/100:.2f} PLN" if pr else "brak"
                imgs = p.get("images", [])
                image = imgs[0].get("src", "") if imgs else ""
                products.append({"id": f"pokenest_{pid}", "name": name, "price": price, "shop": "pokenest", "url": p.get("permalink", ""), "image": image, "stock": 1 if p.get("is_in_stock", False) else 0, "available": p.get("is_in_stock", False)})
    return products