import aiohttp
from bs4 import BeautifulSoup
import asyncio

SHOP = "kartomat"
BASE_URL = "https://kartomat.sklep.pl/pl/c/Pokemon/45"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
EXCLUDE = [
    "korean", "chinese", "chin", "sleeve", "koszulk", "toploader", "academy", "naruto",
    "riftbound", "lorcana", "one piece", "jap", "lego", "72168", "72160", "72150",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "(jp)", "koreański", "koreańsk", "chiński", "chińsk", "(chi)",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "binder", "album", "segregator",
    "deck box", "alcove", "yu-gi-oh", "digimon", "star wars", "magic the gathering",
    "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz", "force of will",
    "zeszyt", "puzzle", "figurk", "figure set"
]

async def fetch(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return ""
            return await resp.text()
    except:
        return ""

def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    for t in soup.select("product-tile"):
        pid = t.get("product-id", "")
        if not pid:
            continue
        name = t.get("name", "").strip()
        if not name:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        price = t.get("price", "0")
        if price in ("0", "1", ""):
            price = "1 zl"
        else:
            price = price + " zl"
        text = t.get_text(" ", strip=True).lower()
        available = "koszyk" in text or "dodaj" in text
        link = ""
        a = t.select_one("a[href*='/p/']")
        if a:
            link = a.get("href", "")
            if link and not link.startswith("http"):
                link = "https://kartomat.sklep.pl" + link
        img = t.select_one("img[data-src]") or t.select_one("img[src]")
        image = ""
        if img:
            image = img.get("data-src") or img.get("src") or ""
            if image and not image.startswith("http"):
                image = "https://kartomat.sklep.pl" + image
        products.append({"id": f"kartomat_{pid}", "name": name, "price": price, "shop": SHOP, "url": link, "image": image, "stock": None, "available": available})
    return products

async def get_products():
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        pages = await asyncio.gather(fetch(session, BASE_URL), fetch(session, f"{BASE_URL}/2"))
    seen = set()
    products = []
    for html in pages:
        if not html:
            continue
        for p in parse_page(html):
            if p["id"] not in seen:
                seen.add(p["id"])
                products.append(p)
    print(f"[KARTOMAT] {len(products)} produktow")
    return products
