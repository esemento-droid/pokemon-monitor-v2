"""
Scraper: proshop.pl — CF protected
Method: patchright (persistent stealth browser) + JS extraction
BROWSER_TYPE = "stealth"
"""
import asyncio
import json
import logging
import os

log = logging.getLogger("monitor")

SHOP = "proshop"
BROWSER_TYPE = "standard"  # Try VPS IP directly — mobile proxy gets ERR_TIMED_OUT
SCAN_TIMEOUT = 90  # CF either passes quickly or blocks — no point waiting long
URL = "https://www.proshop.pl/Pokemon/Pokemon?f~pokmon_tcg=bokse~booster-tin-og-tema~tin~tilbehor"

EXCLUDE = [
    "portfolio", "album", "sleeves", "koszulk", "toploader", "pro-binder", "ultra pro", "ultrapro",
    "plush", "figure", "figurk", "playset", "carry case", "clip", "play 'n", "playmat",
    "mata ", "puzzle", "lego", "deck", "battle deck", "league battle", "rival battle",
    "v battle", "world championship", "wcs ", "battle academy", "japoński", "japońsk",
    "japanese", "(jp)", "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese",
    "(chi)", "s-chinese", "ultra-pro", "segregator", "alcove", "lorcana", "one piece",
    "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt"
]

EXTRACT_JS = """
JSON.stringify((function(){
    const result = [];
    const items = document.querySelectorAll('li.site-productlist-item, .product-list-item, [data-product-id]');
    for (const item of items) {
        try {
            const nameEl = item.querySelector('h2[product-display-name], .site-product-link, [class*="product-name"], h2, h3');
            if (!nameEl) continue;
            const name = nameEl.textContent.trim();
            if (!name || name.length < 5) continue;
            const pidEl = item.querySelector('input[name=productId], [data-product-id]');
            const pid = pidEl ? (pidEl.value || pidEl.getAttribute('data-product-id') || '') : '';
            if (!pid) continue;
            const priceEl = item.querySelector('.site-currency-lg, [class*="price"], .product-price');
            let price = '';
            if (priceEl) {
                let raw = priceEl.textContent.replace(/\\s/g, '').replace(/\\u00a0/g, '');
                const m = raw.match(/([\d.,]+)/);
                if (m) price = m[1].replace(/\\.(?=\\d{3})/g, '').replace(/,/g, '.');
            }
            const linkEl = item.querySelector('a.site-product-link, a[href*="/"]');
            let href = linkEl ? linkEl.getAttribute('href') || '' : '';
            if (href && !href.startsWith('http')) href = 'https://www.proshop.pl' + href;
            const btn = item.querySelector('button.site-btn-green, .btn-add-to-cart, [class*="add-to-cart"]');
            const imgEl = item.querySelector('img[src]');
            let img = '';
            if (imgEl) {
                img = imgEl.src || '';
                if (img && !img.startsWith('http')) img = 'https://www.proshop.pl' + img;
            }
            result.push({pid, name, price, url: href, available: !!btn, img});
        } catch(e) {}
    }
    return result;
})())
"""


async def scan_with_page(page):
    """Persistent browser interface — page already exists, just navigate."""
    products = []

    await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(8)

    # Check CF — quick check, if not resolved wait once more
    title = await page.title()
    if not title or "moment" in title.lower() or "attention" in title.lower() or "cloudflare" in title.lower():
        log.warning("[proshop] CF not resolved, waiting...")
        await asyncio.sleep(10)
        title = await page.title()
        if not title or "attention" in title.lower() or "moment" in title.lower():
            # Retry: reload and wait
            log.warning("[proshop] CF still blocking, reload...")
            try:
                await page.reload(wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(10)
                title = await page.title()
            except Exception:
                pass
            if not title or "attention" in title.lower() or "moment" in title.lower():
                log.error("[proshop] CF block - cannot access")
                return []

    raw = await page.evaluate(EXTRACT_JS)
    if not raw:
        log.warning("[proshop] No data from JS extraction")
        return []

    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        log.error("[proshop] Failed to parse JS data")
        return []

    seen = set()
    for item in items:
        pid = item.get("pid", "")
        name = item.get("name", "")
        if not pid or not name or pid in seen:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        seen.add(pid)
        price_val = item.get("price", "")
        price_str = f"{price_val} zl" if price_val else "brak"
        products.append({
            "id": f"proshop_{pid}",
            "name": name,
            "price": price_str,
            "shop": SHOP,
            "url": item.get("url", ""),
            "image": item.get("img", ""),
            "stock": None,
            "available": item.get("available", False),
        })

    print(f"[PROSHOP] {len(products)} produktow")
    return products


async def get_products():
    """Legacy interface — for testing only."""
    from patchright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled",
                  "--proxy-server=http://127.0.0.1:8888"]
        )
        try:
            page = await browser.new_page()
            return await scan_with_page(page)
        finally:
            await browser.close()
