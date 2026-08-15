import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "redraft"
BASE = "https://redraft.pl"
URL = BASE + "/pl/menu/pokemon-tcg-176.html?limit=100"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126"}
EXCLUDE = [
    "china", "chinese", "japonsk", "japanese", "korean", "sleeve", "koszulk", "toploader",
    "album", "world championships deck", "battle deck", "league battle", "rival battle",
    "v battle", "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "(jp)",
    "koreański", "koreańsk", "chiński", "chińsk", "(chi)", "ultra pro", "ultra-pro", "playmat",
    "portfolio", "binder", "segregator", "deck box", "alcove", "lorcana", "one piece",
    "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]

async def fetch_page(session, page):
    url = URL if page == 1 else f"{URL}&page={page}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None

def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    for p in soup.select(".product[data-product_id]"):
        pid = p.get("data-product_id", "")
        if not pid:
            continue
        link = p.select_one("a[title]")
        if not link:
            continue
        name = link.get("title", "").strip()
        if not name or len(name) < 5:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        href = link.get("href", "")
        price_el = p.select_one("[class*=price]")
        price = "brak"
        if price_el:
            pm = re.search(r"(\d+[,.]\d+)", price_el.get_text())
            if pm:
                price = pm.group(1).replace(",", ".") + " zl"
        text = p.get_text(" ", strip=True).lower()
        available = ("koszyk" in text or "dodaj" in text) and "brak" not in text
        img = p.select_one("img")
        image = ""
        if img:
            image = img.get("src", "")
            if image and not image.startswith("http"):
                image = BASE + image
        products.append({"id": f"redraft_{pid}", "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
    return products

async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        page = 1
        while True:
            html = await fetch_page(session, page)
            if not html:
                break
            page_prods = parse_page(html)
            if not page_prods:
                break
            for prod in page_prods:
                if prod["id"] not in seen_ids:
                    seen_ids.add(prod["id"])
                    products.append(prod)
            if len(page_prods) < 50:
                break
            page += 1
    print(f"[REDRAFT] {len(products)} produktow")
    return products
