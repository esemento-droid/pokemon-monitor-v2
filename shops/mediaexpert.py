"""
Scraper: mediaexpert.pl
Silnik: nodriver (Cloudflare bypass required)
Metoda: headless Chrome + mobile proxy
Szukaj: "pokemon tcg" + "pokemon booster" - sealed products only
Filtr: TYLKO sealed English Pokemon TCG (no decks, singles, Japanese, accessories)
URL: /search?query[menu_item]=&query[querystring]=QUERY
Selektory: .offer-box, aria-label=nazwa, class offer-PID, cena w groszach
"""
import asyncio
import os
import json
import logging
import re

# Ensure DISPLAY is set for headless Chrome (Xvfb)
if not os.environ.get("DISPLAY"):
    os.environ["DISPLAY"] = ":99"

log = logging.getLogger("monitor")

BROWSER_TYPE = "stealth"
SCAN_TIMEOUT = 180  # mediaexpert needs CF wait + 2 search URLs + scrolls = easily 130-150s

SEARCH_URLS = [
    "https://www.mediaexpert.pl/search?query[menu_item]=&query[querystring]=pokemon+tcg",
    "https://www.mediaexpert.pl/search?query[menu_item]=&query[querystring]=pokemon+booster",
]

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

PROXY_ADDR = os.environ.get("PROXY_ADDR", "127.0.0.1:8888")

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


async def scan_with_page(page):
    """Persistent browser interface - page already exists, just navigate."""
    products = []
    seen_ids = set()

    # First URL - navigate + wait for CF to resolve
    await page.goto(SEARCH_URLS[0], wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(8)

    # Check CF resolution
    title = await page.title()
    if not title or "moment" in title.lower() or "checking" in title.lower():
        log.warning("[mediaexpert] CF not resolved, waiting longer...")
        await asyncio.sleep(15)
        title = await page.title()
        if not title or "moment" in title.lower():
            log.error("[mediaexpert] CF block - cannot access")
            return []

    for search_url in SEARCH_URLS:
        if search_url != SEARCH_URLS[0]:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(8)

            # Check CF
            title = await page.title()
            if not title or "moment" in title.lower() or "checking" in title.lower():
                log.warning("[mediaexpert] CF challenge on %s, waiting...", search_url)
                await asyncio.sleep(15)
                title = await page.title()
                if not title or "moment" in title.lower():
                    log.error("[mediaexpert] CF block on %s", search_url)
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
        await asyncio.sleep(2)

        # Scroll down to load lazy products
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(1)

        # Extract products
        raw = await page.evaluate(EXTRACT_JS)
        if not raw:
            log.warning("[mediaexpert] No data from %s", search_url)
            continue

        try:
            items = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            log.error("[mediaexpert] JSON parse error")
            continue

        for item in items:
            pid = item.get("pid", "")
            name = item.get("name", "")
            if not name or not pid:
                continue
            if pid in seen_ids:
                continue

            # Apply filters
            name_lower = name.lower()
            if any(kw in name_lower for kw in EXCLUDE_KW):
                continue
            if not any(kw in name_lower for kw in INCLUDE_KW):
                continue

            seen_ids.add(pid)

            # Parse price (in grosze -> PLN)
            price_raw = item.get("price", "")
            price_str = _format_price(price_raw)

            # URL
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

    log.info(f"[MEDIAEXPERT] {len(products)} produktow")
    return products


async def get_products():
    import nodriver as uc

    products = []
    seen_ids = set()

    browser_args = [
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
    ]
    if PROXY_ADDR and PROXY_ADDR != "none":
        browser_args.append(f"--proxy-server=http://{PROXY_ADDR}")

    try:
        browser = await uc.start(headless=False, sandbox=False, browser_args=browser_args)
    except Exception as e:
        log.error(f"[mediaexpert] Failed to start browser: {e}")
        return []

    try:
        for search_url in SEARCH_URLS:
            page = await browser.get(search_url)
            await asyncio.sleep(12)

            # Check CF
            title = await page.evaluate("document.title")
            if not title or "moment" in title.lower() or "checking" in title.lower():
                log.warning("[mediaexpert] CF challenge, waiting...")
                await asyncio.sleep(15)
                title = await page.evaluate("document.title")
                if not title or "moment" in title.lower():
                    log.error("[mediaexpert] CF block on %s", search_url)
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
            await asyncio.sleep(2)

            # Scroll down to load lazy products
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(1.5)

            # Extract products
            raw = await page.evaluate(EXTRACT_JS)
            if not raw:
                log.warning("[mediaexpert] No data from %s", search_url)
                continue

            try:
                items = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                log.error("[mediaexpert] JSON parse error")
                continue

            for item in items:
                pid = item.get("pid", "")
                name = item.get("name", "")
                if not name or not pid:
                    continue
                if pid in seen_ids:
                    continue

                # Apply filters
                name_lower = name.lower()
                if any(kw in name_lower for kw in EXCLUDE_KW):
                    continue
                if not any(kw in name_lower for kw in INCLUDE_KW):
                    continue

                seen_ids.add(pid)

                # Parse price (in grosze -> PLN)
                price_raw = item.get("price", "")
                price_str = _format_price(price_raw)

                # URL
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

    except Exception as e:
        log.error(f"[mediaexpert] Error: {e}")
    finally:
        try:
            browser.stop()
        except:
            pass

    log.info(f"[MEDIAEXPERT] {len(products)} produktow")
    return products


def _format_price(price_raw):
    """Format price from grosze string (e.g. '54900' -> '549.00 zl')."""
    if not price_raw:
        return "brak"
    try:
        grosze = int(re.sub(r'[^0-9]', '', str(price_raw)))
        pln = grosze / 100.0
        return f"{pln:.2f} zl"
    except (ValueError, TypeError):
        return str(price_raw).strip()
