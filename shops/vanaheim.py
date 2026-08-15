"""
Scraper: vanaheim.pl
Silnik: PrestaShop
Metoda: aiohttp + BeautifulSoup (curl przechodzi CF)
Kategorie: Pokemon TCG/2095 + Preorder/1698 (filtr Pokemon)
Wykluczenia: world championships deck
"""

import asyncio
import logging
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SHOP = "vanaheim"
BASE_URL = "https://vanaheim.pl"
CATEGORIES = [
    "/pl/2095-pokemon-tcg",
    "/pl/1698-preorder-przedsprzedaz",
]
EXCLUDE_KEYWORDS = [
    "world championships deck", "league battle deck", "flesh & blood", "flesh and blood",
    "magic the gathering", "magic:", "naruto", "riftbound", "league of legends", "star wars",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "weiss schwarz", "force of will",
    "rival battle", "v battle", "wcs deck", "wcs ", "battle academy", "japoński", "japońsk",
    "japanese", "(jp)", "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese",
    "(chi)", "s-chinese", "ultra pro", "ultra-pro", "playmat", "portfolio", "binder", "sleeve",
    "toploader", "album", "koszulk", "segregator", "deck box", "alcove", "dragon shield",
    "zeszyt", "puzzle", "figurk", "figure set"
]
POKEMON_KEYWORDS = ["pokemon", "pokémon", "pikachu", "charizard", "booster", "etb", "trainer box"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAX_PAGES = 5


async def get_products():
    """Pobiera produkty Pokemon z vanaheim.pl."""
    products = []
    seen_ids = set()

    try:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            for cat_url in CATEGORIES:
                is_preorder = "preorder" in cat_url.lower()
                page = 1

                while page <= MAX_PAGES:
                    url = BASE_URL + cat_url if page == 1 else f"{BASE_URL}{cat_url}?page={page}"
                    logger.info(f"[vanaheim] Loading: {url}")

                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status != 200:
                            logger.error(f"[vanaheim] HTTP {resp.status} for {url}")
                            break
                        html = await resp.text()

                    soup = BeautifulSoup(html, "lxml")
                    items = soup.select("[data-id-product]")

                    if not items:
                        break

                    for item in items:
                        product_id = item.get("data-id-product", "")

                        if product_id in seen_ids:
                            continue
                        seen_ids.add(product_id)

                        # Nazwa
                        name_el = item.select_one(".product-title a, h3 a")
                        name = name_el.text.strip() if name_el else ""

                        # Preorder: filtruj tylko Pokemon
                        if is_preorder:
                            name_lower = name.lower()
                            item_html = str(item).lower()
                            if not any(kw in name_lower or kw in item_html for kw in POKEMON_KEYWORDS):
                                continue

                        # Wykluczenia
                        if any(kw in name.lower() for kw in EXCLUDE_KEYWORDS):
                            continue

                        # URL
                        url_product = ""
                        if name_el and name_el.get("href"):
                            url_product = name_el["href"]

                        # Cena
                        price_el = item.select_one(".price")
                        price = _format_price(price_el.text.strip() if price_el else "")

                        # Obrazek
                        img_el = item.select_one("img[data-catalog-large]") or item.select_one("img[content]") or item.select_one("meta[itemprop='image']")
                        image = ""
                        if img_el:
                            image = img_el.get("data-catalog-large") or img_el.get("content") or img_el.get("src", "")

                        # Dostępność
                        item_text = item.get_text(" ", strip=True).lower()
                        available = "niedostępn" not in item_text

                        products.append({
                            "id": f"vanaheim_{product_id}",
                            "name": name,
                            "price": price,
                            "shop": SHOP,
                            "url": url_product,
                            "image": image,
                            "stock": 1 if available else 0,
                            "available": available,
                        })

                    # Paginacja
                    pag_next = soup.select_one("a.next, a[rel='next'], .pagination .next a")
                    if not pag_next:
                        break
                    page += 1

                logger.info(f"[vanaheim] {cat_url}: done ({page} pages)")

    except Exception as e:
        logger.error(f"[vanaheim] Error: {e}")

    products = [p for p in products if p["available"]]
    logger.info(f"[vanaheim] Total: {len(products)} products ({sum(1 for p in products if p['available'])} available)")
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
    print(f"\n=== VANAHEIM: {len(results)} products ===")
    available = [p for p in results if p["available"]]
    unavailable = [p for p in results if not p["available"]]
    print(f"Available: {len(available)}")
    for p in available[:10]:
        print(f"  [OK] {p['name']} - {p['price']}")
    print(f"Unavailable: {len(unavailable)}")
    for p in unavailable[:10]:
        print(f"  [XX] {p['name']} - {p['price']}")
