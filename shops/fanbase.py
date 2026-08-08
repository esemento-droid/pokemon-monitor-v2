"""
Scraper: fanbase.pl
Silnik: wlasny
Metoda: aiohttp + BeautifulSoup
Kategoria: pmi,c48.html (Karty Pokemon), 2 strony
Dostepnosc: 'Do koszyka' w tekscie
"""
import asyncio
import logging
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
SHOP = "fanbase.pl"
BASE_URL = "https://fanbase.pl"
CATEGORY_URLS = [
    "/pmi,c48.html",
    "/pmi,c48,2.html",
]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


async def get_products():
    products = []
    seen_ids = set()
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            for cat_url in CATEGORY_URLS:
                url = BASE_URL + cat_url
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        break
                    html = await resp.text()
                soup = BeautifulSoup(html, "lxml")
                items = soup.select(".product")
                for item in items:
                    name_el = None
                    for a in item.select('a'):
                        if ',id' in a.get('href', '') and a.text.strip():
                            name_el = a
                            break
                    if not name_el:
                        continue
                    name = name_el.text.strip()
                    href = name_el.get("href", "")
                    # PID z URL (,idNNN.html)
                    pid = ""
                    if ",id" in href:
                        pid = href.split(",id")[1].split(".")[0]
                    if not pid or pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    # Cena
                    price_el = item.select_one(".pprice")
                    price = _format_price(price_el.text.strip() if price_el else "")
                    # Dostepnosc
                    item_text = item.get_text(" ", strip=True).lower()
                    available = "koszyk" in item_text
                    # Obrazek
                    img_el = item.select_one("img")
                    image = ""
                    if img_el:
                        image = img_el.get("data-src") or img_el.get("src", "")
                        if image and image.startswith("/"):
                            image = BASE_URL + image
                    product_url = BASE_URL + "/" + href if not href.startswith("http") else href
                    products.append({
                        "id": f"fanbase_{pid}",
                        "name": name,
                        "price": price,
                        "shop": SHOP,
                        "url": product_url,
                        "image": image,
                        "stock": 1 if available else 0,
                        "available": available,
                    })
    except Exception as e:
        logger.error(f"[fanbase] Error: {e}")
    logger.info(f"[fanbase] {len(products)} produktow ({sum(1 for p in products if p['available'])} avail)")
    return products


def _format_price(price_raw):
    if not price_raw:
        return "brak"
    try:
        price_str = price_raw.replace("zł", "").replace(" ", "").replace(",", ".").strip()
        price_float = float(price_str)
        return f"{price_float:.2f} PLN"
    except (ValueError, TypeError):
        return price_raw.strip()
