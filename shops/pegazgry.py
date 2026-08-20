import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "pegazgry"
MARK_MISSING_AS_OOS = True  # Site hides OOS from listing — mark missing products as unavailable for RESTOCK detection
BASE = "https://pegaz-gry.pl"
URL = BASE + "/22-pokemon-tcg-gra-karciana-sklep-bydgoszcz"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126"}
EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder", "ultra pro", "UP -",
    "deck box", "playmat", "energy", "energia", "single", "karta pojedyncza", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk",
    "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese", "ultra-pro", "segregator",
    "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]

async def fetch_page(session, page):
    url = URL if page == 1 else f"{URL}?page={page}"
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
    for art in soup.select("article.product-miniature"):
        pid = art.get("data-id-product", "")
        if not pid:
            continue
        name_el = art.select_one(".product-title a")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name or len(name) < 5:
            continue
        if any(ex.lower() in name.lower() for ex in EXCLUDE):
            continue
        href = name_el.get("href", "") if name_el else ""
        price_el = art.select_one(".price")
        price = "brak"
        if price_el:
            pm = re.search(r"(\d+[,.]\d+)", price_el.get_text())
            if pm:
                price = pm.group(1).replace(",", ".") + " zl"
        btn = art.select_one("button[data-button-action]")
        available = btn is not None and not btn.has_attr("disabled")
        img_el = art.select_one("img")
        image = ""
        if img_el:
            image = img_el.get("data-full-size-image-url") or img_el.get("data-src") or img_el.get("src", "")
        products.append({"id": f"pegazgry_{pid}", "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
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
        for a in soup1.select("a[href*=page]"):
            m = re.search(r"page=(\d+)", a.get("href", ""))
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
    print(f"[PEGAZGRY] {len(products)} produktow")
    return products
