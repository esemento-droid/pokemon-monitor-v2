"""
Scraper: tcg-zielona.pl
Platform: WooCommerce Store API (no CF on API endpoint)
Method: aiohttp /wp-json/wc/store/v1/products?category=pokemon-tcg
Category: 122 (Pokémon TCG)
"""
import aiohttp
import asyncio
import html as html_lib

SHOP = "tcg-zielona"
API_URL = "https://tcg-zielona.pl/wp-json/wc/store/v1/products"
CATEGORY = "pokemon-tcg"
PER_PAGE = 100
MAX_PAGES = 3
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "pro-binder", "ultra pro", "ultra-pro",
    "playmat", "mata", "portfolio", "deck box", "pudełko", "bulk", "grading", "psa ",
    "one piece", "lorcana", "yu-gi-oh", "digimon", "magic the", "naruto", "star wars",
    "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz", "force of will",
    "riftbound", "dragon ball",
    "japonsk", "japońsk", "japanese", "japan", "(jp)", "korean", "koreańsk", "korea",
    "chiński", "chińsk", "chinese", "china", "(chi)", "s-chinese",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy",
    "segregator", "alcove", "zeszyt", "puzzle", "figurk", "figure set",
    "singl", "single", "lego", "monopoly",
    "wydarzen", "event", "turniej", "bilet", "wpisowe",
]


async def get_products():
    products = []
    seen = set()

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for page in range(1, MAX_PAGES + 1):
            url = f"{API_URL}?per_page={PER_PAGE}&category={CATEGORY}&page={page}"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        break
                    ct = resp.headers.get("Content-Type", "")
                    if "json" not in ct:
                        break
                    data = await resp.json()
            except Exception as e:
                print(f"[tcg-zielona] Error page {page}: {e}")
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

                # Must be Pokemon-related
                if "pokemon" not in name_low and "pokémon" not in name_low and "pok\u00e9mon" not in name_low:
                    continue

                # Exclude unwanted
                if any(ex in name_low for ex in EXCLUDE):
                    continue

                # Price (minor units, e.g. 24900 = 249.00 PLN)
                prices = item.get("prices", {})
                price_raw = prices.get("price", "0")
                try:
                    price_val = int(price_raw) / 100
                    price = f"{price_val:.2f} zl"
                except (ValueError, TypeError):
                    price = "brak"
                    price_val = 0

                # Skip singles/cheap items (< 10 PLN = not sealed)
                if 0 < price_val < 10:
                    continue

                # Availability
                available = item.get("is_in_stock", False)

                # URL
                permalink = item.get("permalink", "")

                # Image
                images = item.get("images", [])
                image = images[0].get("src", "") if images else ""

                products.append({
                    "id": f"tcgzielona_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": permalink,
                    "image": image,
                    "stock": None,
                    "available": available,
                })

            if len(data) < PER_PAGE:
                break

    print(f"[TCG-ZIELONA] {len(products)} produktow")
    return products
