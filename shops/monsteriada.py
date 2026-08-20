"""
Scraper: monsteriada.pl (PrestaShop — NO Cloudflare, direct aiohttp)
Kategoria: /93-pokemon-tcg-karty-kolekjonerskie
Pagination: ?page=N (up to 8 pages, parallel fetch)
Category: SLOW (many pages, sequential for politeness)
"""

import asyncio
import re

import aiohttp
from bs4 import BeautifulSoup

SHOP = "monsteriada"
MARK_MISSING_AS_OOS = True  # Site hides OOS from listing — mark missing products as unavailable for RESTOCK detection
BASE = "https://monsteriada.pl"
CATEGORY_URL = f"{BASE}/93-pokemon-tcg-karty-kolekjonerskie"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
MAX_PAGES = 8

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "battle deck", "league battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)", "figurk", "puzzle", "zeszyt",
    "pluszak", "brelok", "kubek", "szklank", "maskotk",
    "władca pierścieni", "lord of the ring", "tales of middle",
]


PROXY = "http://127.0.0.1:8888"


async def _fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch via mobile proxy (VPS IP is CF-banned on this site since ~2026-08-20)."""
    for attempt in range(2):
        try:
            async with session.get(url, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status == 200:
                    return await resp.text()
                if resp.status == 403 and attempt == 0:
                    # Fallback: try direct
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp2:
                        if resp2.status == 200:
                            return await resp2.text()
        except Exception:
            if attempt == 0:
                await asyncio.sleep(2)
    return ""


def _parse_page(html: str, seen: set) -> list[dict]:
    products = []
    soup = BeautifulSoup(html, "lxml")
    items = soup.select(".product-miniature, article.product-miniature")

    for item in items:
        name_el = item.select_one(".product-title a, h2 a, h3 a, .product-name a")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        url = name_el.get("href", "")
        if not name or not url or url in seen:
            continue
        seen.add(url)

        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        price_el = item.select_one(".product-price, .price, [itemprop=price]")
        price = price_el.get_text(strip=True) if price_el else "brak"

        try:
            import re
            pv = float(re.search(r"(\d+[\s\xa0]?\d*[.,]\d+)", price.replace("\xa0", "")).group(1).replace(",", ".").replace(" ", ""))
            if pv < 10:
                continue
        except (AttributeError, ValueError):
            pass

        img = item.select_one("img")
        image = ""
        if img:
            image = img.get("data-full-size-image-url") or img.get("data-src") or img.get("src") or ""

        avail_el = item.select_one(".product-availability, .availability")
        avail_text = avail_el.get_text(strip=True).lower() if avail_el else ""
        available = avail_text in ("dostępny", "dostepny", "przedsprzedaż", "przedsprzedaz", "w magazynie")

        pid = url.rstrip("/").split("/")[-1].split(".html")[0]

        products.append({
            "id": f"{SHOP}_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": 1 if available else 0,
            "available": available,
        })

    return products


async def get_products() -> list[dict]:
    products = []
    seen: set = set()

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Page 1
        html1 = await _fetch_page(session, CATEGORY_URL)
        if not html1:
            print(f"[MONSTERIADA] blad pobierania")
            return []

        products.extend(_parse_page(html1, seen))

        # Detect pagination
        soup = BeautifulSoup(html1, "lxml")
        page_links = soup.select(".pagination a, a[rel=next]")
        page_nums = set()
        for link in page_links:
            href = link.get("href", "")
            if "page=" in href:
                try:
                    num = int(href.split("page=")[-1].split("&")[0])
                    page_nums.add(num)
                except ValueError:
                    pass

        max_page = max(page_nums) if page_nums else 1
        max_page = min(max_page, MAX_PAGES)

        # Fetch remaining pages in parallel (no CF = safe to parallel)
        if max_page > 1:
            tasks = [_fetch_page(session, f"{CATEGORY_URL}?page={p}") for p in range(2, max_page + 1)]
            pages = await asyncio.gather(*tasks)
            for html in pages:
                if html:
                    products.extend(_parse_page(html, seen))

    print(f"[MONSTERIADA] {len(products)} produktow")
    return products


if __name__ == "__main__":
    import time
    start = time.time()
    prods = asyncio.run(get_products())
    elapsed = time.time() - start
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}, Time: {elapsed:.1f}s")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:60]:60} | {p['price']}")
