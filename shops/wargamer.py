import aiohttp
import re
from bs4 import BeautifulSoup

SHOP = "wargamer"
BASE = "https://sklep.wargamer.pl"
SEARCH_URL = f"{BASE}/pl/szukaj?s=pokemon&page={{page}}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder", "ultra pro", "playmat",
    "one piece", "lorcana", "yu-gi-oh", "digimon", "magic the", "battle deck", "league battle",
    "rival battle", "v battle", "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk", "korean", "chiński",
    "chińsk", "chinese", "(chi)", "s-chinese", "ultra-pro", "segregator", "deck box", "alcove",
    "naruto", "star wars", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        page = 1
        while True:
            url = SEARCH_URL.format(page=page)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    break
                html = await resp.text()
            soup = BeautifulSoup(html, "lxml")
            items = soup.select(".product-miniature")
            if not items:
                break
            for item in items:
                a = item.select_one(".product-title a") or item.select_one("h2 a")
                if not a:
                    continue
                href = a.get("href", "")
                name = a.get_text(strip=True)
                if not name:
                    continue
                name_low = name.lower()
                if "pokemon" not in name_low and "pokémon" not in name_low:
                    continue
                if any(ex in name_low for ex in EXCLUDE):
                    continue
                pid_m = re.search(r'/(\d+)-', href)
                pid = pid_m.group(1) if pid_m else href
                if pid in seen:
                    continue
                seen.add(pid)
                price_el = item.select_one(".price")
                price = "brak"
                if price_el:
                    price_text = price_el.get_text().replace("\xa0","").replace(" ","")
                    m = re.search(r"(\d+[,.]\d+)", price_text)
                    if m:
                        price = m.group(1).replace(",", ".") + " zl"
                text = item.get_text(" ", strip=True).lower()
                available = ("dodaj" in text or "koszyk" in text) and "brak na stanie" not in text
                img_el = item.select_one("img")
                image = ""
                if img_el:
                    image = img_el.get("data-full-size-image") or img_el.get("data-src") or img_el.get("src") or ""
                products.append({
                    "id": f"wargamer_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": href,
                    "image": image,
                    "stock": None,
                    "available": available,
                })
            if not soup.select("a.next, a[rel=next]"):
                break
            page += 1
    print(f"[WARGAMER] {len(products)} produktow")
    return products
