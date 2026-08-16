"""
Scraper: morigal.pl
Platform: osCommerce/Zen Cart variant
Method: aiohttp + BeautifulSoup (data attributes on product links)
Category: pokemon-tcg-c-2313 (Pokémon TCG)
"""
import aiohttp
import asyncio
import re
import html as html_lib
from bs4 import BeautifulSoup

SHOP = "morigal"
BASE = "https://morigal.pl"
CAT_URL = f"{BASE}/pokemon-tcg-c-2313/"
MAX_PAGES = 5
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "pl,en;q=0.9",
}

EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder",
    "playmat", "mata", "segregator", "deck box", "alcove", "ultra pro", "ultra-pro",
    "one piece", "lorcana", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "dragon shield", "weiss schwarz",
    "riftbound", "dragon ball", "force of will", "sorcery",
    "japonsk", "japońsk", "japanese", "japan", "(jp)",
    "korean", "koreańsk", "chiński", "chinese", "(chi)",
    "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "battle academy",
    "singl", "single", "grading", "psa ", "cgc ",
    "zeszyt", "puzzle", "figurk", "figure set", "plush", "maskotka",
    "wydarzen", "event", "turniej", "bilet", "wpisowe",
    "koszulki", "t-shirt", "lego",
]


def _parse_page(html: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    products = []

    # Products are article.product-column with <a data-id data-name data-price>
    cards = soup.select("article.product-column")

    for card in cards:
        link = card.select_one("a[data-id][data-name]")
        if not link:
            continue

        pid = link.get("data-id", "")
        name = link.get("data-name", "")
        price_raw = link.get("data-price", "0")
        href = link.get("href", "")

        if not pid or not name:
            continue

        name = html_lib.unescape(name)

        # Price
        try:
            price_val = float(price_raw)
            price = f"{price_val:.2f} zl"
        except (ValueError, TypeError):
            price = "brak"
            price_val = 0

        # Image
        img = card.select_one("img.image")
        image = ""
        if img:
            image = img.get("src", "") or ""

        # Availability — check for "brak" or out-of-stock indicators
        card_text = card.get_text(" ", strip=True).lower()
        unavail = "niedost" in card_text or "wyprzedane" in card_text or "brak" in card_text
        # If price is 0, likely unavailable/placeholder
        available = not unavail and price_val > 0

        # URL
        url = href if href.startswith("http") else BASE + href

        products.append({
            "id": f"morigal_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": None,
            "available": available,
        })

    return products


async def get_products():
    all_products = []
    seen = set()

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Fetch pages in parallel
        urls = [CAT_URL] + [f"{CAT_URL}?category_id=2313&page={p}" for p in range(2, MAX_PAGES + 1)]

        async def fetch(url):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        return ""
                    return await resp.text()
            except Exception:
                return ""

        pages = await asyncio.gather(*[fetch(u) for u in urls])

        for html in pages:
            if not html:
                continue
            products = _parse_page(html)
            for p in products:
                name_low = p["name"].lower()

                # Must be Pokemon
                if "pokemon" not in name_low and "pokémon" not in name_low:
                    continue

                # Exclude
                if any(ex in name_low for ex in EXCLUDE):
                    continue

                # Price filter
                try:
                    pv = float(p["price"].replace(" zl", ""))
                    if 0 < pv < 10:
                        continue
                except (ValueError, AttributeError):
                    pass

                if p["id"] not in seen:
                    seen.add(p["id"])
                    all_products.append(p)

    print(f"[MORIGAL] {len(all_products)} produktow")
    return all_products
