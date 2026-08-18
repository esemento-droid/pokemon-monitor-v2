"""
Scraper: limango.pl — Klocki LEGO (outlet flash-sale)
URL: /shop/lego?page=N (all pages)
Strategy: Parse __NEXT_DATA__ JSON from SSR HTML
Pagination: 6 stron (~108 produktow/strone, 569 total brand, ~67 klocki)
"""

import asyncio
import re
import json
import ssl
import os

import aiohttp

# Price comparison — from cache (promoklocki.pl, refreshed every 4h by price_cache.py)
try:
    from price_cache import get_cached_price
    HAS_PRICE_CACHE = True
except ImportError:
    HAS_PRICE_CACHE = False

SHOP = "limango"
BASE = "https://www.limango.pl"
BROWSE_URL = f"{BASE}/shop/lego"
MAX_PAGES = 6

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}

LEGO_SET_CATEGORIES = [
    "zestawy i zabawki konstrukcyjne",
    "klocki",
    "zabawki konstrukcyjne",
]

TOY_PATH_KEYWORDS = ["zabawk", "klocki", "konstruk", "toys", "spielzeug"]
NEXT_DATA_RE = re.compile(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def _extract_name_from_image_url(img_url):
    if not img_url:
        return ""
    filename = img_url.rstrip("/").split("/")[-1]
    filename = re.sub(r'\.(jpg|png|webp|jpeg)$', '', filename, flags=re.IGNORECASE)
    name = filename.replace("-", " ").strip()
    name = re.sub(r'^lego\s+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+r\s+', u'\u00ae ', name)
    name = re.sub(r'\s+\d{1,2}$', '', name)
    name = name.title()
    name = name.replace(u"Lego\u00ae", u"LEGO\u00ae")
    if not name.upper().startswith("LEGO"):
        name = f"LEGO {name}"
    return name.strip()


def _is_lego_set(product):
    """Filter for actual LEGO construction sets (not clothing/accessories)."""
    name = product.get("name", "").lower()
    
    # Reject clothing/accessories with LEGO branding
    clothing_keywords = ["bokser", "kurtk", "spodni", "bluza", "piżam", "skarpet",
                         "czapk", "szalik", "t-shirt", "koszulk", "dress", "leggin",
                         "bluzi", "polar", "buty", "sandał", "kapel", "rękawic",
                         "plecak", "tornister", "torba", "worek", "piórnik",
                         "płytka", "płytk", "baseplate",
                         "pojemnik", "lunch", "bidon", "butelk", "śniadani",
                         "zestaw na", "częściowy zestaw", "lampk", "latark",
                         "kubek", "kubk", "haczyk", "wieszak", "półka",
                         "organizer", "ramka", "zegar"]
    if any(kw in name for kw in clothing_keywords):
        return False
    
    # Accept: subCategoryName indicates construction toy
    cat = (product.get("subCategoryName") or "").lower().strip()
    if cat and any(lc in cat for lc in LEGO_SET_CATEGORIES):
        return True
    
    # Accept: isOneSizeProduct + toy treePath (klocki have "onesize")
    if product.get("isOneSizeProduct"):
        return True
    
    # Accept: treePath has toy/klocki keywords
    for path in product.get("treePaths", []):
        if any(kw in path.lower() for kw in TOY_PATH_KEYWORDS):
            return True
    
    return False


def _build_product_url(product_id, golden_product_id=None):
    """Build limango product URL. Format: /shop/product/{full_id}"""
    return f"{BASE}/shop/product/{product_id}"


def _build_image_url(images):
    default = images.get("default", {})
    url_template = default.get("url", "")
    if not url_template:
        return ""
    formats = default.get("formats", {})
    format_val = formats.get("medium-360", "t_product-medium-360")
    variants = default.get("variants", [])
    variant_id = variants[0].get("id", "1") if variants else "1"
    url = url_template.replace("{format}", format_val)
    url = url.replace("{dpr}", "dpr_2.0")
    url = url.replace("{variant}", variant_id)
    return url


def _parse_page(html):
    """Extract products from page HTML via __NEXT_DATA__."""
    match = NEXT_DATA_RE.search(html)
    if not match:
        return [], 0
    try:
        data = json.loads(match.group(1))
        listing = data["props"]["pageProps"]["preloadedState"]["listing"]
        products = listing["products"]["data"]
        total = listing["products"].get("pagination", {}).get("totalCount", 0)
        return products, total
    except (json.JSONDecodeError, KeyError, TypeError):
        return [], 0


async def get_products():
    products = []
    seen_ids = set()

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BROWSE_URL}?page={page}" if page > 1 else BROWSE_URL
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), ssl=ssl_ctx) as resp:
                    if resp.status != 200:
                        break
                    html = await resp.text()
            except Exception as e:
                print(f"[LIMANGO] Page {page} error: {e}")
                break

            page_products, total = _parse_page(html)
            if not page_products:
                break

            for item in page_products:
                if not _is_lego_set(item):
                    continue

                pid = item.get("id", "")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)

                variant = item.get("cheapestVariantWithStock") or {}
                sales_price = variant.get("salesPrice", {})
                price_amount = sales_price.get("amount")
                price_str = f"{price_amount:.2f} zl" if price_amount else ""

                images = item.get("images", {})
                image_url = _build_image_url(images)

                # Use the actual product name from API (has full LEGO set name!)
                name = item.get("name", "")
                if not name:
                    # Fallback to image URL extraction (legacy)
                    raw_img_url = images.get("default", {}).get("url", "")
                    name = _extract_name_from_image_url(raw_img_url)
                if not name:
                    name = item.get("subCategoryName") or f"LEGO Set {pid}"
                
                # Clean up name for display
                name = name.strip()
                if not name.upper().startswith("LEGO"):
                    name = f"LEGO {name}"

                url_prod = _build_product_url(pid, item.get("goldenProductId"))

                # Extract LEGO set number from name (for price comparison)
                set_number = None
                set_match = re.search(r'\b(\d{5})\b', name)
                if set_match:
                    set_number = set_match.group(1)

                # Available = has stock AND has price
                total_stock = item.get("totalStockAvailable", 0)
                available = bool(total_stock and total_stock > 0 and price_amount and price_amount > 0)

                products.append({
                    "id": f"{SHOP}_{pid}",
                    "name": name,
                    "price": price_str,
                    "shop": SHOP,
                    "url": url_prod,
                    "image": image_url,
                    "stock": item.get("totalStockAvailable", ""),
                    "available": available,
                    "set_number": set_number,
                })

            # Stop if page had fewer products (last page)
            if len(page_products) < 50:
                break

    # Price comparison — uses pre-cached promoklocki.pl prices (refreshed every 4h by price_cache.py)
    # No FlareSolverr at scan time! Instant comparison from JSON cache.
    # Matching: klockoradar sitemap (name → set number), Price: promoklocki (from cache)
    if products:
        try:
            from price_cache import get_cached_price
            from price_compare import match_set_number, format_price_comparison as _fmt, PROMOKLOCKI_BASE

            # Load sitemap from DISK CACHE (built by price_cache.py every 4h)
            # Falls back to empty dict if file not found (no network fetch during scan!)
            sitemap = {}
            sitemap_cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sitemap_cache.json")
            try:
                if os.path.exists(sitemap_cache_file):
                    with open(sitemap_cache_file, "r") as f:
                        sitemap = json.load(f)
                    if sitemap:
                        print(f"[LIMANGO] Sitemap from cache: {len(sitemap)} sets")
                else:
                    print("[LIMANGO] WARNING: No sitemap_cache.json — run price_cache.py first")
            except Exception as e:
                print(f"[LIMANGO] Sitemap cache read error: {e}")

            matched_count = 0
            for p in products:
                if not p.get('available'):
                    continue
                price_val = 0
                if p['price']:
                    try:
                        price_val = float(p['price'].replace(' zl', '').replace(',', '.'))
                    except:
                        continue
                if price_val <= 0:
                    continue

                # Match: exact 5-digit number from name OR fuzzy match via klockoradar sitemap
                set_num = p.get('set_number')
                if not set_num and sitemap:
                    set_num = match_set_number(p['name'], sitemap)
                if not set_num:
                    continue

                # Read from cache (instant!)
                cached = get_cached_price(set_num)
                if not cached:
                    continue

                lowest = cached["lowest_price"]
                diff = price_val - lowest
                pct = (diff / lowest) * 100 if lowest > 0 else 0
                comp = {
                    "set_number": set_num,
                    "lowest_price": lowest,
                    "shop": "promoklocki.pl",
                    "shop_url": cached.get("promoklocki_url", f"{PROMOKLOCKI_BASE}/{set_num}"),
                    "offer_count": 0,
                    "promoklocki_url": f"{PROMOKLOCKI_BASE}/{set_num}",
                    "source": "promoklocki.pl",
                    "difference": round(diff, 2),
                    "percentage": round(pct, 1),
                    "is_cheaper": diff < 0,
                }
                p['price_compare'] = _fmt(comp)
                p['set_number'] = set_num
                p['promoklocki_url'] = f"{PROMOKLOCKI_BASE}/{set_num}"
                matched_count += 1

            if matched_count:
                print(f"[LIMANGO] Price matched: {matched_count}/{len([p for p in products if p.get('available')])} available products")
        except Exception as e:
            print(f"[LIMANGO] Price compare error: {e}")

    print(f"[LIMANGO] {len(products)} klocki LEGO (6 stron)")
    return products


if __name__ == "__main__":
    import time
    start = time.time()
    prods = asyncio.run(get_products())
    elapsed = time.time() - start
    avail = [p for p in prods if p["available"]]
    print(f"\nTotal: {len(prods)}, Available: {len(avail)}, Time: {elapsed:.1f}s")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:65]} | {p['price']} | {p['url']}")
