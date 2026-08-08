import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

BASE_URL = "https://kupteraz.com.pl/pokemon"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}


async def fetch_page(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), ssl=False) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None


async def get_products():
    products = []
    seen_ids = set()

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html1 = await fetch_page(session, BASE_URL)
        if not html1:
            return []

        soup1 = BeautifulSoup(html1, "lxml")

        # Detect max page
        pages = {1}
        for a in soup1.select("a"):
            href = a.get("href", "")
            m = re.search(r"/pokemon/(\d+)", href)
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages)

        # Parallel fetch remaining pages
        pages_html = [html1]
        if max_page > 1:
            tasks = [fetch_page(session, f"{BASE_URL}/{p}") for p in range(2, max_page + 1)]
            results = await asyncio.gather(*tasks)
            pages_html += [h for h in results if h]

    for i, html in enumerate(pages_html):
        soup = BeautifulSoup(html, "lxml") if i > 0 else soup1
        tiles = soup.select("product-tile")
        for tile in tiles:
            pid = tile.get("product-id")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            name = tile.get("name", "")
            if not name:
                continue
            price_val = tile.get("price", "0")
            price = f"{price_val} PLN"
            href = tile.select_one("a")
            href = href.get("href", "") if href else ""
            product_url = f"https://kupteraz.com.pl{href}" if href.startswith("/") else href
            img_el = tile.select_one("img")
            image = ""
            if img_el:
                image = img_el.get("src") or img_el.get("data-src", "")
                if image and not image.startswith("http"):
                    image = "https://kupteraz.com.pl" + image
            try:
                stock_val = int(tile.get("data-basestock", 0))
            except ValueError:
                stock_val = 0
            available = stock_val > 0
            products.append({
                "id": f"kupteraz_{pid}",
                "name": name,
                "price": price,
                "shop": "kupteraz",
                "url": product_url,
                "image": image,
                "stock": 1 if available else 0,
                "available": available,
            })

    return products
