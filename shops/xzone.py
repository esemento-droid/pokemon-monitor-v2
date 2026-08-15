import aiohttp
from bs4 import BeautifulSoup
import re

URL = "https://www.xzone.pl/pokemon-tcg-21?sort=date_desc&s=60&page=1"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
EXCLUDE = [
    "album", "pro-binder", "sleeves", "koszulk", "portfolio", "toploader", "protector", "ultra pro",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra-pro", "playmat", "segregator", "deck box", "alcove", "lorcana", "one piece",
    "yu-gi-oh", "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"
]

async def get_products():
    products = []
    seen_ids = set()
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(URL, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("div.product-item")
    for item in items:
        link = item.select_one("div.product-image a")
        if not link:
            continue
        name = link.get("title", "").strip()
        if not name:
            continue
        name_lower = name.lower()
        if any(ex in name_lower for ex in EXCLUDE):
            continue
        url_prod = link.get("href", "")
        if url_prod and not url_prod.startswith("http"):
            url_prod = f"https://www.xzone.pl{url_prod}"
        slug = url_prod.rstrip("/").split("/")[-1] if url_prod else ""
        if not slug or slug in seen_ids:
            continue
        seen_ids.add(slug)
        buy_btn = item.select_one("a.btn-buy")
        available = buy_btn is not None
        price_el = item.select_one("span.price")
        if price_el:
            price_text = price_el.get_text(strip=True).replace("\xa0", " ")
            price = price_text.replace("z\u0142", "").strip() + " PLN"
        else:
            price = "brak"
        img = item.select_one("img")
        image = img.get("src", "") if img else ""
        products.append({
            "id": f"xzone-{slug}",
            "name": name,
            "price": price,
            "shop": "xzone",
            "url": url_prod,
            "image": image,
            "stock": "",
            "available": available,
        })
    return products
