import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re

SHOP = "proshop"
URL = "https://www.proshop.pl/Pokemon"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
EXCLUDE = ["portfolio", "album", "sleeve", "koszulk", "toploader", "binder", "ultra pro", "ultrapro", "plush", "figure", "figurk", "playset", "carry case", "clip", "play 'n"]


async def get_products():
    products = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=UA)
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(12)
        html = await page.content()
        await browser.close()
    soup = BeautifulSoup(html, "lxml")
    items = soup.select("li.site-productlist-item")
    for item in items:
        name_el = item.select_one("h2[product-display-name]")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name or len(name) < 5:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        pid_el = item.select_one("input[name=productId]")
        pid = pid_el.get("value", "") if pid_el else ""
        if not pid:
            continue
        price_el = item.select_one(".site-currency-lg")
        price = "brak"
        if price_el:
            pt = price_el.get_text(strip=True)
            pm = re.search(r"([\d,.]+)", pt)
            if pm:
                price = pm.group(1).replace(".", "").replace(",", ".") + " zl"
        link = item.select_one("a.site-product-link")
        href = ""
        if link:
            href = "https://www.proshop.pl" + link.get("href", "")
        btn = item.select_one("button.site-btn-green")
        available = btn is not None
        img = item.select_one("img[src]")
        image = ""
        if img:
            src = img.get("src", "")
            if src.startswith("/"):
                image = "https://www.proshop.pl" + src
            else:
                image = src
        products.append({"id": "proshop_" + pid, "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
    print("[PROSHOP]", len(products), "produktow")
    return products
