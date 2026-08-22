"""
Scraper: battlestash.pl
Platform: WooCommerce + Flatsome theme (behind Cloudflare)
Method: CF Solver (Camoufox) → HTML category page parsing
Category URL: /kategoria/gry-karciane/pokemon-tcg/
Selector: .product-small.type-product (Flatsome grid)
Data source: GTM4WP data-gtm4wp_product_data JSON (price, stock, name)
             + HTML fallback (image, availability class)
"""
import asyncio
import json
import re
import html as html_lib

import aiohttp
from bs4 import BeautifulSoup

SHOP = "battlestash.pl"
SCAN_TIMEOUT = 300
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
            payload = {"cmd": "request.get", "url": url, "maxTimeout": 240000}
            async with session.post(
                FLARESOLVERR_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=260),
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
    """Parse products from Flatsome WooCommerce category page."""
    products = []
    soup = BeautifulSoup(html_content, "html.parser")

    # Flatsome: div.product-small with class type-product (top-level product containers)
    items = soup.select("div.product-small.type-product")

    for item in items:
        try:
            classes = " ".join(item.get("class", []))

            # === GTM DATA (primary — has price, stock, name, URL) ===
            gtm_el = item.select_one("span.gtm4wp_productdata[data-gtm4wp_product_data]")
            gtm = {}
            if gtm_el:
                try:
                    gtm = json.loads(gtm_el.get("data-gtm4wp_product_data", "{}"))
                except (json.JSONDecodeError, TypeError):
                    pass

            # === NAME ===
            name = ""
            if gtm.get("item_name"):
                name = gtm["item_name"]
            else:
                name_el = item.select_one(".name.product-title a, .woocommerce-loop-product__title a")
                if name_el:
                    name = name_el.get_text(strip=True)
            if not name:
                continue
            name = html_lib.unescape(name)

            # === URL ===
            url = ""
            if gtm.get("productlink"):
                url = gtm["productlink"]
            else:
                link_el = item.select_one(".name.product-title a, a[href*='/produkt/']")
                if link_el:
                    url = link_el.get("href", "")
            if not url:
                continue
            if not url.startswith("http"):
                url = BASE_URL + url

            # === PRICE ===
            price = "brak"
            if gtm.get("price"):
                price_val = float(gtm["price"])
                if price_val > 0:
                    price = f"{price_val:.2f} PLN"
            else:
                price_el = item.select_one(".price bdi, .price .woocommerce-Price-amount")
                if price_el:
                    price_text = price_el.get_text(strip=True)
                    price_match = re.search(r'([\d.,]+)', price_text.replace("\xa0", ""))
                    if price_match:
                        pv = price_match.group(1).replace(",", ".")
                        try:
                            price = f"{float(pv):.2f} PLN"
                        except ValueError:
                            pass

            # === AVAILABILITY ===
            available = False
            if gtm.get("stockstatus"):
                available = gtm["stockstatus"] == "instock"
            elif "instock" in classes:
                available = True
            elif "outofstock" in classes:
                available = False
            else:
                # Check for add-to-cart button
                atc = item.select_one(".add_to_cart_button, a[href*='add-to-cart']")
                available = atc is not None

            # === IMAGE ===
            img_el = item.select_one("img.attachment-woocommerce_thumbnail, .box-image img")
            image = ""
            if img_el:
                image = img_el.get("src", "")
                if "woocommerce-placeholder" in image:
                    image = ""

            # === ID ===
            pid = str(gtm.get("internal_id", ""))
            if not pid:
                slug_match = re.search(r'/produkt/([^/]+)', url)
                pid = slug_match.group(1) if slug_match else ""
            if not pid:
                continue

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
        next_link = soup.select_one(f"a.page-numbers[href*='page/{page+1}'], a.next.page-numbers")
        if not next_link:
            break

    # Sort: OOS first, available last (for first snapshot ordering)
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))

    print(f"[BATTLESTASH] {len(products)} produktow")
    return products
