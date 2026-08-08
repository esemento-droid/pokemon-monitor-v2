import aiohttp
import re
from bs4 import BeautifulSoup

SHOP = "graal"
BASE = "https://sklep-graal.pl"
CAT_URL = f"{BASE}/pl/c/Pokemon-TCG/25"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}

EXCLUDE = ["sleeve", "koszulk", "toploader", "album", "portfolio", "binder", "ultra pro", "playmat", "koszulek"]

async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(CAT_URL, timeout=aiohttp.ClientTimeout(total=30)) as r:
            html = await r.text()
        max_page = 1
        for m in re.findall(r'/pl/c/Pokemon-TCG/25/(\d+)', html):
            p = int(m)
            if p > max_page:
                max_page = p
        pages_html = [html]
        if max_page > 1:
            import asyncio
            async def fetch_page(pg):
                async with session.get(f"{CAT_URL}/{pg}", timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    return await resp.text()
            tasks = [fetch_page(pg) for pg in range(2, max_page + 1)]
            pages_html += await asyncio.gather(*tasks)
        for page_html in pages_html:
            soup = BeautifulSoup(page_html, "lxml")
            for div in soup.select("div[data-product-id]"):
                pid = div.get("data-product-id", "")
                if not pid:
                    continue
                name_el = div.select_one("span.productname")
                name = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    continue
                name_low = name.lower()
                if any(ex in name_low for ex in EXCLUDE):
                    continue
                link_el = div.select_one("a.prodname")
                url = BASE + link_el["href"] if link_el and link_el.get("href") else ""
                img_el = div.select_one("img[data-src]")
                image = img_el["data-src"] if img_el else ""
                if image and not image.startswith("http"):
                    image = BASE + image
                price_el = div.select_one("div.price em")
                price = price_el.get_text(strip=True) if price_el else ""
                available = "basket/add" in str(div)
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
