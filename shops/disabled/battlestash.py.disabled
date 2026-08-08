"""
Scraper: battlestash.pl
Silnik: WooCommerce Store API
Metoda: aiohttp (API omija Cloudflare)
Kategoria: 712 (Pokemon TCG)
"""
import asyncio
import logging
import aiohttp
import html

logger = logging.getLogger(__name__)
SHOP = "battlestash.pl"
API_URL = "https://battlestash.pl/wp-json/wc/store/v1/products"
CATEGORY_ID = 712
PER_PAGE = 100
MAX_PAGES = 3


async def get_products():
    products = []
    try:
        async with aiohttp.ClientSession() as session:
            for page in range(1, MAX_PAGES + 1):
                url = f"{API_URL}?category={CATEGORY_ID}&per_page={PER_PAGE}&page={page}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        logger.error(f"[battlestash] HTTP {resp.status}")
                        break
                    data = await resp.json()
                if not data:
                    break
                for p in data:
                    pid = str(p.get("id", ""))
                    name = html.unescape(p.get("name", ""))
                    link = p.get("permalink", "")
                    # Dostepnosc
                    available = p.get("is_in_stock", False)
                    # Cena (w groszach)
                    prices = p.get("prices", {})
                    price_raw = prices.get("price", "0")
                    try:
                        price = f"{int(price_raw) / 100:.2f} PLN"
                    except (ValueError, TypeError):
                        price = "brak"
                    # Obrazek
                    images = p.get("images", [])
                    image = images[0].get("src", "") if images else ""
                    products.append({
                        "id": f"battlestash_{pid}",
                        "name": name,
                        "price": price,
                        "shop": SHOP,
                        "url": link,
                        "image": image,
                        "stock": 1 if available else 0,
                        "available": available,
                    })
                if len(data) < PER_PAGE:
                    break
    except Exception as e:
        logger.error(f"[battlestash] Error: {e}")
    logger.info(f"[battlestash] {len(products)} produktow ({sum(1 for p in products if p['available'])} avail)")
    return products
