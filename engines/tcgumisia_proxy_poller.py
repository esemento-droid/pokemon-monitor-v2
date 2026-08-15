"""
TCGumisia Pre-Order Poller (via Mobile Proxy)
=============================================
Polls /pre-order page every 10s through mobile proxy (different IP than VPS).
This avoids 429 rate limiting that happens when VPS IP hits tcgumisia too often.

Runs as a standalone engine - reports to same detector.py pipeline.
Only monitors /pre-order (where 30th drops appear).
VPS scraper (shops/tcgumisia.py) handles /pokemon category separately.

Key design:
- Mobile proxy (127.0.0.1:8888) = different external IP
- Solves PoW once, reuses cookies for ~30min
- Polls /pre-order every 10s (6 req/min = safe)
- Falls back to 30s on errors, recovers automatically
"""

import asyncio
import hashlib
import logging
import re
import time
import aiohttp

logger = logging.getLogger("monitor")

SHOP = "tcgumisia.pl"
BASE_URL = "https://tcgumisia.pl"
PREORDER_URL = f"{BASE_URL}/pre-order"
PROXY = "http://127.0.0.1:8888"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

POLL_INTERVAL = 10  # seconds
POW_REFRESH = 1800  # re-solve PoW every 30 min
ERROR_BACKOFF = 30  # seconds on error

EXCLUDE_KEYWORDS = [
    "lorcana", "one piece", "flesh and blood", "fab", "disney", "album", "sleeves",
    "koszulk", "pro-binder", "toploader", "ultra pro", "ochraniacz", "plastikowy",
    "jpn", "(jpn", "deck", "pencil", "riftbound", "cyberpunk", "playmat", "mata",
    "portfolio", "figurk", "league battle", "rival battle", "v battle",
    "world championship", "wcs ", "battle academy", "japoński", "japońsk",
    "japanese", "(jp)", "koreański", "korean", "chiński", "chinese", "(chi)",
    "ultra-pro", "segregator", "alcove", "yu-gi-oh", "digimon", "naruto",
    "star wars", "magic the gathering", "dragon shield", "weiss schwarz",
    "force of will", "zeszyt", "puzzle", "figure set",
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
    """Solve PoW via mobile proxy."""
    try:
        async with session.get(BASE_URL, proxy=PROXY, timeout=aiohttp.ClientTimeout(total=15)) as resp:
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
        async with session.post(f"{BASE_URL}/__nodea/verify-js", data=data, proxy=PROXY) as resp:
            j = await resp.json()
            return j.get("ok", False)
    except Exception as e:
        logger.error(f"[tcgumisia-proxy] PoW error: {e}")
        return False


def parse_products(html):
    """Parse pre-order page HTML into product list."""
    products = []
    seen = set()

    # Find product boxes
    for m in re.finditer(
        r'<a[^>]*href="(https://tcgumisia\.pl/([^"]+))"[^>]*class="[^"]*c-product-box[^"]*"[^>]*>(.*?)</a>',
        html, re.DOTALL
    ):
        url = m.group(1)
        slug = m.group(2)
        block = m.group(3)

        if slug in seen:
            continue
        seen.add(slug)

        # Name
        name_m = re.search(r'c-product-box__title[^>]*>([^<]+)<', block)
        name = name_m.group(1).strip() if name_m else ""
        if not name:
            continue

        name_low = name.lower()

        # Must be Pokemon
        if not any(kw in name_low for kw in POKEMON_KEYWORDS):
            continue

        # Exclude
        if any(kw in name_low for kw in EXCLUDE_KEYWORDS):
            continue

        # Price
        price = "brak"
        price_m = re.search(r'c-product-box__price-value[^>]*>\s*([\d\s,.]+)', block)
        if price_m:
            price_str = price_m.group(1).replace(" ", "").replace(",", ".")
            try:
                price = f"{float(price_str):.2f} PLN"
            except (ValueError, TypeError):
                pass

        # Availability - check for "sold out" / "niedostępny" indicators
        available = True
        if "niedostępn" in block.lower() or "sold" in block.lower() or "brak" in block.lower():
            available = False
        if "koszyk" in block.lower() or "dodaj" in block.lower():
            available = True

        # Image
        image = ""
        img_m = re.search(r'<img[^>]*(?:data-src|src)="([^"]+)"', block)
        if img_m:
            image = img_m.group(1)
            if not image.startswith("http"):
                image = BASE_URL + image

        products.append({
            "id": f"tcgumisia_{slug}",
            "name": name,
            "price": price,
            "shop": SHOP,
            "url": url,
            "image": image,
            "stock": None,
            "available": available,
        })

    return products


async def get_products():
    """Single poll of /pre-order via mobile proxy. Called by engine_runner."""
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(
        headers={"User-Agent": USER_AGENT},
        cookie_jar=jar
    ) as session:
        # Solve PoW
        ok = await solve_challenge(session)
        if not ok:
            return []

        # Fetch pre-order page
        try:
            async with session.get(
                PREORDER_URL, proxy=PROXY,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 429:
                    logger.warning("[tcgumisia-proxy] 429 on pre-order (proxy)")
                    return []
                if resp.status != 200:
                    return []
                html = await resp.text()
        except Exception as e:
            logger.error(f"[tcgumisia-proxy] Fetch error: {e}")
            return []

    products = parse_products(html)
    if products:
        logger.info(f"[tcgumisia-proxy] {len(products)} pre-order products")
    return products
