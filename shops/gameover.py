import aiohttp
import re
from bs4 import BeautifulSoup

SHOP = "gameover"
BASE = "https://www.krakow.gameover.pl"
SEARCH_URL = f"{BASE}/sklep/index.php?d=szukaj&szukaj=Pokemon+tcg"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
EXCLUDE = [
    "sleeves", "koszulk", "toploader", "album", "pro-binder", "ultra pro", "playmat", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk",
    "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese", "ultra-pro", "portfolio",
    "segregator", "deck box", "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood", "flesh and blood",
    "dragon shield", "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle",
    "figurk", "figure set"
]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(SEARCH_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
    soup = BeautifulSoup(html, "lxml")
    for item in soup.select(".product"):
        text = item.get_text(" ", strip=True)
        links = item.select("a[href]")
        href = ""
        name = ""
        for l in links:
            h = l.get("href", "")
            if "produkt" in h or "towar" in h or "pokemon" in h.lower():
                href = h
                name = l.get_text(strip=True)
                break
        if not name:
            name = text.split(" zł")[0].strip() if "zł" in text else text[:60]
            # remove price from name
            name = re.sub(r'\d+[,.]\d+\s*zł.*', '', name).strip()
        name_low = name.lower()
        if "pokemon" not in name_low and "pokémon" not in name_low:
            continue
        if any(ex in name_low for ex in EXCLUDE):
            continue
        pid = re.search(r'(\d+)', href).group(1) if href and re.search(r'(\d+)', href) else name[:20]
        if pid in seen:
            continue
        seen.add(pid)
        price = "brak"
        m = re.search(r"(\d+[,.]\d+)\s*zł", text)
        if m:
            price = m.group(1).replace(",", ".") + " zl"
        available = "dostępne" in text.lower() or "dostepne" in text.lower()
        img = item.select_one("img")
        image = ""
        if img:
            # Try data-src first (lazy loading), then src
            src = img.get("data-src", "") or img.get("src", "")
            if src and not src.startswith("http"):
                if src.startswith("/"):
                    image = BASE + src
                else:
                    image = BASE + "/" + src
            else:
                image = src
        url_prod = BASE + "/" + href if href and not href.startswith("http") else href
        products.append({"id": f"gameover_{pid}", "name": name, "price": price, "shop": SHOP, "url": url_prod, "image": image, "stock": None, "available": available})
    print(f"[GAMEOVER] {len(products)} produktow")
    return products
