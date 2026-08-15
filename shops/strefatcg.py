"""
Scraper: strefa-tcg.pl
Silnik: Shoper
Metoda: aiohttp + BeautifulSoup (brak CF)
Kategorie: Sealed-Produkty/177 + Preorder/163
Wykluczenia: binder, battle academy
"""

import asyncio
import logging
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SHOP = "strefa-tcg"
BASE_URL = "https://strefa-tcg.pl"
CATEGORIES = [
    "/pl/c/Sealed-Produkty/177",
    "/pl/c/Preorder/163",
]
EXCLUDE_KEYWORDS = [
    "pro-binder", "battle academy", "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "sleeves", "toploader", "album",
    "koszulk", "segregator", "deck box", "alcove", "lorcana", "one piece", "yu-gi-oh",
    "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


async def get_products():
    """Pobiera produkty z strefa-tcg.pl."""
    products = []
    seen_ids = set()

    try:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            for cat_url in CATEGORIES:
                url = BASE_URL + cat_url
                logger.info(f"[strefa-tcg] Loading: {url}")

                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        logger.error(f"[strefa-tcg] HTTP {resp.status} for {url}")
                        continue
                    html = await resp.text()

                soup = BeautifulSoup(html, "lxml")
                items = soup.select("[data-product-id]")

                for item in items:
                    product_id = item.get("data-product-id", "")

                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)

                    # Nazwa
                    name_el = item.select_one(".productname")
                    name = name_el.text.strip() if name_el else ""

                    # Wykluczenia
                    if any(kw in name.lower() for kw in EXCLUDE_KEYWORDS):
                        continue

                    # URL
                    link_el = item.select_one("a.prodimage") or item.select_one("a.prodname")
                    url_product = ""
                    if link_el and link_el.get("href"):
                        href = link_el["href"]
                        url_product = href if href.startswith("http") else BASE_URL + href

                    # Cena
                    price_el = item.select_one(".price em")
                    price = _format_price(price_el.text.strip() if price_el else "")

                    # Obrazek
                    img_el = item.select_one("img[data-src]")
                    image = ""
                    if img_el and img_el.get("data-src"):
                        img_src = img_el["data-src"]
                        image = img_src if img_src.startswith("http") else BASE_URL + img_src

                    # Dostępność
                    has_basket = bool(item.select_one(".addtobasket"))

                    # Stock
                    stock_input = item.select_one("input[name='quantity']")
                    stock = 1 if has_basket else 0

                    products.append({
                        "id": f"strefatcg_{product_id}",
                        "name": name,
                        "price": price,
                        "shop": SHOP,
                        "url": url_product,
                        "image": image,
                        "stock": stock,
                        "available": has_basket,
                    })

                logger.info(f"[strefa-tcg] {cat_url}: {len(items)} items found")

    except Exception as e:
        logger.error(f"[strefa-tcg] Error: {e}")

    logger.info(f"[strefa-tcg] Total: {len(products)} available products")
    return products


def _format_price(price_raw):
    """Formatuje cenę."""
    if not price_raw:
        return "brak"
    try:
        price_str = price_raw.replace(",", ".").replace("\xa0", " ")
        for suffix in ["zł", "PLN", "pln", "zl"]:
            price_str = price_str.replace(suffix, "").strip()
        price_float = float(price_str)
        return f"{price_float:.2f} PLN"
    except (ValueError, TypeError):
        return price_raw.strip()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = asyncio.run(get_products())
    print(f"\n=== STREFA-TCG: {len(results)} products ===")
    for p in results:
        print(f"  {p['name']} - {p['price']}")
