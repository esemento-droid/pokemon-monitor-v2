import aiohttp
import re
from bs4 import BeautifulSoup

SHOP = "carddojo"
BASE = "https://carddojo.pl"
CAT_URL = f"{BASE}/pl/c/Pokemon/75"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}


EXCLUDE = ["battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean",
    "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "binder",
    "sleeve", "toploader", "album", "koszulk", "segregator",
    "deck box", "alcove",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto",
    "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz",
    "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"]


async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(CAT_URL, timeout=aiohttp.ClientTimeout(total=15)) as r:
            html = await r.text()

        max_page = 1
        for m in re.findall(r'/pl/c/Pokemon/75/(\d+)', html):
            p = int(m)
            if p > max_page:
                max_page = p

        pages_html = [html]

        if max_page > 1:
            import asyncio
            async def fetch_page(pg):
                async with session.get(f"{CAT_URL}/{pg}", timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    return await resp.text()
            tasks = [fetch_page(pg) for pg in range(2, max_page + 1)]
            pages_html += await asyncio.gather(*tasks)

        for page_html in pages_html:
            soup = BeautifulSoup(page_html, "lxml")
            for tile in soup.select("product-tile"):
                pid = tile.get("product-id", "")
                if not pid:
                    continue

                name = tile.get("name", "")
                if not name:
                    continue

                price_val = tile.get("price", "")
                price = f"{price_val} PLN" if price_val else ""

                link = tile.select_one("a[href]")
                url = ""
                if link and link.get("href"):
                    href = link["href"]
                    url = BASE + href if href.startswith("/") else href

                img = tile.select_one("img[data-src]") or tile.select_one("img[src]")
                image = ""
                if img:
                    image = img.get("data-src") or img.get("src") or ""
                    if image and not image.startswith("http"):
                        image = BASE + image

                tile_text = tile.get_text(" ", strip=True).lower()
                available = "koszyk" in tile_text or "dodaj" in tile_text

                if any(ex in name.lower() for ex in EXCLUDE): continue


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
    import asyncio
    async def test():
        prods = await get_products()
        avail = [p for p in prods if p["available"]]
        print(f"Total: {len(prods)}, available: {len(avail)}")
        for p in prods[:5]:
            print(f"  {p['id']} | {p['name'][:50]} | {p['price']} | avail={p['available']}")
    asyncio.run(test())
