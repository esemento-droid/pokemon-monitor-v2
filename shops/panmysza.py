import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "panmysza"
BASE = "https://panmysza.pl"
CATEGORY = "/pl/c/Pokemon-TCG/55"
CAT_ID = "55"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
EXCLUDE = [
    "ultra pro", "ultra-pro", "album", "koszulk", "toploader", "sleeves", "mata ", "playmat",
    "one piece", "lorcana", "digimon", "naruto", "dragon ball", "dragon shield", "(jp)",
    "(chi)", "japanese", "chinese", "world championship", "wcs deck", "league battle deck",
    "accessory bundle", "figure set", "dream painting", "brilliant fantasy", "gift box",
    "rival battle", "v battle", "battle academy", "japoński", "japońsk", "koreański",
    "koreańsk", "korean", "chiński", "chińsk", "portfolio", "pro-binder", "segregator", "deck box",
    "alcove", "yu-gi-oh", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle",
    "figurk"
]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        url = f"{BASE}{CATEGORY}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return products
                html = await resp.text()
        except:
            return products
        soup = BeautifulSoup(html, "lxml")
        pages = {1}
        for a in soup.select("a"):
            href = a.get("href", "")
            m = re.search(rf'/{CAT_ID}/(\d+)', href)
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages)
        def parse_page(s):
            results = []
            for tile in s.select(".product"):
                link = tile.select_one('a[href*="/pl/p/"]')
                if not link:
                    continue
                href = link.get("href", "")
                img = tile.select_one("img")
                name = img.get("alt", "").strip() if img else link.get_text(strip=True)
                if any(ex in name.lower() for ex in EXCLUDE):
                    continue
                text = tile.get_text(" ", strip=True)
                price = "brak"
                m2 = re.search(r'Cena:\s*(\d[\d\s]*[,.]\d+)\s*z', text)
                if m2:
                    pt = m2.group(1).replace(" ", "").replace(",", ".")
                    try:
                        price = f"{float(pt):.2f} zl"
                    except:
                        pass
                parts = href.strip("/").split("/")
                pid = parts[-1] if parts else ""
                image = ""
                if img:
                    image = img.get("data-src") or img.get("src") or ""
                    if image and not image.startswith("http"):
                        image = BASE + image
                    if "base64" in image:
                        image = ""
                available = "koszyk" in text.lower()
                results.append({"id": f"panmysza_{pid}", "name": name, "price": price, "shop": SHOP, "url": BASE + href, "image": image, "stock": None, "available": available})
            return results
        products.extend(parse_page(soup))
        if max_page > 1:
            async def fetch_page(pn):
                try:
                    async with session.get(f"{BASE}{CATEGORY}/{pn}", timeout=aiohttp.ClientTimeout(total=15)) as r:
                        return await r.text() if r.status == 200 else ""
                except:
                    return ""
            htmls = await asyncio.gather(*[fetch_page(p) for p in range(2, max_page + 1)])
            for h in htmls:
                if h:
                    products.extend(parse_page(BeautifulSoup(h, "lxml")))
    final = []
    for p in products:
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        final.append(p)
    print(f"[PANMYSZA] {len(final)} produktow")
    return final
