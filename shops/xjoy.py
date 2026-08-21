"""
Scraper: xjoy.pl (PrestaShop + Cloudflare)
Category: /278-pokemon-tcg
Method: FlareSolverr → HTML parse (PrestaShop product-miniature)
Category: SLOW (FlareSolverr)
NOTE: Must be added to SLOW_SHOPS in main.py
"""

import asyncio

import aiohttp
from bs4 import BeautifulSoup

SHOP = "xjoy"
SCAN_TIMEOUT = 180  # Extended: CF solver needs 55s+ for Turnstile on this site
BASE = "https://www.xjoy.pl"
CATEGORY_URL = f"{BASE}/278-pokemon-tcg"
FLARESOLVERR_URL = "http://localhost:8191/v1"
MAX_PAGES = 5

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "battle deck", "league battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)", "figurk", "puzzle", "zeszyt",
    "marvel", "dc comics", "harry potter", "lord of the rings",
]


def _parse_page(html: str, seen: set) -> list[dict]:
    products = []
    soup = BeautifulSoup(html, "lxml")
    items = soup.select("article, .product-miniature, article.product-miniature")

    for item in items:
        name_el = item.select_one(".product-title a, h2 a, h3 a")
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
            pv = float(re.search(r"(\d+[.,]\d+)", price).group(1).replace(",", "."))
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
        available = "dostępn" in avail_text or "w magazyn" in avail_text or "in stock" in avail_text

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

    payload = {
        "cmd": "request.get",
        "url": CATEGORY_URL,
        "maxTimeout": 60000,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{FLARESOLVERR_URL}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=70),
            ) as resp:
                data = await resp.json()

        if data.get("status") != "ok":
            print(f"[XJOY] FlareSolverr error: {data.get('message','')}")
            return []

        html = data.get("solution", {}).get("response", "")
        if not html:
            print(f"[XJOY] empty response")
            return []

    except Exception as e:
        print(f"[XJOY] Error: {e}")
        return []

    products.extend(_parse_page(html, seen))

    # Check for pagination and fetch more pages
    soup = BeautifulSoup(html, "lxml")
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

    # Fetch additional pages via FlareSolverr
    for page in range(2, max_page + 1):
        page_payload = {
            "cmd": "request.get",
            "url": f"{CATEGORY_URL}?page={page}",
            "maxTimeout": 60000,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{FLARESOLVERR_URL}",
                    json=page_payload,
                    timeout=aiohttp.ClientTimeout(total=70),
                ) as resp:
                    page_data = await resp.json()
            if page_data.get("status") == "ok":
                page_html = page_data.get("solution", {}).get("response", "")
                if page_html:
                    products.extend(_parse_page(page_html, seen))
        except Exception:
            pass

    print(f"[XJOY] {len(products)} produktow")
    return products


if __name__ == "__main__":
    prods = asyncio.run(get_products())
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:60]:60} | {p['price']}")
