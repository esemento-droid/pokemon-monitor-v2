import aiohttp
from bs4 import BeautifulSoup
import asyncio
import json
import re

SHOP = "foon.pl"
AJAX_URL = "https://foon.pl/Ajax/Data"
CATEGORY_ID = 1041
BASE = "https://foon.pl"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}
EXCLUDE = ["album", "sleeves", "portfolio", "binder", "ultra pro", "toploader", "japonsk", "japońsk", "japanese", "japan", "korean", "koreańsk", "chiński", "chińsk", "číns", "japonsk", "japanese", "japan", "korean", "koreańsk",
           "koszulki", "one piece", "star wars", "lorcana", "magic the", "korejsk", "cinski", "korean", "chinese", "koreanski", "koreansk",
           "mtg", "yu-gi-oh", "digimon", "obaly", "deck box", "pokemon up", "pokémon up"]

async def fetch_product(session, url, name, img_url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                               headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()
        soup = BeautifulSoup(html, "lxml")
        price = "brak"
        price_div = soup.select_one("div.cenas.price")
        if price_div:
            stara = price_div.select_one("span.stara")
            if stara:
                stara.decompose()
            price_text = price_div.get_text(strip=True)
            price_clean = re.sub(r'[\s\xa0]', '', price_text)
            price_clean = re.sub(r'(\d)\.(\d{3}[,])', r'\1\2', price_clean)
            m = re.search(r'(\d+[,\.]\d+)\s*z', price_clean)
            if m:
                price = m.group(1).replace(",", ".") + " zl"
        if price == "brak":
            m_ld = re.search(r'<script type="application/ld\+json">(\{[^<]+\})</script>', html)
            if m_ld:
                try:
                    ld = json.loads(m_ld.group(1))
                    p = ld.get("offers", {}).get("price")
                    if p:
                        price = f"{p} zl"
                except:
                    pass
        available = False
        if "btn-pridat-do-kosika" in html:
            available = True
        elif "Do koszyka</button>" in html:
            available = True
        if not available:
            if re.search(r'Dos\.pnych\s+([<>]?\s*\d+)\s*szt', html):
                available = True
        if not available:
            m_ld = re.search(r'<script type="application/ld\+json">(\{[^<]+\})</script>', html)
            if m_ld:
                try:
                    ld = json.loads(m_ld.group(1))
                    available = "InStock" in ld.get("offers", {}).get("availability", "")
                except:
                    pass
        return {
            "name": name,
            "price": price,
            "url": url,
            "image": img_url,
            "stock": None,
            "available": available,
        }
    except:
        return None

async def get_products():
    products = []
    async with aiohttp.ClientSession() as session:
        filtr = json.dumps({
            "kategoria": CATEGORY_ID, "vyrobca": 0, "kompatibilita": 0,
            "onPage": 100, "page": 1, "view": 0, "sort": 0,
            "q": "", "zlava": 0, "ks": 0, "kps": []
        })
        for attempt in range(3):
            try:
                async with session.post(AJAX_URL, headers=HEADERS,
                                        json={"filterJson": filtr},
                                        timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        print(f"[foon] HTTP {resp.status} - proba {attempt+1}/3")
                        await asyncio.sleep(2)
                        continue
                    data = await resp.json()
                    break
            except Exception as e:
                print(f"[foon] Blad AJAX proba {attempt+1}/3: {type(e).__name__}")
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    return []
        else:
            return []

        html = data.get("retval", "")
        soup = BeautifulSoup(html, "lxml")
        tasks = []
        for item in soup.select(".k-i-i"):
            a = item.find("a", href=True)
            img = item.find("img")
            if not a or not img:
                continue
            name = img.get("alt", "").strip()
            name_low = name.lower()
            if "pokemon" not in name_low and "pokémon" not in name_low:
                continue
            if any(ex in name_low for ex in EXCLUDE):
                continue
            href = a["href"]
            url = BASE + href
            img_url = img.get("src") or img.get("data-src") or ""
            if img_url and not img_url.startswith("http"):
                img_url = BASE + img_url
            tasks.append((url, name, img_url, href))

        results = await asyncio.gather(
            *[fetch_product(session, t[0], t[1], t[2]) for t in tasks]
        )
        seen = set()
        for i, result in enumerate(results):
            if result is None:
                continue
            pid = tasks[i][3]
            if pid in seen:
                continue
            seen.add(pid)
            parts = pid.strip("/").split("/")
            pid_num = parts[-2] if len(parts) >= 2 else parts[-1]
            result["id"] = f"foon_{pid_num}"
            result["shop"] = SHOP
            products.append(result)
    print(f"[foon] FINAL: {len(products)} produktow")
    return products
