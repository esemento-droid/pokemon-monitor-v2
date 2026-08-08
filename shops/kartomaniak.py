import aiohttp
from bs4 import BeautifulSoup
import asyncio

BASE_URL = "https://kartomaniak.pl/pl/c/Pokemon-TCG/38"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}

async def fetch_page(session, page):
    url = BASE_URL if page == 1 else f"{BASE_URL}/{page}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None

def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    tiles = soup.find_all("product-tile")
    for tile in tiles:
        pid = tile.get("product-id")
        if not pid:
            continue
        name = (tile.get("name") or "").strip()
        if not name:
            continue
        price_val = tile.get("price", "0")
        price = f"{price_val} PLN"
        avail_el = tile.select_one(".product-tile__availability-value")
        available = avail_el is not None and "_inactive" not in " ".join(avail_el.get("class", []))
        link_el = tile.select_one("a[href*='/pl/p/']")
        url_prod = f"https://kartomaniak.pl{link_el['href']}" if link_el and link_el.get("href") else ""
        img_el = tile.select_one("img")
        image = img_el.get("src", "") if img_el else ""
        if image and image.startswith("/"):
            image = f"https://kartomaniak.pl{image}"
        products.append({
            "id": f"kartomaniak-{pid}",
            "name": name,
            "price": price,
            "shop": "kartomaniak",
            "url": url_prod,
            "image": image,
            "stock": "",
            "available": available,
        })
    return products

def get_max_page(html):
    soup = BeautifulSoup(html, "lxml")
    import re
    pages = set()
    for a in soup.select("a[href*='/38/']"):
        m = re.search(r"/38/(\d+)", a.get("href", ""))
        if m:
            pages.add(int(m.group(1)))
    # also check .pagination
    for a in soup.select(".pagination a, a.page-link"):
        m = re.search(r"/(\d+)$", a.get("href", ""))
        if m:
            pages.add(int(m.group(1)))
    return max(pages) if pages else 1

async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Fetch page 1 to detect total pages
        html1 = await fetch_page(session, 1)
        if not html1:
            return []
        max_page = get_max_page(html1)
        # Parse page 1
        for prod in parse_page(html1):
            if prod["id"] not in seen_ids:
                seen_ids.add(prod["id"])
                products.append(prod)
        # Fetch remaining pages in parallel
        if max_page > 1:
            pages_html = await asyncio.gather(*[fetch_page(session, p) for p in range(2, max_page + 1)])
            for html in pages_html:
                if html is None:
                    continue
                for prod in parse_page(html):
                    if prod["id"] in seen_ids:
                        continue
                    seen_ids.add(prod["id"])
                    products.append(prod)
    return products
