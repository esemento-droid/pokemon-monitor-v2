"""
Scraper: strefamtg.pl
Platform: PrestaShop (behind Cloudflare)
Method: FlareSolverr + BeautifulSoup
Category: /2838-talie-i-zestawy-kart-pokemon (3 pages)
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
FLARESOLVERR_URL = "http://localhost:8191/v1"

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


async def fetch_flaresolverr(url):
    """Fetch URL via FlareSolverr to bypass Cloudflare."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"cmd": "request.get", "url": url, "maxTimeout": 30000}
            async with session.post(
                FLARESOLVERR_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                if data.get("status") == "ok":
                    return data.get("solution", {}).get("response", "")
    except Exception as e:
        print(f"[strefamtg] FlareSolverr error: {e}")
    return ""


async def get_products():
    products = []
    seen = set()

    for cat_path in CATEGORY_URLS:
        url = BASE_URL + cat_path
        html = await fetch_flaresolverr(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")

        # Check for CF block
        if "Just a moment" in soup.get_text()[:200]:
            print("[strefamtg] Cloudflare block via FlareSolverr")
            continue

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
