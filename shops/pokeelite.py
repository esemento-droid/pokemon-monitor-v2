from urllib.parse import quote
import aiohttp
from bs4 import BeautifulSoup
import re
import asyncio

BASE = "https://pokeelite.pl/pokemon-c-26.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

EXCLUDE = ["battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean",
    "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "pro-binder",
    "sleeves", "toploader", "album", "koszulk", "segregator",
    "deck box", "alcove",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto",
    "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz",
    "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"]


async def fetch_page(session, page):
    url = BASE if page == 1 else f"{BASE}/s={page}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None

def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    boxes = soup.select(".ElementListingRamka")
    for b in boxes:
        name_el = b.select_one(".ProdCena h3 a")
        if not name_el:
            continue
        name = name_el.text.strip()
        href = name_el.get("href", "")
        pid = href.split("-p-")[-1].replace(".html", "") if "-p-" in href else ""
        if not pid:
            continue
        price_el = b.select_one(".CenaAktualna, .Cena")
        price_raw = price_el.text.strip() if price_el else "brak"
        price = price_raw.replace(" ", "").replace("Â ", "").replace("zł", " PLN")
        img_el = b.select_one("img[data-src-original]")
        image = ""
        if img_el:
            src = img_el.get("data-src-original", "")
            image = "https://pokeelite.pl/" + quote(src, safe="/") if src and not src.startswith("http") else src
        mag = b.select_one(".MagazynIlosc")
        mag_style = mag.get("style", "") if mag else ""
        available = "--ilosc: 0" not in mag_style and mag is not None and price_el is not None
        if any(ex in name.lower() for ex in EXCLUDE): continue

        products.append({"id": f"pokeelite_{pid}", "name": name, "price": price, "shop": "pokeelite", "url": href, "image": image, "stock": 1 if available else 0, "available": available})
    return products

async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html1 = await fetch_page(session, 1)
        if not html1:
            return []
        soup1 = BeautifulSoup(html1, "lxml")
        pages = set()
        for a in soup1.select("a[href]"):
            m = re.search(r"/s=(\d+)", a.get("href", ""))
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages) if pages else 1
        for prod in parse_page(html1):
            if prod["id"] not in seen_ids:
                seen_ids.add(prod["id"])
                products.append(prod)
        if max_page > 1:
            rest = await asyncio.gather(*[fetch_page(session, p) for p in range(2, max_page + 1)])
            for html in rest:
                if not html:
                    continue
                for prod in parse_page(html):
                    if prod["id"] not in seen_ids:
                        seen_ids.add(prod["id"])
                        products.append(prod)
    return products
