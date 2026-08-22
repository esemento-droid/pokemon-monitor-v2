"""
Scraper: xjoy.pl (PrestaShop 1.6 + Cloudflare)
Category: /278-pokemon-tcg (91 products, 4 pages)
Method: CF Solver (Camoufox Firefox) → HTML parse
Group: SLOW (CF_SHOPS / HARD_SHOPS)

DOM structure (PrestaShop 1.6):
- Container: .product-container
- Name: a[itemprop=url][title] OR .product_img_link[title]
- Price: meta[itemprop=price] (numeric, e.g. "25.99")
- Image: meta[itemprop=image] (full URL)
- URL: a[itemprop=url][href]
- Availability: .product-availability → "W magazynie" / "Brak"
- Pagination: ?p=2, ?p=3, ?p=4 (24 per page, 91 total)

STRATEGY: ALWAYS fetch ALL pages (Camoufox has its own semaphore,
doesn't block other shops). Sequential fetch, ~70s per page × 4 = ~280s.
SCAN_TIMEOUT = 360s to accommodate.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup

SHOP = "xjoy"
SCAN_TIMEOUT = 480  # 4 pages × ~70-90s each + generous buffer (better slow than never)
BASE = "https://www.xjoy.pl"
CATEGORY_URL = f"{BASE}/278-pokemon-tcg"
FLARESOLVERR_URL = "http://localhost:8191/v1"
MAX_PAGES = 4  # 91 products / 24 per page = 4 pages

_scan_counter = 0

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
    # Accessories identifiers (PrestaShop xjoy specific)
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
                    parts = [s.strip().split(" ")[0] for s in srcset.split(",") if s.strip()]
                    image = parts[-1] if parts else ""
                if not image:
                    image = img_el.get("src", "")

        # Availability
        avail_el = item.select_one(".product-availability, .availability")
        avail_text = avail_el.get_text(strip=True).lower() if avail_el else ""
        available = "magazyn" in avail_text or "w magazynie" in avail_text or "in stock" in avail_text

        # Also check for add-to-cart button presence (stronger signal on PrestaShop)
        if not available:
            atc = item.select_one("a.ajax_add_to_cart_button, .add-to-cart, button.ajax_add_to_cart_button")
            if atc:
                available = True

        # Fallback: if no availability indicator at all, check for "brak" / "niedostępny"
        if not avail_el:
            # No availability element = assume available (PrestaShop hides it when in stock)
            available = True
        elif "brak" in avail_text or "niedost" in avail_text or "wyczerpan" in avail_text:
            available = False

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


async def _fetch_page(url: str) -> str:
    """Fetch a single page via CF bridge. Returns HTML or empty string."""
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": 120000,  # 120s — CF solver needs up to 55s + queue
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{FLARESOLVERR_URL}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=150),  # Client-side: 150s
            ) as resp:
                data = await resp.json()

        if data.get("status") != "ok":
            print(f"[XJOY] CF error {url[-30:]}: {data.get('message', '')[:60]}")
            return ""

        html = data.get("solution", {}).get("response", "")

        # Validate: not a challenge page and has content
        if not html or len(html) < 1000:
            print(f"[XJOY] Short response {url[-30:]}: {len(html or '')} chars")
            return ""

        if "weryfikac" in html.lower() and len(html) < 30000:
            print(f"[XJOY] Challenge page returned for {url[-30:]}")
            return ""

        return html

    except asyncio.TimeoutError:
        print(f"[XJOY] Timeout 150s for {url[-30:]}")
        return ""
    except Exception as e:
        print(f"[XJOY] Error {url[-30:]}: {type(e).__name__}: {e}")
        return ""


async def get_products() -> list[dict]:
    """
    Fetch ALL xjoy pages every scan.
    
    xjoy is a HARD_SHOP (Camoufox, separate semaphore) — doesn't block other shops.
    Sequential fetch: 4 pages × ~70s = ~280s. SCAN_TIMEOUT = 360s.
    """
    global _scan_counter
    _scan_counter += 1

    products = []
    seen: set = set()

    # Always fetch all pages
    urls = [CATEGORY_URL] + [f"{CATEGORY_URL}?p={p}" for p in range(2, MAX_PAGES + 1)]

    for url in urls:
        html = await _fetch_page(url)
        if html:
            page_products = _parse_page(html, seen)
            products.extend(page_products)
        elif url == CATEGORY_URL:
            # Page 1 failed — abort (CF not working for xjoy right now)
            print(f"[XJOY] Page 1 failed — aborting scan")
            return []
        # If page 2-4 fails, continue with what we have (don't abort)

    # Sort: OOS first, available last (Discord snapshot order)
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))

    print(f"[XJOY] {len(products)} produktow (cycle {_scan_counter})")
    return products


if __name__ == "__main__":
    prods = asyncio.run(get_products())
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}")
    for p in prods:
        status = "✅" if p["available"] else "❌"
        print(f"  {status} {p['name'][:60]:60} | {p['price']:12}")
