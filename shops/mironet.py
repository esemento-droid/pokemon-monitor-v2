"""
Scraper: mironet.pl
Silnik: Wlasny (ProductList)
Metoda: aiohttp + BeautifulSoup
Szukanie: Pokemon tcg
Wykluczenia: album, UP: (Ultra Pro akcesoria)
"""
import asyncio
import re
import logging
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
SHOP = "mironet.pl"
SEARCH_URL = "https://www.mironet.pl/ProductList/showSearch?EXPF=Pokemon+tcg"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
EXCLUDE_KEYWORDS = ["album", "up:", "ultra pro", "ultra-pro", "koszulk", "sleeve", "playmat", "mata"]


async def get_products():
    products = []
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            async with session.get(SEARCH_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.error(f"[mironet] HTTP {resp.status}")
                    return products
                html = await resp.text()
        soup = BeautifulSoup(html, "lxml")
        links = soup.find_all("a", href=re.compile(r"\+dp\d+"))
        seen = {}
        for l in links:
            href = l.get("href", "")
            m = re.search(r"\+dp(\d+)", href)
            if not m:
                continue
            pid = m.group(1)
            name = l.text.strip()
            if not name or len(name) < 10 or pid in seen:
                continue
            if any(kw in name.lower() for kw in EXCLUDE_KEYWORDS):
                continue
            # Cena z rodzicow
            price = "brak"
            for anc in [l.parent, l.parent.parent, l.parent.parent.parent]:
                if not anc:
                    continue
                txt = anc.get_text(" ", strip=True)
                prices = re.findall(r"[\d\s,]+zł", txt)
                if prices:
                    price = _format_price(prices[-1].strip())
                    break
            # Dostepnosc
            form = soup.select_one(f"[data-product-id='{pid}']")
            available = False
            if form:
                available = "koszyk" in form.get_text(" ", strip=True).lower()
            # Obrazek
            image = ""
            for anc in [l.parent, l.parent.parent]:
                if not anc:
                    continue
                img = anc.select_one("img")
                if img:
                    image = img.get("data-src") or img.get("src", "")
                    if image and image.startswith("/"):
                        image = "https://www.mironet.pl" + image
                    break
            url = f"https://www.mironet.pl{href}" if href.startswith("/") else href
            seen[pid] = True
            products.append({
                "id": f"mironet_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": url,
                "image": image,
                "stock": 1 if available else 0,
                "available": available,
            })
    except Exception as e:
        logger.error(f"[mironet] Error: {e}")
    logger.info(f"[mironet] {len(products)} produktow ({sum(1 for p in products if p['available'])} avail)")
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
