"""
Scraper: thepokemania.de — German/Romanian Pokemon TCG shop
URL: /pokemon-tcg-sets/lingua-englisch (English sealed products only)
Method: aiohttp + GA4 dataLayer + LD+JSON + data-src images
Pagination: 60 items/page, /p2, /p3... (6 pages, ~316 products)
Currency: EUR (GA4 stores RON, exchange_rate in page env)
Category: FAST (pure HTTP, no CF)
"""
import asyncio
import re
import json
import aiohttp

SHOP = "thepokemania"
BASE = "https://thepokemania.de"
CATEGORY_URL = "/pokemon-tcg-sets/lingua-englisch"
MAX_PAGES = 6

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# GA4 item regex (extracts id, name, price in RON)
GA4_RE = re.compile(
    r'\{"item_id":(\d+),"item_name":"([^"]*)","item_category":"([^"]*)","item_brand":"([^"]*)","item_list_name":"([^"]*)","price":([\d.]+)'
)

EXCLUDE = [
    "sleeves", "hüllen", "toploader", "album", "portfolio", "binder", "playmat",
    "würfel", "dice", "münze", "coin", "damage counter",
    "yu-gi-oh", "one piece", "lorcana", "digimon", "magic the", "naruto",
    "flesh & blood", "dragon shield", "weiss schwarz",
    # German language products (we want English only - URL filter handles this)
]


async def _fetch_page(session, url):
    """Fetch single page with retry."""
    for attempt in range(2):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    return await resp.text()
        except Exception:
            if attempt == 0:
                await asyncio.sleep(2)
    return ""


def _parse_page(html):
    """
    Extract products from page HTML.
    Sources: GA4 dataLayer (id, name, price_ron), LD+JSON (URLs), data-src (images)
    """
    # Exchange rate RON -> EUR
    rate_match = re.search(r'"exchange_rate":([\d.]+)', html)
    rate = float(rate_match.group(1)) if rate_match else 5.0916

    # GA4 items (id, name, price in RON)
    ga4_items = []
    for m in GA4_RE.finditer(html):
        ga4_items.append({
            "id": m.group(1),
            "name": m.group(2).encode().decode('unicode_escape'),
            "price_ron": float(m.group(6)),
        })

    # LD+JSON ItemList (URLs in order)
    urls = []
    ld_match = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.DOTALL)
    if ld_match:
        try:
            data = json.loads(ld_match.group(1))
            for item in (data if isinstance(data, list) else [data]):
                if isinstance(item, dict) and item.get("@type") == "ItemList":
                    for el in item.get("itemListElement", []):
                        urls.append(el.get("url", ""))
        except (json.JSONDecodeError, TypeError):
            pass

    # Product images (data-src, 2 per product: main + hover)
    imgs = re.findall(r'data-src="(https://c\.cdnmp\.net/[^"]+)"', html)

    # Availability: "Add to cart" or "Vorbestellung" = available, else unavailable
    avail_matches = re.findall(r'(Add to cart|Vorbestellung|Ausverkauft|Nicht verfügbar)', html)

    # Merge by position
    products = []
    for i, ga in enumerate(ga4_items):
        url = urls[i] if i < len(urls) else ""
        # 2 images per product (main + hover), take first
        img = imgs[i * 2] if i * 2 < len(imgs) else ""

        # Convert RON to EUR
        price_eur = ga["price_ron"] / rate

        # Availability from page order
        available = True
        if i < len(avail_matches):
            available = avail_matches[i] in ("Add to cart", "Vorbestellung")

        products.append({
            "id": ga["id"],
            "name": ga["name"],
            "price_eur": price_eur,
            "url": url,
            "image": img,
            "available": available,
        })

    return products


async def get_products():
    products = []
    seen_ids = set()

    # Build page URLs
    urls = [f"{BASE}{CATEGORY_URL}"]
    for p in range(2, MAX_PAGES + 1):
        urls.append(f"{BASE}{CATEGORY_URL}/p{p}")

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Parallel fetch all pages
        pages_html = await asyncio.gather(*[_fetch_page(session, url) for url in urls])

    for html in pages_html:
        if not html:
            continue

        page_products = _parse_page(html)

        for item in page_products:
            pid = item["id"]
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            name = item["name"]
            name_lower = name.lower()

            # Exclude accessories
            if any(ex in name_lower for ex in EXCLUDE):
                continue

            price_eur = item["price_eur"]
            price_str = f"{price_eur:.2f} EUR" if price_eur > 0 else "brak"

            products.append({
                "id": f"thepokemania_{pid}",
                "name": name,
                "price": price_str,
                "shop": SHOP,
                "url": item["url"],
                "image": item["image"],
                "stock": None,
                "available": item["available"],
            })

    print(f"[THEPOKEMANIA] {len(products)} produktow")
    return products
