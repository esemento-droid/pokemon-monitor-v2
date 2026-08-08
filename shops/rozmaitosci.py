import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

BASE_URL = "https://www.skleprozmaitosci.pl/Pokemon_TCG"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

async def fetch_page(session, page):
    url = BASE_URL if page == 1 else f"{BASE_URL}/pa/{page}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None

def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    for fig in soup.select("figure.product-tile"):
        name_el = fig.select_one(".product-name a")
        if not name_el:
            continue
        name = name_el.text.strip()
        href = name_el.get("href", "")
        product_url = f"https://www.skleprozmaitosci.pl{href}" if href.startswith("/") else href
        pid = href.rstrip("/").split("-p")[-1] if "-p" in href else href
        if not pid:
            continue
        price_el = fig.select_one("[data-price]")
        price_val = price_el.get("data-price", "") if price_el else ""
        price = f"{price_val} PLN" if price_val else "brak"
        img_el = fig.select_one("img[data-src], img[src]")
        image = ""
        if img_el:
            image = img_el.get("data-src") or img_el.get("src", "")
            if image and not image.startswith("http"):
                image = "https://www.skleprozmaitosci.pl" + image
        fig_text = fig.get_text(" ", strip=True).lower()
        available = "brak" not in fig_text and "niedost" not in fig_text
        products.append({"id": f"rozmaitosci_{pid}", "name": name, "price": price, "shop": "rozmaitosci", "url": product_url, "image": image, "stock": 1 if available else 0, "available": available})
    return products

async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html1 = await fetch_page(session, 1)
        if not html1:
            return []
        soup1 = BeautifulSoup(html1, "lxml")
        pages = set()
        for a in soup1.select("a"):
            m = re.search(r"/pa/(\d+)", a.get("href", ""))
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages) if pages else 1
        for prod in parse_page(html1):
            if prod["id"] not in seen_ids:
                seen_ids.add(prod["id"])
                products.append(prod)
        if max_page > 1:
            rest = await asyncio.gather(*[fetch_page(session, p) for p in range(2, max_page + 1)])
            for html in rest:
                if not html:
                    continue
                for prod in parse_page(html):
                    if prod["id"] not in seen_ids:
                        seen_ids.add(prod["id"])
                        products.append(prod)
    return products
