import aiohttp
import re
from bs4 import BeautifulSoup

SHOP = "vinylcave"
BASE = "https://vinylcave.pl"
CAT_URL_FIRST = f"{BASE}/pl/c/Karty-kolekcjonerskie/462"
CAT_URL = f"{BASE}/pl/c/Karty-kolekcjonerskie/462/{{page}}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "sleeve", "koszulk", "toploader", "album", "portfolio", "binder", "ultra pro", "playmat",
    "japonsk", "japońsk", "japanese", "korean", "koreańsk", "one piece", "lorcana", "yu-gi-oh",
    "digimon", "magic the", "deck box", "memory game", "ravensburger", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "(jp)", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra-pro", "segregator", "alcove", "naruto", "star wars", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        page = 1
        max_page = 1
        while page <= max_page:
            url = CAT_URL_FIRST if page == 1 else CAT_URL.format(page=page)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        break
                    html = await resp.text()
            except:
                break
            soup = BeautifulSoup(html, "lxml")
            items = soup.select(".product-tile")
            if not items:
                break
            if page == 1:
                for pg_link in soup.select("a[href*='/462/']"):
                    pm = re.search(r"/462/(\d+)", pg_link.get("href", ""))
                    if pm:
                        mp = int(pm.group(1))
                        if mp > max_page:
                            max_page = mp
            for item in items:
                name_el = item.select_one(".product-tile__name")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name:
                    continue
                name_low = name.lower()
                if "pokemon" not in name_low and "pokémon" not in name_low:
                    continue
                if any(ex in name_low for ex in EXCLUDE):
                    continue
                link = item.select_one("a[href*='/pl/p/']")
                if not link:
                    continue
                href = link.get("href", "")
                pid_m = re.search(r"/(\d+)$", href)
                pid = pid_m.group(1) if pid_m else ""
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                price_el = item.select_one(".product-tile__price")
                price = "brak"
                if price_el:
                    price_text = price_el.get_text(strip=True).replace("\xa0", "").replace(" ", "")
                    m = re.search(r"(\d+[,.]\d+)", price_text)
                    if m:
                        price = m.group(1).replace(",", ".") + " zl"
                item_text = item.get_text(" ", strip=True).lower()
                available = "koszyk" in item_text or "dostępne" in item_text or "dostepne" in item_text
                img = item.select_one("img")
                image = ""
                if img:
                    src = img.get("src", "")
                    image = BASE + src if src.startswith("/") else src
                products.append({
                    "id": f"vinylcave_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": BASE + href if href.startswith("/") else href,
                    "image": image,
                    "stock": None,
                    "available": available,
                })
            page += 1
    print(f"[VINYLCAVE] {len(products)} produktow")
    return products
