import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

SHOP = "pokespot"
BASE = "https://pokespot.pl"
CAT_URL = f"{BASE}/Pokemon-TCG/3"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}

EXCLUDE = [
    "sleeve", "koszulk", "toploader", "playmat", "album", "portfolio", "binder", "ultra pro",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra-pro", "segregator", "deck box", "alcove", "lorcana", "one piece", "yu-gi-oh",
    "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]

async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS, connector=aiohttp.TCPConnector(ssl=False)) as session:
        async with session.get(CAT_URL, timeout=aiohttp.ClientTimeout(total=30)) as r:
            html = await r.text()

        max_page = 1
        for m in re.findall(r'/Pokemon-TCG/3/default/(\d+)', html):
            p = int(m)
            if p > max_page:
                max_page = p

        pages_html = [html]

        if max_page > 1:
            async def fetch_page(pg):
                async with session.get(f"{CAT_URL}/default/{pg}", timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    return await resp.text()
            tasks = [fetch_page(pg) for pg in range(2, max_page + 1)]
            pages_html += await asyncio.gather(*tasks)

        for page_html in pages_html:
            soup = BeautifulSoup(page_html, "lxml")
            for t in soup.select("product-tile"):
                pid = t.get("product-id", "")
                if not pid:
                    continue

                name = t.get("name", "")
                if not name:
                    continue

                name_low = name.lower()
                if any(ex in name_low for ex in EXCLUDE):
                    continue

                price = t.get("price", "")
                if price:
                    price = f"{price} zl"

                text = t.get_text(" ", strip=True).lower()
                available = "niedost" not in text

                link = t.select_one("a[href]")
                url = ""
                if link and link.get("href"):
                    href = link["href"]
                    url = BASE + href if href.startswith("/") else href

                img = t.select_one("img[data-src]") or t.select_one("img[src]")
                image = ""
                if img:
                    image = img.get("data-src") or img.get("src") or ""
                    if image and not image.startswith("http"):
                        image = BASE + image

                products.append({
                    "id": f"{SHOP}_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": url,
                    "image": image,
                    "stock": None,
                    "available": available,
                })

    return products

if __name__ == "__main__":
    async def test():
        prods = await get_products()
        avail = [p for p in prods if p["available"]]
        print(f"Total: {len(prods)}, available: {len(avail)}")
        for p in prods[:5]:
            print(f"  {p['id']} | {p['name'][:50]} | {p['price']} | avail={p['available']}")
    asyncio.run(test())
