"""Merfolk.pl scraper - aiohttp (no PW needed, VPS IP OK)"""
import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

SHOP = "merfolk"
BASE = "https://sklep.merfolk.pl"
CAT_URL = BASE + "/category/POKEMON-TCG-345476?OfferPage={page}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
MAX_PAGES = 10

EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder", "ultra pro", "playmat",
    "one piece", "lorcana", "yu-gi-oh", "digimon", "czapka", "funko", "figurk", "plusz", "jpn",
    "chn", "kor", "japanese", "chinese", "korean", "battle deck", "league battle",
    "rival battle", "v battle", "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "(jp)", "chiński", "chińsk", "(chi)", "ultra-pro", "segregator",
    "deck box", "alcove", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figure set"
]


async def fetch_page(session, page):
    url = CAT_URL.format(page=page)
    for attempt in range(3):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()
        except Exception:
            if attempt < 2:
                await asyncio.sleep(1)
    return None


async def get_products():
    products = []
    seen = set()
    prev_ids = set()

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for pg in range(1, MAX_PAGES + 1):
            html = await fetch_page(session, pg)
            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")
            items = soup.select(".product-item")
            if not items:
                break

            # Detect repeated page (last page loops)
            page_ids = set()
            for item in items:
                title_el = item.select_one(".product-title a")
                if title_el:
                    page_ids.add(title_el.get("href", ""))
            if page_ids and page_ids == prev_ids:
                break
            prev_ids = page_ids

            for item in items:
                title_el = item.select_one(".product-title a")
                if not title_el:
                    continue
                name = title_el.get_text(strip=True)
                name_low = name.lower()
                if any(ex in name_low for ex in EXCLUDE):
                    continue

                href = title_el.get("href", "")
                pid_m = re.search(r'-s(\d+)', href)
                pid = pid_m.group(1) if pid_m else href
                if pid in seen:
                    continue
                seen.add(pid)

                # Price
                price_el = item.select_one(".product-price-wrap")
                price = "brak"
                if price_el:
                    price_text = price_el.get_text(strip=True).replace("\xa0", "").replace(" ", "")
                    m = re.search(r"(\d+[,.]\d+)", price_text)
                    if m:
                        price = m.group(1).replace(",", ".") + " zl"

                # Availability
                avail_el = item.select_one(".availability-num")
                available = avail_el is not None and "szt" in avail_el.get_text().lower()

                # Image
                img_el = item.select_one(".product-image-container img")
                image = img_el.get("src", "") if img_el else ""

                # URL
                url_prod = BASE + href.split("?")[0] if href.startswith("/") else href.split("?")[0]

                products.append({
                    "id": f"merfolk_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": url_prod,
                    "image": image,
                    "stock": None,
                    "available": available,
                })

    print(f"[MERFOLK] {len(products)} produktow")
    return products


if __name__ == "__main__":
    r = asyncio.run(get_products())
    avail = [p for p in r if p["available"]]
    print(f"  Available: {len(avail)}/{len(r)}")
    for p in r[:5]:
        print(f"  {p['id']}: {p['name'][:50]} - {p['price']} - {'AVAIL' if p['available'] else 'SOLD'}")
