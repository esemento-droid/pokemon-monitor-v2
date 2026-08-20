"""
Scraper: maginarium.pl (WooCommerce — NO Cloudflare, direct aiohttp)
Search URL: /?s=Pokemon+tcg+&post_type=product
15+ pages, parallel fetch.
Category: SLOW (many pages)
"""

import asyncio

import aiohttp
from bs4 import BeautifulSoup

SHOP = "maginarium"
BASE = "https://maginarium.pl"
SEARCH_PARAMS = "?s=Pokemon+tcg+&post_type=product"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
MAX_PAGES = 30

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "battle deck", "league battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "battle arena", "theme deck",
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)", "figurk", "puzzle", "zeszyt",
]


PROXY = "http://127.0.0.1:8888"


async def _fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch via mobile proxy (VPS IP is CF-banned on this site since ~2026-08-20)."""
    for attempt in range(2):
        try:
            async with session.get(url, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status == 200:
                    return await resp.text()
                if resp.status == 404:
                    return ""  # Page doesn't exist (past last page)
                if resp.status == 403:
                    # CF challenge via proxy too — try without proxy as last resort
                    if attempt == 0:
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
    items = soup.select("li.product, li.type-product")

    for item in items:
        classes = item.get("class", [])
        available = "outofstock" not in classes

        a = item.find("a")
        if not a:
            continue
        url = a.get("href", "")
        if not url or url in seen:
            continue
        seen.add(url)

        title = item.select_one("h2, h3, .woocommerce-loop-product__title")
        name = title.get_text(" ", strip=True) if title else ""
        if not name:
            continue

        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        price_el = item.select_one(".woocommerce-Price-amount")
        price = price_el.get_text(strip=True) if price_el else "brak"

        try:
            pv = float(price.replace("zł", "").replace("\xa0", "").replace(",", ".").replace(" ", ""))
            if pv < 10:
                continue
        except (ValueError, AttributeError):
            pass

        img = item.find("img")
        image = ""
        if img:
            image = img.get("data-src") or img.get("src") or ""
            if "woocommerce-placeholder" in image:
                image = ""

        pid = url.rstrip("/").split("/")[-1]

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
        # Page 1 first (to check if site responds)
        url1 = f"{BASE}/{SEARCH_PARAMS}"
        html1 = await _fetch_page(session, url1)
        if not html1:
            print("[MAGINARIUM] blad pobierania strony 1")
            return []

        products.extend(_parse_page(html1, seen))

        # Parallel fetch remaining pages (no CF = safe)
        # Fetch in batches of 5 to be polite
        for batch_start in range(2, MAX_PAGES + 1, 5):
            batch_end = min(batch_start + 5, MAX_PAGES + 1)
            urls = [f"{BASE}/page/{p}/{SEARCH_PARAMS}" for p in range(batch_start, batch_end)]
            tasks = [_fetch_page(session, u) for u in urls]
            pages = await asyncio.gather(*tasks)

            empty_count = 0
            for html in pages:
                if not html:
                    empty_count += 1
                    continue
                new = _parse_page(html, seen)
                if not new:
                    empty_count += 1
                else:
                    products.extend(new)

            # If most pages in batch are empty, we've hit the end
            if empty_count >= 3:
                break

    print(f"[MAGINARIUM] {len(products)} produktow")
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
