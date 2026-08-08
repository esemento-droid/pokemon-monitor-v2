import aiohttp
import re
from bs4 import BeautifulSoup

SHOP = "zarc"
BASE = "https://zarc.pl"
URL = f"{BASE}/pl/c/Pokemon-TCG/92"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
EXCLUDE = ["sleeve", "koszulk", "toploader", "album", "portfolio", "binder", "ultra pro", "playmat", "japonsk", "japońsk", "japanese", "korean", "koreańsk", "one piece", "lorcana", "yu-gi-oh", "digimon", "magic the", "wcs"]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
    soup = BeautifulSoup(html, "lxml")
    for item in soup.select(".product-tile"):
        name_el = item.select_one(".product-tile__name")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        name_low = name.lower()
        if "pokemon" not in name_low and "pokémon" not in name_low:
            continue
        if any(ex in name_low for ex in EXCLUDE):
            continue
        link = item.select_one("a[href*='/pl/p/']")
        if not link:
            continue
        href = link.get("href", "")
        pid_m = re.search(r"/(\d+)$", href)
        pid = pid_m.group(1) if pid_m else ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        price_el = item.select_one(".product-tile__price")
        price = "brak"
        if price_el:
            pt = price_el.get_text(strip=True).replace("\xa0","").replace(" ","")
            m = re.search(r"(\d+[,.]\d+)", pt)
            if m:
                price = m.group(1).replace(",",".") + " zl"
        footer = item.select_one(".product-tile__footer-btn")
        available = footer is not None and "koszyk" in footer.get_text(strip=True).lower()
        img = item.select_one("img")
        image = ""
        if img:
            src = img.get("src","")
            image = BASE + src if src.startswith("/") else src
        products.append({"id": f"zarc_{pid}", "name": name, "price": price, "shop": SHOP, "url": BASE + href, "image": image, "stock": None, "available": available})
    print(f"[ZARC] {len(products)} produktow")
    return products
