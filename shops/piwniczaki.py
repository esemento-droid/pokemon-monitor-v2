"""
Scraper: piwniczaki — direct aiohttp (no browser needed)
Platform: RedCart-like
Moved from NODRIVER to FAST (pure HTTP, no JS required)
"""
import asyncio
import logging
import re
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
SHOP = "piwniczaki"
BASE_URL = "https://www.sklep-piwniczaki.pl"
CAT_URL = f"{BASE_URL}/pokemon-tcg"
MAX_PAGES = 5
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "portfolio", "pro-binder",
    "playmat", "ultra pro", "ultra-pro", "segregator", "deck box", "alcove",
    "one piece", "lorcana", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "dragon shield", "weiss schwarz",
    "force of will", "riftbound", "battle deck", "league battle", "rival battle",
    "v battle", "world championship", "wcs deck", "battle academy",
    "japanese", "japońsk", "korean", "koreańsk", "chinese", "chiński",
    "zeszyt", "puzzle", "figurk", "figure set",
]


def _parse_page(html):
    """Parse products from single page HTML."""
    products = []
    soup = BeautifulSoup(html, "lxml")
    for box in soup.select(".c-product-box"):
        name_el = box.select_one(".c-product-box__title")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name or len(name) < 5:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue

        price_el = box.select_one(".c-product-box__price-value")
        price_raw = price_el.get_text(strip=True) if price_el else ""
        price = f"{price_raw} PLN" if price_raw else "brak"

        link_el = box.select_one("a[href]")
        href = link_el.get("href", "") if link_el else ""
        if href and not href.startswith("http"):
            href = BASE_URL + href

        img_el = box.select_one("img")
        image = ""
        if img_el:
            image = img_el.get("data-src") or img_el.get("data-lazy") or img_el.get("src") or ""
            if image and not image.startswith("http"):
                image = BASE_URL + image

        pid_el = box.select_one("[data-product-id]")
        pid = pid_el.get("data-product-id", "") if pid_el else ""
        if not pid:
            # fallback: from URL
            m = re.search(r"-(\d+)\.html", href)
            pid = m.group(1) if m else ""
        if not pid:
            continue

        avail_el = box.select_one(".c-avaibility")
        avail_class = avail_el.get("class", []) if avail_el else []
        available = not any("--none" in c for c in avail_class)

        products.append({
            "id": f"piwniczaki_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": href,
            "image": image,
            "stock": 1 if available else 0,
            "available": available,
        })
    return products


async def get_products():
    """Main interface — pure aiohttp, no browser."""
    products = []
    seen_ids = set()
    headers = {"User-Agent": USER_AGENT}

    async with aiohttp.ClientSession(headers=headers) as session:
        pages_html = []
        urls = [CAT_URL] + [f"{CAT_URL}/name_asc/{p}" for p in range(2, MAX_PAGES + 1)]
        proxy = "http://127.0.0.1:8888"

        # Fetch with retry — proxy first, fallback direct
        async def fetch(url):
            for attempt, px in enumerate([proxy, proxy, None]):
                try:
                    kwargs = {"timeout": aiohttp.ClientTimeout(total=20)}
                    if px:
                        kwargs["proxy"] = px
                    async with session.get(url, **kwargs) as r:
                        if r.status == 200:
                            text = await r.text()
                            if ".c-product-box" in text or len(text) > 5000:
                                return text
                        if attempt < 2:
                            await asyncio.sleep(1)
                except Exception:
                    if attempt < 2:
                        await asyncio.sleep(1)
            return None

        results = await asyncio.gather(*[fetch(u) for u in urls])

        for html in results:
            if not html:
                continue
            page_products = _parse_page(html)
            for p in page_products:
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    products.append(p)

    products.sort(key=lambda x: (x.get("available", False), x.get("name", "")))
    print(f"[PIWNICZAKI] {len(products)} produktow")
    return products
