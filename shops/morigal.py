"""
Scraper: morigal.pl
Platform: osCommerce variant behind Cloudflare
Method: FlareSolverr + BeautifulSoup (data attributes on product links)
Category: pokemon-tcg-c-2313 (Pokémon TCG)
"""
import aiohttp
import asyncio
import re
import html as html_lib
from bs4 import BeautifulSoup

SHOP = "morigal"
SCAN_TIMEOUT = 180  # CF solver: semaphore queue + 55s solve
BASE = "https://morigal.pl"
CAT_URL = f"{BASE}/pokemon-tcg-c-2313/"
FLARESOLVERR_URL = "http://localhost:8191/v1"

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
    "koszulki", "t-shirt", "lego", "figurka",
]


def _parse_page(html: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    products = []

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

        try:
            price_val = float(price_raw)
            price = f"{price_val:.2f} zl"
        except (ValueError, TypeError):
            price = "brak"
            price_val = 0

        img = card.select_one("img.image")
        image = ""
        if img:
            image = img.get("src", "") or ""

        card_text = card.get_text(" ", strip=True).lower()
        unavail = "niedost" in card_text or "wyprzedane" in card_text or "brak" in card_text
        available = not unavail and price_val > 0

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

    try:
        async with aiohttp.ClientSession() as session:
            payload = {"cmd": "request.get", "url": CAT_URL, "maxTimeout": 55000}
            async with session.post(
                FLARESOLVERR_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    print(f"[morigal] FlareSolverr HTTP {resp.status}")
                    return []
                result = await resp.json()
                if result.get("status") != "ok":
                    print(f"[morigal] FlareSolverr failed: {result.get('message', '')}")
                    return []
                html = result.get("solution", {}).get("response", "")
    except Exception as e:
        print(f"[morigal] FlareSolverr error: {e}")
        return []

    if not html:
        print("[MORIGAL] 0 produktow (empty response)")
        return []

    products = _parse_page(html)

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

    print(f"[MORIGAL] {len(all_products)} produktow")
    return all_products
