"""Battlestash.pl scraper - patchright + mobile proxy (CF bypass)"""
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
           "podobne produkty", "keyforge", "ultimate guard", "vampire", "deck"]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

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
            const link = item.querySelector('a[href*="/product/"], a.woocommerce-LoopProduct-link, a[href*="battlestash"]');
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
            const addBtn = item.querySelector('.add_to_cart_button, [class*="add-to-cart"], .ajax_add_to_cart');
            const available = addBtn !== null;
            const pidMatch = href.match(/\\/([^\\/]+)\\/?$/);
            const pid = pidMatch ? pidMatch[1] : '';
            result.push({pid, name, price, url: href, img, available});
        } catch(e) {}
    }
    return result;
})())
"""

MAX_RETRIES = 2


async def get_products():
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await _scrape()
        except Exception as e:
            err = str(e)
            if attempt < MAX_RETRIES:
                log.warning(f"[battlestash] Attempt {attempt+1} failed ({err[:60]}), retrying...")
                await asyncio.sleep(5)
                continue
            log.error(f"[battlestash] Error after {MAX_RETRIES+1} attempts: {err[:80]}")
            return []
    return []


async def _scrape():
    from patchright.async_api import async_playwright

    products = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            proxy={"server": f"http://{PROXY_ADDR}"} if PROXY_ADDR and PROXY_ADDR != "none" else None,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
        )
        page = await browser.new_page(user_agent=UA)

        try:
            await page.goto(URL, wait_until="domcontentloaded", timeout=45000)

            # Wait for CF challenge to resolve
            for _ in range(12):
                title = await page.title()
                if "moment" not in title.lower() and "checking" not in title.lower() and "attention" not in title.lower():
                    break
                await asyncio.sleep(2)

            # Verify CF passed
            title = await page.title()
            if "moment" in title.lower() or "checking" in title.lower() or "attention" in title.lower():
                log.error("[battlestash] CF block - challenge not resolved")
                await browser.close()
                return []

            # Wait for products to load
            await asyncio.sleep(3)

            # Debug: save page state
            try:
                html_content = await page.content()
                debug_path = "/opt/pokemon-monitor-v2/data/battlestash_debug.html"
                with open(debug_path, "w") as f:
                    f.write(html_content)
                log.info(f"[battlestash] DEBUG: saved HTML ({len(html_content)} chars), title='{title}'")
            except Exception as de:
                log.warning(f"[battlestash] DEBUG save failed: {de}")

            # Scroll to load lazy images
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

            # Check pagination - get all pages
            all_items = []

            # Extract page 1
            raw = await page.evaluate(EXTRACT_JS)
            if raw:
                try:
                    items = json.loads(raw)
                    all_items.extend(items)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Check for pagination
            next_pages = await page.evaluate("""
                JSON.stringify(Array.from(document.querySelectorAll('.page-numbers a:not(.next)')).map(a => a.href).filter(h => h && h.includes('/page/')))
            """)
            try:
                page_urls = json.loads(next_pages) if next_pages else []
            except:
                page_urls = []

            # Fetch additional pages (max 3 more)
            for pg_url in page_urls[:3]:
                try:
                    await page.goto(pg_url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(3)
                    raw = await page.evaluate(EXTRACT_JS)
                    if raw:
                        items = json.loads(raw)
                        all_items.extend(items)
                except Exception as e:
                    log.warning(f"[battlestash] Page {pg_url} error: {e}")
                    break

            # Process all items
            seen = set()
            for item in all_items:
                pid = item.get("pid", "")
                name = item.get("name", "")
                if not pid or not name or pid in seen:
                    continue
                name_lower = name.lower()
                if "pokemon" not in name_lower and "pokémon" not in name_lower:
                    continue
                if any(ex in name_lower for ex in EXCLUDE):
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

        finally:
            await browser.close()

    print(f"[BATTLESTASH] {len(products)} produktow")
    return products
