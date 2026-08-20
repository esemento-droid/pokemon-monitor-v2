"""
Scraper: battlestash.pl
Platform: WooCommerce Store API (behind Cloudflare)
Method: FlareSolverr → /wp-json/wc/store/v1/products
Category: 712 (Pokemon TCG)
"""
import aiohttp
import asyncio
import json
import html as html_lib

SHOP = "battlestash.pl"
SCAN_TIMEOUT = 180  # Extended: CF solver needs 55s+ for Turnstile
API_URL = "https://battlestash.pl/wp-json/wc/store/v1/products"
CATEGORY_ID = 712
PER_PAGE = 100
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
    """Fetch URL via FlareSolverr to bypass Cloudflare."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
            async with session.post(
                FLARESOLVERR_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=70),
            ) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                if data.get("status") == "ok":
                    return data.get("solution", {}).get("response", "")
    except Exception as e:
        print(f"[battlestash] FlareSolverr error: {e}")
    return ""


async def get_products():
    products = []
    seen = set()

    for page in range(1, MAX_PAGES + 1):
        url = f"{API_URL}?category={CATEGORY_ID}&per_page={PER_PAGE}&page={page}"
        raw = await fetch_flaresolverr(url)
        if not raw:
            break

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # FlareSolverr might return HTML wrapper - try to extract JSON
            try:
                # Sometimes response is wrapped in <pre> tags
                import re
                json_m = re.search(r'[\[{].*[}\]]', raw, re.DOTALL)
                if json_m:
                    data = json.loads(json_m.group(0))
                else:
                    break
            except:
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
            # Clean up any remaining HTML entities
            name = name.replace("&#8211;", "–").replace("&#8217;", "'").replace("&amp;", "&")

            name_low = name.lower()
            if any(ex in name_low for ex in EXCLUDE):
                continue

            # Price (minor units)
            prices = item.get("prices", {})
            price_raw = prices.get("price", "0")
            try:
                price_val = int(price_raw) / 100
                price = f"{price_val:.2f} PLN"
            except (ValueError, TypeError):
                price = "brak"

            available = item.get("is_in_stock", False)
            permalink = item.get("permalink", "")
            images = item.get("images", [])
            image = images[0].get("src", "") if images else ""

            products.append({
                "id": f"battlestash_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": permalink,
                "image": image,
                "stock": 1 if available else 0,
                "available": available,
            })

        if len(data) < PER_PAGE:
            break

    print(f"[BATTLESTASH] {len(products)} produktow")
    return products
