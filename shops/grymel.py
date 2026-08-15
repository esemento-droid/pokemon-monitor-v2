import aiohttp
import re
from bs4 import BeautifulSoup

SHOP = "grymel"
BASE = "https://grymel.pl"
SEARCH_URL = f"{BASE}/szukaj?controller=search&s=Pokemon+tcg"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "sleeve", "koszulk", "toploader", "album", "portfolio", "binder", "ultra pro", "playmat",
    "kubek", "figurk", "plusz", "puzzle", "alcove", "deck box", "one piece", "lorcana",
    "yu-gi-oh", "digimon", "zegarek", "scarlet", "violet", "switch", "nintendo", "let's go",
    "shining pearl", "brilliant diamond", "pokemon snap", "legends", "mystery dungeon",
    "pokemon shield", "pokemon sword", "t-shirt", "koszulk", "battle deck", "league battle",
    "rival battle", "v battle", "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk", "korean", "chiński",
    "chińsk", "chinese", "(chi)", "s-chinese", "ultra-pro", "segregator", "naruto",
    "star wars", "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "figure set"
]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(SEARCH_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
    soup = BeautifulSoup(html, "lxml")
    for item in soup.select(".product-miniature"):
        a = item.select_one(".product-title a, h2 a")
        if not a:
            continue
        name = a.get_text(strip=True)
        name_low = name.lower()
        if "pokemon" not in name_low and "pokémon" not in name_low:
            continue
        if any(ex in name_low for ex in EXCLUDE):
            continue
        href = a.get("href", "")
        pid_m = re.search(r"/(\d+)-", href)
        pid = pid_m.group(1) if pid_m else href
        if pid in seen:
            continue
        seen.add(pid)
        price_el = item.select_one(".price")
        price = "brak"
        if price_el:
            m = re.search(r"(\d+[,.]\d+)", price_el.get_text())
            if m:
                price = m.group(1).replace(",", ".") + " zl"
        text = item.get_text(" ", strip=True).lower()
        available = "koszyk" in text or "dodaj" in text
        img = item.select_one("img")
        image = ""
        if img:
            image = img.get("data-full-size-image") or img.get("src") or ""
        products.append({"id": f"grymel_{pid}", "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
    print(f"[GRYMEL] {len(products)} produktow")
    return products
