"""
Scraper: dystryktzero.pl (Cloudflare protected)
Method: FlareSolverr → HTML parse
Category: SLOW (FlareSolverr)
NOTE: Must be added to SLOW_SHOPS in main.py
"""

import aiohttp
from bs4 import BeautifulSoup

SHOP = "dystryktzero"
SCAN_TIMEOUT = 180  # CF solver: semaphore queue + 55s solve
URL = "https://www.dystryktzero.pl/karty-pokemon/"
FLARESOLVERR_URL = "http://localhost:8191/v1"

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "battle deck", "league battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)", "figurk", "puzzle", "zeszyt",
]


async def get_products() -> list[dict]:
    products = []

    payload = {
        "cmd": "request.get",
        "url": URL,
        "maxTimeout": 55000,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{FLARESOLVERR_URL}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                data = await resp.json()

        if data.get("status") != "ok":
            print(f"[DYSTRYKTZERO] FlareSolverr error: {data.get('message','')}")
            return []

        html = data.get("solution", {}).get("response", "")
        if not html:
            print(f"[DYSTRYKTZERO] empty response")
            return []

    except Exception as e:
        print(f"[DYSTRYKTZERO] Error: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")
    seen = set()

    # Try common product selectors
    for sel in ["li.product", "li.type-product", ".product-item", ".product-card",
                ".product-miniature", "article.product", ".product-wrapper",
                "[class*=ProductCard]", "[class*=product-card]"]:
        items = soup.select(sel)
        if items and len(items) > 1:
            for item in items:
                a = item.find("a", href=True)
                if not a:
                    continue
                url = a.get("href", "")
                if url in seen:
                    continue

                name_el = item.select_one("h2, h3, [class*=name], [class*=title]")
                name = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    continue
                seen.add(url)

                name_lower = name.lower()
                if any(ex in name_lower for ex in EXCLUDE):
                    continue

                price_el = item.select_one("[class*=price], .price")
                price = price_el.get_text(strip=True) if price_el else "brak"

                try:
                    import re
                    pv = float(re.search(r"(\d+[.,]\d+)", price).group(1).replace(",", "."))
                    if pv < 10:
                        continue
                except (AttributeError, ValueError):
                    pass

                img = item.select_one("img")
                image = img.get("data-src") or img.get("src") or "" if img else ""

                classes = item.get("class", [])
                available = not any("outofstock" in c or "unavailable" in c for c in classes)
                if not available:
                    avail_el = item.select_one("[class*=avail], [class*=stock]")
                    if avail_el and "dostępn" in avail_el.get_text(strip=True).lower():
                        available = True

                full_url = url if url.startswith("http") else f"https://dystryktzero.pl{url}"
                pid = url.rstrip("/").split("/")[-1]

                products.append({
                    "id": f"{SHOP}_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": full_url,
                    "image": image,
                    "stock": 1 if available else 0,
                    "available": available,
                })
            break

    print(f"[DYSTRYKTZERO] {len(products)} produktow")
    return products


if __name__ == "__main__":
    import asyncio
    prods = asyncio.run(get_products())
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:60]:60} | {p['price']}")
