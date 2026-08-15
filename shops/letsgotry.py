"""
Scraper: letsgotry.pl
Silnik: aiohttp + BeautifulSoup (PrestaShop)
Autor: aug 2 2026
"""
import asyncio
import logging
import re
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SHOP = "letsgotry.pl"
BASE_URL = "https://letsgotry.pl"
CATEGORY_URLS = ["/736-zestawy-eng?resultsPerPage=100"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

EXCLUDE_KEYWORDS = [
    "pluszak", "plush", "maskotka", "album", "pro-binder", "klaser", "sleeves", "toploader",
    "segregator", "mata", "playmat", "figurk", "kubek", "koszulk", "portfel", "piórnik",
    "puzzle", "poduszk", "battle deck", "league battle", "rival battle", "v battle",
    "world championship", "wcs deck", "wcs ", "battle academy", "japoński", "japońsk",
    "japanese", "(jp)", "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese",
    "(chi)", "s-chinese", "ultra pro", "ultra-pro", "portfolio", "deck box", "alcove",
    "lorcana", "one piece", "yu-gi-oh", "digimon", "naruto", "star wars",
    "magic the gathering", "flesh & blood", "flesh and blood", "dragon shield",
    "weiss schwarz", "force of will", "riftbound", "zeszyt", "figure set"
]

SINGLE_PATTERNS = [
    r"^[A-Z][a-z]+ (ex|EX|V|VMAX|VSTAR|GX) ",
    r"\b[A-Z]{2,4}[\s-]\d{3}\b",
    r"(\/\d{3}|#\d{3})",
    r"\b(PAL|OBF|MEW|SVI|PAF|TEF|TWM|SFA|SSP|SCR|PRE|SVP|CRZ)\b",
]

def _is_single(name, url):
    for pat in SINGLE_PATTERNS:
        if re.search(pat, name):
            return True
    single_url_parts = ["/promo/", "/paldea-evolved/", "/obsidian-flames/",
        "/scarlet-violet-151/", "/temporal-forces/", "/twilight-masquerade/",
        "/stellar-crown/", "/surging-sparks/", "/prismatic-evolutions/"]
    for part in single_url_parts:
        if part in url.lower():
            return True
    return False

async def get_products():
    products = []
    seen_ids = set()
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            for cat_url in CATEGORY_URLS:
                url = BASE_URL + cat_url
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()

                soup = BeautifulSoup(html, "lxml")
                for item in soup.select("article.product-miniature"):
                    pid = item.get("data-id-product", "")
                    if not pid or pid in seen_ids:
                        continue

                    name_el = item.select_one(".product-title a, h3 a")
                    if not name_el:
                        continue
                    name = name_el.get_text(strip=True)
                    href = name_el.get("href", "")

                    if not name or len(name) < 5:
                        continue
                    if any(kw in name.lower() for kw in EXCLUDE_KEYWORDS):
                        continue
                    if False:  # disabled for zestawy-eng
                        continue

                    seen_ids.add(pid)

                    price_el = item.select_one(".price")
                    price = _format_price(price_el.get_text(strip=True) if price_el else "")

                    stock_el = item.select_one("[class*=stock]")
                    stock_text = stock_el.get_text(strip=True).lower() if stock_el else ""
                    available = "wyprzedane" not in stock_text

                    img_el = item.select_one("img")
                    image = ""
                    if img_el:
                        image = img_el.get("data-src") or img_el.get("src") or ""
                        if image and not image.startswith("http"):
                            image = BASE_URL + image

                    products.append({
                        "id": f"letsgotry_{pid}",
                        "name": name,
                        "price": price,
                        "shop": SHOP,
                        "url": href,
                        "image": image,
                        "stock": 1 if available else 0,
                        "available": available,
                    })
    except Exception as e:
        logger.error(f"[letsgotry] Error: {e}")

    print(f"[LETSGOTRY] {len(products)} produktow")
    return products

def _format_price(price_raw):
    if not price_raw:
        return "brak"
    m = re.search(r"(\d[\d\s]*[,.]\d+)", price_raw)
    if m:
        p = m.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")
        return f"{float(p):.2f} PLN"
    return "brak"
