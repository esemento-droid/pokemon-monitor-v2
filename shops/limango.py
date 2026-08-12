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
    cat = (product.get("subCategoryName") or "").lower().strip()
    if cat and any(lc in cat for lc in LEGO_SET_CATEGORIES):
        return True
    for path in product.get("treePaths", []):
        if any(kw in path.lower() for kw in TOY_PATH_KEYWORDS):
            return True
    return False


def _build_product_url(product_id):
    numeric_id = product_id.split("_")[-1] if "_" in product_id else product_id
    return f"{BASE}/p/{numeric_id}"


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

                raw_img_url = images.get("default", {}).get("url", "")
                name = _extract_name_from_image_url(raw_img_url)
                if not name:
                    name = item.get("subCategoryName") or f"LEGO Set {pid}"

                url_prod = _build_product_url(pid)

                # Available if has variant with price, "zarezerwowany" = not available
                available = bool(variant and price_amount and price_amount > 0)

                products.append({
                    "id": f"{SHOP}_{pid}",
                    "name": name,
                    "price": price_str,
                    "shop": SHOP,
                    "url": url_prod,
                    "image": image_url,
                    "stock": "",
                    "available": available,
                })

            # Stop if page had fewer products (last page)
            if len(page_products) < 50:
                break

    # Price comparison — klockoradar only (fast, no CF)
    # FlareSolverr/promoklocki is too slow for batch (30s per product)
    if HAS_PRICE_COMPARE and products:
        try:
            from price_compare import _load_sitemap, match_set_number, _fetch_klockoradar_price, format_price_comparison as _fmt, HEADERS as PC_HEADERS
            async with aiohttp.ClientSession(headers=PC_HEADERS) as pc_session:
                # Pre-load sitemap once
                sitemap = await _load_sitemap(pc_session)
                if sitemap:
                    for p in products:
                        if not p.get('available'):
                            continue
                        price_val = 0
                        if p['price']:
                            try:
                                price_val = float(p['price'].replace(' zl','').replace(',','.'))
                            except:
                                continue
                        if price_val <= 0:
                            continue
                        set_num = match_set_number(p['name'], sitemap)
                        if not set_num:
                            continue
                        price_data = await _fetch_klockoradar_price(pc_session, set_num)
                        if not price_data:
                            continue
                        lowest = price_data["lowest_price"]
                        diff = price_val - lowest
                        pct = (diff / lowest) * 100 if lowest > 0 else 0
                        comp = {
                            "set_number": set_num,
                            "lowest_price": lowest,
                            "shop": price_data.get("shop", ""),
                            "shop_url": price_data.get("shop_url", ""),
                            "offer_count": price_data.get("offer_count", 0),
                            "klockoradar_url": price_data.get("klockoradar_url", ""),
                            "promoklocki_url": f"https://promoklocki.pl/{set_num}",
                            "source": "klockoradar.pl",
                            "difference": round(diff, 2),
                            "percentage": round(pct, 1),
                            "is_cheaper": diff < 0,
                        }
                        p['price_compare'] = _fmt(comp)
                        p['set_number'] = set_num
                        p['klockoradar_url'] = price_data.get('klockoradar_url', '')
        except Exception as e:
            print(f"[LIMANGO] Price compare error: {e}")
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
