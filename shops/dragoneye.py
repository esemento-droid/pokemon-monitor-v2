"""
Scraper: dragoneye.pl (osCommerce)
Categories: /pokemon-tcg-c-16_261.html + /przedsprzedaz-c-75.html
Selector: .listing .boxProdSmall (NOT .product-wrapper which is recommendations)
Dynamic pagination (?page=N)
"""

import asyncio
import re

import aiohttp
from bs4 import BeautifulSoup

SHOP = "dragoneye"
BASE = "https://dragoneye.pl"
CATEGORIES = [
    f"{BASE}/pokemon-tcg-c-16_261.html",
    f"{BASE}/przedsprzedaz-c-75.html",
]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE = [
    "sleeve", "koszulk", "playmat", "album", "binder",
    "toploader", "holder", "protector", "japonsk", "japanese", "chinese",
]

INCLUDE = ["pokemon", "pokémon"]


def _parse_price(text: str) -> str:
    text = text.strip()
    text = re.sub(r'[\s\xa0]', '', text)
    text = text.replace('zł', '').replace('PLN', '').strip()
    text = text.replace(',', '.')
    if text:
        return f"{text} zl"
    return ""


async def get_products() -> list[dict]:
    products = []
    seen_ids = set()

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        for cat_url in CATEGORIES:
            async with session.get(cat_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                text = await resp.text(encoding="utf-8", errors="ignore")

            # Detect pagination
            page_nums = re.findall(r'page=(\d+)', text)
            max_page = max([int(x) for x in page_nums]) if page_nums else 1

            all_html = [text]

            for page in range(2, max_page + 1):
                sep = '&' if '?' in cat_url else '?'
                page_url = f"{cat_url}{sep}page={page}"
                try:
                    async with session.get(page_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        all_html.append(await resp.text(encoding="utf-8", errors="ignore"))
                except Exception:
                    break

            for html in all_html:
                soup = BeautifulSoup(html, "lxml")
                boxes = soup.select(".listing .boxProdSmall")

                for box in boxes:
                    # ID from data-idproduktu
                    pid_el = box.select_one("[data-idproduktu]")
                    pid = pid_el.get("data-idproduktu", "") if pid_el else ""
                    if not pid or pid in seen_ids:
                        continue

                    # Name
                    name_el = box.select_one("p.nazwa a")
                    name = name_el.get_text(strip=True) if name_el else ""
                    if not name:
                        continue

                    name_lower = name.lower()

                    # INCLUDE filter for przedsprzedaz (mixed category)
                    if "przedsprzedaz" in cat_url:
                        if not any(inc in name_lower for inc in INCLUDE):
                            continue

                    # EXCLUDE filter
                    if any(ex in name_lower for ex in EXCLUDE):
                        continue

                    seen_ids.add(pid)

                    # URL
                    url = name_el.get("href", "") if name_el else ""
                    if url and not url.startswith("http"):
                        url = BASE + "/" + url.lstrip("/")

                    # Image
                    img = box.select_one("img")
                    image = ""
                    if img:
                        src = img.get("src", "")
                        if src and not src.startswith("http"):
                            src = BASE + "/" + src.lstrip("/")
                        image = src

                    # Price
                    price_el = box.select_one(".cenaBrutto")
                    price = _parse_price(price_el.get_text(strip=True)) if price_el else ""

                    # Availability
                    box_text = box.get_text(" ", strip=True).lower()
                    available = "niedostępn" not in box_text

                    products.append({
                        "id": f"{SHOP}_{pid}",
                        "name": name,
                        "price": price,
                        "shop": SHOP,
                        "url": url,
                        "image": image,
                        "stock": "",
                        "available": available,
                    })

    return products


if __name__ == "__main__":
    import time
    start = time.time()
    prods = asyncio.run(get_products())
    elapsed = time.time() - start
    avail = [p for p in prods if p["available"]]
    print(f"Total: {len(prods)}, Available: {len(avail)}, Time: {elapsed:.1f}s")
    for p in prods:
        status = "V" if p["available"] else "X"
        print(f"  {status} {p['name'][:55]} | {p['price']}")
