import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

SHOP = "karcianybunkier"
BASE = "https://karcianybunkier.pl"
CATS = [
    f"{BASE}/httpspokevcrplangielskie-c-16-18html-c-16_18.html",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
EXCLUDE = [
    "china", "chinese", "japonsk", "japanese", "japan", "korean", "one piece", "ultra pro",
    "album", "sleeve", "koszulk", "toploader", "binder", "playmat", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "(jp)", "koreański", "koreańsk", "chiński",
    "chińsk", "(chi)", "ultra-pro", "portfolio", "segregator", "deck box", "alcove", "lorcana",
    "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]


def parse_page(html):
    products = []
    soup = BeautifulSoup(html, "lxml")
    for tile in soup.select(".Okno.OknoRwd"):
        classes = " ".join(tile.get("class", []))
        available = "BezZakupu" not in classes

        # Name from img alt
        img = tile.select_one("img")
        name = img.get("alt", "").strip() if img else ""
        if not name:
            continue

        if any(ex in name.lower() for ex in EXCLUDE):
            continue

        # URL + PID
        link = tile.select_one('a[href*="-p-"]')
        if not link:
            continue
        href = link.get("href", "")
        m = re.search(r"-p-(\d+)", href)
        if not m:
            continue
        pid = m.group(1)

        # Price
        text = tile.get_text(" ", strip=True)
        pm = re.search(r"(\d+[,.]\d+)\s*z", text)
        price = pm.group(1).replace(",", ".") + " zl" if pm else "brak"

        # Image
        image = ""
        if img:
            image = img.get("data-src-original") or img.get("data-src") or img.get("src") or ""
            if "loader" in image or "base64" in image:
                image = ""
            if image and not image.startswith("http"):
                image = f"{BASE}/{image}"
            if image:
                image = image.replace(" ", "%20")

        products.append({
            "id": f"karcianybunkier_{pid}",
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
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for cat_url in CATS:
            try:
                async with session.get(cat_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
            except:
                continue

            batch = parse_page(html)
            for p in batch:
                if p["id"] not in seen:
                    seen.add(p["id"])
                    products.append(p)

    print(f"[KARCIANYBUNKIER] {len(products)} produktow")
    return products
