import aiohttp
from bs4 import BeautifulSoup
import re
import asyncio

SHOP = "hobbity"
URLS = [
    "https://hobbity.pl/gry-karciane-kolekcjonerskie/pokemon-tcg",
    "https://hobbity.pl/przedsprzedaz",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

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


async def fetch(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=True) as resp:
            if resp.status != 200:
                return ""
            return await resp.text()
    except:
        return ""

def parse_page(html, require_pokemon=False):
    products = []
    soup = BeautifulSoup(html, "lxml")
    for item in soup.select(".js-product-miniature"):
        pid = item.get("data-id-product", "")
        if not pid:
            continue
        name_el = item.select_one("h4 a, h3 a")
        name = name_el.get("title", "") if name_el else ""
        if not name:
            continue
        if require_pokemon and "pokemon" not in name.lower() and "pokémon" not in name.lower():
            continue
        href = name_el.get("href", "") if name_el else ""
        price_el = item.select_one(".price")
        price = "brak"
        if price_el:
            m = re.search(r"(\d+[,.]\d+)", price_el.get_text())
            if m:
                price = m.group(1).replace(",", ".") + " zl"
        btn = item.select_one("button[data-button-action=add-to-cart]")
        available = btn is not None and not btn.has_attr("disabled")
        img_el = item.select_one("img")
        image = ""
        if img_el:
            image = img_el.get("data-full-size-image-url") or img_el.get("data-original") or img_el.get("src") or ""
        if any(ex in name.lower() for ex in EXCLUDE): continue

        products.append({"id": f"hobbity_{pid}", "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": None, "available": available})
    return products

async def get_products():
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        all_html = []
        for base_url in URLS:
            first = await fetch(session, base_url)
            if not first:
                continue
            all_html.append((first, "przedsprzedaz" in base_url))
            pages = set(re.findall(r"page=(\d+)", first))
            tasks = [fetch(session, f"{base_url}?page={n}") for n in pages if n != "1"]
            if tasks:
                extra = await asyncio.gather(*tasks)
                for h in extra:
                    if h:
                        all_html.append((h, "przedsprzedaz" in base_url))
    seen = set()
    products = []
    for html, is_preorder in all_html:
        for p in parse_page(html, require_pokemon=is_preorder):
            if p["id"] not in seen:
                seen.add(p["id"])
                products.append(p)
    print(f"[HOBBITY] {len(products)} produktow")
    return products
