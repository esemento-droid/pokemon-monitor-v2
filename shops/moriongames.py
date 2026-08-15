import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "moriongames"
URL = "https://www.moriongames.pl/pokemon-m-69.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
EXCLUDE = [
    "wcd deck", "world championship", "album", "koszulki", "sleeves", "battle deck",
    "league battle", "rival battle", "v battle", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk", "korean", "chiński",
    "chińsk", "chinese", "(chi)", "s-chinese", "ultra pro", "ultra-pro", "playmat",
    "portfolio", "pro-binder", "toploader", "segregator", "deck box", "alcove", "lorcana",
    "one piece", "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering",
    "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz", "force of will",
    "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]

async def fetch_page(session, page):
    url = URL if page == 1 else f"{URL}/s={page}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
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
        for a in soup1.select("a[href*='/s=']"):
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
            link = okno.select_one('a[href*=-p-]')
            if not link:
                continue
            name = link.get("title", "") or link.text.strip()
            if not name:
                img = okno.select_one("img[alt]")
                name = img.get("alt", "") if img else ""
            if not name:
                continue
            name_lower = name.lower()
            if any(ex in name_lower for ex in EXCLUDE):
                continue
            if "pokemon" not in name_lower and "pokémon" not in name_lower:
                continue
            href = link.get("href", "")
            price_el = okno.select_one(".CenaAktualna")
            price = "brak"
            if price_el:
                pm = re.search(r"([\d]+[,][\d]{2})", price_el.text)
                if pm:
                    price = f"{pm.group(1)} zl"
            classes = " ".join(okno.get("class", []))
            available = "BezZakupu" not in classes
            img = okno.select_one("img[data-src-original]")
            image = ""
            if img:
                src = img.get("data-src-original", "")
                image = f"https://www.moriongames.pl/{src}" if src and not src.startswith("http") else src
            products.append({
                "id": f"moriongames_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": href,
                "image": image,
                "stock": 1 if available else 0,
                "available": available,
            })
    print(f"[MORIONGAMES] {len(products)} produktow")
    return products
