"""
TCGumisia Proxy Poller (via Mobile Proxy)
=========================================
Polls /pokemon + /pre-order pages every 20s through mobile proxy (different IP than VPS).
This avoids 429 rate limiting that happens when VPS IP hits tcgumisia too often.

Runs as a standalone engine - reports to same detector.py pipeline.
Monitors BOTH /pokemon (where 30th ETB lives) and /pre-order.
VPS scraper (shops/tcgumisia.py) handles same categories but from VPS IP.
Double coverage = catch flash restocks even if one IP has connection issues.

Key design:
- Mobile proxy (127.0.0.1:8888) = different external IP
- Solves PoW once, reuses cookies for ~30min
- Polls both pages every 20s (12 req/min = safe)
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
POKEMON_URL = f"{BASE_URL}/pokemon"
PROXY = "http://127.0.0.1:8888"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

POLL_INTERVAL = 20  # seconds (was 10 — tcgumisia rate limits mobile IP)
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
        # NOTE: "Dodano do koszyka" appears on ALL items (it's a toast text, not a button).
        # Only trust the availability dot text.
        available = True
        if "niedostępn" in block.lower() or "sold out" in block.lower():
            available = False

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
    """Single poll of /pokemon + /pre-order via mobile proxy. Called by engine_runner."""
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(
        headers={"User-Agent": USER_AGENT},
        cookie_jar=jar
    ) as session:
        # Solve PoW
        ok = await solve_challenge(session)
        if not ok:
            return []

        all_products = []
        seen_slugs = set()

        # Fetch BOTH pages (ETB 30th is on /pokemon, NOT /pre-order!)
        for page_url in [POKEMON_URL, PREORDER_URL]:
            html = None
            for attempt in range(3):
                try:
                    async with session.get(
                        page_url, proxy=PROXY,
                        timeout=aiohttp.ClientTimeout(total=20)
                    ) as resp:
                        if resp.status == 429:
                            logger.warning(f"[tcgumisia-proxy] 429 on {page_url} (proxy)")
                            break
                        if resp.status != 200:
                            break
                        html = await resp.text()
                    break  # Success
                except (aiohttp.ServerDisconnectedError, aiohttp.ClientOSError, ConnectionResetError) as e:
                    if attempt < 2:
                        logger.warning(f"[tcgumisia-proxy] Connection error (attempt {attempt+1}/3): {e}")
                        await asyncio.sleep(3 * (attempt + 1))
                        continue
                    logger.error(f"[tcgumisia-proxy] Connection failed after 3 attempts: {e}")
                    break
                except Exception as e:
                    logger.error(f"[tcgumisia-proxy] Fetch error: {e}")
                    break

            if not html:
                continue

            products = parse_products(html)
            for p in products:
                slug = p["url"].replace("https://tcgumisia.pl/", "")
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    all_products.append(p)

        if all_products:
            logger.info(f"[tcgumisia-proxy] {len(all_products)} products (pokemon+pre-order)")
        return all_products
