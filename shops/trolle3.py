import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

BASE_URL = "https://3trolle.pl/szukaj?controller=search&s=pokemon+tcg"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

async def fetch_page(session, page):
    url = BASE_URL if page == 1 else f"{BASE_URL}&page={page}"
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
    arts = soup.select("article.product-miniature")
    for a in arts:
        pid = a.get("data-id-product")
        if not pid:
            continue
        title_el = a.select_one(".product-title a, h2 a")
        if not title_el:
            continue
        name = title_el.text.strip()
        if "deck" in name.lower():
            continue
        href = title_el.get("href", "")
        price_el = a.select_one("span.product-price[content]")
        price = price_el.get("content", "") + " PLN" if price_el else "brak"
        img_el = a.select_one("img[data-src]")
        image = img_el.get("data-src", "") if img_el else ""
        txt = a.get_text(" ", strip=True).lower()
        available = "brak" not in txt
        products.append({"id": f"3trolle_{pid}", "name": name, "price": price, "shop": "3trolle", "url": href, "image": image, "stock": 1 if available else 0, "available": available})
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
        for a in soup1.select("a[href*=page]"):
            m = re.search(r"page=(\d+)", a.get("href", ""))
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
