import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "arena-sklep"
BASE = "https://arena-sklep.pl"
CATEGORIES = ["/15-pokemon-tcg", "/140-pokemon-day-2026-30th-anniversary"]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

async def fetch_page(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None

async def get_products():
    products = []
    seen_ids = set()

    urls = [BASE + cat for cat in CATEGORIES]
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        pages_html = await asyncio.gather(*[fetch_page(session, url) for url in urls])

    for html in pages_html:
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        for art in soup.select("article.product-miniature"):
            pid = art.get("data-id-product", "")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            title_el = art.select_one(".product-title a, h2 a")
            name = title_el.text.strip() if title_el else ""
            if not name:
                continue
            href = title_el.get("href", "") if title_el else ""

            price_el = art.select_one("span.price")
            price = "brak"
            if price_el:
                price_txt = price_el.text.strip()
                m = re.search(r"[\d]+[,,][\d]{2}", price_txt.replace("\xa0", ""))
                if m:
                    price = f"{m.group(0)} zl"

            img_el = art.select_one("img")
            image = ""
            if img_el:
                image = img_el.get("data-src") or img_el.get("src") or ""

            txt = art.get_text(" ", strip=True).lower()
            available = "brak" not in txt and "niedost" not in txt

            products.append({
                "id": f"arena_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": href,
                "image": image,
                "stock": 1 if available else 0,
                "available": available,
            })

    print(f"[ARENA] {len(products)} produktow")
    return products
