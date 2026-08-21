"""
Scraper: tcg-zielona.pl
Platform: WooCommerce Store API behind Cloudflare
Method: FlareSolverr → /wp-json/wc/store/v1/products?category=pokemon-tcg
Category: 122 (Pokémon TCG)
Note: API endpoint IS behind CF from datacenter IPs — need FlareSolverr bypass
"""
import aiohttp
import asyncio
import json
import html as html_lib

SHOP = "tcg-zielona"
SCAN_TIMEOUT = 180  # CF solver: semaphore queue + 55s solve per page × 3 pages
API_URL = "https://tcg-zielona.pl/wp-json/wc/store/v1/products"
CATEGORY = "pokemon-tcg"
PER_PAGE = 100
MAX_PAGES = 3
FLARESOLVERR_URL = "http://localhost:8191/v1"

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

    async with aiohttp.ClientSession() as session:
        for page in range(1, MAX_PAGES + 1):
            url = f"{API_URL}?per_page={PER_PAGE}&category={CATEGORY}&page={page}"

            # Use FlareSolverr to bypass Cloudflare
            try:
                payload = {"cmd": "request.get", "url": url, "maxTimeout": 55000}
                async with session.post(
                    FLARESOLVERR_URL, json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        print(f"[tcg-zielona] FlareSolverr HTTP {resp.status} page {page}")
                        break
                    result = await resp.json()
                    if result.get("status") != "ok":
                        print(f"[tcg-zielona] FlareSolverr failed page {page}: {result.get('message', '')}")
                        break
                    raw_response = result.get("solution", {}).get("response", "")
            except Exception as e:
                print(f"[tcg-zielona] FlareSolverr error page {page}: {e}")
                break

            if not raw_response:
                break

            # Parse JSON from FlareSolverr response
            try:
                # FlareSolverr wraps response in HTML sometimes for API calls
                # Try direct JSON parse first
                data = json.loads(raw_response)
            except (json.JSONDecodeError, TypeError):
                # If wrapped in HTML (e.g. <pre> tag), extract JSON
                import re
                json_match = re.search(r'[\[\{].*[\]\}]', raw_response, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        print(f"[tcg-zielona] Cannot parse JSON page {page}")
                        break
                else:
                    print(f"[tcg-zielona] No JSON in response page {page}, len={len(raw_response)}")
                    break

            if not data or not isinstance(data, list):
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
