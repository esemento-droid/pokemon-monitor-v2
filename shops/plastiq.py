"""
Scraper: plastiq.pl
Platform: Shoper
Method: aiohttp + BeautifulSoup (no JS needed)
Products: Pokemon TCG category (karty-pokemon,c127.html)
"""
import asyncio
import aiohttp
import logging
import re
from bs4 import BeautifulSoup

log = logging.getLogger("monitor")

SHOP = "plastiq"
BASE_URL = "https://plastiq.pl"
CATEGORY_URL = f"{BASE_URL}/karty-pokemon,c127.html"
MAX_PAGES = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl,en;q=0.9",
}

EXCLUDE = [
    # Decks
    "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "battle academy",
    # Foreign
    "japoński", "japońsk", "japanese", "koreański", "korean",
    "chiński", "chinese", "s-chinese",
    # Accessories
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder",
    "playmat", "mata", "segregator", "deck box", "alcove",
    "ultra pro", "ultra-pro",
    # Other games
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto",
    "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "gundam", "banpresto", "fuggler",
    # Junk
    "zeszyt", "puzzle", "figurk", "figure set", "plusz", "maskotka",
]


def _parse_page(html: str) -> list[dict]:
    """Parse a single category page."""
    soup = BeautifulSoup(html, "lxml")
    products = []

    cards = soup.select(".product")

    for card in cards:
        try:
            # Name + URL
            name_el = card.select_one(".description h4 a, .description a")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 5:
                continue
            href = name_el.get("href", "")

            # ID from URL
            pid_match = re.search(r",id(\d+)\.html", href)
            pid = pid_match.group(1) if pid_match else ""
            if not pid:
                continue

            # Price
            price_el = card.select_one(".price .pprice, .price strong, .price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price_match = re.search(r"(\d+[.,]\d{2})", price_text)
            price = price_match.group(1).replace(",", ".") if price_match else ""

            # Image
            img_el = card.select_one("img")
            image = ""
            if img_el:
                image = img_el.get("data-src", "") or img_el.get("src", "")
                if image and not image.startswith("http"):
                    image = BASE_URL + image
                if "empty.svg" in image:
                    image = ""

            # Availability: products with basket/cart button or price = available
            # Products without price on listing = check for "Zapytaj" or unavailable markers
            card_text = card.get_text(" ", strip=True).lower()
            has_basket = card.select_one("[class*=basket], [class*=cart], .addtobasket") is not None
            is_unavail = "niedost" in card_text or "wyprzedane" in card_text or "zapytaj" in card_text
            available = (bool(price) or has_basket) and not is_unavail

            # Full URL
            url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")

            # Price string
            price_str = f"{price} zl" if price else "brak"

            products.append({
                "id": f"plastiq_{pid}",
                "name": name,
                "price": price_str,
                "shop": SHOP,
                "url": url,
                "image": image,
                "stock": None,
                "available": available,
            })

        except Exception as e:
            log.debug(f"[plastiq] Parse error: {e}")
            continue

    return products


async def get_products() -> list[dict]:
    """Scrape all pages of Pokemon TCG category."""
    all_products = []
    seen_ids = set()

    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            for page in range(1, MAX_PAGES + 1):
                url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}?str-{page}"

                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status != 200:
                            break
                        html = await resp.text()
                except Exception as e:
                    log.warning(f"[plastiq] Page {page} fetch error: {e}")
                    break

                products = _parse_page(html)

                if not products:
                    break

                for p in products:
                    name_lower = p["name"].lower()
                    # Must mention pokemon
                    if "pokemon" not in name_lower and "pokémon" not in name_lower:
                        continue
                    # Exclude filter
                    if any(ex in name_lower for ex in EXCLUDE):
                        continue
                    # Price filter: <10 PLN = single
                    try:
                        price_val = float(p["price"].replace(" zl", ""))
                        if price_val < 10:
                            continue
                    except (ValueError, AttributeError):
                        pass
                    # Dedup
                    if p["id"] not in seen_ids:
                        seen_ids.add(p["id"])
                        all_products.append(p)

                # Small delay between pages
                if page < MAX_PAGES:
                    await asyncio.sleep(1)

    except Exception as e:
        log.error(f"[plastiq] Error: {str(e)[:80]}")
        return []

    print(f"[PLASTIQ] {len(all_products)} produktow")
    return all_products
