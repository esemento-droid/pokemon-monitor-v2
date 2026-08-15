import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "poketrader"
URL = "https://poketrader.eu/pokemon-tcg-c-16.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
EXCLUDE = [
    "one piece", "japonsk", "japanese", "chinese", "china", "sleeve", "koszulk", "toploader",
    "album", "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "(jp)", "koreański",
    "koreańsk", "korean", "chiński", "chińsk", "(chi)", "ultra pro", "ultra-pro", "playmat",
    "portfolio", "binder", "segregator", "deck box", "alcove", "lorcana", "yu-gi-oh",
    "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]

async def fetch_page(session, page):
    url = URL if page == 1 else f"{URL}/s={page}"
    try:
        async with session.get(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None

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
        all_html = [html1]
        if max_page > 1:
            rest = await asyncio.gather(*[fetch_page(session, p) for p in range(2, max_page + 1)])
            all_html.extend(rest)
    for html in all_html:
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        for okno in soup.select(".Okno.OknoRwd"):
            div_id = okno.get("id", "")
            m = re.search(r"prd-\d+-(\d+)", div_id)
            if not m:
                continue
            pid = m.group(1)
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            link = okno.select_one("a[href*=-p-]")
            if not link:
                continue
            name = link.get("title", "") or link.get_text(strip=True)
            if not name or len(name) < 5:
                continue
            if any(ex in name.lower() for ex in EXCLUDE):
                continue
            href = link.get("href", "")
            price_el = okno.select_one(".CenaAktualna, .Cena")
            price = "brak"
            if price_el:
                pm = re.search(r"([\d\s]+[,.]\d+)", price_el.get_text())
                if pm:
                    price = pm.group(1).replace(" ", "").replace(",", ".") + " zl"
            classes = " ".join(okno.get("class", []))
            available = "BezZakupu" not in classes
            img = okno.select_one("img")
            image = ""
            if img:
                image = img.get("data-src-original") or img.get("src", "")
                if image and not image.startswith("http"):
                    image = "https://poketrader.eu/" + image
            products.append({"id": f"poketrader_{pid}", "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": 1 if available else 0, "available": available})
    print(f"[POKETRADER] {len(products)} produktow")
    return products
