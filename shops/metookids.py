import aiohttp
import re
from bs4 import BeautifulSoup

SHOP = "metookids"
BASE = "https://metookids.pl"
CAT_URL = f"{BASE}/pol_m_POKEMON-i-KARTY-KOLEKCJONERSKIE_POKEMON-376.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder", "ultra pro", "playmat",
    "japonsk", "japońsk", "japanese", "korean", "koreańsk", "one piece", "lorcana", "yu-gi-oh",
    "digimon", "magic the", "figurk", "plusz", "zabawk", "chinese", "china", "chiński",
    "japan", "grading", "me too", "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy", "(jp)", "(chi)", "ultra-pro",
    "segregator", "deck box", "alcove", "naruto", "star wars", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figure set"
]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(CAT_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
    soup = BeautifulSoup(html, "lxml")
    for item in soup.select(".product"):
        name_el = item.select_one(".product__name")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        name_low = name.lower()
        if "pokemon" not in name_low and "pokémon" not in name_low:
            continue
        if any(ex in name_low for ex in EXCLUDE):
            continue
        link = item.select_one("a[href*='product-pol']")
        if not link:
            continue
        href = link.get("href", "")
        pid_m = re.search(r"product-pol-(\d+)", href)
        pid = pid_m.group(1) if pid_m else ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        price_el = item.select_one(".product__prices")
        price = "brak"
        if price_el:
            pt = price_el.get_text(strip=True).replace("\xa0", "").replace(" ", "")
            m = re.search(r"(\d+[,.]\d+)", pt)
            if m:
                price = m.group(1).replace(",", ".") + " zl"
        # IdoSell: if product has no "unavailable" class/icon, it's available
        unavail = item.select_one(".product__unavailable,.unavailable,[class*=unavail]")
        item_text = item.get_text(" ", strip=True).lower()
        available = unavail is None and "niedost" not in item_text and "brak" not in item_text
        img = item.select_one("img")
        image = ""
        if img:
            src = img.get("src", "")
            image = BASE + src if src.startswith("/") else src
        products.append({"id": f"metookids_{pid}", "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
    print(f"[METOOKIDS] {len(products)} produktow")
    return products
