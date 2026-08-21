"""
Scraper: battlestash.pl
Platform: WooCommerce (behind Cloudflare)
Method: CF Solver (Camoufox) → HTML category page parsing
Category URL: /kategoria/gry-karciane/pokemon-tcg/
Note: WP REST API (/wp-json/) returns 403 behind CF without challenge page.
      Must use HTML category page which shows Turnstile → solvable by Camoufox.
"""
import aiohttp
import asyncio
import json
import re
import html as html_lib
from bs4 import BeautifulSoup

SHOP = "battlestash.pl"
SCAN_TIMEOUT = 180  # Extended: CF solver needs 55s+ for Turnstile
BASE_URL = "https://battlestash.pl"
CATEGORY_URL = f"{BASE_URL}/kategoria/gry-karciane/pokemon-tcg/"
MAX_PAGES = 3
FLARESOLVERR_URL = "http://localhost:8191/v1"

EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "pro-binder", "ultra pro", "ultra-pro",
    "playmat", "mata", "portfolio", "deck box",
    "one piece", "lorcana", "yu-gi-oh", "digimon", "magic the", "naruto", "star wars",
    "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz", "force of will",
    "riftbound",
    "japonsk", "japońsk", "japanese", "japan", "(jp)", "korean", "koreańsk", "korea",
    "chiński", "chińsk", "chinese", "china", "(chi)", "s-chinese",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy",
    "segregator", "alcove", "zeszyt", "puzzle", "figurk", "figure set", "turniej",
]


async def fetch_flaresolverr(url):
    """Fetch URL via CF Bridge (cf_solver.py) to bypass Cloudflare."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
            async with session.post(
                FLARESOLVERR_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                if data.get("status") == "ok":
                    return data.get("solution", {}).get("response", "")
    except Exception as e:
        print(f"[battlestash] CF Solver error: {e}")
    return ""


def parse_products_from_html(html_content):
    """Parse products from WooCommerce category page HTML."""
    products = []
    soup = BeautifulSoup(html_content, "html.parser")

    # WooCommerce standard: products in <ul class="products"> > <li class="product">
    product_items = soup.select("li.product, .product-item, .products .product")
    if not product_items:
        # Try broader selectors
        product_items = soup.select("[class*='product']")

    for item in product_items:
        try:
            # Skip non-product elements
            classes = " ".join(item.get("class", []))
            if "product-category" in classes or "widget" in classes:
                continue

            # Name
            name_el = item.select_one("h2 a, .woocommerce-loop-product__title, h3 a, .product-title a, a.woocommerce-LoopProduct-link h2")
            if not name_el:
                name_el = item.select_one("h2, h3, .product-title")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            name = html_lib.unescape(name)
            if not name or len(name) < 5:
                continue

            # URL
            link_el = item.select_one("a[href*='/produkt/'], a[href*='/product/'], h2 a, h3 a, a.woocommerce-LoopProduct-link")
            if not link_el:
                link_el = item.select_one("a[href]")
            url = link_el.get("href", "") if link_el else ""
            if not url or "kategoria" in url:
                continue
            if not url.startswith("http"):
                url = BASE_URL + url

            # Price
            price_el = item.select_one(".price .woocommerce-Price-amount, .price ins .woocommerce-Price-amount, .price bdi")
            if not price_el:
                price_el = item.select_one(".price")
            price = "brak"
            if price_el:
                price_text = price_el.get_text(strip=True)
                # Extract numeric price (Polish: "199,00 zł" or "199.00 zł")
                price_match = re.search(r'([\d.,]+)', price_text.replace("\xa0", "").replace(" ", ""))
                if price_match:
                    price_raw = price_match.group(1).replace(",", ".")
                    # Handle case where there are multiple dots (thousands separator)
                    parts = price_raw.split(".")
                    if len(parts) > 2:
                        price_raw = "".join(parts[:-1]) + "." + parts[-1]
                    try:
                        price_val = float(price_raw)
                        if price_val > 0:
                            price = f"{price_val:.2f} PLN"
                    except ValueError:
                        pass

            # Availability (WooCommerce: outofstock class on <li>)
            available = True
            if "outofstock" in classes or "out-of-stock" in classes:
                available = False
            # Also check for "Wyprzedane"/"Brak" badge
            stock_el = item.select_one(".out-of-stock, .sold-out, [class*='outofstock']")
            if stock_el:
                available = False

            # Image
            img_el = item.select_one("img[data-src], img[src]")
            image = ""
            if img_el:
                image = img_el.get("data-src") or img_el.get("data-lazy-src") or img_el.get("src", "")
                # Skip placeholder images
                if "placeholder" in image.lower() or "woocommerce-placeholder" in image.lower():
                    image = ""
                if image and not image.startswith("http"):
                    image = BASE_URL + image

            # Generate ID from URL slug
            slug_match = re.search(r'/(?:produkt|product)/([^/]+)', url)
            pid = slug_match.group(1) if slug_match else re.sub(r'[^a-z0-9]', '', name.lower()[:30])

            products.append({
                "id": f"battlestash_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": url,
                "image": image,
                "stock": 1 if available else 0,
                "available": available,
            })
        except Exception:
            continue

    return products


async def get_products():
    products = []
    seen = set()

    for page in range(1, MAX_PAGES + 1):
        if page == 1:
            url = CATEGORY_URL
        else:
            url = f"{CATEGORY_URL}page/{page}/"

        raw = await fetch_flaresolverr(url)
        if not raw or len(raw) < 1000:
            break

        # DEBUG: save HTML for analysis (remove after fix)
        if page == 1 and not products:
            try:
                with open("/tmp/battlestash_debug.html", "w") as f:
                    f.write(raw[:50000])
                print(f"[BATTLESTASH] DEBUG: saved {len(raw)} chars to /tmp/battlestash_debug.html")
            except:
                pass

        page_products = parse_products_from_html(raw)
        if not page_products:
            break

        for p in page_products:
            name_low = p["name"].lower()
            if any(ex in name_low for ex in EXCLUDE):
                continue
            if p["url"] in seen:
                continue
            seen.add(p["url"])
            products.append(p)

        # Check if there's a next page
        soup = BeautifulSoup(raw, "html.parser")
        next_link = soup.select_one(f"a.page-numbers[href*='page/{page+1}'], a.next")
        if not next_link:
            break

    # Sort: OOS first, available last (for first snapshot ordering)
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))

    print(f"[BATTLESTASH] {len(products)} produktow")
    return products
