"""
Scraper: wilczek.poznan.pl — uses cf_solver (patchright) for JS rendering
Site is SPA — products load via JavaScript, plain HTTP returns empty page.
Uses existing cf_solver browser (shared context pool) = no extra Chrome.
"""
import re
import logging
import asyncio
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
SHOP = "wilczek"
URL = "https://wilczek.poznan.pl/product/search?query=Pokemon+tcg+&filter=1"
BASE = "https://wilczek.poznan.pl"

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
    """Uses cf_solver to render JS page — no extra Chrome process."""
    from cf_solver import solve

    html = await solve(URL, timeout=30)
    if not html:
        logger.error("[wilczek] cf_solver returned None")
        return []

    products = _parse_html(html)
    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))
    print(f"[WILCZEK] {len(products)} produktow")
    return products
