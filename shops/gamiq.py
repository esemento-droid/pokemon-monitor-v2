import aiohttp
from bs4 import BeautifulSoup
import json
import re

SHOP = "gamiq"
URL = "https://www.gamiq.pl/pokemon-tcg,g238.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
BASE = "https://www.gamiq.pl"
EXCLUDE = [
    "koszulki", "akcesoria", "album", "battle academy", "battle deck", "league battle",
    "rival battle", "v battle", "world championship", "wcs deck", "wcs ", "japoński",
    "japońsk", "japanese", "(jp)", "koreański", "koreańsk", "korean", "chiński", "chińsk",
    "chinese", "(chi)", "s-chinese", "ultra pro", "ultra-pro", "playmat", "portfolio",
    "binder", "sleeve", "toploader", "segregator", "deck box", "alcove", "lorcana",
    "one piece", "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering",
    "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz", "force of will",
    "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]

async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
    # Parse gtag JSON for prices
    prices = {}
    m = re.search(r'view_item_list.*?items:\s*(\[.*?\])\s*\}', html, re.DOTALL)
    if m:
        try:
            items = json.loads(m.group(1))
            for item in items:
                prices[str(item.get("item_id", ""))] = item.get("price", 0)
        except:
            pass
    soup = BeautifulSoup(html, "lxml")
    for box in soup.select("div.offer_box[data-id_produkt]"):
        pid = box.get("data-id_produkt", "")
        if not pid:
            continue
        name_el = box.select_one("a.name")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        name_low = name.lower()
        if any(ex in name_low for ex in EXCLUDE):
            continue
        url = name_el.get("href", "")
        if not url.startswith("http"):
            url = BASE + url
        # Price from gtag JSON
        price_val = prices.get(pid, 0)
        price = f"{price_val:.2f} zl" if price_val else "brak"
        # Image
        img_el = box.select_one("img")
        image = ""
        if img_el:
            image = img_el.get("src") or img_el.get("data-src") or ""
        # Availability: has add_to_cart_btn
        available = bool(box.select_one(".add_to_cart_btn"))
        products.append({
            "id": f"gamiq_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": None,
            "available": available,
        })
    print(f"[GAMIQ] {len(products)} produktow")
    return products
