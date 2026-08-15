"""
Scraper: swiatkart.pl
Silnik: aiohttp + BeautifulSoup (async gather)
Autor: aug 2 2026
"""
import asyncio
import logging
import re
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SHOP = "swiatkart.pl"
BASE_URL = "https://swiatkart.pl"
CATEGORIES = [
    "/pl/c/Elite-Trainer-Box/43",
    "/pl/c/Booster-Box/38",
    "/pl/c/Boostery/58",
    "/pl/c/Zestawy-Kolekcjonerskie/45",
    "/pl/c/Zestawy-Vbox%2C-Vmax%2C-EX-box/55",
    "/pl/c/Blistry/60",
    "/pl/c/Puszki-Tin/57",
    "/pl/c/30th-Celebration/213",
]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE_KEYWORDS = [
    "korea", "korean", "chiny", "chinese", "japonsk", "japanese", "japan", "japonia", "(jp)",
    "cbb", "gem pack", "(m1l)", "(m2)", "(m3)", "(m4)", "(m5)", "(sv1", "(sv2", "(sv3", "(sv4",
    "(sv5", "(sv6", "(sv7", "(sv8", "(sv9", "(csv", "lunar new year", "blade awakening",
    "ninja spinner", "nihil zero", "inferno x", "mega brave", "abyss eye", "clay burst",
    "terastal festival", "battle partners", "sleeves", "toploader", "album", "pro-binder", "klaser",
    "playmat", "figurk", "plusz", "maskotk", "kubek", "koszulk", "cgc ", "psa ", "one piece",
    "lorcana", "magic", "riftbound", "star wars", "yu-gi-oh", "flesh and blood", "mega dream",
    "code card", "crimson haze", "scarlet ex (sv", "mask of change", "paradise dragona",
    "ruler of the black", "super electric breaker", "shiny treasure", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "chiński", "chińsk", "(chi)", "ultra pro",
    "ultra-pro", "portfolio", "segregator", "deck box", "alcove", "digimon", "naruto",
    "flesh & blood", "dragon shield", "weiss schwarz", "force of will", "zeszyt", "puzzle",
    "figure set"
]

def _is_pokemon(name):
    nl = name.lower()
    return "pokemon" in nl or "pok\u00e9mon" in nl

def _is_single(name):
    if re.search(r"\([A-Z]{2,4}\s*\d{2,3}\)", name):
        return True
    if re.search(r"\(x?[A-Z]{2,4}\s+\d{2,3}\)", name):
        return True
    return False

async def _fetch(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 200:
                return await resp.text()
    except:
        pass
    return ""

async def get_products():
    products = []
    seen_ids = set()
    try:
        pages = []
        for cat in CATEGORIES:
            pages.append(cat)

        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            for i in range(0, len(pages), 10):
                batch = pages[i:i+10]
                urls = [BASE_URL + p for p in batch]
                htmls = await asyncio.gather(*[_fetch(session, u) for u in urls])
                for html in htmls:
                    if not html:
                        continue
                    _parse_page(html, products, seen_ids)
    except Exception as e:
        logger.error(f"[swiatkart] Error: {e}")

    print(f"[SWIATKART] {len(products)} produktow")
    return products

def _parse_page(html, products, seen_ids):
    soup = BeautifulSoup(html, "lxml")
    for tile in soup.select("product-tile"):
        link = tile.select_one("a[title][href]")
        if not link:
            continue
        href = link.get("href", "")
        if "/pl/p/" not in href:
            continue

        name = link.get("title", "").strip()
        if not href.startswith("http"):
            href = BASE_URL + href

        if not name or len(name) < 5:
            continue
        if not _is_pokemon(name):
            continue
        if _is_single(name):
            continue
        if any(kw in name.lower() for kw in EXCLUDE_KEYWORDS):
            continue

        pid_m = re.search(r"/(\d+)$", href)
        pid = pid_m.group(1) if pid_m else ""
        if not pid or pid in seen_ids:
            continue
        seen_ids.add(pid)

        price_el = tile.select_one("[class*=price-current], [class*=price]")
        price = _format_price(price_el.get_text(strip=True) if price_el else "")

        avail_tag = tile.select_one("[class*=avail]")
        available = "niedost" not in (avail_tag.get_text().lower() if avail_tag else "")

        img_el = tile.select_one("img")
        image = ""
        if img_el:
            image = img_el.get("data-src") or img_el.get("src") or ""
            if image and not image.startswith("http"):
                image = BASE_URL + image

        products.append({
            "id": f"swiatkart_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": href,
            "image": image,
            "stock": 1 if available else 0,
            "available": available,
        })

def _format_price(price_raw):
    if not price_raw:
        return "brak"
    m = re.search(r"(\d[\d\s\xa0]*[,.]\d+)", price_raw)
    if m:
        p = m.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")
        return f"{float(p):.2f} PLN"
    return "brak"
