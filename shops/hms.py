import aiohttp
from bs4 import BeautifulSoup
import asyncio

URL = "https://hms.pl/c/1802/pokemon-tcg-gry-karciane-gry-planszowe-rpg-karciane-i-bitewne.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

async def get_products():
    products = []
    html = None

    async with aiohttp.ClientSession() as session:
        for attempt in range(3):
            try:
                async with session.get(URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        print(f"[HMS] HTTP {resp.status} - proba {attempt+1}/3")
                        await asyncio.sleep(2)
                        continue
                    html = await resp.text()
                    break
            except Exception as e:
                print(f"[HMS] Blad proba {attempt+1}/3: {type(e).__name__}")
                if attempt < 2:
                    await asyncio.sleep(3)

    if not html:
        print("[HMS] Nie udalo sie pobrac strony po 3 probach")
        return []

    soup = BeautifulSoup(html, "lxml")
    items = soup.select(".product-item")

    for item in items:
        a = item.find("a", href=True)
        if not a:
            continue
        link = a["href"]
        if link.startswith("/"):
            link = "https://hms.pl" + link

        title = item.find("h2")
        name = title.get_text(" ", strip=True) if title else ""
        if not name:
            continue

        img = item.find("img")
        image = img.get("src", "") if img else ""

        p1 = item.select_one(".price_1")
        p2 = item.select_one(".price_2")
        price = ""
        if p1 and p2:
            price = p1.get_text(strip=True) + p2.get_text(strip=True) + " PLN"

        text = item.get_text(" ", strip=True).lower()
        available = True
        if "brak" in text or "niedost" in text or "out of stock" in text or "stock_5" in str(item):
            available = False

        products.append({
            "id": link,
            "name": name,
            "shop": "hms",
            "price": price,
            "url": link,
            "image": image,
            "available": available,
            "stock": 1 if available else 0,
        })

    print(f"[HMS] {len(products)} produktow")
    return products
