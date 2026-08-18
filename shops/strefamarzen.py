import asyncio
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

SHOP = "strefamarzen"
BASE = "https://strefamarzen.pl"
SEARCH_URL = f"{BASE}/pl/search?text=Pokemon+tcg"
EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder", "ultra pro", "playmat",
    "japonsk", "japońsk", "japanese", "korean", "koreańsk", "one piece", "lorcana", "yu-gi-oh",
    "digimon", "magic the", "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy", "(jp)", "chiński", "chińsk",
    "chinese", "(chi)", "s-chinese", "ultra-pro", "segregator", "deck box", "alcove", "naruto",
    "star wars", "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz",
    "force of will", "riftbound", "zeszyt", "puzzle", "figurk", "figure set"
]


def _parse_html(html):
    """Parse products from HTML."""
    products = []
    seen = set()
    soup = BeautifulSoup(html, "lxml")
    for wrapper in soup.select(".product__content_wrapper"):
        link = wrapper.select_one("a.product__name")
        if not link:
            continue
        name = link.get_text(strip=True)
        name_low = name.lower()
        if "pokemon" not in name_low and "pokémon" not in name_low:
            continue
        if any(ex in name_low for ex in EXCLUDE):
            continue
        href = link.get("href", "")
        pid_m = re.search(r"-(\d+)(?:\?|$)", href)
        pid = pid_m.group(1) if pid_m else ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        price_el = wrapper.select_one(".price.--main")
        price = "brak"
        if price_el:
            pt = price_el.get_text(strip=True).replace("\xa0", "")
            m = re.search(r"(\d+[,.]\d+)", pt)
            if m:
                price = m.group(1).replace(",", ".") + " zl"
        parent = wrapper.parent
        text = parent.get_text(" ", strip=True).lower() if parent else ""
        available = "niedost" not in text
        full_url = href if href.startswith("http") else BASE + href
        image = ""
        img_container = wrapper.parent if wrapper.parent else wrapper
        img_el = img_container.select_one("img[src*='/products/'], img[data-src*='/products/']")
        if not img_el:
            img_el = img_container.select_one("img")
        if img_el:
            image = img_el.get("data-src", "") or img_el.get("src", "") or ""
            if image and not image.startswith("http"):
                if image.startswith("/"):
                    image = BASE + image
                else:
                    image = BASE + "/" + image
            if image and ("logo" in image.lower() or "placeholder" in image.lower() or image.startswith("data:")):
                image = ""
        products.append({"id": f"strefamarzen_{pid}", "name": name, "price": price, "shop": SHOP, "url": full_url, "image": image, "stock": None, "available": available})
    return products


async def scan_with_page(page):
    """Chrome Pool interface — gets ready page, returns products."""
    await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(5000)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(3000)
    html = await page.content()
    products = _parse_html(html)
    print(f"[STREFAMARZEN] {len(products)} produktow")
    return products


async def get_products():
    """Legacy interface — fallback/testing."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120")
            return await scan_with_page(page)
        finally:
            await browser.close()
