"""
Scraper: xjoy.pl (PrestaShop 1.6 + Cloudflare)
Category: /278-pokemon-tcg (91 products, 4 pages)
Method: CF Solver (Camoufox/patchright) → HTML parse
Category: SLOW (CF_SHOPS)

DOM structure (PrestaShop 1.6):
- Container: .product-container
- Name: a[itemprop=url][title] OR .product_img_link[title]
- Price: meta[itemprop=price] (numeric, e.g. "25.99")
- Image: meta[itemprop=image] (full URL)
- URL: a[itemprop=url][href]
- Availability: .product-availability → "W magazynie" / "Brak"
- Pagination: ?p=2, ?p=3, ?p=4 (24 per page, 91 total)
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup

SHOP = "xjoy"
SCAN_TIMEOUT = 180
BASE = "https://www.xjoy.pl"
CATEGORY_URL = f"{BASE}/278-pokemon-tcg"
FLARESOLVERR_URL = "http://localhost:8191/v1"
MAX_PAGES = 5

EXCLUDE = [
    # Accessories
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "deck protector", "snap binder", "penny sleeve",
    # Other games
    "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz",
    # Decks
    "battle deck", "league battle", "v battle", "world championship",
    "wcs deck", "battle academy",
    # Foreign editions
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)",
    # Junk
    "figurk", "puzzle", "zeszyt", "marvel", "dc comics", "harry potter",
    "lord of the rings", "warhammer", "witcher", "mtg:", "mtg ",
    # Accessories identifiers
    "4-pocket", "9-pocket", "4pkt", "9pkt", "100+", "2\" album",
    "dual deck box", "pro dual",
]


def _parse_page(html: str, seen: set) -> list[dict]:
    """Parse a single page of xjoy products."""
    products = []
    soup = BeautifulSoup(html, "lxml")
    items = soup.select(".product-container")

    for item in items:
        # Name + URL from itemprop link
        link_el = item.select_one("a[itemprop=url]") or item.select_one("a.product_img_link")
        if not link_el:
            continue

        name = link_el.get("title", "").strip()
        url = link_el.get("href", "").strip()

        if not name or not url or url in seen:
            continue
        seen.add(url)

        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        # Price from schema.org meta
        price_meta = item.select_one("meta[itemprop=price]")
        if price_meta:
            price_val = price_meta.get("content", "")
            try:
                pv = float(price_val)
                if pv < 10:
                    continue  # Single packs / junk
                price = f"{pv:.2f} zł"
            except (ValueError, TypeError):
                price = "brak"
        else:
            # Fallback: text price
            price_el = item.select_one(".product-price, .price")
            price = price_el.get_text(strip=True) if price_el else "brak"
            try:
                import re
                pv = float(re.search(r"(\d+[.,]\d+)", price).group(1).replace(",", "."))
                if pv < 10:
                    continue
            except (AttributeError, ValueError):
                pass

        # Image from schema.org meta or srcset
        image = ""
        img_meta = item.select_one("meta[itemprop=image]")
        if img_meta:
            image = img_meta.get("content", "")
        if not image:
            img_el = item.select_one("img[itemprop=image]")
            if img_el:
                # Get largest from srcset
                srcset = img_el.get("srcset", "")
                if srcset:
                    # Last entry in srcset is largest
                    parts = [s.strip().split(" ")[0] for s in srcset.split(",") if s.strip()]
                    image = parts[-1] if parts else ""
                if not image:
                    image = img_el.get("src", "")

        # Availability
        avail_el = item.select_one(".product-availability, .availability")
        avail_text = avail_el.get_text(strip=True).lower() if avail_el else ""
        # "W magazynie" = available, anything else = OOS
        available = "magazyn" in avail_text or "w magazynie" in avail_text or "in stock" in avail_text

        # Also check for add-to-cart button presence (stronger signal)
        if not available:
            atc = item.select_one("a.ajax_add_to_cart_button, .add-to-cart")
            if atc:
                available = True

        # Product ID from URL
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
    """Fetch all pages of xjoy Pokemon TCG category via CF solver."""
    products = []
    seen: set = set()

    # Fetch all pages (xjoy uses ?p=N for pagination)
    urls = [CATEGORY_URL] + [f"{CATEGORY_URL}?p={p}" for p in range(2, MAX_PAGES + 1)]

    for url in urls:
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 60000,
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
                continue

            html = data.get("solution", {}).get("response", "")
            if not html or len(html) < 1000:
                continue

            # Verify it's not a challenge page
            if "weryfikac" in html.lower() and len(html) < 30000:
                continue

            page_products = _parse_page(html, seen)
            products.extend(page_products)

            # If page returned 0 new products, we've hit the end
            if not page_products and url != CATEGORY_URL:
                break

        except Exception as e:
            print(f"[XJOY] Error fetching {url}: {e}")
            continue

    # Sort: OOS first, available last (Discord snapshot order)
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))

    print(f"[XJOY] {len(products)} produktow (po exclude)")
    return products


if __name__ == "__main__":
    prods = asyncio.run(get_products())
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}")
    for p in prods:
        status = "✅" if p["available"] else "❌"
        print(f"  {status} {p['name'][:60]:60} | {p['price']:12}")
