import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "czytam.pl"
BASE = "https://czytam.pl"
CAT = "/seria/pokemon"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
MAX_PAGES = 7

TCG_WORDS = ["tcg", "booster", "trainer box", "elite trainer", "etb", "blister", "collection", "premium", "tin ", "deck", "scarlet", "violet", "paldea", "obsidian", "prismatic", "mega evolution", "chaos rising", "pitch black", "destined rivals", "journey together"]

async def fetch_page(session, page):
    url = f"{BASE}{CAT}?page={page}" if page > 1 else f"{BASE}{CAT}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None

async def get_products():
    products = []
    seen_ids = set()

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        results = await asyncio.gather(*[fetch_page(session, p) for p in range(1, MAX_PAGES + 1)])
        pages_html = []
        for html in results:
            if not html or "product-box" not in html:
                break
            pages_html.append(html)

    for html in pages_html:
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        items = soup.select(".product-box")
        for item in items:
            pid = item.get("data-id", "")
            if not pid or pid in seen_ids:
                continue

            title_el = item.select_one("a.pblink")
            name = title_el.get("title", "") if title_el else ""
            name_low = name.lower()

            if not any(w in name_low for w in TCG_WORDS):
                continue

            seen_ids.add(pid)

            href = title_el.get("href", "") if title_el else ""

            price_el = item.select_one("[class*=price]")
            price = "brak"
            if price_el:
                m = re.search(r"[\d]+[.,][\d]{2}", price_el.get_text().replace(" ", ""))
                if m:
                    price = f"{m.group(0)} zl"

            img_el = item.select_one("img")
            image = ""
            if img_el:
                image = img_el.get("srcset", "").split()[0] if img_el.get("srcset") else img_el.get("src", "")

            tile_text = item.get_text(" ", strip=True).lower()
            available = "do koszyka" in tile_text

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
