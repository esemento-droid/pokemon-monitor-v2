"""Empik scraper - nodriver (CF bypass) - stable version"""
import asyncio
import os
import json
import logging
import re

log = logging.getLogger("monitor")

SEARCH_URL = "https://www.empik.com/szukaj/produkt?q=pokemon+tcg&searchCategory=all&sort=publishDesc"
EXCLUDE_KW = [
    "korea", "korean", "japan", "japanese", "kore", "japońsk", "jap",
    "deck", "battle deck", "league battle",
    "magazyn", "trenuj ze mn",
    "mata do gry", "playmat", "playmaty",
    "koszulki na karty", "sleeve", "battle box",
    "minimalistyczna mata",
]
MAX_PAGES = 3
PROXY_ADDR = os.environ.get("PROXY_ADDR", "none")

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
            const img = imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : '';
            const mpMatch = href.match(/mpShopId=(\\d+)/);
            const shopId = mpMatch ? mpMatch[1] : '0';
            result.push({pid: pidMatch[1], name: name, price: price, img: img, url: href, shopId: shopId});
        } catch(e) {}
    }
    return result;
})())
"""


async def get_products():
    import nodriver as uc

    products = []
    seen_ids = set()

    browser_args = [
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
        "--disable-extensions",
        "--disable-background-networking",
    ]
    # Only add proxy if PROXY_ADDR is set and reachable
    if PROXY_ADDR and PROXY_ADDR != "none":
        browser_args.append(f"--proxy-server=http://{PROXY_ADDR}")

    try:
        browser = await uc.start(
            headless=True,
            sandbox=False,
            browser_args=browser_args,
        )
    except Exception as e:
        log.error(f"[empik] Failed to start browser: {e}")
        return []

    try:
        page = await browser.get(SEARCH_URL)

        # CF resolves automatically with nodriver, just wait for page load
        await asyncio.sleep(12)

        # Verify page loaded
        title = await page.evaluate("document.title")
        if not title or "moment" in title.lower() or "just a moment" in title.lower():
            log.warning("[empik] CF not resolved, waiting longer...")
            await asyncio.sleep(10)
            title = await page.evaluate("document.title")
            if not title or "moment" in title.lower():
                log.error("[empik] CF block - cannot access")
                return []

        for pg in range(1, MAX_PAGES + 1):
            if pg > 1:
                url = SEARCH_URL + f"&start={(pg - 1) * 60}"
                page = await browser.get(url)
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
                name_lower = name.lower()

                if any(kw in name_lower for kw in EXCLUDE_KW):
                    continue

                seen_ids.add(pid)
                price_val = item.get("price", "")
                price_str = f"{price_val} zl" if price_val else "brak"
                url = item.get("url", "")
                if url and not url.startswith("http"):
                    url = "https://www.empik.com" + url

                shop_id = item.get("shopId", "0")
                stock_label = "empik" if shop_id == "0" else f"marketplace_{shop_id}"

                products.append({
                    "id": f"empik_{pid}",
                    "name": name,
                    "price": price_str,
                    "shop": "empik",
                    "url": url,
                    "image": item.get("img", ""),
                    "stock": stock_label,
                    "available": bool(price_val),
                })

            if len(items) < 20:
                break

    except Exception as e:
        log.error(f"[empik] Error: {e}")
    finally:
        try:
            browser.stop()
        except:
            pass

    log.info(f"[EMPIK] {len(products)} produktow")
    return products
