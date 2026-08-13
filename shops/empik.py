"""Empik scraper - FlareSolverr (CF bypass), no browser needed."""
import asyncio
import re
import logging
import aiohttp

log = logging.getLogger("monitor")

CATEGORY_URLS = [
    "https://www.empik.com/bohater/pokemon/karty-kolekcjonerskie",
    "https://www.empik.com/strefa/karty-pokemon",
    "https://www.empik.com/szukaj/produkt?q=pokemon+tcg&searchCategory=all&sort=publishDesc",
    "https://www.empik.com/szukaj/produkt?q=pokemon+tin&searchCategory=all&sort=publishDesc",
    "https://www.empik.com/szukaj/produkt?q=pokemon+booster&searchCategory=all&sort=publishDesc",
    "https://www.empik.com/szukaj/produkt?q=pokemon+collection&searchCategory=all&sort=publishDesc",
    "https://www.empik.com/szukaj/produkt?q=pokemon+elite+trainer&searchCategory=all&sort=publishDesc",
]

# Search queries: fewer pages (they return 150+ products per page)
SEARCH_MAX_PAGES = 2

EXCLUDE_KW = [
    "korea", "korean", "kore", "kor ", " kor",
    "japan", "japanese", "japo\u0144sk", "jap",
    "chn", "chi\u0144sk", "chinese", "china",
    " de ", "deutsch", "german", "niemieck", "kollektion", "kollection", "tedesco",
    "espa\u0144ol", "castellano", "hiszpa\u0144sk", " spa ",
    "deck", "battle deck", "league battle", "talia",
    "magazyn", "trenuj ze mn",
    "mata do gry", "playmat", "playmaty",
    "koszulki na karty", "sleeve", "battle box",
    "minimalistyczna mata", "ultra pro", "ultra-pro",
    "album", "segregator", "portfolio",
    "gem pack", "single", "karta ",
    "akrylowe", "akrylowy", "acrylic",
    "torba", "plecak",
    "plakat", "poster",
    "pin collection", "coin",
    "puzzle", "figurka", "figurk",
    "koc ", "klocki", "construx", "mega construx",
    "ninja spinner",
    "terastal gathering", "battle partners",
    "paradigm trigger",
    "battle academy",
    "planet wow",
    " up:", "up:",
    "pokopia",
    "wizytownik",
]

FS_URL = "http://localhost:8191/v1"
FS_SESSION = "empik_scraper"
MAX_PAGES = 7
PER_PAGE = 30


async def _fetch_page(session, url):
    """Fetch a page via FlareSolverr, return HTML or None."""
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": 30000,
        "session": FS_SESSION,
    }
    try:
        async with session.post(FS_URL, json=payload, timeout=aiohttp.ClientTimeout(total=35)) as resp:
            data = await resp.json()
            if data.get("status") == "ok":
                return data["solution"]["response"]
            else:
                log.warning("[empik] FlareSolverr status=%s for %s", data.get("status"), url)
    except Exception as e:
        log.error("[empik] FlareSolverr error: %s", e)
    return None


def _parse_products(html):
    """Parse products from Empik HTML using regex."""
    products = []
    blocks = re.split(r'class="[^"]*search-list-item[^"]*"', html)

    for block in blocks[1:]:
        link_match = re.search(r'href="([^"]*,p(\d+)[^"]*)"', block)
        if not link_match:
            continue
        href = link_match.group(1)
        pid = link_match.group(2)

        # Title
        name = ""
        title_match = re.search(
            r'class="[^"]*product-title[^"]*"[^>]*>(.*?)</(?:h2|h3|div)', block, re.DOTALL
        )
        if title_match:
            name = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
        if not name:
            title_match = re.search(r'title="([^"]+)"', block)
            if title_match:
                name = title_match.group(1).strip()

        # Price
        price = ""
        price_match = re.search(r'data-product-price="([\d.]+)"', block)
        if price_match:
            price = price_match.group(1)
        if not price:
            price_match = re.search(r'itemprop="price"\s+content="([\d.]+)"', block)
            if price_match:
                price = price_match.group(1)
        if not price:
            price_match = re.search(r'data-price="([\d.]+)"', block)
            if price_match:
                price = price_match.group(1)
        if not price:
            price_match = re.search(r'(\d+,\d{2})\s*z[łl]', block)
            if price_match:
                price = price_match.group(1).replace(',', '.')
        if not price:
            price_match = re.search(r'(\d[\d\s]*\d),(\d{2})', block)
            if price_match:
                price = price_match.group(1).replace(' ', '') + '.' + price_match.group(2)

        # Image
        img = ""
        img_match = re.search(r'<img[^>]+src="(https://ecsmedia\.pl/[^"]+)"', block)
        if img_match:
            img = img_match.group(1)
        if not img:
            img_match = re.search(r'<img[^>]+src="(https://[^"]*\.(?:jpg|jpeg|png|webp)[^"]*)"', block, re.IGNORECASE)
            if img_match:
                img = img_match.group(1)
        if not img:
            img_match = re.search(r'<img[^>]+data-src="(https://[^"]+)"', block)
            if img_match:
                img = img_match.group(1)

        # Marketplace check
        mp_match = re.search(r'mpShopId=(\d+)', href)
        shop_id = mp_match.group(1) if mp_match else "0"

        # Merchant name from data attribute (fallback)
        merchant = "empik"
        merchant_match = re.search(r'data-merchant-name="([^"]+)"', block)
        if merchant_match:
            merchant = merchant_match.group(1).lower()

        products.append({
            "pid": pid,
            "name": name,
            "price": price,
            "shop_id": shop_id,
            "merchant": merchant,
            "url": href,
            "img": img,
        })

    return products


def _is_excluded(name):
    """Check if product name matches any exclude keyword."""
    name_lower = name.lower()
    for kw in EXCLUDE_KW:
        if kw in name_lower:
            return True
    # Suffix checks
    name_stripped = name.rstrip()
    if name_stripped.endswith(" DE") or name_stripped.endswith("-DE") or "(DE)" in name:
        return True
    if name_stripped.endswith(" KOR") or name_stripped.endswith(" SPA"):
        return True
    if name_stripped.endswith(" JPN") or name_stripped.endswith(" JAP"):
        return True
    return False


async def get_products():
    """Main scraper entry point. Returns list of product dicts."""
    products = []
    seen_pids = set()

    async with aiohttp.ClientSession() as session:
        for cat_url in CATEGORY_URLS:
            # Search queries get fewer pages (they return more products per page)
            is_search = "szukaj" in cat_url
            max_pg = SEARCH_MAX_PAGES if is_search else MAX_PAGES
            separator = "&" if "?" in cat_url else "?"

            for pg in range(1, max_pg + 1):
                url = cat_url if pg == 1 else f"{cat_url}{separator}start={(pg - 1) * PER_PAGE}"

                html = await _fetch_page(session, url)
                if not html:
                    break

                items = _parse_products(html)
                if not items:
                    break

                for item in items:
                    pid = item["pid"]
                    if pid in seen_pids:
                        continue
                    seen_pids.add(pid)

                    name = item["name"]
                    if _is_excluded(name):
                        continue

                    price_val = item["price"]
                    price_str = f"{price_val} zl" if price_val else "brak"
                    url_product = item["url"]
                    if url_product and not url_product.startswith("http"):
                        url_product = "https://www.empik.com" + url_product

                    shop_id = item["shop_id"]
                    stock_label = "empik" if shop_id == "0" else f"marketplace_{shop_id}"

                    products.append({
                        "id": f"empik_{pid}",
                        "name": name,
                        "price": price_str,
                        "shop": "empik",
                        "url": url_product,
                        "image": item.get("img", ""),
                        "stock": stock_label,
                        "available": bool(price_val),
                    })

                if len(items) < 15:
                    break

    log.info("[EMPIK] %d produktow", len(products))
    return products
