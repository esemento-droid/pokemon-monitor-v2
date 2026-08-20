"""
Scraper: bonito.pl — bot protection JS verification
Method: playwright standard browser (headless, VPS IP - no proxy)
NOTE: Orange IP 37.47.130.139 is BANNED. VPS IP (146.59.45.228) works with JS challenge.
BROWSER_TYPE = "standard" — uses VPS IP directly (not mobile proxy)
SCAN_TIMEOUT = 150 — needs time for JS challenge
"""
import asyncio
import json
import logging
import re

log = logging.getLogger("monitor")

SHOP = "bonito"
BROWSER_TYPE = "stealth"  # stealth patchright passes JS challenges better
SCAN_TIMEOUT = 150  # JS challenge needs patience
SEARCH_URL = "https://bonito.pl/szukaj?fraza=pokemon+tcg"

EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder",
    "playmat", "mata", "figurka", "plush", "puzzle", "lego",
    "piórnik", "piornik", "plecak", "worek", "zeszyt", "teczka",
    "saszetka", "klaser", "japanese", "japońsk", "korean", "koreańsk",
    "chiński", "chinese", "s-chinese",
    "one piece", "lorcana", "yu-gi-oh", "digimon", "magic the",
    "naruto", "star wars", "flesh & blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound",
    "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "battle academy",
    "deck box", "alcove", "segregator",
    "ultra pro", "ultra-pro",
    "figure set", "figurk",
]

EXTRACT_JS = """
JSON.stringify((function(){
    const result = [];
    const items = document.querySelectorAll('.product-item, .product-box, [class*="product"]');
    for (const item of items) {
        try {
            const nameEl = item.querySelector('a[class*="name"], h2 a, h3 a, .product-name a, [class*="title"] a');
            if (!nameEl) continue;
            const name = nameEl.textContent.trim();
            if (!name || name.length < 5) continue;
            const href = nameEl.getAttribute('href') || '';
            const priceEl = item.querySelector('[class*="price"], .product-price');
            let price = '';
            if (priceEl) {
                const raw = priceEl.textContent.replace(/\\s/g, '').replace(/\\u00a0/g, '');
                const m = raw.match(/(\\d+)[,\\.](\\d{2})/);
                if (m) price = m[1] + '.' + m[2];
            }
            const imgEl = item.querySelector('img');
            const img = imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || imgEl.getAttribute('data-original') || '') : '';
            const btnEl = item.querySelector('button[class*="cart"], [class*="add-to-cart"], .add-to-cart, button[class*="koszyk"]');
            const text = item.innerText.toLowerCase();
            const unavail = text.includes('niedost') || text.includes('wyprzedane') || text.includes('brak');
            const available = btnEl !== null && !unavail;
            const pidMatch = href.match(/\\/(\\d+)/) || href.match(/id=(\\d+)/);
            const pid = pidMatch ? pidMatch[1] : href.split('/').filter(x=>x).pop() || '';
            result.push({pid, name, price, url: href, img, available});
        } catch(e) {}
    }
    return result;
})())
"""


async def scan_with_page(page):
    """Persistent browser interface — page already exists, just navigate."""
    products = []

    await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=45000)

    # Wait for bot protection to resolve
    for _ in range(15):
        content = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 200) : ''")
        if "weryfikacja" not in content.lower() and "sprawdzanie" not in content.lower():
            break
        await asyncio.sleep(2)

    await asyncio.sleep(3)

    title = await page.title()
    if "weryfikacja" in title.lower():
        log.error("[bonito] Bot protection not resolved")
        return []

    # Scroll to load lazy content
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(2)

    # Extract products with JS
    raw = await page.evaluate(EXTRACT_JS)
    items = []
    if raw:
        try:
            items = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass

    # BS4 fallback if JS extraction failed
    if not items:
        from bs4 import BeautifulSoup
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        for card in soup.select('.product-item, .product-box, [class*="product-card"], .search-result-item, .item'):
            name_el = card.select_one('a[class*="name"], h2 a, h3 a, [class*="title"] a')
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 5:
                continue
            href = name_el.get("href", "")
            if href and not href.startswith("http"):
                href = "https://bonito.pl" + href

            price_el = card.select_one('[class*="price"]')
            price = "brak"
            if price_el:
                m = re.search(r"(\d+[,.]\d+)", price_el.get_text())
                if m:
                    price = m.group(1).replace(",", ".") + " zl"

            pid_match = re.search(r"/(\d+)", href)
            pid = pid_match.group(1) if pid_match else href.split("/")[-1]

            text = card.get_text(" ", strip=True).lower()
            available = "niedost" not in text and "wyprzedane" not in text

            img_el = card.select_one("img")
            image = ""
            if img_el:
                image = img_el.get("src") or img_el.get("data-src") or ""

            items.append({"pid": pid, "name": name, "price": price, "url": href, "img": image, "available": available})

    # Filter and deduplicate
    seen = set()
    for item in items:
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
        if isinstance(price_val, str) and price_val and not price_val.endswith("zl"):
            price_str = f"{price_val} zl"
        else:
            price_str = price_val if price_val else "brak"

        url = item.get("url", "")
        if url and not url.startswith("http"):
            url = "https://bonito.pl" + url

        products.append({
            "id": f"bonito_{pid}",
            "name": name,
            "price": price_str,
            "shop": SHOP,
            "url": url,
            "image": item.get("img", ""),
            "stock": None,
            "available": item.get("available", False),
        })

    print(f"[BONITO] {len(products)} produktow")
    return products


async def get_products():
    """Legacy interface — for testing only."""
    from patchright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
        )
        try:
            page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
            return await scan_with_page(page)
        finally:
            await browser.close()
