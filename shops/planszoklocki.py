import aiohttp
from bs4 import BeautifulSoup
import re

SHOP = "planszoklocki"
URL = "https://planszoklocki.pl/pl/menu/pokemon-tcg-262"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BASE = "https://planszoklocki.pl"
EXCLUDE = [
    "japonsk", "japanese", "korean", "koreansk", "chinsk", "chinese", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "(jp)", "koreański", "koreańsk", "chiński",
    "chińsk", "(chi)", "ultra pro", "ultra-pro", "playmat", "portfolio", "binder", "sleeve",
    "toploader", "album", "koszulk", "segregator", "deck box", "alcove", "lorcana",
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
    soup = BeautifulSoup(html, "lxml")
    for p in soup.select(".product"):
        a = p.select_one("a[href]")
        if not a:
            continue
        href = a.get("href", "")
        if not href.startswith("http"):
            href = BASE + href
        texts = list(p.stripped_strings)
        full_text = " ".join(texts).lower()
        available = "chwilowo niedost" not in full_text
        name = ""
        for t in texts:
            if len(t) > 15 and "zl" not in t.lower() and t.lower() not in ["promocja", "nowość", "chwilowo niedostępny", "brutto"]:
                name = t
                break
        if not name:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        price = "brak"
        for t in texts:
            if "zl" in t.lower() or "zł" in t:
                price = t.replace("\xa0", "").replace(" ", "").replace(",", ".").replace("zł", "").strip() + " zl"
                break
        m = re.search(r"-(\d+)\.html", href) or re.search(r"-(\d+)$", href)
        pid = m.group(1) if m else "0"
        img = p.select_one("img")
        image = ""
        if img:
            src = img.get("src") or img.get("data-src") or ""
            if src and not src.startswith("http"):
                src = BASE + src
            image = src
        products.append({"id": f"planszoklocki_{pid}", "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
    print(f"[PLANSZOKLOCKI] {len(products)} produktow")
    return products
