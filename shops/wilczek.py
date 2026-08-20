"""
Scraper: wilczek.poznan.pl — standalone patchright (JS render, VPS IP)
Site is SPA — products load via JavaScript, plain HTTP returns empty page.
No bot protection, just needs JS execution. Uses VPS IP (no proxy).
SHOP_GROUP = VERY_SLOW (browser launch per scan)
"""
import re
import os
import logging
import asyncio
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
SHOP = "wilczek"
URL = "https://wilczek.poznan.pl/product/search?query=Pokemon+tcg+&filter=1"
BASE = "https://wilczek.poznan.pl"
SCAN_TIMEOUT = 60

EXCLUDE = [
    "japonsk", "japanese", "korean", "chinsk", "chinese", "sleeves", "koszulk", "toploader",
    "album", "brilliant fantasy", "dark crystal", "true mystery", "battle academy", "wcd",
    "world championship deck", "trainer's toolkit", "trainer toolkit", "battle deck",
    "league battle", "rival battle", "v battle", "wcs deck", "wcs ", "japoński", "japońsk",
    "(jp)", "koreański", "koreańsk", "chiński", "chińsk", "(chi)", "ultra pro", "ultra-pro",
    "playmat", "portfolio", "pro-binder", "segregator", "deck box", "alcove", "lorcana",
    "one piece", "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering",
    "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz", "force of will",
    "riftbound", "zeszyt", "puzzle", "figurk", "figure set",
]


def _parse_html(html):
    """Parse products from rendered HTML."""
    products = []
    soup = BeautifulSoup(html, "lxml")
    for item in soup.select(".product"):
        text = item.get_text(" ", strip=True)
        a = item.select_one("a[href]")
        if not a:
            continue
        href = a.get("href", "")
        if not href or href == "#":
            continue
        if not href.startswith("http"):
            href = BASE + href
        pm = re.search(r"(\d[\d ]*[,.]\d+)\s*z", text)
        price = "brak"
        if pm:
            price = pm.group(1).replace(" ", "").replace(",", ".") + " zl"
        parts = re.split(r"(Duza ilosc|Ostatnie sztuki|Brak|\d+[,.]\d+\s*z)", text, flags=re.IGNORECASE)
        name = parts[0].strip().rstrip(".")
        if not name or len(name) < 5:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        available = "duza ilosc" in text.lower() or "ostatnie sztuki" in text.lower()
        pid = re.search(r"/([^/]+)\.html", href)
        pid = pid.group(1) if pid else href.split("/")[-1]
        img_el = item.select_one("img")
        image = ""
        if img_el:
            image = img_el.get("src") or img_el.get("data-src") or ""
            if image and not image.startswith("http"):
                image = BASE + image
        products.append({
            "id": f"wilczek_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": href,
            "image": image,
            "stock": None,
            "available": available,
        })
    return products


async def get_products():
    """Standalone patchright — VPS IP, no proxy, JS render."""
    from patchright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
        )
        try:
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            await page.goto(URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            html = await page.content()
        finally:
            await browser.close()

    products = _parse_html(html)
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))
    print(f"[WILCZEK] {len(products)} produktow")
    return products
