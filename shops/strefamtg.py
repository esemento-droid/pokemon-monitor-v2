"""
Scraper: strefamtg.pl
Platform: PrestaShop (NO Cloudflare — direct aiohttp works fine)
Method: aiohttp + BeautifulSoup (parallel pages)
Category: /2838-talie-i-zestawy-kart-pokemon (3 pages)
Group: FAST (moved from SLOW — no CF bypass needed)
"""
import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

SHOP = "strefamtg.pl"
BASE_URL = "https://strefamtg.pl"
CATEGORY_URLS = [
    "/2838-talie-i-zestawy-kart-pokemon",
    "/2838-talie-i-zestawy-kart-pokemon?page=2",
    "/2838-talie-i-zestawy-kart-pokemon?page=3",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "pro-binder", "ultra pro", "ultra-pro",
    "playmat", "mata", "klaser", "portfolio", "deck box",
    "one piece", "lorcana", "yu-gi-oh", "digimon", "magic the", "naruto", "star wars",
    "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz", "force of will",
    "riftbound",
    "japonsk", "japońsk", "japanese", "japan", "(jp)", "korean", "koreańsk", "korea",
    "chiński", "chińsk", "chinese", "china", "(chi)", "s-chinese",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy",
    "segregator", "alcove", "zeszyt", "puzzle", "figurk", "figure set",
    "szczoteczk", "pojedynek pokemonow",
]


async def _fetch_page(session, url):
    """Fetch single page with retry."""
    for attempt in range(2):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    return await resp.text()
        except Exception:
            if attempt == 0:
                await asyncio.sleep(2)
    return ""


async def get_products():
    products = []
    seen = set()

    urls = [BASE_URL + path for path in CATEGORY_URLS]

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Parallel fetch all pages
        pages = await asyncio.gather(*[_fetch_page(session, url) for url in urls])

    for html in pages:
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")

        for item in soup.select("article.product-miniature, div.product-miniature, [class*=product-miniature]"):
            name_el = item.select_one("h2 a, h3 a, .product-title a, a.product-name, a[class*=title]")
            if not name_el:
                name_el = item.select_one("a[href*='/']")
            if not name_el:
                continue

            name = name_el.get_text(strip=True)
            if not name or len(name) < 5:
                continue

            name_low = name.lower()
            if any(ex in name_low for ex in EXCLUDE):
                continue

            # Must contain pokemon/pokémon
            if "pokemon" not in name_low and "pokémon" not in name_low:
                continue

            href = name_el.get("href", "")
            if href and not href.startswith("http"):
                href = BASE_URL + href

            # PID from URL
            pid_m = re.search(r"-(\d+)\.html|/(\d+)-", href)
            pid = (pid_m.group(1) or pid_m.group(2)) if pid_m else href.split("/")[-1]
            if not pid or pid in seen:
                continue
            seen.add(pid)

            # Price
            price = "brak"
            price_el = item.select_one(".price, [class*=price]")
            if price_el:
                price_text = price_el.get_text(strip=True)
                m = re.search(r"(\d[\d\s]*[,.]\d+)", price_text)
                if m:
                    p = m.group(1).replace(" ", "").replace(",", ".")
                    try:
                        price = f"{float(p):.2f} PLN"
                    except (ValueError, TypeError):
                        pass

            # Availability
            available = True
            item_text = item.get_text(" ", strip=True).lower()
            if "brak" in item_text or "niedostępn" in item_text or "wyczerpan" in item_text:
                available = False

            # Image
            image = ""
            img_el = item.select_one("img")
            if img_el:
                image = img_el.get("data-src") or img_el.get("src") or ""
                if image and not image.startswith("http"):
                    image = BASE_URL + image

            products.append({
                "id": f"strefamtg_{pid}",
                "name": name,
                "price": price,
                "shop": SHOP,
                "url": href,
                "image": image,
                "stock": None,
                "available": available,
            })

    print(f"[STREFAMTG] {len(products)} produktow")
    return products
