"""
Scraper: eduksiazka.pl (SPA + Cloudflare)
Method: FlareSolverr → page render → parse product JSON from page
Platform: Custom SPA (React/Vue), requires full JS render
Category: SLOW (FlareSolverr)
NOTE: Must be added to SLOW_SHOPS in main.py
"""

import aiohttp
import json
import html as html_lib
import re

from bs4 import BeautifulSoup

SHOP = "eduksiazka"
SCAN_TIMEOUT = 120  # CF solver needs time
# Search URL for pokemon tcg products
URL = "https://eduksiazka.pl/gry-64/pokemon-karty-i-akcesoria-128"
FLARESOLVERR_URL = "http://localhost:8191/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

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
                timeout=aiohttp.ClientTimeout(total=70),
            ) as resp:
                data = await resp.json()

        if data.get("status") != "ok":
            print(f"[EDUKSIAZKA] FlareSolverr error: {data.get('message','')}")
            return []

        html = data.get("solution", {}).get("response", "")
        if not html:
            print(f"[EDUKSIAZKA] empty response")
            return []

    except Exception as e:
        print(f"[EDUKSIAZKA] Error: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")

    # Try to find product data in JSON or HTML
    # EdukSiazka SPA may embed product data in script tags
    scripts = soup.find_all("script")
    for s in scripts:
        text = s.string or ""
        if "products" in text and "price" in text and len(text) > 500:
            # Try to extract JSON array
            match = re.search(r'"products"\s*:\s*(\[.*?\])', text, re.DOTALL)
            if match:
                try:
                    items = json.loads(match.group(1))
                    for item in items:
                        name = html_lib.unescape(item.get("name", ""))
                        if not name:
                            continue
                        name_lower = name.lower()
                        if any(ex in name_lower for ex in EXCLUDE):
                            continue
                        price = item.get("price", {})
                        if isinstance(price, dict):
                            price_val = price.get("final", 0) or price.get("regular", 0)
                        else:
                            price_val = float(price) if price else 0
                        if 0 < price_val < 10:
                            continue
                        price_str = f"{price_val:.2f} zl" if price_val > 0 else "brak"
                        url = item.get("url", "") or item.get("link", "")
                        image = item.get("image", "") or item.get("thumbnail", "")
                        available = item.get("in_stock", False) or item.get("is_available", False)
                        pid = item.get("id", name)
                        products.append({
                            "id": f"{SHOP}_{pid}",
                            "name": name,
                            "price": price_str,
                            "shop": SHOP,
                            "url": url,
                            "image": image,
                            "stock": 1 if available else 0,
                            "available": available,
                        })
                except (json.JSONDecodeError, TypeError):
                    pass

    # Fallback: parse product elements from rendered HTML
    if not products:
        items = soup.select("[class*=product], [class*=Product]")
        seen = set()
        for item in items:
            a = item.find("a", href=True)
            if not a:
                continue
            url = a.get("href", "")
            if not url or url in seen:
                continue

            name_el = item.select_one("[class*=name], [class*=title], h2, h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name or "pokemon" not in name.lower():
                continue
            seen.add(url)

            name_lower = name.lower()
            if any(ex in name_lower for ex in EXCLUDE):
                continue

            price_el = item.select_one("[class*=price], [class*=Price]")
            price = price_el.get_text(strip=True) if price_el else "brak"

            img = item.select_one("img")
            image = img.get("src", "") if img else ""

            available = True  # assume available if rendered

            products.append({
                "id": url,
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": url if url.startswith("http") else f"https://eduksiazka.pl{url}",
                "image": image,
                "stock": 1 if available else 0,
                "available": available,
            })

    print(f"[EDUKSIAZKA] {len(products)} produktow")
    return products


if __name__ == "__main__":
    import asyncio
    prods = asyncio.run(get_products())
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:60]:60} | {p['price']}")
