"""
HYDRA v3 Engine: strefatcg_api.py
=================================
Rapid category poller for strefa-tcg.pl (Shoper platform).

Strategy:
- Scans /pl/c/Sealed-Produkty/177 + /pl/c/Preorder/163 every 3 seconds
- Uses regex (no BeautifulSoup) for lightweight parsing
- Detects availability via 'product_inactive' class
- Reports to detector.py using same product dict contract

This runs ALONGSIDE shops/strefatcg.py (old scraper stays as fallback).
Whichever detects a restock or new drop FIRST triggers the bot.

Filters:
- ONLY sealed products (same categories as old scraper)
- EXCLUDES: same as shops/strefatcg.py (binder, battle academy)
"""

import asyncio
import logging
import re
import time

import aiohttp

logger = logging.getLogger("engine.strefatcg")

# ============================================================
# CONFIGURATION
# ============================================================

SHOP = "strefa-tcg"
BASE_URL = "https://strefa-tcg.pl"
CATEGORY_URLS = [
    "/pl/c/Sealed-Produkty/177?page=1&limit=100",
    "/pl/c/Preorder/163?page=1&limit=100",
]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"

POLL_INTERVAL = 3  # seconds between full poll cycles
REQUEST_TIMEOUT = 15

EXCLUDE_KEYWORDS = ["binder", "battle academy"]


# ============================================================
# PARSER (regex, no BS4)
# ============================================================

PRODUCT_BLOCK_RE = re.compile(
    r'data-product-id="(\d+)"(.*?)(?=data-product-id=|</section|$)',
    re.DOTALL
)
TITLE_RE = re.compile(r'title="([^"]{5,})"')
LINK_RE = re.compile(r'href="(/pl/p/[^"]+)"')
PRICE_RE = re.compile(r'(\d[\d\s]*,\d{2})\s*z')


def _parse_products(html: str) -> list:
    """Parse products from HTML using regex. Fast and lightweight."""
    products = []
    seen_ids = set()

    for match in PRODUCT_BLOCK_RE.finditer(html):
        pid = match.group(1)
        block = match.group(2)

        if pid in seen_ids:
            continue
        seen_ids.add(pid)

        # Name
        name_m = TITLE_RE.search(block)
        name = name_m.group(1) if name_m else ""
        # Decode HTML entities
        name = name.replace("&#039;", "'").replace("&amp;", "&").replace("&quot;", '"')

        # Exclude
        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE_KEYWORDS):
            continue

        # URL
        link_m = LINK_RE.search(block)
        url = f"{BASE_URL}{link_m.group(1)}" if link_m else ""

        # Price
        price_m = PRICE_RE.search(block)
        price_str = price_m.group(1).replace(" ", "") if price_m else "0"
        # Normalize: "1 750,00" -> "1750.00 PLN"
        price_str = price_str.replace(",", ".")
        price_display = f"{price_str} PLN"

        # Availability: product_inactive = not available
        available = "product_inactive" not in block

        products.append({
            "id": f"strefatcg_{pid}",
            "name": name,
            "price": price_display,
            "shop": SHOP,
            "url": url,
            "image": "",
            "stock": "",
            "available": available,
        })

    return products


# ============================================================
# MAIN POLL FUNCTION
# ============================================================

async def get_products() -> list:
    """Fetch and parse all products from strefatcg categories."""
    all_products = []
    seen_ids = set()

    try:
        async with aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        ) as session:
            for cat_path in CATEGORY_URLS:
                url = f"{BASE_URL}{cat_path}"
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            logger.warning(f"[strefatcg] HTTP {resp.status} for {cat_path}")
                            continue
                        html = await resp.text()
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.warning(f"[strefatcg] Error fetching {cat_path}: {e}")
                    continue

                products = _parse_products(html)
                for p in products:
                    if p["id"] not in seen_ids:
                        seen_ids.add(p["id"])
                        all_products.append(p)

    except Exception as e:
        logger.error(f"[strefatcg] Session error: {e}")

    return all_products


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":
    import time as _time

    async def _test():
        start = _time.time()
        products = await get_products()
        elapsed = _time.time() - start
        avail = [p for p in products if p["available"]]
        print(f"Total: {len(products)} | Available: {len(avail)} | Time: {elapsed:.2f}s")
        print()
        for p in products:
            status = "V" if p["available"] else "X"
            print(f"  {status} {p['name'][:55]} | {p['price']} | {p['url'][-30:]}")

    asyncio.run(_test())
