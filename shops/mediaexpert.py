"""
Scraper: mediaexpert.pl
Silnik: NODRIVER (stealth patchright, headless=False + mobile proxy)
Method: HYBRID — first scan via page.goto (get product catalog),
        subsequent scans via GraphQL API poll (instant, no navigation).
        
GraphQL endpoint: /api/graphql/product-offer/query
- Returns: price_gross, promo_price_gross, availability (ozg status)
- Works WITHOUT page navigation (uses existing CF cookies)
- Response time: ~200ms vs 70s page load

Architecture:
1. First scan: goto search pages → extract products (names, IDs, images, URLs)
2. All subsequent scans: GraphQL poll by product IDs → update prices/availability
3. Every 30 min: full refresh via goto (catch new products)
"""
import asyncio
import json
import logging
import os
import re
import time

if not os.environ.get("DISPLAY"):
    os.environ["DISPLAY"] = ":99"

log = logging.getLogger("monitor")

BROWSER_TYPE = "stealth"
SCAN_TIMEOUT = 150  # Only used for full refresh (goto-based)

SEARCH_URLS = [
    "https://www.mediaexpert.pl/search?query[menu_item]=&query[querystring]=pokemon+tcg",
    "https://www.mediaexpert.pl/search?query[menu_item]=&query[querystring]=pokemon+booster",
]

GRAPHQL_BASE = "https://www.mediaexpert.pl/api/graphql/product-offer/query"

EXCLUDE_KW = [
    "korea", "korean", "japan", "japanese", "kore", "japońsk", "jap",
    "deck", "battle deck", "league battle", "starter deck", "theme deck",
    "singiel", "single",
    "mata do gry", "playmat", "playmaty",
    "koszulki na karty", "sleeve", "sleeves",
    "album", "segregator", "binder", "portfolio",
    "toploader", "top loader",
    "figurka", "figure", "plush", "maskotka", "puzzle",
    "lego", "mega construx",
    "gra nintendo", "gra switch", "switch",
    "klaser", "piórnik",
]

INCLUDE_KW = [
    "booster", "etb", "elite trainer", "tin", "puszka",
    "box", "collection", "kolekcja", "zestaw", "bundle",
    "blister", "pack", "display", "karty pokemon",
    "tcg", "poke ball", "pokeball",
]

# Extract all products from .offer-box elements
EXTRACT_JS = """
JSON.stringify(Array.from(document.querySelectorAll('.offer-box')).map(box => {
    const label = (box.getAttribute('aria-label') || '').trim();
    const cls = box.className || '';
    const idMatch = cls.match(/offer-(\\d+)/);
    const pid = idMatch ? idMatch[1] : '';
    const link = box.querySelector('a[href*="/"]');
    const href = link ? link.href : '';
    const priceEl = box.querySelector('[class*="price"], [class*="Price"]');
    const priceText = priceEl ? priceEl.innerText.trim().replace(/[^0-9]/g, '') : '';
    const imgEl = box.querySelector('img');
    const img = imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : '';
    const boxText = box.innerText.toLowerCase();
    const unavail = boxText.includes('niedost') || boxText.includes('wyprzedane') || boxText.includes('wycofan');
    return {name: label, pid: pid, url: href, price: priceText, img: img, unavail: unavail};
}))
"""

# Persistent state (survives between scans — same worker, same asyncio task)
_product_catalog = {}   # pid → {name, url, image} (from full goto scan)
_last_full_refresh = 0  # timestamp of last goto-based scan
FULL_REFRESH_INTERVAL = 1800  # 30 min — catch new products


async def scan_with_page(page):
    """
    HYBRID scan:
    - If no catalog or >30min since last full scan: do full goto (slow but complete)
    - Otherwise: GraphQL poll only (instant — ~1-2s for all products)
    """
    global _product_catalog, _last_full_refresh
    
    now = time.time()
    need_full_refresh = (not _product_catalog) or (now - _last_full_refresh > FULL_REFRESH_INTERVAL)
    
    if need_full_refresh:
        # Full scan: navigate to search pages, extract product catalog
        products = await _full_scan(page)
        if products:
            # Update catalog
            _product_catalog = {}
            for p in products:
                pid = p["id"].replace("mediaexpert_", "")
                _product_catalog[pid] = {
                    "name": p["name"],
                    "url": p["url"],
                    "image": p["image"],
                }
            _last_full_refresh = now
            log.info(f"[MEDIAEXPERT] Full refresh: {len(_product_catalog)} products cataloged")
        return products
    else:
        # Fast scan: GraphQL poll for price/availability updates
        products = await _graphql_poll(page)
        return products


async def _full_scan(page):
    """Full page navigation scan — used for initial catalog + periodic refresh."""
    products = []
    seen_ids = set()

    for i, search_url in enumerate(SEARCH_URLS):
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            log.warning(f"[mediaexpert] goto failed for URL {i+1}: {e}")
            continue

        # Quick CF check
        await asyncio.sleep(2)
        title = await page.title()
        if not title or "moment" in title.lower() or "checking" in title.lower():
            await asyncio.sleep(4)
            title = await page.title()
            if not title or "moment" in title.lower():
                log.warning(f"[mediaexpert] CF block on URL {i+1}, skipping")
                continue

        # Dismiss cookies
        await page.evaluate("""
            (() => {
                const bb = document.querySelectorAll('button');
                for (const b of bb) {
                    const t = (b.textContent || '').toLowerCase();
                    if ((t.includes('akceptuj') || t.includes('zgadzam') || t.includes('rozumiem'))
                        && b.offsetParent !== null) {
                        b.click(); return;
                    }
                }
            })()
        """)

        # Scroll to trigger lazy loading
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        # Extract products
        raw = await page.evaluate(EXTRACT_JS)
        if not raw:
            continue

        try:
            items = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        for item in items:
            pid = item.get("pid", "")
            name = item.get("name", "")
            if not name or not pid:
                continue
            if pid in seen_ids:
                continue

            name_lower = name.lower()
            if any(kw in name_lower for kw in EXCLUDE_KW):
                continue
            if not any(kw in name_lower for kw in INCLUDE_KW):
                continue

            seen_ids.add(pid)
            price_str = _format_price(item.get("price", ""))
            item_url = item.get("url", "")
            if item_url and not item_url.startswith("http"):
                item_url = "https://www.mediaexpert.pl" + item_url

            products.append({
                "id": f"mediaexpert_{pid}",
                "name": name,
                "price": price_str,
                "shop": "mediaexpert",
                "url": item_url,
                "image": item.get("img", ""),
                "stock": 0 if item.get("unavail") else 1,
                "available": not item.get("unavail", False),
            })

    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))
    return products


async def _graphql_poll(page):
    """
    Fast GraphQL poll — no page navigation!
    Uses page.request (shares browser cookies/session) to hit GraphQL API.
    Returns full product list with updated prices/availability.
    ~200ms per request vs 70s page navigation.
    """
    if not _product_catalog:
        return []

    pids = list(_product_catalog.keys())
    
    # GraphQL supports batch — query all product IDs at once
    ids_str = ",".join(f'"{pid}"' for pid in pids)
    query = (
        'query Q{byId(identifierName:"productId",identifierValues:[' + ids_str + '])'
        '{id product_id price_gross promo_price_gross discount'
        ' _embedded{ozg{status}pickupDate{pos_delivery_display_label customer_delivery_display_label}}}}'
    )
    
    ts = int(time.time())
    url = f"{GRAPHQL_BASE}/{ts}?query={query}"
    
    try:
        resp = await page.request.get(url, timeout=15000)
        if resp.status != 200:
            log.warning(f"[mediaexpert] GraphQL status {resp.status}")
            # Fallback to full scan on next iteration
            global _last_full_refresh
            _last_full_refresh = 0
            return []
        
        body = await resp.text()
        data = json.loads(body)
        offers = data.get("data", {}).get("byId", [])
        
    except Exception as e:
        log.warning(f"[mediaexpert] GraphQL error: {str(e)[:80]}")
        _last_full_refresh = 0  # Force full refresh next time
        return []
    
    # Build product list from catalog + GraphQL price/availability
    products = []
    offer_map = {str(o.get("product_id", "")): o for o in offers}
    
    for pid, catalog_data in _product_catalog.items():
        offer = offer_map.get(pid, {})
        
        # Price from GraphQL (in grosze)
        price_gross = offer.get("price_gross")
        promo_price = offer.get("promo_price_gross")
        actual_price = promo_price if promo_price else price_gross
        price_str = _format_price(str(actual_price)) if actual_price else "brak"
        
        # Availability: ozg.status = true means product is available for order
        ozg = offer.get("_embedded", {}).get("ozg", {})
        available = ozg.get("status", False) if ozg else False
        
        # Pickup info (optional — shows if any store has stock)
        pickup = offer.get("_embedded", {}).get("pickupDate", {})
        has_pickup = bool(pickup.get("pos_delivery_display_label"))
        
        # If no ozg but has pickup — treat as available
        if not available and has_pickup:
            available = True
        
        products.append({
            "id": f"mediaexpert_{pid}",
            "name": catalog_data["name"],
            "price": price_str,
            "shop": "mediaexpert",
            "url": catalog_data["url"],
            "image": catalog_data["image"],
            "stock": 1 if available else 0,
            "available": available,
        })
    
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))
    log.info(f"[MEDIAEXPERT] GraphQL poll: {len(products)} products, {sum(1 for p in products if p['available'])} avail")
    return products


def _format_price(price_raw):
    """Format price from grosze string (e.g. '54900' -> '549.00 zl')."""
    if not price_raw:
        return "brak"
    try:
        grosze = int(re.sub(r'[^0-9]', '', str(price_raw)))
        if grosze == 0:
            return "brak"
        pln = grosze / 100.0
        return f"{pln:.2f} zl"
    except (ValueError, TypeError):
        return str(price_raw).strip()


async def get_products():
    """Legacy interface — for standalone testing only."""
    from patchright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled",
                  "--proxy-server=http://127.0.0.1:8888"]
        )
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            return await scan_with_page(page)
        finally:
            await browser.close()
