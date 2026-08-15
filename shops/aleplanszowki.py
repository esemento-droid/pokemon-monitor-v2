import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup

SHOP = "aleplanszowki"
BASE = "https://aleplanszowki.pl"
URL = BASE + "/search?controller=search&s=Pokemon+&order=product.date_add.desc"
EXCLUDE = [
    "flesh and blood", "flesh & blood", "gamegenic", "clip'n'go", "clip n go", "plusz",
    "figurk", "japonsk", "japanese", "korean", "chinese", "chinsk", "sleeve", "koszulk",
    "toploader", "album", "ultra pro", "binder", "battle deck", "league battle",
    "rival battle", "v battle", "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "(jp)", "koreański", "koreańsk", "chiński", "chińsk", "(chi)",
    "ultra-pro", "playmat", "portfolio", "segregator", "deck box", "alcove", "lorcana",
    "one piece", "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering",
    "dragon shield", "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle",
    "figure set"
]


async def fetch_page(session, page):
    url = f"{URL}&page={page}" if page > 1 else URL
    async with session.get(url) as resp:
        if resp.status != 200:
            return []
        html = await resp.text()
    return parse_page(html)


def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    for item in soup.select("article.product-miniature"):
        pid = item.get("data-id-product", "")
        if not pid:
            continue
        name_el = item.select_one(".product-title a")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name or len(name) < 5:
            continue
        name_low = name.lower()
        if not any(k in name_low for k in ["pokemon", "pok\u00e9mon", "pikachu", "charizard", "evolution"]):
            continue
        if any(ex in name_low for ex in EXCLUDE):
            continue
        price_el = item.select_one(".price")
        price = "brak"
        if price_el:
            pt = price_el.get_text(strip=True)
            pm = re.search(r"(\d+[,.]\d+)", pt)
            if pm:
                price = pm.group(1).replace(",", ".") + " zl"
        avail_el = item.select_one(".product-availability")
        avail_text = avail_el.get_text(strip=True).lower() if avail_el else ""
        btn = item.select_one("button[data-button-action]")
        available = "brak" not in avail_text and "niedost" not in avail_text
        if btn and btn.has_attr("disabled"):
            available = False
        href = ""
        if name_el:
            href = name_el.get("href", "")
            if href and not href.startswith("http"):
                href = BASE + href
        img_el = item.select_one("img")
        image = ""
        if img_el:
            image = img_el.get("data-full-size-image-url") or img_el.get("data-src") or img_el.get("src") or ""
            if image and not image.startswith("http"):
                image = BASE + image
        products.append({
            "id": f"aleplanszowki_{pid}",
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
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126"}
    async with aiohttp.ClientSession(headers=headers) as session:
        # First page to detect total pages
        async with session.get(URL) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
        products = parse_page(html)
        # Detect pages
        soup = BeautifulSoup(html, "lxml")
        pages = set()
        for a in soup.select(".pagination a, a[href*=page]"):
            m = re.search(r"page=(\d+)", a.get("href", ""))
            if m:
                pages.add(int(m.group(1)))
        extra_pages = [p for p in pages if p > 1]
        if extra_pages:
            tasks = [fetch_page(session, p) for p in sorted(extra_pages)]
            results = await asyncio.gather(*tasks)
            for r in results:
                products.extend(r)
    print(f"[ALEPLANSZOWKI] {len(products)} produktow")
    return products
