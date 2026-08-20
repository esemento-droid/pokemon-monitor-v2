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
# SHOP_DISABLED removed by seed script
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
]

# Exclude Romanian names + German edition cards (DE in name/URL = German card language)
EXCLUDE_NON_EN = [
    "cutie ", "colecție", "colectie", "sigilat",
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
    Sources: GA4 dataLayer (id, name, price_ron), LD+JSON (URLs), data-src (images),
    HTML grid-image classes (availability: out-of-stock class)
    """
    from bs4 import BeautifulSoup

    # Exchange rate RON -> EUR
    rate_match = re.search(r'"exchange_rate":([\d.]+)', html)
    rate = float(rate_match.group(1)) if rate_match else 5.0916

    # GA4 items (id, name, price in RON)
    ga4_items = []
    for m in GA4_RE.finditer(html):
        # Decode unicode escapes and remove surrogates (invalid UTF-8)
        raw_name = m.group(2)
        try:
            name = raw_name.encode().decode('unicode_escape')
        except (UnicodeDecodeError, UnicodeEncodeError):
            name = raw_name
        # Remove surrogate characters (cause DB errors)
        name = name.encode('utf-8', errors='replace').decode('utf-8')
        ga4_items.append({
            "id": m.group(1),
            "name": name,
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

    # Product images (data-src, 1 per product in order)
    imgs = re.findall(r'data-src="(https://c\.cdnmp\.net/[^"]+)"', html)

    # Availability from HTML: grid-image--out-of-stock class
    soup = BeautifulSoup(html, "lxml")
    grid_items = soup.select('.grid-image')
    avail_list = []
    for gi in grid_items:
        classes = ' '.join(gi.get('class', []))
        is_oos = 'out-of-stock' in classes
        avail_list.append(not is_oos)

    # Merge by position
    products = []
    for i, ga in enumerate(ga4_items):
        url = urls[i] if i < len(urls) else ""
        img = imgs[i] if i < len(imgs) else ""
        price_eur = ga["price_ron"] / rate
        available = avail_list[i] if i < len(avail_list) else True

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
        # Sequential fetch with delay (site returns 429 on parallel)
        pages_html = []
        for url in urls:
            html = await _fetch_page(session, url)
            pages_html.append(html)
            if html:
                await asyncio.sleep(1.5)

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

            # Exclude accessories & other games
            if any(ex in name_lower for ex in EXCLUDE):
                continue

            # Exclude Romanian-named products
            if any(kw in name_lower for kw in EXCLUDE_NON_EN):
                continue

            # Exclude German edition cards: " DE " in name or URL = Deutsche Edition
            # e.g. "Paldea Evolved DE Factory Sealed" or URL contains "-de-"
            item_url = item["url"]
            if " DE " in name or " de " in item_url.split("/")[-1].replace("-", " "):
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

    # Sort: OOS first (silent DB), then available (Discord SNAPSHOT)
    # User sees available products at BOTTOM of Discord (most recent = visible without scrolling)
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))


    print(f"[THEPOKEMANIA] {len(products)} produktow")
    return products
