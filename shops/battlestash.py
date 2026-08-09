"""Battlestash.pl scraper - nodriver + proxy (CF blocks all non-homepage)"""
import asyncio
import os
import json
import logging
import re

log = logging.getLogger("monitor")

SHOP = "battlestash.pl"
URL = "https://battlestash.pl/kategoria-produktu/pokemon-tcg/"
PROXY_ADDR = os.environ.get("PROXY_ADDR", "127.0.0.1:8888")
EXCLUDE = ["sleeve", "koszulk", "toploader", "album", "binder", "ultra pro", "playmat",
           "one piece", "lorcana", "yu-gi-oh", "digimon", "magic", "mata", "deck box",
           "podobne produkty", "keyforge", "ultimate guard", "vampire"]

EXTRACT_JS = """
JSON.stringify((function(){
    const result = [];
    const items = document.querySelectorAll('.product, .type-product, li.product');
    for (const item of items) {
        try {
            const nameEl = item.querySelector('.woocommerce-loop-product__title, h2, h3');
            if (!nameEl) continue;
            const name = nameEl.textContent.trim();
            if (!name || name.length < 5) continue;
            if (!name.toLowerCase().includes('pokemon') && !name.toLowerCase().includes('pokémon')) continue;
            const link = item.querySelector('a[href*="/product/"], a.woocommerce-LoopProduct-link');
            const href = link ? link.getAttribute('href') || '' : '';
            const priceEl = item.querySelector('.price ins .amount, .price .amount, .price');
            let price = '';
            if (priceEl) {
                const raw = priceEl.textContent.replace(/\\s/g, '').replace(/\\u00a0/g, '');
                const m = raw.match(/(\\d+)[,\\.](\\d{2})/);
                if (m) price = m[1] + '.' + m[2];
                else {
                    const m2 = raw.match(/(\\d+)/);
                    if (m2) price = m2[1];
                }
            }
            const imgEl = item.querySelector('img');
            const img = imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : '';
            const addBtn = item.querySelector('.add_to_cart_button, [class*="add-to-cart"]');
            const available = addBtn !== null;
            const pidMatch = href.match(/\\/([^\\/]+)\\/?$/);
            const pid = pidMatch ? pidMatch[1] : '';
            result.push({pid, name, price, url: href, img, available});
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
    ]
    if PROXY_ADDR and PROXY_ADDR != "none":
        browser_args.append(f"--proxy-server=http://{PROXY_ADDR}")

    try:
        browser = await uc.start(headless=False, sandbox=False, browser_args=browser_args)
    except Exception as e:
        log.error(f"[battlestash] Failed to start browser: {e}")
        return []

    try:
        page = await browser.get(URL)
        await asyncio.sleep(12)

        title = await page.evaluate("document.title")
        if not title or "moment" in title.lower() or "attention" in title.lower():
            log.warning("[battlestash] CF not resolved, waiting...")
            await asyncio.sleep(10)
            title = await page.evaluate("document.title")
            if not title or "moment" in title.lower():
                log.error("[battlestash] CF block")
                return []

        raw = await page.evaluate(EXTRACT_JS)
        if not raw:
            return []

        try:
            items = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
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
                "id": f"battlestash_{pid}",
                "name": name,
                "price": price_str,
                "shop": SHOP,
                "url": item.get("url", ""),
                "image": item.get("img", ""),
                "stock": None,
                "available": item.get("available", False),
            })

    except Exception as e:
        log.error(f"[battlestash] Error: {e}")
    finally:
        try:
            browser.stop()
        except:
            pass

    print(f"[BATTLESTASH] {len(products)} produktow")
    return products
