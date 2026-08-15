"""
Scraper: zgrani.pl
Silnik: aiohttp + BeautifulSoup (IdoSell)
Autor: aug 2 2026
"""
import asyncio
import logging
import re
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SHOP = "zgrani.pl"
BASE_URL = "https://zgrani.pl"
CATEGORY_URLS = ["/pl/menu/pokemon-208", "/pl/menu/pokemon-208?counter=1"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE_KEYWORDS = [
    "oversize", "talia", "battle deck", "szczoteczk", "signal", "figurk", "znacznik", "marker",
    "album", "sleeves", "koszulk", "pro-binder", "toploader", "klaser", "segregator", "pudelko",
    "pudełko", "deck box", "pluszak", "maskotka", "plakat", "torba", "pokeball deck", "outlet",
    "interaktywn", "gra ", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "alcove", "lorcana", "one piece",
    "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figure set"
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
                for item in soup.select("div.product[data-product_id]"):
                    pid = item.get("data-product_id", "")
                    if not pid or pid in seen_ids:
                        continue
                    seen_ids.add(pid)

                    name_el = item.select_one("a.product__name")
                    if not name_el:
                        continue
                    name = name_el.text.strip()

                    if any(kw in name.lower() for kw in EXCLUDE_KEYWORDS):
                        continue

                    href = name_el.get("href", "")
                    if href and not href.startswith("http"):
                        href = BASE_URL + href

                    price_el = item.select_one("strong.price")
                    price = _format_price(price_el.get_text(strip=True) if price_el else "")

                    img_el = item.select_one("img")
                    image = ""
                    if img_el:
                        image = img_el.get("src") or img_el.get("data-src") or ""
                        if image and not image.startswith("http"):
                            image = BASE_URL + image

                    products.append({
                        "id": f"zgrani_{pid}",
                        "name": name,
                        "price": price,
                        "shop": SHOP,
                        "url": href,
                        "image": image,
                        "stock": 1,
                        "available": True,
                    })
    except Exception as e:
        logger.error(f"[zgrani] Error: {e}")

    print(f"[ZGRANI] {len(products)} produktow")
    return products

def _format_price(price_raw):
    if not price_raw:
        return "brak"
    m = re.search(r"(\d[\d\s]*[,.]\d+)", price_raw)
    if m:
        p = m.group(1).replace(" ", "").replace(",", ".")
        return f"{float(p):.2f} PLN"
    return "brak"
