import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

SHOP = "kimland"
BASE = "https://www.kimland.pl"
CAT_URL = f"{BASE}/pl/c/Pokemony/242"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
EXCLUDE = [
    "ultra pro", "ultra-pro", "album", "koszulk", "toploader", "sleeves", "playmat", "pro-binder",
    "one piece", "japonsk", "japanese", "korean", "chinese", "figurk", "spinner", "maskotk",
    "pluszak", "puzzle", "klocki", "mega construx", "funko", "lampk", "zegar", "radio",
    "pas clip", "pokeball", "poke ball", "battle deck", "league battle", "rival battle",
    "v battle", "world championship", "wcs deck", "wcs ", "battle academy", "japoński",
    "japońsk", "(jp)", "koreański", "koreańsk", "chiński", "chińsk", "(chi)", "portfolio",
    "segregator", "deck box", "alcove", "lorcana", "yu-gi-oh", "digimon", "naruto",
    "star wars", "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "figure set"
]
INCLUDE = ["tcg", "kart", "booster", "blister", "tin", "etb", "display", "elite trainer", "saszetk"]


def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    for tile in soup.select(".product_view-extended"):
        name_el = tile.select_one(".productname")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        if not any(inc in name.lower() for inc in INCLUDE):
            continue

        link = tile.select_one('a[href*="/pl/p/"]')
        if not link:
            continue
        href = link.get("href", "")
        pid = href.strip("/").split("/")[-1] if href else ""
        if not pid:
            continue
        url_prod = f"{BASE}{href}" if not href.startswith("http") else href

        price = "brak"
        price_el = tile.select_one("em.color")
        if price_el:
            pt = price_el.get_text(strip=True).replace("\xa0", "").replace(" ", "")
            m = re.search(r"([\d,]+)\s*z", pt)
            if m:
                price = m.group(1).replace(",", ".") + " zl"
        if price == "brak":
            price_div = tile.select_one(".price")
            if price_div:
                m2 = re.search(r"([\d\s,]+[,.]\d+)\s*z", price_div.get_text())
                if m2:
                    pt = m2.group(1).replace(" ", "").replace(",", ".")
                    price = f"{float(pt):.2f} zl"

        img = tile.select_one("img")
        image = ""
        if img:
            image = img.get("data-src") or img.get("src") or ""
            if image and not image.startswith("http"):
                image = BASE + image
            if "base64" in image:
                image = ""

        text = tile.get_text(" ", strip=True).lower()
        available = "koszyk" in text

        products.append({
            "id": f"kimland_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url_prod,
            "image": image,
            "stock": None,
            "available": available,
        })
    return products, soup


async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS, connector=aiohttp.TCPConnector(ssl=False)) as session:
        async with session.get(CAT_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()

        batch, soup = parse_page(html)
        for p in batch:
            if p["id"] not in seen:
                seen.add(p["id"])
                products.append(p)

        # Dynamic pagination
        pages = {1}
        for a in soup.select("a"):
            href = a.get("href", "")
            m = re.search(r"/242/(\d+)", href)
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages)

        if max_page > 1:
            async def fetch_page(page):
                url = f"{CAT_URL}/{page}"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                        if r.status != 200:
                            return ""
                        return await r.text()
                except:
                    return ""

            htmls = await asyncio.gather(*[fetch_page(p) for p in range(2, max_page + 1)])
            for h in htmls:
                if not h:
                    continue
                batch, _ = parse_page(h)
                for p in batch:
                    if p["id"] not in seen:
                        seen.add(p["id"])
                        products.append(p)

    print(f"[KIMLAND] {len(products)} produktow")
    return products
