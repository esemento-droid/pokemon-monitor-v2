import asyncio
import time

SCAN_DELAY = 600
import re
import aiohttp
from bs4 import BeautifulSoup

SHOP = "am76"
BASE = "https://am76.pl"
SEARCH_URL = BASE + "/wyszukiwarka?komenda=wyszukiwarka&szukana=Pokemon%20tcg&sort=data_dodania%20DESC&p={page}"
PREORDER_URL = BASE + "/przedsprzedaz"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = ["album", "sleeve", "koszulk", "toploader", "binder", "ultra pro", "playmat"]

PROXY = "http://127.0.0.1:8888"

async def fetch_page(session, url):
    async with session.get(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=30), proxy=PROXY) as resp:
        if resp.status != 200:
            return ""
        raw = await resp.read()
        return raw.decode("windows-1250", errors="ignore")

def parse_products(html, seen_ids):
    products = []
    soup = BeautifulSoup(html, "lxml")
    panels = soup.select("div.panel.panel-default")
    for panel in panels:
        footer = panel.select_one(".panel-footer")
        if not footer:
            continue
        # Full name from tooltip
        link = footer.select_one("a[href*=produkt]")
        if not link:
            continue
        name = link.get("data-original-title", "")
        if not name:
            name_el = footer.select_one(".name")
            name = name_el.get_text(strip=True) if name_el else ""
        # clean prefix
        name = re.sub(r"^Wi.cej informacji o ", "", name)
        if not name or len(name) < 5:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        # ID from href
        href = link.get("href", "")
        m = re.search(r":(\d+)", href)
        if not m:
            continue
        pid = m.group(1)
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        # Price
        price_el = footer.select_one(".price")
        price = "brak"
        if price_el:
            pt = price_el.get_text(strip=True)
            if pt:
                price = pt + " zl"
        # Availability
        cart_btn = footer.select_one("a.btn-primary")
        available = cart_btn is not None and "Koszyk" in cart_btn.get_text()
        # Image
        img = panel.select_one("img")
        image = ""
        if img:
            src = img.get("src", "")
            if src.startswith("/"):
                image = BASE + src
            elif src:
                image = src
        # URL
        product_url = BASE + "/" + href if not href.startswith("http") else href
        products.append({"id": "am76_" + pid, "name": name, "price": price, "shop": SHOP, "url": product_url, "image": image, "stock": None, "available": available})
    return products

async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Fetch pages sequentially to avoid rate-limit
        for pg in range(1, 4):
            html = await fetch_page(session, SEARCH_URL.format(page=pg))
            if html:
                if 'zbyt duza liczbe' in html:
                    print('[AM76] Rate-limited, stopping')
                    break
                products.extend(parse_products(html, seen_ids))
            await asyncio.sleep(2)
        # Also fetch preorder page
        await asyncio.sleep(2)
        pre_html = await fetch_page(session, PREORDER_URL)
        if pre_html:
            products.extend(parse_products(pre_html, seen_ids))
    print(f"[AM76] {len(products)} produktow")
    return products
