"""
Scraper: tantis.pl
Platform: Custom (CF protected, HTML scraping)
Method: Patchright (headless=False, NO proxy) + HTML extraction
Products: Pokemon TCG category page
"""
import asyncio
import re
import logging
from patchright.async_api import async_playwright

log = logging.getLogger("monitor")

SHOP = "tantis"
BASE_URL = "https://tantis.pl"
CATEGORY_URL = f"{BASE_URL}/pokemon-tcg-c7053"
# Try loading more products per page
CATEGORY_URLS = [
    f"{BASE_URL}/pokemon-tcg-c7053?limit=100",
    f"{BASE_URL}/pokemon-tcg-c7053",
]

EXCLUDE = [
    # Accessories
    "ultra-pro", "ultra pro", "playmat", "portfolio", "pro-binder", "deck box", "sleeves",
    "toploader", "album", "alcove", "koszulk", "segregator",
    # Junk
    "nihil", "historia pokemon", "niezbędnik", "puzzle", "figurk", "figure set",
    "pokemon go", "karty do kolekc", "symphonia", "synmphonia", "lalie",
    # Decks
    "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy",
    # Foreign
    "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean",
    "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    # Other games
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood",
    "dragon shield", "weiss schwarz", "force of will", "riftbound",
    # Junk
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
            // Extract just the number, ignore "Wysyłka" etc
            const priceMatch = priceBox.textContent.match(/(\\d+[,.]\\d{2})\\s*zł/);
            if (priceMatch) price = priceMatch[1].replace(',', '.');
        }
        const imgEl = el.querySelector('img');
        const img = imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : '';
        const unavail = el.querySelector('.ui-product-tuple__price-box--unavailable') !== null;
        const cartBtn = el.querySelector('.ui-product-tuple__cart-button');
        const notifBtn = el.querySelector('.ui-product-tuple__notification-button-container');
        const avail = (cartBtn !== null) && !unavail && !notifBtn;
        // PID from URL
        const pidMatch = url.match(/p(\\d+)/);
        const pid = pidMatch ? pidMatch[1] : '';
        if (name) results.push({pid, name, price, url, img, avail});
    });
    return results;
}
"""

MAX_RETRIES = 2


async def get_products():
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await _scrape()
        except Exception as e:
            err = str(e)
            if attempt < MAX_RETRIES:
                log.warning(f"[tantis] Attempt {attempt+1} failed ({err[:60]}), retrying...")
                await asyncio.sleep(3)
                continue
            log.error(f"[tantis] Error: {err[:80]}")
            return []
    return []


async def _scrape():
    products = []
    seen_ids = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            proxy={"server": "http://127.0.0.1:8888"},
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
        )
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

        try:
            # Try URLs in order (limit=100 first, fallback to default)
            loaded = False
            for url in CATEGORY_URLS:
                try:
                    await page.goto(url, wait_until="load", timeout=45000)
                    # Wait for CF challenge
                    for _ in range(12):
                        title = await page.title()
                        if "moment" not in title.lower() and "checking" not in title.lower():
                            break
                        await asyncio.sleep(2)
                    await asyncio.sleep(2)

                    # Verify page loaded
                    count = await page.evaluate("() => document.querySelectorAll('.ui-product-tuple').length")
                    if count > 0:
                        loaded = True
                        break
                except Exception as e:
                    log.debug(f"[tantis] URL {url} failed: {e}")
                    continue

            if not loaded:
                log.warning("[tantis] Could not load category page")
                await browser.close()
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

                # Must be Pokemon
                if "pokemon" not in name_lower and "pokémon" not in name_lower:
                    continue

                # Exclude filter
                if any(ex in name_lower for ex in EXCLUDE):
                    continue

                # Price
                price_val = item.get("price", "")
                if price_val:
                    price_str = f"{price_val} PLN"
                    # Filter singles <10 PLN
                    try:
                        if float(price_val) < 10:
                            continue
                    except ValueError:
                        pass
                else:
                    price_str = "brak"

                # Dedup
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)

                # URL
                url = item.get("url", "")
                if url and not url.startswith("http"):
                    url = BASE_URL + url

                # Image
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

            # Check if there's pagination (next page)
            has_next = await page.evaluate("""() => {
                const next = document.querySelector('a[rel="next"], [class*=pagination] a[class*=next]');
                return next ? next.href : null;
            }""")

            # Load page 2 if exists
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

        finally:
            await browser.close()

    print(f"[TANTIS] {len(products)} produktow")
    return products
