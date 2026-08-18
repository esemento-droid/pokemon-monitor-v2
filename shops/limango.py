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

import aiohttp

# Price comparison
import sys
sys.path.insert(0, '/opt/pokemon-monitor-v2')
try:
    from price_compare import get_price_comparison, format_price_comparison
    HAS_PRICE_COMPARE = True
except ImportError:
    HAS_PRICE_COMPARE = False

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
    # Method 1: subCategoryName (most reliable)
    cat = (product.get("subCategoryName") or "").lower().strip()
    if cat and any(lc in cat for lc in LEGO_SET_CATEGORIES):
        return True
    # Method 2: isOneSizeProduct = True (klocki mają "onesize", ubrania mają rozmiary)
    if product.get("isOneSizeProduct"):
        # Double check: treePath must have toy/klocki keywords
        for path in product.get("treePaths", []):
            if any(kw in path.lower() for kw in TOY_PATH_KEYWORDS):
                return True
    # Method 3: name contains set number pattern (5 digits)
    name = product.get("name", "")
    if re.search(r'\b\d{5}\b', name):
        # Has 5-digit number AND treePath is toy-related
        for path in product.get("treePaths", []):
            if any(kw in path.lower() for kw in TOY_PATH_KEYWORDS):
                return True
    # Reject: clothing with LEGO branding (bokserki, kurtki, piżamy etc.)
    clothing_keywords = ["bokser", "kurtk", "spodni", "bluza", "piżam", "skarpet",
                         "czapk", "szalik", "t-shirt", "koszulk", "dress"]
    name_lower = name.lower()
    if any(kw in name_lower for kw in clothing_keywords):
        return False
    return False


def _build_product_url(product_id, golden_product_id=None):
    """Build limango product URL. Uses goldenProductId for new URL format."""
    if golden_product_id:
        return f"{BASE}/p/{golden_product_id}"
    numeric_id = product_id.split("_")[-1] if "_" in product_id else product_id
    return f"{BASE}/shop/lego?productId={numeric_id}"


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

                # Available if has variant with price, "zarezerwowany" = not available
                available = bool(variant and price_amount and price_amount > 0)

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
    if products:
        try:
            from price_cache import get_cached_price
            from price_compare import _load_sitemap, match_set_number, format_price_comparison as _fmt, PROMOKLOCKI_BASE, HEADERS as PC_HEADERS

            # Load sitemap for fuzzy matching (products without set number in name)
            sitemap = None
            try:
                async with aiohttp.ClientSession(headers=PC_HEADERS) as pc_session:
                    sitemap = await _load_sitemap(pc_session)
            except Exception:
                pass

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

                # Get set number: from name or fuzzy match
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
                    "klockoradar_url": f"https://klockoradar.pl/sets/{set_num}",
                    "promoklocki_url": f"{PROMOKLOCKI_BASE}/{set_num}",
                    "source": "promoklocki.pl",
                    "difference": round(diff, 2),
                    "percentage": round(pct, 1),
                    "is_cheaper": diff < 0,
                }
                p['price_compare'] = _fmt(comp)
                p['set_number'] = set_num
                p['klockoradar_url'] = f"https://klockoradar.pl/sets/{set_num}"
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
