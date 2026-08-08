import aiohttp
from bs4 import BeautifulSoup
import asyncio

SHOP = "tcgtrener.pl"
BASE = "https://tcgtrener.pl"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}

CATEGORIES = [
    "/pl/c/Karty-Pokemon/43",
    "/pl/c/Puszki-i-EX-Boxy/88",
    "/pl/c/Mega-Evolutions/49",
    "/pl/c/Prismatic-Evolutions/38",
    "/pl/c/Destined-Rivals/45",
    "/pl/c/Journey-Together/39",
    "/pl/c/Perfect-Order/70",
    "/pl/c/Phantasmal-Flames/53",
    "/pl/c/Chaos-Rising/77",
    "/pl/c/Pitch-Black/80",
    "/pl/c/Ascended-Heroes/56",
    "/pl/c/30th-Celebration/76",
]

async def fetch_page(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None

def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    tiles = soup.select("product-tile")
    for tile in tiles:
        pid = tile.get("product-id", "")
        if not pid:
            continue
        name = tile.get("name", "")
        price = tile.get("price", "")
        currency = tile.get("currency", "PLN")
        a = tile.select_one("a")
        href = a.get("href", "") if a else ""
        if href and not href.startswith("http"):
            href = BASE + href
        aria = a.get("aria-label", "") if a else ""
        available = "niedost" not in aria.lower()
        img = tile.select_one("img")
        image = ""
        if img:
            image = img.get("src", "")
            if image and not image.startswith("http"):
                image = BASE + image
        price_str = f"{price} {currency}" if price else "brak"
        products.append({
            "id": pid,
            "name": name,
            "price": price_str,
            "shop": SHOP,
            "url": href,
            "image": image,
            "stock": "Dostepny" if available else "Niedostepny",
            "available": available,
        })
    return products

async def get_products():
    products = []
    seen_ids = set()

    # Build all URLs (first page of each category)
    urls = [BASE + cat for cat in CATEGORIES]

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Parallel fetch all first pages
        pages_html = await asyncio.gather(*[fetch_page(session, url) for url in urls])

        # Check for additional pages and fetch them
        extra_urls = []
        for i, html in enumerate(pages_html):
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            nxt = soup.select_one("link[rel='next']")
            if nxt:
                for p in range(2, 5):
                    extra_urls.append(f"{BASE}{CATEGORIES[i]}/{p}")

        if extra_urls:
            extra_pages = await asyncio.gather(*[fetch_page(session, url) for url in extra_urls])
            pages_html = list(pages_html) + list(extra_pages)

    for html in pages_html:
        if not html:
            continue
        page_products = parse_page(html)
        for prod in page_products:
            if prod["id"] in seen_ids:
                continue
            seen_ids.add(prod["id"])
            products.append(prod)

    print(f"[{SHOP}] FINAL: {len(products)} produktow")
    return products
