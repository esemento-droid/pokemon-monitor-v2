"""
Empik scraper - patchright (persistent browser, CF bypass) + mobile proxy
BROWSER_TYPE = "stealth" — uses patchright browser with proxy from browser_manager
"""
import asyncio
import json
import logging
import re

log = logging.getLogger("monitor")

SHOP = "empik"
BROWSER_TYPE = "stealth"

SEARCH_URLS = [
    "https://www.empik.com/szukaj/produkt?q=pokemon+tcg&searchCategory=all&sort=publishDesc",
    "https://www.empik.com/szukaj/produkt?q=pokemon+tcg&searchCategory=all&sort=priceDesc",
]
EXCLUDE_KW = [
    "korea", "korean", "kore", "kor ", " kor",
    "japan", "japanese", "japo\u0144sk", "jap ", " jap",
    "chn", "chi\u0144sk", "chinese", "china",
    " de ", "deutsch", "german", "niemieck", "kollektion", "kollection", "tedesco",
    "espa\u0144ol", "castellano", "hiszpa\u0144sk", " spa ",
    "deck", "battle deck", "league battle",
    "magazyn", "trenuj ze mn",
    "mata do gry", "playmat", "playmaty",
    "koszulki na karty", "sleeves", "battle box",
    "minimalistyczna mata", "ultra pro", "ultra-pro",
    "album", "segregator", "portfolio", "binder",
    "gem pack", "single", "karta ",
    "akrylowe", "akrylowy", "acrylic",
    "torba", "plecak",
    "plakat", "poster",
    "pin collection", "coin",
    "puzzle", "figurka", "figurk",
    "koc ", "klocki", "construx", "mega construx",
    "ninja spinner",
    "terastal gathering", "battle partners",
    "paradigm trigger", "talia",
]
MAX_PAGES = 5

EXTRACT_JS = """
JSON.stringify((function(){
    const result = [];
    const items = document.querySelectorAll('.search-list-item');
    for (const item of items) {
        try {
            const titleEl = item.querySelector('h2.product-title');
            const link = item.querySelector('a[href*=",p"]');
            const priceEl = item.querySelector('.product-price__value, .price, [class*="price"]');
            const imgEl = item.querySelector('img');
            if (!link) continue;
            const href = link.getAttribute('href') || '';
            const pidMatch = href.match(/,p(\\d+),/);
            if (!pidMatch) continue;
            const name = titleEl ? titleEl.textContent.trim() : '';
            if (!name) continue;
            const priceText = priceEl ? priceEl.textContent.trim() : '';
            const priceMatch = priceText.match(/([\\d]+[,.]?[\\d]*)\\s*z/);
            const price = priceMatch ? priceMatch[1].replace(',', '.') : '';
            const img = imgEl ? (imgEl.getAttribute('lazy-img') || imgEl.getAttribute('data-src') || imgEl.getAttribute('data-lazy-img') || imgEl.getAttribute('data-original') || imgEl.getAttribute('srcset')?.split(' ')[0] || imgEl.src || '') : '';
            const mpMatch = href.match(/mpShopId=(\\d+)/);
            const shopId = mpMatch ? mpMatch[1] : '0';
            result.push({pid: pidMatch[1], name: name, price: price, img: img, url: href, shopId: shopId});
        } catch(e) {}
    }
    return result;
})())
"""


async def scan_with_page(page):
    """Persistent browser interface — page already exists, just navigate."""
    products = []
    seen_ids = set()

    # First URL — navigate + wait for CF to resolve
    await page.goto(SEARCH_URLS[0], wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(12)

    # Check CF resolution
    title = await page.title()
    if not title or "moment" in title.lower():
        log.warning("[empik] CF not resolved, waiting longer...")
        await asyncio.sleep(10)
        title = await page.title()
        if not title or "moment" in title.lower():
            log.error("[empik] CF block - cannot access")
            return []

    # Scrape all search URLs + pages
    for search_url in SEARCH_URLS:
        for pg in range(1, MAX_PAGES + 1):
            if pg == 1:
                url = search_url
            else:
                url = search_url + f"&start={(pg - 1) * 60}"

            if search_url != SEARCH_URLS[0] or pg > 1:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(6)

            raw = await page.evaluate(EXTRACT_JS)
            if not raw:
                break

            try:
                items = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                break

            if not items:
                break

            for item in items:
                pid = item.get("pid", "")
                if not pid or pid in seen_ids:
                    continue

                name = item.get("name", "")
                if any(kw in name.lower() for kw in EXCLUDE_KW):
                    continue

                name_upper = name.rstrip()
                if name_upper.endswith(" DE") or name_upper.endswith("-DE") or "(DE)" in name:
                    continue
                if name_upper.endswith(" KOR") or name_upper.endswith(" SPA") or name_upper.endswith(" JPN"):
                    continue

                seen_ids.add(pid)
                price_val = item.get("price", "")
                price_str = f"{price_val} zl" if price_val else "brak"
                url_product = item.get("url", "")
                if url_product and not url_product.startswith("http"):
                    url_product = "https://www.empik.com" + url_product

                shop_id = item.get("shopId", "0")
                stock_label = "empik" if shop_id == "0" else f"marketplace_{shop_id}"

                # Fix image URL
                img_url = item.get("img", "")
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                if img_url.startswith("data:") or not img_url:
                    img_url = ""

                products.append({
                    "id": f"empik_{pid}",
                    "name": name,
                    "price": price_str,
                    "shop": "empik",
                    "url": url_product,
                    "image": img_url,
                    "stock": stock_label,
                    "available": bool(price_val),
                })

            if len(items) < 20:
                break

    log.info(f"[EMPIK] {len(products)} produktow")
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
            page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
            return await scan_with_page(page)
        finally:
            await browser.close()
