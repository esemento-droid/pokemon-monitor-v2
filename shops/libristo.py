"""
Scraper: libristo.pl (www.libristo.pl)
Platform: Custom (Libristo)
Method: aiohttp + BeautifulSoup (search page, server-side rendered)
Category: search?t=Pokemon+tcg (multiple pages)
"""
import aiohttp
import asyncio
import re
import html as html_lib
from bs4 import BeautifulSoup

SHOP = "libristo"
BASE = "https://www.libristo.pl"
SEARCH_URL = f"{BASE}/pl/wyszukiwanie?t=Pokemon+tcg"
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
    "riftbound", "dragon ball", "force of will",
    "japonsk", "japońsk", "japanese", "japan", "(jp)", "japonský",
    "korean", "koreańsk", "chiński", "chinese", "(chi)",
    "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "battle academy",
    "singl", "single", "grading", "psa ", "cgc ",
    "zeszyt", "puzzle", "figurk", "figure set", "plush",
    "wydarzen", "event", "turniej", "bilet", "wpisowe",
]


def _parse_page(html: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    products = []

    # Product cards are div.shrink-0 (w-[170px]) with links to /pl/prasa/
    cards = soup.select("div.shrink-0")

    for card in cards:
        link = card.select_one('a[href*="/pl/prasa/"]')
        if not link:
            continue

        href = link.get("href", "")
        if "pokemon" not in href.lower():
            continue

        # ID from URL: _XXXXX at the end
        pid_match = re.search(r"_(\d+)$", href.rstrip("/"))
        pid = pid_match.group(1) if pid_match else ""
        if not pid:
            continue

        # Name from img alt or link text
        name = ""
        img = card.select_one("img[alt]")
        if img:
            alt = img.get("alt", "")
            if len(alt) > 5 and "tag" not in alt.lower() and "flag" not in alt.lower():
                name = alt
        if not name:
            # Get all meaningful text
            texts = [t.strip() for t in card.stripped_strings if len(t.strip()) > 5]
            name = texts[0] if texts else ""
        if not name:
            continue

        name = html_lib.unescape(name)

        # Price
        card_text = card.get_text(" ", strip=True)
        price_match = re.search(r"(\d+[.,]\d{2})\s*zł", card_text)
        price = price_match.group(1).replace(",", ".") + " zl" if price_match else "brak"

        # Image (skip tag/flag svgs)
        image = ""
        imgs = card.select("img")
        for im in imgs:
            src = im.get("src", "") or im.get("data-src", "")
            if src and "tag" not in src and "flag" not in src and src.startswith("http"):
                image = src
                break

        # Availability — libristo usually shows "niedostępny" or "wyprzedany"
        avail_text = card_text.lower()
        available = "niedost" not in avail_text and "wyprzeda" not in avail_text and "brak" not in avail_text

        # Full URL
        url = href if href.startswith("http") else BASE + href

        products.append({
            "id": f"libristo_{pid}",
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
        urls = [SEARCH_URL] + [f"{SEARCH_URL}&strona={p}" for p in range(2, MAX_PAGES + 1)]

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

    print(f"[LIBRISTO] {len(all_products)} produktow")
    return all_products
