"""
Scraper: tantis.pl — CF protected
Method: patchright (persistent stealth browser + proxy) + JS extraction + API fallback
BROWSER_TYPE = "stealth"
"""
import asyncio
import json
import re
import logging

log = logging.getLogger("monitor")

SHOP = "tantis"
BROWSER_TYPE = "stealth"
BASE_URL = "https://tantis.pl"
CATEGORY_URLS = [
    f"{BASE_URL}/pokemon-tcg-c7053?limit=100&sort=newest",
    f"{BASE_URL}/pokemon-tcg-c7053?limit=100",
    f"{BASE_URL}/pokemon-tcg-c7053",
]

EXCLUDE = [
    "ultra-pro", "ultra pro", "playmat", "portfolio", "pro-binder", "deck box", "sleeves",
    "toploader", "album", "alcove", "koszulk", "segregator",
    "nihil", "historia pokemon", "niezbędnik", "puzzle", "figurk", "figure set",
    "pokemon go", "karty do kolekc", "symphonia", "synmphonia", "lalie",
    "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean",
    "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood",
    "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "figurk", "figure set",
]

EXTRACT_JS = """
() => {
    const tuples = document.querySelectorAll('.ui-product-tuple');
    const results = [];
    tuples.forEach(el => {
        const titleEl = el.querySelector('.ui-product-tuple__title a') || el.querySelector('.ui-product-tuple__title');
        const name = titleEl ? titleEl.textContent.trim() : '';
        const linkEl = el.querySelector('a[href*="/p"]');
        const url = linkEl ? linkEl.href : '';
        const priceBox = el.querySelector('.ui-product-tuple__price-box');
        let price = '';
        if (priceBox) {
            const priceMatch = priceBox.textContent.match(/(\\d+[,.]\\d{2})\\s*zł/);
            if (priceMatch) price = priceMatch[1].replace(',', '.');
        }
        const imgEl = el.querySelector('img');
        const img = imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : '';
        const unavail = el.querySelector('.ui-product-tuple__price-box--unavailable') !== null;
        const cartBtn = el.querySelector('.ui-product-tuple__cart-button');
        const notifBtn = el.querySelector('.ui-product-tuple__notification-button-container');
        const avail = (cartBtn !== null) && !unavail && !notifBtn;
        const pidMatch = url.match(/p(\\d+)/);
        const pid = pidMatch ? pidMatch[1] : '';
        if (name) results.push({pid, name, price, url, img, avail});
    });
    return results;
}
"""


async def scan_with_page(page):
    """Persistent browser interface — page already exists, just navigate."""
    products = []
    seen_ids = set()

    # Try URLs in order (limit=100 first)
    loaded = False
    for url in CATEGORY_URLS:
        try:
            await page.goto(url, wait_until="load", timeout=45000)
            for _ in range(12):
                title = await page.title()
                if "moment" not in title.lower() and "checking" not in title.lower():
                    break
                await asyncio.sleep(2)
            await asyncio.sleep(2)

            count = await page.evaluate("() => document.querySelectorAll('.ui-product-tuple').length")
            if count > 0:
                loaded = True
                break
        except Exception:
            continue

    if not loaded:
        log.warning("[tantis] Could not load category page")
        return []

    # Scroll to load lazy content
    for _ in range(5):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.8)

    # Extract products
    items = await page.evaluate(EXTRACT_JS)

    for item in items:
        name = item.get("name", "")
        pid = item.get("pid", "")
        if not name or not pid:
            continue
        name_lower = name.lower()
        if "pokemon" not in name_lower and "pokémon" not in name_lower:
            continue
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        price_val = item.get("price", "")
        if price_val:
            price_str = f"{price_val} PLN"
            try:
                if float(price_val) < 10:
                    continue
            except ValueError:
                pass
        else:
            price_str = "brak"

        if pid in seen_ids:
            continue
        seen_ids.add(pid)

        url = item.get("url", "")
        if url and not url.startswith("http"):
            url = BASE_URL + url
        image = item.get("img", "")
        if image and not image.startswith("http"):
            image = BASE_URL + image

        products.append({
            "id": f"tantis_{pid}",
            "name": name,
            "price": price_str,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": None,
            "available": item.get("avail", False),
        })

    # Page 2
    has_next = await page.evaluate("""() => {
        const next = document.querySelector('a[rel="next"], [class*=pagination] a[class*=next]');
        return next ? next.href : null;
    }""")

    if has_next and len(items) >= 10:
        try:
            await page.goto(has_next, wait_until="load", timeout=30000)
            await asyncio.sleep(3)
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.5)

            items2 = await page.evaluate(EXTRACT_JS)
            for item in items2:
                name = item.get("name", "")
                pid = item.get("pid", "")
                if not name or not pid or pid in seen_ids:
                    continue
                name_lower = name.lower()
                if "pokemon" not in name_lower and "pokémon" not in name_lower:
                    continue
                if any(ex in name_lower for ex in EXCLUDE):
                    continue
                price_val = item.get("price", "")
                if price_val:
                    price_str = f"{price_val} PLN"
                    try:
                        if float(price_val) < 10:
                            continue
                    except ValueError:
                        pass
                else:
                    price_str = "brak"
                seen_ids.add(pid)
                url = item.get("url", "")
                if url and not url.startswith("http"):
                    url = BASE_URL + url
                image = item.get("img", "")
                if image and not image.startswith("http"):
                    image = BASE_URL + image
                products.append({
                    "id": f"tantis_{pid}",
                    "name": name,
                    "price": price_str,
                    "shop": SHOP,
                    "url": url,
                    "image": image,
                    "stock": None,
                    "available": item.get("avail", False),
                })
        except Exception as e:
            log.debug(f"[tantis] Page 2 error: {e}")

    # API fallback
    try:
        raw = await page.evaluate("""
            async (path) => {
                const r = await fetch(path, {
                    headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
                    credentials: 'same-origin'
                });
                if (!r.ok) return '[]';
                return await r.text();
            }
        """, "/front-api/v1/products?categoryId=7053&limit=100")
        api_items = json.loads(raw)
        if isinstance(api_items, list):
            for item in api_items:
                pid = str(item.get("productId", ""))
                name = item.get("name", "")
                if not pid or not name or pid in seen_ids:
                    continue
                name_lower = name.lower()
                if "pokemon" not in name_lower and "pokémon" not in name_lower:
                    continue
                if any(ex in name_lower for ex in EXCLUDE):
                    continue
                price_val = item.get("price", 0)
                if price_val and price_val < 10:
                    continue
                price_str = f"{price_val:.2f} PLN" if price_val else "brak"
                seen_ids.add(pid)
                url = item.get("url", "")
                if url and not url.startswith("http"):
                    url = BASE_URL + url
                image = ""
                img_data = item.get("image")
                if isinstance(img_data, dict):
                    image = img_data.get("url", "")
                elif isinstance(img_data, str):
                    image = img_data
                products.append({
                    "id": f"tantis_{pid}",
                    "name": name,
                    "price": price_str,
                    "shop": SHOP,
                    "url": url,
                    "image": image,
                    "stock": None,
                    "available": item.get("available", False),
                })
    except Exception as e:
        log.debug(f"[tantis] API fallback error: {e}")

    print(f"[TANTIS] {len(products)} produktow")
    return products


async def get_products():
    """Legacy interface — for testing only."""
    from patchright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            proxy={"server": "http://127.0.0.1:8888"},
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        try:
            page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
            return await scan_with_page(page)
        finally:
            await browser.close()
