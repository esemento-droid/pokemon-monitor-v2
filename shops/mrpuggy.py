import aiohttp
from bs4 import BeautifulSoup
import asyncio

SHOP = "mrpuggy"
BASE = "https://mrpuggy.pl"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

CATEGORIES = [
    ("/pl/c/Pokemon-TCG-produkty/364", 12),
    ("/pl/c/Pokemon-TCG-serie/338", 10),
    ("/pl/c/Pokemon-przedsprzedaz/156", 5),
]

async def fetch_page(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=True, max_redirects=5, proxy="http://127.0.0.1:8888") as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None

async def get_products():
    products = []
    seen_ids = set()

    # Build all page URLs
    urls = []
    for cat, max_pages in CATEGORIES:
        for page in range(1, max_pages + 1):
            url = f"{BASE}{cat}" if page == 1 else f"{BASE}{cat}/{page}"
            urls.append(url)

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        pages_html = []
        for i in range(0, len(urls), 2):
            batch = await asyncio.gather(*[fetch_page(session, url) for url in urls[i:i+2]])
            pages_html.extend(batch)
            await asyncio.sleep(0.5)

    for html in pages_html:
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        for tile in soup.select("product-tile"):
            pid = tile.get("product-id")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            name = (tile.get("name") or "").strip()
            if not name:
                continue
            name_lower = name.lower()
            if "pokemon" not in name_lower and "pok\xe9mon" not in name_lower:
                continue

            price_val = tile.get("price", "0")
            price = f"{price_val} PLN" if price_val else "brak"

            a = tile.select_one("a")
            href = a.get("href", "") if a else ""
            url = f"{BASE}{href}" if href.startswith("/") else href

            img_el = tile.select_one("img")
            image = ""
            if img_el:
                image = img_el.get("src") or img_el.get("data-src", "")
                if image and image.startswith("/"):
                    image = BASE + image

            txt = tile.get_text(" ", strip=True).lower()
            available = "koszyk" in txt or "dodaj" in txt

            products.append({
                "id": f"mrpuggy_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": url,
                "image": image,
                "stock": 1 if available else 0,
                "available": available,
            })

    print(f"[MRPUGGY] {len(products)} produktow")
    return products
