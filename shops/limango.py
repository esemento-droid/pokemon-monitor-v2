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

# Price comparison — live from klockoradar (no cache needed)
try:
    from price_compare import match_set_number, format_price_comparison as _fmt, PROMOKLOCKI_BASE
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
    name = product.get("name", "").lower()
    
    # Reject clothing/accessories with LEGO branding
    clothing_keywords = ["bokser", "kurtk", "spodni", "bluza", "piżam", "skarpet",
                         "czapk", "szalik", "t-shirt", "koszulk", "dress", "leggin",
                         "bluzi", "polar", "buty", "sandał", "kapel", "rękawic",
                         "plecak", "tornister", "torba", "worek", "piórnik",
                         "płytka", "płytk", "baseplate",
                         "pojemnik", "lunch", "bidon", "butelk", "śniadani",
                         "zestaw na", "częściowy zestaw", "lampk", "latark",
                         "kubek", "kubk", "haczyk", "wieszak", "półka", "półk",
                         "organizer", "ramka", "zegar",
                         "regał", "regal", "szuflad", "szafk", "stolik",
                         "biurk", "komoda", "łóżk", "łóżeczk", "dywan",
                         "naklejk", "tapeta", "zasłon", "firanka", "pościel",
                         "ręcznik", "koc ", "poduszk", "mata piankowa"]
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
                set_match = re.search(r'\b(\d{4,6})\b', name)
                if set_match:
                    num = set_match.group(1)
                    # Prefer 5-digit (most LEGO sets), accept 4-digit >= 1000
                    if len(num) == 5 or len(num) == 6 or (len(num) == 4 and int(num) >= 1000):
                        set_number = num

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

    # Price comparison — DISABLED (2026-08-21: OVH abuse report from klockoradar.pl owner)
    # Was generating 1200+ req/h, bursts of 14 req/s. Re-enable ONLY with proper rate limiting.
    if False and products and HAS_PRICE_COMPARE:
        try:
            # Load sitemap for fuzzy matching (name → set_number)
            # Try disk cache first, fallback to live fetch
            sitemap = {}
            sitemap_cache_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sitemap_cache.json")
            try:
                if os.path.exists(sitemap_cache_file):
                    with open(sitemap_cache_file, "r") as f:
                        sitemap = json.load(f)
            except Exception:
                pass

            if not sitemap:
                # Live fetch sitemap (first run only, ~5s)
                from price_compare import _load_sitemap, HEADERS as PC_HEADERS
                async with aiohttp.ClientSession(headers=PC_HEADERS) as _s:
                    sitemap = await _load_sitemap(_s)
                # Save for next time
                if sitemap:
                    try:
                        with open(sitemap_cache_file, "w") as f:
                            json.dump(sitemap, f, ensure_ascii=False)
                    except Exception:
                        pass

            if not sitemap:
                print("[LIMANGO] WARNING: No sitemap for price compare")
            else:
                matched_count = 0
                available_products = [p for p in products if p.get('available')]

                # Fetch klockoradar prices in parallel (all available products at once)
                async def _fetch_kr_price(session, set_num):
                    """Fetch lowest price from klockoradar for one set."""
                    url = f"https://klockoradar.pl/sets/{set_num}"
                    try:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status != 200:
                                return None
                            html = await resp.text()
                        for ld_raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL):
                            try:
                                data = json.loads(ld_raw)
                            except Exception:
                                continue
                            if data.get("@type") != "Product":
                                continue
                            offers = data.get("offers", {})
                            if offers.get("@type") == "AggregateOffer" and offers.get("lowPrice"):
                                low = float(offers["lowPrice"])
                                shop_name = ""
                                ind = offers.get("offers", [])
                                if ind:
                                    try:
                                        cheapest = min(ind, key=lambda o: float(o.get("price", 99999)))
                                        shop_name = cheapest.get("seller", {}).get("name", "")
                                    except Exception:
                                        pass
                                kr_name = data.get("name", "")
                                return {"lowest_price": low, "shop": shop_name, "klockoradar_url": url, "kr_name": kr_name}
                    except Exception:
                        pass
                    return None

                # Match set numbers first
                product_sets = []  # [(product, set_nums, price_val)] — set_nums can be str or list
                for p in available_products:
                    price_val = 0
                    if p['price']:
                        try:
                            price_val = float(p['price'].replace(' zl', '').replace(',', '.'))
                        except Exception:
                            continue
                    if price_val <= 0:
                        continue
                    set_num = p.get('set_number')
                    if not set_num:
                        set_num = match_set_number(p['name'], sitemap)
                    if set_num:
                        product_sets.append((p, set_num, price_val))

                # Parallel fetch (max 5 concurrent, polite)
                if product_sets:
                    sem = asyncio.Semaphore(5)
                    async def _bounded_fetch(session, set_num):
                        async with sem:
                            result = await _fetch_kr_price(session, set_num)
                            await asyncio.sleep(0.2)
                            return result

                    # Collect all unique set numbers (flatten lists)
                    all_set_nums = set()
                    for _, set_num, _ in product_sets:
                        if isinstance(set_num, list):
                            all_set_nums.update(set_num)
                        else:
                            all_set_nums.add(set_num)

                    unique_sets = list(all_set_nums)
                    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
                        tasks = [_bounded_fetch(session, sn) for sn in unique_sets]
                        results = await asyncio.gather(*tasks)

                    # Map results
                    price_map = {}
                    for sn, result in zip(unique_sets, results):
                        if result:
                            price_map[sn] = result

                    # Apply to products
                    for p, set_num, price_val in product_sets:
                        # Single match
                        if isinstance(set_num, str):
                            kr_data = price_map.get(set_num)
                            if not kr_data:
                                continue
                            lowest = kr_data["lowest_price"]
                            diff = price_val - lowest
                            pct = (diff / lowest) * 100 if lowest > 0 else 0
                            comp = {
                                "set_number": set_num,
                                "lowest_price": lowest,
                                "shop": kr_data.get("shop", ""),
                                "difference": round(diff, 2),
                                "percentage": round(pct, 1),
                                "is_cheaper": diff < 0,
                            }
                            p['price_compare'] = _fmt(comp)
                            p['set_number'] = set_num
                            p['promoklocki_url'] = f"{PROMOKLOCKI_BASE}/{set_num}"
                            p['klockoradar_url'] = kr_data.get("klockoradar_url", f"https://klockoradar.pl/sets/{set_num}")
                            matched_count += 1

                        # Multi match (ambiguous) — show all candidates
                        elif isinstance(set_num, list):
                            lines = []
                            first_set = None
                            for sn in set_num:
                                kr_data = price_map.get(sn)
                                if not kr_data:
                                    continue
                                if not first_set:
                                    first_set = sn
                                lowest = kr_data["lowest_price"]
                                diff = price_val - lowest
                                kr_name = kr_data.get("kr_name", f"Set #{sn}")
                                shop = kr_data.get("shop", "")
                                if diff > 0:
                                    lines.append(f"**#{sn}** {kr_name}: {lowest:.2f} zł ({shop}) — drożej o {diff:.2f} zł")
                                elif diff < 0:
                                    lines.append(f"**#{sn}** {kr_name}: {lowest:.2f} zł ({shop}) — TANIEJ o {abs(diff):.2f} zł")
                                else:
                                    lines.append(f"**#{sn}** {kr_name}: {lowest:.2f} zł ({shop}) — taka sama")
                            if lines:
                                p['price_compare'] = "⚠️ Kilka pasujących setów:\n" + "\n".join(lines)
                                p['set_number'] = first_set
                                p['promoklocki_url'] = f"{PROMOKLOCKI_BASE}/{first_set}"
                                p['klockoradar_url'] = f"https://klockoradar.pl/sets/{first_set}"
                                matched_count += 1

                    if matched_count:
                        print(f"[LIMANGO] Price matched: {matched_count}/{len(available_products)} available products")
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
