import aiohttp
from bs4 import BeautifulSoup

URL = "https://www.ataf.pl/pl/c/Pokemon/464"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

EXCLUDE = [
    "capslab", "czapka", "trucker", "snapback", "pluszak", "plush", "figurka", "battle deck",
    "league battle", "rival battle", "v battle", "world championship", "wcs deck", "wcs ",
    "battle academy", "japoński", "japońsk", "japanese", "(jp)", "koreański", "koreańsk",
    "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese", "ultra pro", "ultra-pro",
    "playmat", "portfolio", "pro-binder", "sleeves", "toploader", "album", "koszulk", "segregator",
    "deck box", "alcove", "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "puzzle", "figure set"
]


async def get_products():
    products = []
    async with aiohttp.ClientSession() as session:
        async with session.get(URL, headers=HEADERS,  timeout=aiohttp.ClientTimeout(total=15)) as resp:
            html = await resp.text()

    soup = BeautifulSoup(html, "lxml")

    for item in soup.select("div.product.product_view-extended"):
        try:
            pid = item.get("data-product-id", "")
            if not pid:
                continue

            link = item.select_one("a.prodimage")
            if not link:
                continue

            name = link.get("title", "").strip()
            if not name:
                continue

            name_lower = name.lower()
            if any(ex in name_lower for ex in EXCLUDE):
                continue

            url = link.get("href", "")
            if url.startswith("/"):
                url = f"https://www.ataf.pl{url}"

            price_el = item.select_one(".price em")
            price = price_el.get_text(strip=True) if price_el else "brak"

            form = item.select_one("form.basket, form.form-basket")
            if form:
                classes = form.get("class", [])
                available = "none" not in classes
            else:
                available = False

            img = item.select_one("img")
            image = ""
            if img:
                image = img.get("data-src") or img.get("data-original") or img.get("src") or ""
                if image.startswith("/"):
                    image = f"https://www.ataf.pl{image}"

            products.append({
                "id": f"ataf_{pid}",
                "name": name,
                "price": price,
                "shop": "ataf.pl",
                "url": url,
                "image": image,
                "stock": "Dostepny" if available else "Brak",
                "available": available,
            })
        except Exception:
            continue

    print(f"[ATAF] Znaleziono produktow: {len(products)}")
    return products
