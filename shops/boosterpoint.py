"""
BoosterPoint.pl scraper — patchright (persistent stealth browser)
1) WC Store API paginated (all products visible in API)
2) HTML category /30th-celebration/ (products hidden from API)
BROWSER_TYPE = "stealth"
"""
import asyncio
import json
import re
import logging
from html import unescape

log = logging.getLogger("monitor")

SHOP = "boosterpoint"
BROWSER_TYPE = "stealth"
BASE = "https://boosterpoint.pl"

EXCLUDE_KW = [
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder",
    "playmat", "mata do gry", "deck box", "ultra pro", "one piece", "lorcana",
    "yu-gi-oh", "digimon", "kostki gamegenic", "dobble",
    "squishmallows", "pluszak", "przytulanka", "plusz", "bidon", "kubek",
    "piórnik", "gumka", "pencil", "funko", "espresso",
    "live break", "shadow booster",
]

HIDDEN_CATEGORIES = [
    "/pokemon-tcg/mega-evolution-tcg/30th-celebration/",
]


async def scan_with_page(page):
    """Persistent browser interface — page already exists, just navigate."""
    products = []
    seen_ids = set()

    # Pass JS challenge on homepage
    await page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
    for _ in range(12):
        title = await page.title()
        if "verif" not in title.lower() and "503" not in title:
            break
        await asyncio.sleep(2)

    # === PART 1: WC Store API (all visible products) ===
    page_num = 1
    while True:
        result = await page.evaluate(f"""
            async () => {{
                const r = await fetch('/wp-json/wc/store/v1/products?per_page=100&page={page_num}');
                const h = {{}};
                r.headers.forEach((v, k) => h[k] = v);
                return {{status: r.status, text: await r.text(), headers: h}};
            }}
        """)

        if result["status"] != 200:
            break

        text = result["text"]
        idx = text.find("[")
        if idx < 0:
            break

        data = json.loads(text[idx:])
        if not data:
            break

        for p in data:
            pid = str(p["id"])
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            name = unescape(p.get("name", ""))
            name_lower = name.lower()
            if any(kw in name_lower for kw in EXCLUDE_KW):
                continue

            price_raw = p.get("prices", {}).get("price", "0")
            price = f"{int(price_raw) / 100:.2f} zl" if price_raw else "brak"
            img = ""
            if p.get("images"):
                img = p["images"][0].get("src", "")

            products.append({
                "id": f"boosterpoint_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": p.get("permalink", ""),
                "image": img.replace(" ", "%20"),
                "stock": None,
                "available": p.get("is_in_stock", False),
            })

        total_pages = int(result.get("headers", {}).get("x-wp-totalpages", "1"))
        if page_num >= total_pages:
            break
        page_num += 1

    # === PART 2: Hidden categories (HTML scrape via fetch) ===
    for cat_url in HIDDEN_CATEGORIES:
        cat_page = 1
        while True:
            url = f"{cat_url}page/{cat_page}/" if cat_page > 1 else cat_url
            result = await page.evaluate(f"""
                async () => {{
                    const r = await fetch('{url}');
                    return {{status: r.status, text: await r.text()}};
                }}
            """)
            if result["status"] != 200:
                break

            html = result["text"]
            prod_urls = re.findall(r'href="(https://boosterpoint\.pl/produkt/([^"]+)/)"', html)
            names = re.findall(r'woocommerce-loop-product__title[^>]*>(.+?)<', html)

            found_new = False
            for i, (full_url, slug) in enumerate(prod_urls):
                if slug in seen_ids:
                    continue
                seen_ids.add(slug)
                found_new = True

                pid_match = re.search(rf'data-product_id="(\d+)"[^>]*href="{re.escape(full_url)}"', html)
                if not pid_match:
                    pid_match = re.search(rf'href="{re.escape(full_url)}"[^<]*data-product_id="(\d+)"', html)
                pid = pid_match.group(1) if pid_match else slug

                if pid != slug and pid in seen_ids:
                    continue
                seen_ids.add(pid)

                name = unescape(names[i]) if i < len(names) else slug.replace("-", " ").title()
                if any(kw in name.lower() for kw in EXCLUDE_KW):
                    continue

                products.append({
                    "id": f"boosterpoint_{pid}",
                    "name": name,
                    "price": "brak",
                    "shop": SHOP,
                    "url": full_url,
                    "image": "",
                    "stock": None,
                    "available": 'add_to_cart' in html,
                })

            if not found_new or 'class="next' not in html:
                break
            cat_page += 1

    print(f"[BOOSTERPOINT] {len(products)} produktow")
    return products


async def get_products():
    """Legacy interface — for testing only."""
    from patchright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--proxy-server=http://127.0.0.1:8888"]
        )
        try:
            ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
            page = await ctx.new_page()
            return await scan_with_page(page)
        finally:
            await browser.close()
