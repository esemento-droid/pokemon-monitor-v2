import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup

SHOP = "flamberg"
URL = "https://flamberg.com.pl/pl/menu/boostery-i-boxy-688"
BASE = "https://flamberg.com.pl"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
EXCLUDE = [
    "japonsk", "japanese", "korean", "chinsk", "chinese", "sleeves", "koszulk", "toploader",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "(jp)", "koreański",
    "koreańsk", "chiński", "chińsk", "(chi)", "ultra pro", "ultra-pro", "playmat", "portfolio",
    "pro-binder", "album", "segregator", "deck box", "alcove", "lorcana", "one piece", "yu-gi-oh",
    "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]

async def get_products():
    products = []
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    print(f"[flamberg] HTTP {resp.status}")
                    return []
                html = await resp.text()
    except Exception as e:
        print(f"[flamberg] Error: {e}")
        return []
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    for p in soup.select(".product"):
        pid_el = p.select_one("[data-product-id]")
        pid = pid_el.get("data-product-id", "") if pid_el else ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        text = p.get_text(" ", strip=True)
        imgs = [i for i in p.select("img") if i.get("alt", "") and len(i.get("alt", "")) > 5]
        name = imgs[0].get("alt", "") if imgs else ""
        if not name:
            continue
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        price = "brak"
        m = re.search(r"(\d+[,.]\d+)\s*PLN", text)
        if m:
            price = m.group(1).replace(",", ".") + " zl"
        available = "chwilowo niedost" not in text.lower()
        link = ""
        for a in p.select("a[href]"):
            h = a.get("href", "")
            if h and "/pl/" in h and h != "#" and "menu" not in h:
                link = h if h.startswith("http") else BASE + h
                break
        img = ""
        for i in imgs:
            src = i.get("src", "")
            if src and "1px" not in src and "gif" not in src:
                img = src if src.startswith("http") else BASE + src
                break
        products.append({"id": f"flamberg_{pid}", "name": name, "price": price, "shop": SHOP, "url": link, "image": img, "stock": None, "available": available})
    print(f"[FLAMBERG] {len(products)} produktow")
    return products
