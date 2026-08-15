import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "cardfan"
BASE_URL = "https://www.cardfan.pl/pl/c/Zestawy/69"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BASE = "https://www.cardfan.pl"
EXCLUDE = [
    "japonsk", "japanese", "korean", "koreansk", "chinsk", "chinese", "sleeves", "koszulk",
    "toploader", "puste pude", "energy", "kart energy", "battle deck", "league battle",
    "rival battle", "v battle", "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "(jp)", "koreański", "koreańsk", "chiński", "chińsk", "(chi)",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "pro-binder", "album", "segregator",
    "deck box", "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]

async def fetch_page(session, url):
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
    for p in soup.select("[data-product-id]"):
        pid = p.get("data-product-id", "")
        if not pid:
            continue
        classes = " ".join(p.get("class", []))
        available = "product_inactive" not in classes
        name_el = p.select_one("span.productname")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        price_el = p.select_one(".price")
        price = "brak"
        if price_el:
            m = re.search(r"(\d+[,.]\d+)", price_el.get_text(strip=True))
            if m:
                price = m.group(1).replace(",", ".") + " zl"
        link_el = p.select_one("a.prodname, a[title]")
        url = ""
        if link_el and link_el.get("href"):
            url = link_el["href"]
            if not url.startswith("http"):
                url = BASE + url
        img_el = p.select_one("img[alt][src*=environment]")
        image = ""
        if img_el:
            image = img_el.get("src", "")
            if image and not image.startswith("http"):
                image = BASE + image
        products.append({"id": f"cardfan_{pid}", "name": name, "price": price, "shop": SHOP, "url": url, "image": image, "stock": None, "available": available})
    return products

async def get_products():
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        first = await fetch_page(session, BASE_URL)
        if not first:
            return []
        pages = set(re.findall(r"/Zestawy/69/(\d+)", first))
        tasks = [fetch_page(session, f"{BASE_URL}/{n}") for n in pages if n != "1"]
        extra = await asyncio.gather(*tasks)
    all_html = [first] + list(extra)
    seen = set()
    products = []
    for html in all_html:
        if not html:
            continue
        for p in parse_page(html):
            if p["id"] not in seen:
                seen.add(p["id"])
                products.append(p)
    print(f"[CARDFAN] {len(products)} produktow")
    return products
