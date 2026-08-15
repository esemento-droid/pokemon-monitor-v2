"""
BoosterPoint.pl scraper - Patchright
1) WC Store API paginated (all products visible in API)
2) HTML category /30th-celebration/ (products hidden from API)
JS challenge bypass on homepage first.
"""
import asyncio
import json
import re
import os
from html import unescape

SHOP = "boosterpoint"
BASE = "https://boosterpoint.pl"
PROXY = "http://" + open("/tmp/px").read().strip() if os.path.exists("/tmp/px") else ""

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


async def get_products():
    from patchright.async_api import async_playwright

    products = []
    seen_ids = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                f"--proxy-server={PROXY}" if PROXY else "",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        try:
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

            # === PART 2: Hidden categories (HTML scrape) ===
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

                    # Find product URLs and names
                    prod_urls = re.findall(
                        r'href="(https://boosterpoint\.pl/produkt/([^"]+)/)"',
                        html
                    )
                    names = re.findall(r'woocommerce-loop-product__title[^>]*>(.+?)<', html)

                    found_new = False
                    for i, (full_url, slug) in enumerate(prod_urls):
                        # Deduplicate by slug (no numeric ID available for hidden products)
                        if slug in seen_ids:
                            continue
                        seen_ids.add(slug)
                        found_new = True

                        # Try to get product ID from data-product_id in surrounding HTML
                        pid_match = re.search(
                            rf'data-product_id="(\d+)"[^>]*href="{re.escape(full_url)}"',
                            html
                        )
                        if not pid_match:
                            pid_match = re.search(
                                rf'href="{re.escape(full_url)}"[^<]*data-product_id="(\d+)"',
                                html
                            )
                        pid = pid_match.group(1) if pid_match else slug

                        # Already seen by numeric ID?
                        if pid != slug and pid in seen_ids:
                            continue
                        seen_ids.add(pid)

                        name = unescape(names[i]) if i < len(names) else slug.replace("-", " ").title()
                        name_lower = name.lower()
                        if any(kw in name_lower for kw in EXCLUDE_KW):
                            continue

                        # Price from HTML (hard to extract reliably)
                        price = "brak"

                        # Available if add_to_cart link exists for this product
                        available = f'add_to_cart_button" href="?add-to-cart=' in html or 'add_to_cart' in html

                        products.append({
                            "id": f"boosterpoint_{pid}",
                            "name": name,
                            "price": price,
                            "shop": SHOP,
                            "url": full_url,
                            "image": "",
                            "stock": None,
                            "available": available,
                        })

                    if not found_new:
                        break
                    if 'class="next' not in html:
                        break
                    cat_page += 1

        except Exception as e:
            print(f"[boosterpoint] Error: {e}")
        finally:
            await browser.close()

    return products


if __name__ == "__main__":
    r = asyncio.run(get_products())
    print(f"{len(r)} products")
    avail = [p for p in r if p["available"]]
    unavail = [p for p in r if not p["available"]]
    print(f"Available: {len(avail)}, Unavailable: {len(unavail)}")
    thirty = [p for p in r if "30th" in p["name"].lower() or "celebration" in p["name"].lower()]
    print(f"30th products: {len(thirty)}")
    for p in thirty:
        print(f"  {p['id']} | avail:{p['available']} | {p['price']} | {p['name']}")
