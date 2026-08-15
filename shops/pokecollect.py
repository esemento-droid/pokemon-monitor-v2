import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re

SHOP = "pokecollect"
BASE = "https://pokecollect.pl"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
CATEGORIES = [
    ("/pl/c/Booster-Box/17", "17"),
    ("/pl/c/Elite-Trainer-Box/16", "16"),
    ("/pl/c/Zestawy-kolekcjonerskie/18", "18"),
    ("/pl/c/Saszetki-z-kartami/21", "21"),
    ("/pl/c/Gotowe-talie/19", "19"),
    ("/pl/c/Puszki-z-kartami/30", "30"),
    ("/pl/c/Ascended-Heroes/92", "92"),
    ("/pl/c/Battle-Styles/25", "25"),
    ("/pl/c/Brilliant-Stars/37", "37"),
    ("/pl/c/Celebrations-25th/28", "28"),
    ("/pl/c/Chaos-Rising/112", "112"),
    ("/pl/c/Crown-Zenith/46", "46"),
    ("/pl/c/Darkness-Ablaze/52", "52"),
    ("/pl/c/Perfect-Order/103", "103"),
    ("/pl/c/Pitch-Black/114", "114"),
    ("/pl/c/Prismatic-Evolutions/67", "67"),
    ("/pl/c/Shining-Fates/26", "26"),
    ("/pl/c/Shrouded-Fable/63", "63"),
    ("/pl/c/Silver-Tempest/44", "44"),
    ("/pl/c/Produkty-generacjami/24", "24"),
    ("/pl/c/Unikaty/35", "35"),
    ("/pl/c/Outlet/39", "39"),
    ("/pl/c/30th-Celebration/118", "118"),
    ("/pl/c/Karty-Japonskie/61", "61"),
]
EXCLUDE = [
    "ultra pro", "ultra-pro", "album", "koszulk", "toploader", "sleeves", "mata ", "playmat",
    "przypink", "lego", "figurk", "maskotk", "pluszak", "pudelk", "pude\u0142k", "one piece",
    "battle deck", "league battle", "rival battle", "v battle", "world championship",
    "wcs deck", "wcs ", "battle academy", "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "portfolio", "pro-binder", "segregator", "deck box", "alcove", "lorcana", "yu-gi-oh",
    "digimon", "naruto", "star wars", "magic the gathering", "flesh & blood",
    "flesh and blood", "dragon shield", "weiss schwarz", "force of will", "riftbound",
    "zeszyt", "puzzle", "figure set"
]


def parse_page(s):
    """Parse products from a category page - supports both extended and photo view types."""
    results = []
    # Primary: try .product_view-extended (main product container)
    items = s.select(".product_view-extended")
    # Fallback: if no extended items, try .product-inner-wrap (photo view mode)
    if not items:
        items = s.select(".product-inner-wrap")

    for tile in items:
        name_el = tile.select_one("span.productname") or tile.select_one("a.prodname")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if any(ex in name.lower() for ex in EXCLUDE):
            continue
        price = "brak"
        # Try em.color first (discounted price)
        price_el = tile.select_one("em.color")
        if price_el:
            pt = price_el.get_text(strip=True).replace("\xa0", "").replace(" ", "").replace("z\u0142", "").replace(",", ".").strip()
            try:
                price = f"{float(pt):.2f} zl"
            except (ValueError, TypeError):
                pass
        # Fallback: .price div text
        if price == "brak":
            price_div = tile.select_one(".price")
            if price_div:
                m2 = re.search(r'(\d[\d\s]*[,.]\d+)\s*z', price_div.get_text())
                if m2:
                    pt = m2.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")
                    try:
                        price = f"{float(pt):.2f} zl"
                    except (ValueError, TypeError):
                        pass
        link = tile.select_one('a[href*="/pl/p/"]')
        prod_url = BASE + link["href"] if link else ""
        pid = ""
        if link:
            parts = link["href"].strip("/").split("/")
            pid = parts[-1] if parts else ""
        if not pid:
            continue
        img = tile.select_one("img")
        image = ""
        if img:
            image = img.get("data-src") or img.get("src") or ""
            if image and not image.startswith("http"):
                image = BASE + image
            if "base64" in image:
                image = ""
        text = tile.get_text(" ", strip=True).lower()
        available = "koszyk" in text or "dodaj" in text
        results.append({"id": f"pokecollect_{pid}", "name": name, "price": price, "shop": SHOP, "url": prod_url, "image": image, "stock": None, "available": available})
    return results


async def fetch_category(session, path, cat_id):
    products = []
    url = f"{BASE}{path}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return products
            html = await resp.text()
    except:
        return products
    soup = BeautifulSoup(html, "lxml")
    pages = {1}
    for a in soup.select("a"):
        href = a.get("href", "")
        m = re.search(rf'/{cat_id}/(\d+)', href)
        if m:
            pages.add(int(m.group(1)))
    max_page = max(pages)

    products.extend(parse_page(soup))
    if max_page > 1:
        async def fetch_page(page_num):
            page_url = f"{BASE}{path}/{page_num}"
            try:
                async with session.get(page_url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status != 200:
                        return ""
                    return await r.text()
            except:
                return ""
        htmls = await asyncio.gather(*[fetch_page(p) for p in range(2, max_page + 1)])
        for h in htmls:
            if not h:
                continue
            products.extend(parse_page(BeautifulSoup(h, "lxml")))
    return products


async def get_products():
    seen = set()
    products = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        results = await asyncio.gather(*[fetch_category(session, path, cid) for path, cid in CATEGORIES])
        for cat_products in results:
            for p in cat_products:
                if p["id"] in seen:
                    continue
                seen.add(p["id"])
                products.append(p)
    print(f"[POKECOLLECT] {len(products)} produktow")
    return products
