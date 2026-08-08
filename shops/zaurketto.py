import re
"""
Scraper: Zaurketto.pl
Platform: Sky-Shop
Method: aiohttp + BeautifulSoup
Category: /Pokemon-TCG-c30 (8 pages)
Products: ~96
Availability: "brak" not in text = available
"""

import aiohttp
from bs4 import BeautifulSoup

BASE_URL = "https://zaurketto.pl/Pokemon-TCG-c30"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        import asyncio as _aio
        async def _fetch(s,pg):
            u = BASE_URL if pg == 1 else f"{BASE_URL}/pa/{pg}"
            async with s.get(u, timeout=aiohttp.ClientTimeout(total=30)) as r:
                return await r.text() if r.status == 200 else None
        html1 = await _fetch(session, 1)
        if not html1:
            return []
        soup1 = BeautifulSoup(html1, "lxml")
        pags = set()
        for a in soup1.select("a[href*='/pa/']"):
            m = re.search(r"/pa/(\d+)", a.get("href", ""))
            if m:
                pags.add(int(m.group(1)))
        max_page = max(pags) if pags else 1
        rest = await _aio.gather(*[_fetch(session,p) for p in range(2, max_page+1)]) if max_page > 1 else []
        pages = [html1] + list(rest)
        for html in pages:
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            figs = soup.select("figure.product-tile")
            if not figs:
                break
            for fig in figs:
                name_el = fig.select_one(".product-name")
                if not name_el:
                    continue
                name = name_el.text.strip()
                href = name_el.get("href", "")
                product_url = f"https://zaurketto.pl{href}" if href.startswith("/") else href
                pid = href.rstrip("/").split("-p")[-1] if "-p" in href else href
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                price_el = fig.select_one("[data-price]")
                price_val = price_el.get("data-price", "") if price_el else ""
                price = f"{price_val} PLN" if price_val else "brak"
                img_el = fig.select_one("img[data-src], img[src]")
                image = ""
                if img_el:
                    image = img_el.get("data-src") or img_el.get("src", "")
                    if image and not image.startswith("http"):
                        image = "https://zaurketto.pl" + image
                fig_text = fig.get_text(" ", strip=True).lower()
                available = "brak" not in fig_text and "niedost" not in fig_text
                # Skip decks (except 30th anniversary)
                name_lower = name.lower()
                if "deck" in name_lower and "30th" not in name_lower:
                    continue
                products.append({
                    "id": f"zaurketto_{pid}",
                    "name": name,
                    "price": price,
                    "shop": "zaurketto",
                    "url": product_url,
                    "image": image,
                    "stock": 1 if available else 0,
                    "available": available,
                })
            next_link = soup.select_one('link[rel="next"]')
            if not next_link:
                break
    return products
