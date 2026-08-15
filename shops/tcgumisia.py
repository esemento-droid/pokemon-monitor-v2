"""
Scraper: tcgumisia.pl
Silnik: wlasny + nodea PoW
Metoda: aiohttp + BeautifulSoup
Autor: fix jul 30/31 2026
"""
import asyncio
import logging
import hashlib
import re
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SHOP = "tcgumisia.pl"
BASE_URL = "https://tcgumisia.pl"
CATEGORY_URLS = ["/pokemon", "/pre-order"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
EXCLUDE_KEYWORDS = [
    "lorcana", "one piece", "flesh and blood", "fab", "disney", "album", "sleeves", "koszulk",
    "pro-binder", "toploader", "ultra pro", "ochraniacz", "plastikowy", "jpn", "(jpn", "deck",
    "pencil", "riftbound", "cyberpunk", "league battle", "rival battle", "v battle",
    "world championship", "wcs ", "battle academy", "japoński", "japońsk", "japanese", "(jp)",
    "koreański", "koreańsk", "korean", "chiński", "chińsk", "chinese", "(chi)", "s-chinese",
    "ultra-pro", "playmat", "portfolio", "segregator", "alcove", "yu-gi-oh", "digimon",
    "naruto", "star wars", "magic the gathering", "flesh & blood", "dragon shield",
    "weiss schwarz", "force of will", "zeszyt", "puzzle", "figurk", "figure set"
]
POKEMON_KEYWORDS = ["pokemon", "pokémon", "pikachu", "charizard", "booster", "etb", "trainer box"]


def solve_pow(token, diff):
    nonce = 0
    while True:
        h = hashlib.sha256(f"{token}|{nonce}".encode()).digest()
        bits = 0
        for byte in h:
            if byte == 0:
                bits += 8
            else:
                for b in range(7, -1, -1):
                    if (byte & (1 << b)) == 0:
                        bits += 1
                    else:
                        break
                break
        if bits >= diff:
            return nonce
        nonce += 1

async def solve_challenge(session):
    async with session.get(BASE_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        html = await resp.text()
    if "Weryfikacja" not in html or "nodea" not in html:
        return True
    token_m = re.search(r'token="([^"]+)"', html)
    diff_m = re.search(r"diff=(\d+)", html)
    if not token_m or not diff_m:
        return False
    token = token_m.group(1)
    diff = int(diff_m.group(1))
    nonce = await asyncio.get_event_loop().run_in_executor(None, solve_pow, token, diff)
    data = {"token": token, "nonce": str(nonce), "fp": '{"wd":0,"lang":2,"hc":4,"ch":1,"gl":"none"}'}
    async with session.post(f"{BASE_URL}/__nodea/verify-js", data=data) as resp:
        j = await resp.json()
        return j.get("ok", False)


async def get_products():
    products = []
    seen_ids = set()
    try:
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, cookie_jar=jar) as session:
            ok = await solve_challenge(session)
            if not ok:
                logger.error("[tcgumisia] PoW verification failed")
                return []
            for cat_url in CATEGORY_URLS:
                is_preorder = "pre-order" in cat_url
                url = BASE_URL + cat_url
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                soup = BeautifulSoup(html, "lxml")
                boxes = soup.select("div.c-product-box")
                for box in boxes:
                    title_el = box.select_one(".c-product-box__title")
                    if not title_el:
                        continue
                    name = title_el.text.strip()
                    if any(kw in name.lower() for kw in EXCLUDE_KEYWORDS):
                        continue
                    if is_preorder:
                        if not any(kw in name.lower() for kw in POKEMON_KEYWORDS):
                            continue
                    link = None
                    for a in box.select("a[href*=tcgumisia]"):
                        if "koszyk" not in a.get("href", ""):
                            link = a
                            break
                    href = link.get("href", "") if link else ""
                    # Normalize: remove trailing /75 (category suffix) to avoid duplicates
                    href_clean = re.sub(r'/\d+$', '', href.rstrip("/"))
                    pid = href_clean.replace("https://tcgumisia.pl/", "").replace("/", "_") if href_clean else ""
                    href = href_clean
                    if not pid or pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    price_el = box.select_one(".c-product-box__price-value")
                    price = _format_price(price_el.text.strip() if price_el else "")
                    avail_el = box.select_one(".c-avaibility")
                    avail_cls = " ".join(avail_el.get("class", [])) if avail_el else ""
                    available = "--none" not in avail_cls
                    img_el = box.select_one("img")
                    image = ""
                    if img_el:
                        image = img_el.get("data-src") or img_el.get("src", "")
                    products.append({"id": "tcgumisia_" + pid, "name": name, "price": price, "shop": SHOP, "url": href, "image": image, "stock": 1 if available else 0, "available": available})
    except Exception as e:
        logger.error(f"[tcgumisia] Error: {e}")
    print(f"[TCGUMISIA] {len(products)} produktow")
    return products


def _format_price(price_raw):
    if not price_raw:
        return "brak"
    try:
        price_str = price_raw.replace("PLN", "").replace("zq", "").replace(" ", "").replace(",", ".").strip()
        price_float = float(price_str)
        return f"{price_float:.2f} PLN"
    except (ValueError, TypeError):
        return price_raw.strip()
