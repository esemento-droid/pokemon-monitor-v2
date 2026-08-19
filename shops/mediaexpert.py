"""
Scraper: mediaexpert.pl
Silnik: NODRIVER (stealth patchright, headless=False + mobile proxy)
Reason: CF requires headless=False fingerprint + mobile proxy IP.
         cf_bridge (headless=True) gets blocked. VPS IP banned.
Method: scan_with_page (persistent browser) + JS extraction.
Searches: "pokemon tcg" + "pokemon booster"
Target scan time: 40-60s (goto 30s + CF 2-4s + scroll 1s per URL)
"""
import asyncio
import json
import logging
import os
import re

if not os.environ.get("DISPLAY"):
    os.environ["DISPLAY"] = ":99"

log = logging.getLogger("monitor")

BROWSER_TYPE = "stealth"
SCAN_TIMEOUT = 150  # 2 URLs × 30s goto + CF wait + scroll — needs headroom

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
    """Persistent browser interface - page already exists, just navigate.
    
    Optimized for speed:
    - CF resolves in ~3-5s on subsequent visits (session cookies persist)
    - First visit may take 5-10s for challenge
    - Total target: 30-50s for both URLs
    """
    products = []
    seen_ids = set()

    for i, search_url in enumerate(SEARCH_URLS):
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            log.warning(f"[mediaexpert] goto failed for URL {i+1}: {e}")
            continue

        # Quick CF check — on persistent browser, cookies usually pass CF instantly
        await asyncio.sleep(2)
        title = await page.title()
        if not title or "moment" in title.lower() or "checking" in title.lower():
            # CF challenge — wait but not forever
            await asyncio.sleep(4)
            title = await page.title()
            if not title or "moment" in title.lower():
                log.warning(f"[mediaexpert] CF block on URL {i+1}, skipping")
                continue

        # Dismiss cookies (first time only, fast no-op afterwards)
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

        # Quick scroll to trigger lazy loading
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        # Extract products
        raw = await page.evaluate(EXTRACT_JS)
        if not raw:
            log.warning(f"[mediaexpert] No data from URL {i+1}")
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

    # Sort: OOS first, available last (Discord scroll fix)
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))

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
