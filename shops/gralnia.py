"""
Scraper: gralnia.pl (redirects to aftermarket.pl — FlareSolverr needed)
Method: FlareSolverr → follow redirects → parse
Category: SLOW (FlareSolverr)
NOTE: Must be added to SLOW_SHOPS in main.py. Test on VPS!
URL may need update after checking actual redirect target with FlareSolverr.
"""

import aiohttp
from bs4 import BeautifulSoup

SHOP = "gralnia"
URL = "https://gralnia.pl/?s=pokemon+tcg&post_type=product"
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
        "maxTimeout": 30000,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{FLARESOLVERR_URL}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                data = await resp.json()

        if data.get("status") != "ok":
            print(f"[GRALNIA] FlareSolverr error: {data.get('message','')}")
            return []

        html = data.get("solution", {}).get("response", "")
        if not html:
            print(f"[GRALNIA] empty response")
            return []

    except Exception as e:
        print(f"[GRALNIA] Error: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")
    seen = set()

    # Try WooCommerce, PrestaShop, or generic selectors
    for sel_group in [
        ["li.product", "li.type-product"],
        [".product-miniature", "article.product-miniature"],
        [".product-item", ".product-card"],
    ]:
        items = []
        for sel in sel_group:
            items = soup.select(sel)
            if items:
                break
        if items:
            break

    for item in items:
        a = item.find("a", href=True)
        if not a:
            continue
        url = a.get("href", "")
        if not url or url in seen:
            continue
        seen.add(url)

        name_el = item.select_one("h2, h3, .woocommerce-loop-product__title, .product-title a, [class*=name]")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue

        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        price_el = item.select_one(".woocommerce-Price-amount, .price, [class*=price]")
        price = price_el.get_text(strip=True) if price_el else "brak"

        img = item.find("img")
        image = img.get("data-src") or img.get("src") or "" if img else ""

        classes = item.get("class", [])
        available = "outofstock" not in classes

        full_url = url if url.startswith("http") else f"https://gralnia.pl{url}"
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

    print(f"[GRALNIA] {len(products)} produktow")
    return products


if __name__ == "__main__":
    import asyncio
    prods = asyncio.run(get_products())
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:60]:60} | {p['price']}")
