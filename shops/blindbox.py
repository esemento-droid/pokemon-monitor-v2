import asyncio
import re
import aiohttp
from bs4 import BeautifulSoup

SHOP = "blindbox"
BASE = "https://www.blindbox.pl"
CAT_URL = f"{BASE}/merchandise/karty-przetargowe/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
EXCLUDE = ["sleeve", "koszulk", "toploader", "playmat", "album", "portfolio", "binder", "ultra pro", "one piece", "naruto", "dragon ball", "lorcana", "yu-gi-oh", "digimon"]

async def get_products():
    products = []
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(CAT_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    print(f"[blindbox] HTTP {resp.status}")
                    return []
                html = await resp.text()
    except Exception as e:
        print(f"[blindbox] Error: {e}")
        return []
    soup = BeautifulSoup(html, "lxml")
    for prod in soup.select(".produktM"):
        links = prod.select('a[href*="pokemon"]')
        if not links:
            continue
        href = links[0].get("href", "")
        pid_m = re.search(r'/([^/]+).html$', href)
        pid = pid_m.group(1) if pid_m else ""
        if not pid:
            continue
        name_el = prod.select_one("h2")
        name = ""
        if name_el:
            spans = name_el.select("span")
            if len(spans) >= 2:
                name = spans[-1].get_text(strip=True)
            else:
                name = name_el.get_text(strip=True)
        if not name:
            continue
        name_low = name.lower()
        if any(ex in name_low for ex in EXCLUDE):
            continue
        text = prod.get_text(" ", strip=True)
        price_m = re.search(r'(\d+[.,]?\d*)\s*z[łl\xb3]', text)
        price = f"{price_m.group(1)} zl" if price_m else ""
        available = "magazyn" in text.lower()
        url = href
        if not url.startswith("http"):
            url = BASE + "/merchandise/karty-przetargowe/" + url.split("/")[-1] if "../" in url else BASE + url
        img = prod.select_one("img")
        image = img.get("src", "") if img else ""
        products.append({
            "id": f"{SHOP}_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": None,
            "available": available,
        })
    return products
