"""
Scraper: poke.basanti.pl
Platform: PrestaShop
Method: aiohttp + proxy (converted from PW Aug 5)
"""
import aiohttp
import re
from bs4 import BeautifulSoup

SHOP = "basanti"
PROXY = "http://127.0.0.1:8888"
SEARCH_URL = "https://poke.basanti.pl/szukaj?s=pokemon&resultsPerPage=200"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

EXCLUDE = ["battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy",
    "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean",
    "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra pro", "ultra-pro", "playmat", "portfolio", "pro-binder",
    "sleeves", "toploader", "album", "koszulk", "segregator",
    "deck box", "alcove",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto",
    "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz",
    "force of will", "riftbound",
    "zeszyt", "puzzle", "figurk", "figure set"]


async def get_products():
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            async with session.get(SEARCH_URL, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
        except Exception:
            return []

    soup = BeautifulSoup(html, "lxml")
    for art in soup.select("article.product-miniature"):
        pid = art.get("data-id-product", "")
        if not pid:
            continue
        title_el = art.select_one(".product-title a")
        name = title_el.get_text(strip=True) if title_el else ""
        if not name:
            continue
        href = title_el.get("href", "") if title_el else ""
        price_el = art.select_one("span.price")
        price = "brak"
        if price_el:
            content = price_el.get("content", "")
            if content:
                try:
                    price = f"{float(content):.2f} PLN"
                except (ValueError, TypeError):
                    pass
            if price == "brak":
                m = re.search(r"[\d]+[.,][\d]{2}", price_el.get_text().replace("\xa0", ""))
                if m:
                    price = f"{m.group(0).replace(',','.')} PLN"

        img_el = art.select_one("picture img, img")
        image = ""
        if img_el:
            image = img_el.get("data-src") or img_el.get("src") or ""

        out_of_stock = "out-of-stock" in art.get("class", [])
        qty_el = art.select_one("input[name=\"total_qty\"]")
        stock = 0
        if qty_el:
            try:
                stock = int(qty_el.get("value", 0))
            except (ValueError, TypeError):
                stock = 0
        available = not out_of_stock and stock > 0

        if not available:
            continue

        if any(ex in name.lower() for ex in EXCLUDE): continue


        products.append({
            "id": f"basanti_{pid}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": href,
            "image": image,
            "stock": stock,
            "available": True,
        })

    print(f"[BASANTI] {len(products)} produktow")
    return products
