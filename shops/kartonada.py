import aiohttp
import re
from bs4 import BeautifulSoup

SHOP = "kartonada"
BASE = "https://www.kartonada.pl"
CATEGORIES = [
    f"{BASE}/karty-pokemon-tcg",
    f"{BASE}/karty-pokemon-tcg/battle-decks",
    f"{BASE}/karty-pokemon-tcg/blistry-pokemon",
    f"{BASE}/karty-pokemon-tcg/booster-boxes",
    f"{BASE}/karty-pokemon-tcg/booster-bundle",
    f"{BASE}/karty-pokemon-tcg/boosters",
    f"{BASE}/karty-pokemon-tcg/elite-trainer-box-etb",
    f"{BASE}/karty-pokemon-tcg/puszki-pokemon-tins",
    f"{BASE}/karty-pokemon-tcg/zestawy-pokemon-vbox-vmax-ex-box",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder", "ultra pro", "playmat",
    "japonsk", "japońsk", "japanese", "korean", "koreańsk", "chiński", "chinese",
    "mystery box", "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy", "(jp)", "(chi)", "ultra-pro",
    "segregator", "deck box", "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood", "flesh and blood",
    "dragon shield", "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle",
    "figurk", "figure set"
]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        all_items = []
        for cat_url in CATEGORIES:
            try:
                async with session.get(cat_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                soup = BeautifulSoup(html, "lxml")
                all_items.extend(soup.select(".product-tile"))
            except:
                continue
    items = all_items
    for item in items:
        name_el = item.select_one("h3.name")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if not name:
            continue
        name_low = name.lower()
        if "pokemon" not in name_low and "pokémon" not in name_low:
            continue
        if any(ex in name_low for ex in EXCLUDE):
            continue
        link = item.select_one("a[href]")
        if not link:
            continue
        href = link.get("href", "")
        pid_m = re.search(r"/(\d+),", href)
        pid = pid_m.group(1) if pid_m else ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        price_el = item.select_one("[class*=price]")
        price = "brak"
        if price_el:
            price_text = price_el.get_text(strip=True).replace("\xa0", "").replace(" ", "")
            m = re.search(r"(\d+[,.]\d+)", price_text)
            if m:
                price = m.group(1).replace(",", ".") + " zl"
        item_text = item.get_text(" ", strip=True).lower()
        available = "koszyk" in item_text or ("dostępn" in item_text and "niedost" not in item_text)
        img = item.select_one("img")
        image = ""
        if img:
            src = img.get("data-src") or img.get("src") or ""
            image = BASE + src if src.startswith("/") else src
        url_prod = BASE + href if href.startswith("/") else href
        products.append({
            "id": f"kartonada_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url_prod,
            "image": image,
            "stock": None,
            "available": available,
        })
    print(f"[KARTONADA] {len(products)} produktow")
    return products
