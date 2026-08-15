import aiohttp
import asyncio
import hashlib
import re
from bs4 import BeautifulSoup

SHOP = "hearts"
BASE = "https://hearts.pub"
SEARCH_URL = f"{BASE}/sklep/szukaj?s=pokemon&resultsPerPage=200"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}

EXCLUDE = ["battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean",
    "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "binder",
    "sleeve", "toploader", "album", "koszulk", "segregator",
    "deck box", "alcove",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto",
    "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz",
    "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"]


def solve_pow(token, diff):
    nonce = 0
    while True:
        h = hashlib.sha256(f"{token}|{nonce}".encode()).digest()
        bits = 0
        for byte in h:
            if byte == 0:
                bits += 8
            else:
                for b in range(7, -1, -1):
                    if (byte & (1 << b)) == 0:
                        bits += 1
                    else:
                        break
                break
        if bits >= diff:
            return nonce
        nonce += 1

async def solve_challenge(session):
    async with session.get(BASE, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        html = await resp.text()
    if "Weryfikacja" not in html or "nodea" not in html:
        return True
    token_m = re.search(r'token="([^"]+)"', html)
    diff_m = re.search(r"diff=(\d+)", html)
    if not token_m or not diff_m:
        return False
    token = token_m.group(1)
    diff = int(diff_m.group(1))
    nonce = await asyncio.get_event_loop().run_in_executor(None, solve_pow, token, diff)
    data = {"token": token, "nonce": str(nonce), "fp": '{"wd":0,"lang":2,"hc":4,"ch":1,"gl":"none"}'}
    async with session.post(f"{BASE}/__nodea/verify-js", data=data) as resp:
        j = await resp.json()
        return j.get("ok", False)

async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        ok = await solve_challenge(session)
        if not ok:
            print("[HEARTS] PoW failed")
            return []
        async with session.get(SEARCH_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                print(f"[HEARTS] HTTP {resp.status}")
                return []
            html = await resp.text()
        soup = BeautifulSoup(html, "lxml")
        for item in soup.select(".product-miniature"):
            a = item.select_one(".product-title a")
            if not a:
                continue
            href = a.get("href", "")
            if "pokemon" not in href.lower():
                continue
            pid_m = re.search(r"/([^/]+)$", href)
            pid = pid_m.group(1) if pid_m else "0"
            if pid in seen:
                continue
            seen.add(pid)
            name = a.get("title") or a.get_text(strip=True)
            price_el = item.select_one(".price")
            price = "brak"
            if price_el:
                m = re.search(r"(\d+[,.]\d+)", price_el.get_text())
                if m:
                    price = m.group(1).replace(",", ".") + " zl"
            text = item.get_text(" ", strip=True).lower()
            available = "brak towar" not in text
            img_el = item.select_one("img")
            image = ""
            if img_el:
                image = (img_el.get("data-full-size-image") or img_el.get("src") or img_el.get("data-src") or "").replace("home_default", "large_default")
            if any(ex in name.lower() for ex in EXCLUDE): continue

            products.append({"id": f"hearts_{pid}", "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
    print(f"[HEARTS] {len(products)} produktow")
    return products
