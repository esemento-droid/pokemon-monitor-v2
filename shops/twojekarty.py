import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

SHOP = "twojekarty"
BASE = "https://twojekarty.pl"
CAT_URL_FIRST = f"{BASE}/pokemon-tcg-c-10.html"
CAT_URL_PAGE = f"{BASE}/pokemon-tcg-c-10.html/s={{page}}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "sleeve", "koszulk", "toploader", "album", "portfolio", "binder", "ultra pro", "playmat",
    "figurk", "zabawk", "plusz", "japonsk", "japońsk", "japanese", "korean", "koreańsk",
    "chiński", "chińsk", "chinese", "jpn", "chn", "kor", "lorcana", "one piece", "magic the",
    "yu-gi-oh", "digimon", "dragon ball", "japan", "china", "jpn", "chn", "kor", "korea",
    "stadium", "deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs ", "battle academy", "(jp)", "(chi)", "ultra-pro", "segregator", "alcove", "naruto",
    "star wars", "flesh & blood", "flesh and blood", "dragon shield", "weiss schwarz",
    "force of will", "riftbound", "zeszyt", "puzzle", "figure set"
]

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        page = 1
        max_page = 1
        while page <= max_page:
            url = CAT_URL_FIRST if page == 1 else CAT_URL_PAGE.format(page=page)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        break
                    html = await resp.text()
            except:
                break
            soup = BeautifulSoup(html, "lxml")
            items = soup.select("[id^=\"prd-\"]")
            if not items:
                break
            # detect max page
            if page == 1:
                for pg_link in soup.select("a[href*='c-10']"):
                    pg_m = __import__("re").search(r"/s=(\d+)", pg_link.get("href",""))
                    if pg_m:
                        mp = int(pg_m.group(1))
                        if mp > max_page:
                            max_page = mp
            for item in items:
                link = item.select_one(".ProdCena h3 a") or item.select_one("a[href*='-p-']")
                if not link:
                    continue
                name = link.get("title") or link.get_text(strip=True)
                if not name:
                    continue
                name_low = name.lower()
                if any(ex in name_low for ex in EXCLUDE):
                    continue
                pass  # category is already Pokemon TCG
                href = link.get("href", "")
                pid_m = re.search(r'-p-(\d+)', href)
                pid = pid_m.group(1) if pid_m else ""
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                price_el = item.select_one(".CenaAktualna")
                price = "brak"
                if price_el:
                    price_text = price_el.get_text(strip=True).replace("\xa0", "").replace(" ", "")
                    m = re.search(r"(\d+[,.]\d+)", price_text)
                    if m:
                        price = m.group(1).replace(",", ".") + " zl"
                bez = item.select_one(".BezZakupu")
                avail_text = item.get_text(" ", strip=True).lower()
                available = bez is None and "niedost" not in avail_text and "brak" not in avail_text
                img = item.select_one("img.Zdjecie")
                image = ""
                if img:
                    src = img.get("data-src-original") or img.get("src") or ""
                    if src and "loader" not in src:
                        image = src if src.startswith("http") else f"{BASE}/{src}"
                products.append({
                    "id": f"twojekarty_{pid}",
                    "name": name,
                    "price": price,
                    "shop": SHOP,
                    "url": href,
                    "image": image,
                    "stock": None,
                    "available": available,
                })
            page += 1
    print(f"[TWOJEKARTY] {len(products)} produktow")
    return products
