import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "poketeka.pl"
BASE = "https://www.poketeka.pl"
CAT = "/56-pokemon-tcg"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
MAX_PAGES = 12

async def fetch_page(session, page):
    url = f"{BASE}{CAT}?page={page}" if page > 1 else f"{BASE}{CAT}"
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

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        pages_html = await asyncio.gather(*[fetch_page(session, p) for p in range(1, MAX_PAGES + 1)])

    for html in pages_html:
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        prods = soup.select(".product-miniature.js-product-miniature")
        for p in prods:
            pid = p.get("data-id-product", "")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            title_el = p.select_one(".product-title a")
            name = title_el.get_text(strip=True) if title_el else ""
            href = title_el.get("href", "") if title_el else ""
            if href and not href.startswith("http"):
                href = BASE + href

            price_el = p.select_one("span.price, .product-price-and-shipping .price")
            price = "brak"
            if price_el:
                price_txt = price_el.get_text(strip=True)
                m = re.search(r"[\d]+[,,][\d]{2}", price_txt.replace("\xa0", ""))
                if m:
                    price = f"{m.group(0)} zl"

            img_el = p.select_one("img")
            image = ""
            if img_el:
                image = img_el.get("data-src") or img_el.get("src") or ""
                if image and not image.startswith("http"):
                    image = BASE + image

            tile_text = p.get_text(" ", strip=True).lower()
            available = "brak na stanie" not in tile_text.lower() and "niedost" not in tile_text.lower()

            products.append({
                "id": pid,
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": href,
                "image": image,
                "stock": "Dostepny" if available else "Niedostepny",
                "available": available,
            })

    print(f"[{SHOP}] FINAL: {len(products)} produktow")
    return products
