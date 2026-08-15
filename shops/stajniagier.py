"""
Scraper: stajnia-gier.pl
Silnik: aiohttp + BeautifulSoup (PrestaShop)
Autor: aug 2 2026
"""
import asyncio
import logging
import re
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SHOP = "stajnia-gier.pl"
BASE_URL = "https://stajnia-gier.pl"
CATEGORY_URLS = ["/178-pokemon-tcg", "/178-pokemon-tcg?page=2"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE_KEYWORDS = [
    "sleeve", "koszulk", "toploader", "album", "binder", "klaser", "segregator", "ultra pro",
    "riftbound", "yu-gi-oh", "yu gi oh", "magic the gathering", "mtg ", "one piece",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra-pro", "playmat", "portfolio", "deck box", "alcove", "lorcana", "digimon", "naruto",
    "star wars", "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz",
    "force of will", "zeszyt", "puzzle", "figurk", "figure set"
]

async def get_products():
    products = []
    seen_ids = set()
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            for cat_url in CATEGORY_URLS:
                url = BASE_URL + cat_url
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()

                soup = BeautifulSoup(html, "lxml")
                for item in soup.select("article.product-miniature"):
                    pid = item.get("data-id-product", "")
                    if not pid or pid in seen_ids:
                        continue

                    name_el = item.select_one(".product-title a, h3 a")
                    if not name_el:
                        continue
                    name = name_el.get_text(strip=True)

                    if not name or len(name) < 5:
                        continue
                    if any(kw in name.lower() for kw in EXCLUDE_KEYWORDS):
                        continue

                    href = name_el.get("href", "")
                    if "/pokemon-tcg/" not in href:
                        continue

                    seen_ids.add(pid)

                    price_el = item.select_one(".price, [class*=price]")
                    price = _format_price(price_el.get_text(strip=True) if price_el else "")

                    avail_el = item.select_one(".product-available")
                    unavail_el = item.select_one(".product-unavailable")
                    available = avail_el is not None and unavail_el is None

                    img_el = item.select_one("img")
                    image = ""
                    if img_el:
                        image = img_el.get("data-src") or img_el.get("src") or ""
                        if image and not image.startswith("http"):
                            image = BASE_URL + image

                    products.append({
                        "id": f"stajniagier_{pid}",
                        "name": name,
                        "price": price,
                        "shop": SHOP,
                        "url": href,
                        "image": image,
                        "stock": 1 if available else 0,
                        "available": available,
                    })
    except Exception as e:
        logger.error(f"[stajniagier] Error: {e}")

    print(f"[STAJNIAGIER] {len(products)} produktow")
    return products

def _format_price(price_raw):
    if not price_raw:
        return "brak"
    m = re.search(r"(\d[\d\s]*[,.]\d+)", price_raw)
    if m:
        p = m.group(1).replace(" ", "").replace(",", ".")
        return f"{float(p):.2f} PLN"
    return "brak"
