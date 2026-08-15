"""
Scraper: strefakart.pl
Platform: WooCommerce Store API (no CF, direct access)
Method: aiohttp /wp-json/wc/store/v1/products
Products: ~317 Pokemon TCG sealed
"""
import aiohttp
import asyncio
import html as html_lib

SHOP = "strefakart"
API_URL = "https://strefakart.pl/wp-json/wc/store/v1/products"
PER_PAGE = 100
MAX_PAGES = 5
PROXY = "http://127.0.0.1:8888"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "pro-binder", "ultra pro", "ultra-pro",
    "playmat", "mata", "portfolio", "deck box", "pudełko", "bulk", "grading", "psa ",
    "one piece", "lorcana", "yu-gi-oh", "digimon", "magic the", "naruto", "star wars",
    "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz", "force of will",
    "riftbound",
    "japonsk", "japońsk", "japanese", "japan", "(jp)", "korean", "koreańsk", "korea",
    "chiński", "chińsk", "chinese", "china", "(chi)", "s-chinese",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy",
    "segregator", "alcove", "zeszyt", "puzzle", "figurk", "figure set",
    "singl", "single",
]


async def get_products():
    products = []
    seen = set()

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for page in range(1, MAX_PAGES + 1):
            url = f"{API_URL}?per_page={PER_PAGE}&search=pokemon&page={page}"
            try:
                async with session.get(url, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        break
                    ct = resp.headers.get("Content-Type", "")
                    if "json" not in ct:
                        print(f"[strefakart] Not JSON on page {page}, trying without proxy...")
                        # Fallback: try without proxy
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp2:
                            if resp2.status != 200 or "json" not in resp2.headers.get("Content-Type", ""):
                                break
                            data = await resp2.json()
                    else:
                        data = await resp.json()
            except Exception as e:
                print(f"[strefakart] Error page {page}: {e}")
                break

            if not data:
                break

            for item in data:
                pid = str(item.get("id", ""))
                if not pid or pid in seen:
                    continue
                seen.add(pid)

                name = html_lib.unescape(item.get("name", ""))
                if not name:
                    continue

                name_low = name.lower()
                if any(ex in name_low for ex in EXCLUDE):
                    continue

                # Price (in minor units, e.g. 13900 = 139.00 PLN)
                prices = item.get("prices", {})
                price_raw = prices.get("price", "0")
                try:
                    price_val = int(price_raw) / 100
                    price = f"{price_val:.2f} zl"
                except (ValueError, TypeError):
                    price = "brak"

                # Availability
                available = item.get("is_in_stock", False)

                # URL
                permalink = item.get("permalink", "")

                # Image
                images = item.get("images", [])
                image = images[0].get("src", "") if images else ""

                products.append({
                    "id": f"strefakart_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": permalink,
                    "image": image,
                    "stock": None,
                    "available": available,
                })

    print(f"[STREFAKART] {len(products)} produktow")
    return products
