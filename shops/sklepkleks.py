"""
Scraper: sklepkleks.com
Platform: Custom (PrestaShop-like) behind Cloudflare
Method: FlareSolverr + BeautifulSoup
Category: k879 (Karty Pokemon) — 24 products
Selectors: div.product-a → a[href], img[src*=galerie], price in text
"""
import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

SHOP = "sklepkleks"
SCAN_TIMEOUT = 180  # CF solver needs time (semaphore queue + 55s solve)
BASE = "https://sklepkleks.com"
CAT_URL = f"{BASE}/k879,do-zabawy-gry-i-puzzle-karty-pokemon.html"
FLARESOLVERR_URL = "http://localhost:8191/v1"

EXCLUDE = [
    "singl", "karta pokemon", "psa ", "cgc ", "slab ", "losow",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk", "korean",
    "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "pro-binder", "sleeves",
    "toploader", "album", "koszulk", "segregator", "deck box", "alcove",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set",
    "na sztuki", "złot", "czarn", "vmax kart", "karta gx", "karta ex",
    "gamegenic", "koszulka na karty", "labyrinth",
]


async def get_products():
    products = []
    seen = set()

    # Fetch category page via FlareSolverr (bypasses Cloudflare)
    html = ""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"cmd": "request.get", "url": CAT_URL, "maxTimeout": 55000}
            async with session.post(
                FLARESOLVERR_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "ok":
                        html = data.get("solution", {}).get("response", "")
    except Exception as e:
        print(f"[sklepkleks] FlareSolverr error: {e}")

    if not html:
        print("[SKLEPKLEKS] 0 produktow (FlareSolverr failed)")
        return []

    soup = BeautifulSoup(html, "lxml")

    # Product containers: div.product-a
    items = soup.select("div.product-a")
    if not items:
        # Fallback: any div containing galerie image + price
        for div in soup.find_all("div"):
            if div.select_one("img[src*='galerie']") and "zł" in div.get_text():
                items.append(div)

    for item in items:
        # Link with product URL
        link = item.select_one("a[href*=',']")
        if not link:
            continue
        href = link.get("href", "")

        # PID from URL: pXXXXX,name.html
        pid_m = re.search(r"p(\d+),", href)
        if not pid_m:
            continue
        pid = pid_m.group(1)
        if pid in seen:
            continue
        seen.add(pid)

        # Full URL
        full_url = href if href.startswith("http") else BASE + "/" + href

        # Name from link title or text
        name = link.get("title", "").strip()
        if not name:
            name = link.get_text(strip=True)
        if not name or len(name) < 5:
            continue

        # Must be Pokemon-related
        name_low = name.lower()
        if "pokemon" not in name_low and "pokémon" not in name_low:
            continue

        # Exclude unwanted
        if any(ex in name_low for ex in EXCLUDE):
            continue

        # Price from item text
        price = "brak"
        item_text = item.get_text(" ", strip=True)
        price_m = re.search(r"([\d]+[.,][\d]{2})\s*zł", item_text)
        if price_m:
            price = price_m.group(1).replace(",", ".") + " zl"

        # Image
        image = ""
        img_el = item.select_one("img[src*='galerie']")
        if img_el:
            src = img_el.get("data-src") or img_el.get("src") or ""
            if src:
                if src.startswith("http"):
                    image = src
                elif src.startswith("/"):
                    image = BASE + src
                else:
                    image = BASE + "/" + src

        # Availability: "koszyk" or "dodaj" = available
        available = "koszyk" in item_text.lower() or "dodaj" in item_text.lower()

        products.append({
            "id": f"sklepkleks_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": full_url,
            "image": image,
            "stock": None,
            "available": available,
        })

    print(f"[SKLEPKLEKS] {len(products)} produktow")
    return products
