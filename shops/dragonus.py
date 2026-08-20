"""
Scraper: dragonus.pl — direct aiohttp (no browser needed)
Platform: Shoper
Moved from NODRIVER to FAST (pure HTTP, no JS required)
"""
import asyncio
import re
import logging
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
SHOP = "dragonus"
BASE = "https://dragonus.pl"
CAT_URL = f"{BASE}/pl/c/Pokemon/315"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE = [
    "sleeves", "koszulk", "toploader", "playmat", "ultra pro", "one piece", "naruto",
    "dragon ball", "magic:", "mtg:", "lorcana", "yu-gi-oh", "portfolio", "pro-binder",
    "album", "deck box", "energii", "ygo", "academy", "accessory", "flip out",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk",
    "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese", "ultra-pro", "segregator",
    "alcove", "digimon", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set",
]


def _parse_html(pages_html):
    """Parse products from list of page HTMLs."""
    products = []
    seen = set()
    for page_html in pages_html:
        soup = BeautifulSoup(page_html, "lxml")
        for r in soup.select("td.even, td.odd"):
            name_el = r.select_one("span.productname")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            name_low = name.lower()
            if any(ex in name_low for ex in EXCLUDE):
                continue
            link = r.select_one('a[href*="/pl/p/"]')
            href = link["href"] if link and link.get("href") else ""
            pid_m = re.search(r'/(\d+)$', href)
            pid = pid_m.group(1) if pid_m else ""
            if not pid or pid in seen:
                continue
            seen.add(pid)
            url = BASE + href if href.startswith("/") else href
            img = r.select_one("img[data-src]") or r.select_one("img[src*=product]")
            image = ""
            if img:
                image = img.get("data-src") or img.get("src") or ""
                if image and not image.startswith("http"):
                    image = BASE + image
            price_el = r.select_one(".price em") or r.select_one("em")
            price = price_el.get_text(strip=True) if price_el else ""
            available = "basket/add" in str(r)
            products.append({
                "id": f"{SHOP}_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": url,
                "image": image,
                "stock": None,
                "available": available,
            })
    return products


async def get_products():
    """Main interface — pure aiohttp, parallel page fetch, via mobile proxy."""
    headers = {"User-Agent": USER_AGENT}
    proxy = "http://127.0.0.1:8888"

    async with aiohttp.ClientSession(headers=headers) as session:
        # Fetch first page to detect pagination
        async with session.get(CAT_URL, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status != 200:
                logger.error(f"[dragonus] HTTP {r.status}")
                return []
            html1 = await r.text()

        # Detect max page
        max_page = 1
        for m in re.findall(r'/pl/c/Pokemon/315/(\d+)', html1):
            pg = int(m)
            if pg > max_page:
                max_page = pg

        # Parallel fetch remaining pages
        async def fetch(url):
            try:
                async with session.get(url, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        return await resp.text()
            except Exception:
                pass
            return None

        other_urls = [f"{CAT_URL}/{pg}" for pg in range(2, max_page + 1)]
        other_pages = await asyncio.gather(*[fetch(u) for u in other_urls])

        pages_html = [html1] + [p for p in other_pages if p]

    products = _parse_html(pages_html)
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))
    print(f"[DRAGONUS] {len(products)} produktow")
    return products


if __name__ == "__main__":
    async def test():
        prods = await get_products()
        avail = [p for p in prods if p["available"]]
        print(f"Total: {len(prods)}, available: {len(avail)}")
        for p in prods[:10]:
            print(f"  {p['id']} | {p['name'][:50]} | {p['price']} | avail={p['available']}")
    asyncio.run(test())
