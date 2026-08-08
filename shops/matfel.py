"""
Scraper: matfel.pl
Silnik: IAI-Shop
Metoda: aiohttp + search.php
Szukanie: pokemon tcg
Dostępność: 'niedostępn' w tekście produktu = niedostępny
"""
import asyncio
import logging
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
SHOP = "matfel.pl"
SEARCH_URL = "https://matfel.pl/search.php?text=pokemon+tcg"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


async def get_products():
    products = []
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            async with session.get(SEARCH_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.error(f"[matfel] HTTP {resp.status}")
                    return products
                html = await resp.text()
            soup = BeautifulSoup(html, "lxml")
            items = soup.select(".product")
            for item in items:
                name_el = item.select_one(".product__name")
                if not name_el:
                    continue
                name = name_el.text.strip()
                href = name_el.get("href", "")
                # PID
                pid = ""
                if "product-pol-" in href:
                    pid = href.split("product-pol-")[1].split("-")[0]
                if not pid:
                    continue
                # Cena
                price_el = item.select_one(".product__prices")
                price = _format_price(price_el.text.strip() if price_el else "")
                # Dostepnosc
                item_text = item.get_text(" ", strip=True).lower()
                available = "niedostępn" not in item_text
                # Obrazek
                img_el = item.select_one("img")
                image = ""
                if img_el:
                    image = img_el.get("data-src") or img_el.get("src", "")
                    if image and image.startswith("/"):
                        image = "https://matfel.pl" + image
                products.append({
                    "id": f"matfel_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": href,
                    "image": image,
                    "stock": 1 if available else 0,
                    "available": available,
                })
    except Exception as e:
        logger.error(f"[matfel] Error: {e}")
    logger.info(f"[matfel] {len(products)} produktow ({sum(1 for p in products if p['available'])} avail)")
    return products


def _format_price(price_raw):
    if not price_raw:
        return "brak"
    try:
        # Wez pierwszQ cene (przed /)
        price_str = price_raw.split("/")[0].strip()
        # Jesli sa dwie ceny (stara+nowa) - wez ostatnia cyfre
        parts = price_str.split("zł")
        if len(parts) > 1:
            price_str = parts[-2].strip()
        for suffix in ["zł", "PLN", "pln", "zl"]:
            price_str = price_str.replace(suffix, "").strip()
        price_str = price_str.replace(",", ".").replace("\xa0", "").replace(" ", "")
        price_float = float(price_str)
        return f"{price_float:.2f} PLN"
    except (ValueError, TypeError):
        return price_raw.strip()
