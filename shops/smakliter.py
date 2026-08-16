"""
Scraper: smakliter.pl
Search URL: /?filter=Pokemon+tcg (sorted by newest)
Static HTML, single page (30 products max).
Cel: łapanie nowych dropów (NEW_LISTING).
"""

import aiohttp
from bs4 import BeautifulSoup

SHOP = "smakliter"
BASE = "https://smakliter.pl"
SEARCH_URL = (
    f"{BASE}/?catId=&pageNo=0&flag=&menuFilter=&featureValueId="
    "&sortingField=CreateDate_Desc&pageSize=30&available=false"
    "&filter=Pokemon+tcg"
    "&ProductNameFilter=&AS_Text_autor=&AS_Text_kod_paskowy="
    "&AS_Text_isbn=&AS_Text_seriacykl=&AS_Text_wydawca="
    "&AS_Flag_nowosc=false&AS_Flag_zapowiedz=false"
)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE = [
    "sleeves", "koszulk", "playmat", "album", "pro-binder", "toploader",
    "holder", "protector", "ultra pro", "ultra-pro", "portfolio", "segregator",
    "deck box", "alcove", "one piece", "lorcana", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood",
    "dragon shield", "weiss schwarz", "battle deck", "league battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "japanese", "japoński", "japońsk", "(jp)", "koreański", "korean",
    "chiński", "chinese", "(chi)", "figurk", "puzzle", "zeszyt",
]


async def get_products() -> list[dict]:
    products = []
    seen = set()

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        async with session.get(SEARCH_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                print(f"[SMAKLITER] HTTP {resp.status}")
                return []
            html = await resp.text()

    soup = BeautifulSoup(html, "lxml")
    containers = soup.select("div.productContainer.slide")

    for c in containers:
        # Link
        a = c.find("a", href=True)
        if not a:
            continue
        href = a.get("href", "")
        if href in seen:
            continue
        seen.add(href)

        url = href if href.startswith("http") else f"{BASE}{href}"

        # ID from URL (produkt-XXXXXXX)
        pid = ""
        if ",produkt-" in href:
            pid = href.split(",produkt-")[-1]
        if not pid:
            pid = href

        # Name
        name_div = c.select_one(".productContainerDataName .linkButtonAlt")
        name = name_div.get_text(strip=True) if name_div else ""
        if not name:
            img = c.select_one("img")
            if img:
                name = (img.get("alt", "") or img.get("title", "")).replace("Opakowanie ", "")
        if not name:
            continue

        # Exclude
        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue

        # Price filter (<10 PLN = single)
        price_el = c.select_one(".productContainerDataFinalPrice")
        price = price_el.get_text(" ", strip=True) if price_el else "brak"
        try:
            price_val = float(price.replace("\xa0", "").replace(" zł", "").replace(" ", "").replace(",", "."))
            if price_val < 10:
                continue
        except (ValueError, AttributeError):
            pass

        # Image
        img = c.select_one("img.lazy")
        image = img.get("data-src", "") if img else ""

        # Availability
        unavail = c.select_one(".productUnavailable")
        available = unavail is None

        products.append({
            "id": f"{SHOP}_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": 1 if available else 0,
            "available": available,
        })

    print(f"[SMAKLITER] {len(products)} produktow")
    return products


if __name__ == "__main__":
    import asyncio
    import time
    start = time.time()
    prods = asyncio.run(get_products())
    elapsed = time.time() - start
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}, Time: {elapsed:.1f}s")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:60]:60} | {p['price']}")
