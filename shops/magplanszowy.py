import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "magplanszowy"
BASE = "https://magplanszowy.pl"
SEARCH_URL = BASE + "/pl/searchquery/POK+TCG/1/phot/5"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126"}
EXCLUDE = [
    "sleeve", "koszulk", "toploader", "album", "portfolio", "binder", "UP -", "ultra pro",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra-pro", "playmat", "segregator", "deck box", "alcove", "lorcana", "one piece",
    "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]

async def fetch_page(session, page):
    url = BASE + f"/pl/searchquery/POK+TCG/{page}/phot/5"
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
    for a in soup.select("a[href*='/pl/p/']"):
        name = a.get_text(strip=True)
        if not name or len(name) < 5:
            continue
        if "POK TCG" not in name and "Pokemon" not in name:
            continue
        if any(ex.lower() in name.lower() for ex in EXCLUDE):
            continue
        href = a.get("href", "")
        m = re.search(r"/(\d+)$", href)
        if not m:
            continue
        pid = m.group(1)
        parent = a.parent
        for _ in range(6):
            cls = " ".join(parent.get("class", []))
            if "product" in cls:
                break
            parent = parent.parent
        text = parent.get_text(" ", strip=True)
        avail = "Do koszyka" in text
        pm = re.search(r"(\d+[,.]\d+)\s*z", text)
        price = pm.group(1).replace(",", ".") + " zl" if pm else "brak"
        img_el = parent.select_one("img[data-src], img[src]")
        image = ""
        if img_el:
            image = img_el.get("data-src") or img_el.get("src", "")
            if image and not image.startswith("http"):
                image = BASE + image
        url_prod = href if href.startswith("http") else BASE + href
        products.append({"id": f"magplanszowy_{pid}", "name": name, "price": price, "shop": SHOP, "url": url_prod, "image": image, "stock": None, "available": avail})
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
            m = re.search(r"POK\+TCG/(\d+)/", a.get("href", ""))
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages) if pages else 1
        all_html = [html1]
        if max_page > 1:
            rest = await asyncio.gather(*[fetch_page(session, p) for p in range(2, max_page + 1)])
            all_html.extend(rest)
    for html in all_html:
        if not html:
            continue
        for prod in parse_page(html):
            if prod["id"] not in seen_ids:
                seen_ids.add(prod["id"])
                products.append(prod)
    print(f"[MAGPLANSZOWY] {len(products)} produktow")
    return products
