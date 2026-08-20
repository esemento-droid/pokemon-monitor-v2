"""
Pokebeast.pl - scraper Pokemon ENG sealed
WooCommerce Store API (v1) — fast, no browser needed.
Category ID 16 = POKEMON (ENG).
"""
import aiohttp
import logging

log = logging.getLogger("monitor")

BASE = "https://pokebeast.pl"
API = f"{BASE}/wp-json/wc/store/v1/products"
CATEGORY_ID = 16  # POKEMON (ENG)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

EXCLUDE = [
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean", "chiński", "chinese",
    "sleeves", "toploader", "pro-binder", "portfolio", "playmat", "album", "ultra pro", "ultra-pro",
    "deck box", "segregator",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "magic the gathering",
    "battle deck", "league battle", "v battle", "battle academy",
]


async def get_products():
    products = []
    seen = set()
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            page = 1
            while True:
                url = f"{API}?per_page=100&page={page}&category={CATEGORY_ID}"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), ssl=False) as resp:
                        if resp.status != 200:
                            break
                        data = await resp.json()
                except Exception as e:
                    log.warning(f"[pokebeast] API error page {page}: {e}")
                    break

                if not data:
                    break

                for item in data:
                    pid = item.get("id")
                    if not pid or pid in seen:
                        continue
                    seen.add(pid)

                    name = item.get("name", "").strip()
                    if not name:
                        continue

                    # Exclude filter
                    name_lower = name.lower()
                    if any(exc in name_lower for exc in EXCLUDE):
                        continue

                    # Price
                    prices = item.get("prices", {})
                    raw_price = prices.get("price", "0")
                    minor_unit = prices.get("currency_minor_unit", 2)
                    try:
                        price_val = int(raw_price) / (10 ** minor_unit)
                        price = f"{price_val:.2f} zl"
                    except (ValueError, TypeError):
                        price = "brak"

                    # Skip singles (<10 PLN)
                    try:
                        if price != "brak" and float(price.replace(" zl", "")) < 10:
                            continue
                    except ValueError:
                        pass

                    # URL
                    product_url = item.get("permalink", "")

                    # Image
                    images = item.get("images", [])
                    image = images[0].get("src", "") if images else ""

                    # Availability
                    available = item.get("is_in_stock", False)

                    products.append({
                        "id": f"pokebeast_{pid}",
                        "name": name,
                        "price": price,
                        "shop": "pokebeast",
                        "url": product_url,
                        "image": image,
                        "stock": 1 if available else 0,
                        "available": available,
                    })

                page += 1
                if len(data) < 100:
                    break

    except Exception as e:
        log.error(f"[pokebeast] Error: {e}")

    # First snapshot sort: OOS first, available last
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))
    print(f"[pokebeast] {len(products)} produktow")
    return products
