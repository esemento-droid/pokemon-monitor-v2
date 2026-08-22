"""
Scraper: xjoy.pl (PrestaShop 1.6 + Cloudflare)
Category: /278-pokemon-tcg (91 products, 4 pages)
Method: PERSISTENT CAMOUFOX PAGE (scan_with_page)
Group: NODRIVER (browser_manager → camoufox browser type)

Architecture:
- ONE persistent Camoufox browser page (tab) — lives forever
- Scan = page.goto(url) + wait for CF + parse HTML
- Zero start/stop cycles, zero zombie processes
- Self-healing: if page crashes → browser_manager recreates it
- CF challenge passes in ~18s (proven by diagnostic)

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
from bs4 import BeautifulSoup

SHOP = "xjoy"
BROWSER_TYPE = "camoufox"  # Uses persistent Camoufox browser (not patchright)
SCAN_TIMEOUT = 300  # 4 pages × ~30s each + CF challenge wait + buffer
SCAN_DELAY = 90  # Scan every 90-135s (CF rate limit friendly)
BASE = "https://www.xjoy.pl"
CATEGORY_URL = f"{BASE}/278-pokemon-tcg"
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

        # Also check for add-to-cart button presence
        if not available:
            atc = item.select_one("a.ajax_add_to_cart_button, .add-to-cart, button.ajax_add_to_cart_button")
            if atc:
                available = True

        # Fallback: no availability element = assume available (PrestaShop hides when in stock)
        if not avail_el:
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


async def _wait_for_cf(page, max_wait=45):
    """Wait for Cloudflare challenge to resolve. Returns True if resolved."""
    for i in range(max_wait):
        try:
            title = await page.title()
            body = await page.evaluate(
                "() => document.body ? document.body.innerText.substring(0, 200) : ''"
            )
            combined = ((title or "") + (body or "")).lower()

            is_challenge = any(x in combined for x in [
                "moment", "checking", "attention", "just a moment",
                "verif", "checking your browser", "please wait",
                "weryfikac", "czekanie na odpowied", "witryna sprawdza", "cloudflare"
            ])

            if not is_challenge:
                return True

            # Click Turnstile checkbox area (Camoufox humanize handles movement)
            if i in [2, 5, 8, 12, 18, 25, 32, 40]:
                try:
                    await page.mouse.click(210, 290)
                except Exception:
                    pass

        except Exception:
            # Page might be navigating — wait and retry
            pass

        await asyncio.sleep(1)

    return False


async def _fetch_page_with_browser(page, url):
    """Navigate persistent page to URL, wait for CF, return HTML."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass  # Timeout on goto is OK — page might still load

    # Wait for CF challenge to resolve
    resolved = await _wait_for_cf(page, max_wait=45)
    if not resolved:
        return ""

    # Extra wait for content to render
    await asyncio.sleep(2)
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass

    html = await page.content()

    # Validate
    if not html or len(html) < 1000:
        return ""
    if "weryfikac" in html.lower() and len(html) < 30000:
        return ""

    return html


async def scan_with_page(page) -> list[dict]:
    """
    Scan xjoy using persistent Camoufox page.
    
    Sequential page navigation: page 1 → page 2 → page 3 → page 4.
    Same page, different URLs. CF cookie persists across navigations.
    """
    global _scan_counter
    _scan_counter += 1

    products = []
    seen: set = set()

    # All pages to fetch
    urls = [CATEGORY_URL] + [f"{CATEGORY_URL}?p={p}" for p in range(2, MAX_PAGES + 1)]

    for url in urls:
        html = await _fetch_page_with_browser(page, url)
        if not html and url == CATEGORY_URL:
            # Page 1 failed — CF not passing, abort
            print(f"[XJOY] Page 1 CF failed — aborting scan")
            return []
        if not html:
            # Page 2-4 failed — retry once
            await asyncio.sleep(3)
            html = await _fetch_page_with_browser(page, url)
        if html:
            page_products = _parse_page(html, seen)
            products.extend(page_products)
        # Brief delay between pages (be nice to CF)
        await asyncio.sleep(2)

    # Sort: OOS first, available last (Discord snapshot order)
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))

    print(f"[XJOY] {len(products)} produktow (cycle {_scan_counter})")
    return products


# Legacy get_products() for standalone testing
async def get_products() -> list[dict]:
    """Standalone test mode — launches own Camoufox browser."""
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        headless=True,
        proxy={"server": "http://127.0.0.1:8888"},
        geoip=True,
        humanize=True,
        os="windows",
    ) as browser:
        page = await browser.new_page()
        result = await scan_with_page(page)
        return result


if __name__ == "__main__":
    prods = asyncio.run(get_products())
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}")
    for p in prods:
        status = "✅" if p["available"] else "❌"
        print(f"  {status} {p['name'][:60]:60} | {p['price']:12}")
