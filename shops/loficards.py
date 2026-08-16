"""
Scraper: loficards.pl
Platform: Sky-Shop
Method: aiohttp + BeautifulSoup (no JS needed)
Products: Pokemon TCG English sealed (kategoria Karty Angielskie)
"""
import asyncio
import aiohttp
import logging
import re
from bs4 import BeautifulSoup

log = logging.getLogger("monitor")

SHOP = "loficards"
BASE_URL = "https://loficards.pl"
CATEGORY_URL = f"{BASE_URL}/pokemon-Karty-Angielskie"
MAX_PAGES = 8

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
    "final fantasy",
    # Junk
    "zeszyt", "puzzle", "figurk", "figure set", "plush", "pluszak",
    # Singles (graded/PSA)
    "psa ", "psa-", "cgc ", "bgs ",
]


def _parse_page(html: str) -> list[dict]:
    """Parse a single category page and return products."""
    soup = BeautifulSoup(html, "lxml")
    products = []

    # Each product card is a div with class col_custom containing product data
    cards = soup.select("div.col_custom")

    for card in cards:
        try:
            # Name + URL
            name_el = card.select_one("a.product-name")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 5:
                continue
            href = name_el.get("href", "")

            # ID from data-product-id attribute (on favorite button)
            pid_el = card.find(attrs={"data-product-id": True})
            if pid_el:
                pid = pid_el["data-product-id"]
            else:
                # Fallback: extract from URL
                pid_match = re.search(r"-p(\d+)", href)
                pid = pid_match.group(1) if pid_match else href.rstrip("/").split("/")[-1]

            # Price
            price_el = card.select_one(".product-price-container [data-price]")
            price = price_el["data-price"] if price_el else ""

            # Image
            img_el = card.select_one(".product-img-container img")
            image = ""
            if img_el:
                image = img_el.get("src", "") or img_el.get("data-src", "")
                if image and not image.startswith("http"):
                    image = BASE_URL + image
                # Skip placeholder
                if "data:image" in image:
                    image = img_el.get("data-src", "") or img_el.get("srcset", "").split(" ")[0]
                    if image and not image.startswith("http"):
                        image = BASE_URL + image

            # Availability: "Do koszyka" button means available
            action_el = card.select_one(".product-action")
            action_text = action_el.get_text(strip=True).lower() if action_el else ""
            card_text = card.get_text(" ", strip=True).lower()
            available = ("koszyk" in action_text or "dodaj" in action_text) and \
                        "niedost" not in card_text and "wyprzedane" not in card_text and "brak" not in card_text

            # Full URL
            url = href if href.startswith("http") else BASE_URL + href

            # Price formatting
            price_str = f"{price} zl" if price else "brak"

            products.append({
                "id": f"loficards_{pid}",
                "name": name,
                "price": price_str,
                "shop": SHOP,
                "url": url,
                "image": image,
                "stock": None,
                "available": available,
            })

        except Exception as e:
            log.debug(f"[loficards] Parse error: {e}")
            continue

    return products


async def get_products() -> list[dict]:
    """Scrape all pages of Pokemon TCG English cards (parallel fetch)."""
    all_products = []
    seen_ids = set()

    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            # Fetch all pages in parallel (7 pages, 12 products each)
            urls = [CATEGORY_URL] + [f"{CATEGORY_URL}/pa/{p}" for p in range(2, MAX_PAGES + 1)]

            async def fetch_page(url):
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                        if resp.status != 200:
                            return ""
                        return await resp.text()
                except Exception:
                    return ""

            pages_html = await asyncio.gather(*[fetch_page(u) for u in urls])

            for html in pages_html:
                if not html:
                    continue
                products = _parse_page(html)

                for p in products:
                    name_lower = p["name"].lower()
                    # Apply exclude filter
                    if any(ex in name_lower for ex in EXCLUDE):
                        continue
                    # Price filter: <10 PLN = probably single
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

    except Exception as e:
        log.error(f"[loficards] Error: {str(e)[:80]}")
        return []

    print(f"[LOFICARDS] {len(all_products)} produktow")
    return all_products
