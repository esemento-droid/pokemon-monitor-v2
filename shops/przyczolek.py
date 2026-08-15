import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup

BASE_URL = "https://przyczolek.pl/pokemon-tcg/{}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "singl", "psa ", "cgc ", "slab ", "sleeves", "koszulk", "toploader", "pro-binder", "portfolio",
    "ultra pro", "playmat", "album", "wcs", "battle deck", "league battle", "rival battle",
    "v battle", "world championship", "battle academy", "japoński", "japońsk", "japanese",
    "(jp)", "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)",
    "s-chinese", "ultra-pro", "segregator", "deck box", "alcove", "lorcana", "one piece",
    "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]


async def fetch_page(session, url):
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            return ""
        return await resp.text()


async def get_products():
    products = []
    seen = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html1 = await fetch_page(session, BASE_URL.format(1))
        if not html1:
            return []
        soup1 = BeautifulSoup(html1, "lxml")
        pages = {1}
        for a in soup1.select("a"):
            href = a.get("href", "")
            m = re.search(r"pokemon-tcg/(\d+)", href)
            if m:
                pages.add(int(m.group(1)))
        max_page = max(pages)
        if max_page > 1:
            tasks = [fetch_page(session, BASE_URL.format(p)) for p in range(2, max_page + 1)]
            extra = await asyncio.gather(*tasks)
        else:
            extra = []
    all_htmls = [html1] + [h for h in extra if h]
    for i, html in enumerate(all_htmls):
        soup = BeautifulSoup(html, "lxml") if i > 0 else soup1
        for item in soup.select("[data-product-id]"):
            pid = item.get("data-product-id", "")
            a = item.select_one("a.prodimage, a[title]")
            if not a:
                continue
            name = a.get("title", "").strip()
            if not pid or not name:
                continue
            if pid in seen:
                continue
            seen.add(pid)
            name_lower = name.lower()
            if any(ex in name_lower for ex in EXCLUDE):
                continue
            url_prod = a.get("href", "")
            if url_prod and not url_prod.startswith("http"):
                url_prod = f"https://przyczolek.pl{url_prod}"
            text = item.get_text(" ", strip=True).lower()
            available = "koszyk" in text or "dodaj" in text
            price_el = item.select_one(".price, .product-price")
            price = "brak"
            if price_el:
                price_text = price_el.get_text(strip=True).replace("\xa0", " ")
                pm = re.search(r"[\d,.]+", price_text)
                if pm:
                    price = pm.group(0).replace(",", ".") + " PLN"
            img = item.select_one("img")
            image = img.get("src", "") or img.get("data-src", "") if img else ""
            products.append({
                "id": f"przyczolek_{pid}",
                "name": name,
                "price": price,
                "shop": "przyczolek",
                "url": url_prod,
                "image": image,
                "stock": "",
                "available": available,
            })
    return products
