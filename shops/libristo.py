"""
Scraper: libristo.pl (www.libristo.pl)
Platform: Custom (Libristo) behind Cloudflare
Method: FlareSolverr + BeautifulSoup (search page)
Category: search?t=Pokemon+tcg
"""
import aiohttp
import asyncio
import re
import html as html_lib
from bs4 import BeautifulSoup

SHOP = "libristo"
BASE = "https://www.libristo.pl"
SEARCH_URL = f"{BASE}/pl/wyszukiwanie?t=Pokemon+tcg"
MAX_PAGES = 3
FLARESOLVERR_URL = "http://localhost:8191/v1"

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

    cards = soup.select("div.shrink-0")

    for card in cards:
        link = card.select_one('a[href*="/pl/prasa/"]')
        if not link:
            continue

        href = link.get("href", "")
        if "pokemon" not in href.lower():
            continue

        pid_match = re.search(r"_(\d+)$", href.rstrip("/"))
        pid = pid_match.group(1) if pid_match else ""
        if not pid:
            continue

        name = ""
        img = card.select_one("img[alt]")
        if img:
            alt = img.get("alt", "")
            if len(alt) > 5 and "tag" not in alt.lower() and "flag" not in alt.lower():
                name = alt
        if not name:
            texts = [t.strip() for t in card.stripped_strings if len(t.strip()) > 5]
            name = texts[0] if texts else ""
        if not name:
            continue

        name = html_lib.unescape(name)

        card_text = card.get_text(" ", strip=True)
        price_match = re.search(r"(\d+[.,]\d{2})\s*zł", card_text)
        price = price_match.group(1).replace(",", ".") + " zl" if price_match else "brak"

        image = ""
        imgs = card.select("img")
        for im in imgs:
            src = im.get("src", "") or im.get("data-src", "")
            if src and "tag" not in src and "flag" not in src and src.startswith("http"):
                image = src
                break

        avail_text = card_text.lower()
        available = "niedost" not in avail_text and "wyprzeda" not in avail_text

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

    async with aiohttp.ClientSession() as session:
        for page in range(1, MAX_PAGES + 1):
            url = SEARCH_URL if page == 1 else f"{SEARCH_URL}&strona={page}"

            try:
                payload = {"cmd": "request.get", "url": url, "maxTimeout": 30000}
                async with session.post(
                    FLARESOLVERR_URL, json=payload,
                    timeout=aiohttp.ClientTimeout(total=45),
                ) as resp:
                    if resp.status != 200:
                        break
                    result = await resp.json()
                    if result.get("status") != "ok":
                        break
                    html = result.get("solution", {}).get("response", "")
            except Exception as e:
                print(f"[libristo] FlareSolverr error page {page}: {e}")
                break

            if not html:
                break

            products = _parse_page(html)
            if not products:
                break

            for p in products:
                name_low = p["name"].lower()
                if "pokemon" not in name_low and "pokémon" not in name_low:
                    continue
                if any(ex in name_low for ex in EXCLUDE):
                    continue
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
