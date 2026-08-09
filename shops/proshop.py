"""Proshop.pl scraper - nodriver (CF bypass) + mobile proxy"""
import asyncio
import os
import json
import logging
import re

log = logging.getLogger("monitor")

SHOP = "proshop"
URL = "https://www.proshop.pl/Pokemon"
PROXY_ADDR = os.environ.get("PROXY_ADDR", "127.0.0.1:8888")
EXCLUDE = ["portfolio", "album", "sleeve", "koszulk", "toploader", "binder", "ultra pro",
           "ultrapro", "plush", "figure", "figurk", "playset", "carry case", "clip", "play 'n",
           "playmat", "mata ", "puzzle", "lego"]

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
                const m = priceEl.textContent.match(/([\d.,]+)/);
                if (m) price = m[1].replace(/\\.(?=\\d{3})/g, '').replace(',', '.');
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


async def get_products():
    import nodriver as uc

    products = []

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
        log.error(f"[proshop] Failed to start browser: {e}")
        return []

    try:
        page = await browser.get(URL)
        await asyncio.sleep(15)

        title = await page.evaluate("document.title")
        if not title or "moment" in title.lower() or "attention" in title.lower() or "cloudflare" in title.lower():
            log.warning("[proshop] CF not resolved, waiting longer...")
            await asyncio.sleep(10)
            title = await page.evaluate("document.title")
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

    except Exception as e:
        log.error(f"[proshop] Error: {e}")
    finally:
        try:
            browser.stop()
        except:
            pass

    print(f"[PROSHOP] {len(products)} produktow")
    return products
